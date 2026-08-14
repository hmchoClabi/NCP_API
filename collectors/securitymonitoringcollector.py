"""VPC Security Monitoring 기간 이벤트 수집기."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import requests

from normalizers.securitymonitoringnormalizer import (
    SecurityMonitoringNormalizer,
)
from utils.common_rest import safe_exception_message
from utils.provider_permissions import extract_required_actions
from utils.response_validation import validate_collection_response


class SecurityMonitoringCollector:
    """보안 상품별 실패를 격리하고 VPC 이벤트만 수집한다."""

    PAGE_SIZE = 100
    MAX_PAGES = 1_000
    _SERVICES = (
        ("ANTIVIRUS", "get_anti_virus_list", "antiVirusDataList"),
        ("DDOS", "get_ddos_list", "ddosDataList"),
        ("IDS", "get_ids_list", "idsDataList"),
        ("IPS", "get_ips_list", "ipsDataList"),
        ("WAF", "get_waf_list", "wafDataList"),
    )

    def __init__(self, api_factory: Any):
        self.api_factory = api_factory
        self.normalizer = SecurityMonitoringNormalizer()
        self.last_errors: list[dict[str, Any]] = []
        self.last_dataset_status = "NOT_COLLECTED"
        self.last_service_statuses: dict[str, str] = {}

    def collect(
        self,
        start_time: int,
        end_time: int,
    ) -> list[dict[str, Any]]:
        """Anti-Virus, DDoS, IDS, IPS, WAF를 서로 독립적으로 조회한다."""

        self.last_errors = []
        self.last_dataset_status = "NOT_COLLECTED"
        self.last_service_statuses = {}
        if (
            isinstance(start_time, bool)
            or isinstance(end_time, bool)
            or not isinstance(start_time, int)
            or not isinstance(end_time, int)
            or start_time > end_time
        ):
            raise ValueError("보안 이벤트 조회 기간은 밀리초 정수 범위여야 합니다.")

        try:
            api = self.api_factory.get("security_monitoring")
        except Exception as exc:
            self._record_error(
                stage="api_factory",
                api="security_monitoring",
                service="SECURITY_MONITORING",
                exc=exc,
            )
            self.last_dataset_status = "FAILED"
            return []

        events: list[dict[str, Any]] = []
        for service, method_name, list_key in self._SERVICES:
            service_events, status = self._collect_service(
                api=api,
                service=service,
                method_name=method_name,
                list_key=list_key,
                start_time=start_time,
                end_time=end_time,
            )
            self.last_service_statuses[service] = status
            events.extend(service_events)

        statuses = set(self.last_service_statuses.values())
        if statuses == {"FAILED"}:
            self.last_dataset_status = "FAILED"
        elif "FAILED" in statuses or "PARTIAL" in statuses:
            self.last_dataset_status = "PARTIAL"
        elif events:
            self.last_dataset_status = "COLLECTED"
        else:
            self.last_dataset_status = "COLLECTED_EMPTY"
        events.sort(
            key=lambda item: item.get("detected_at") or 0,
            reverse=True,
        )
        return events

    def _collect_service(
        self,
        *,
        api: Any,
        service: str,
        method_name: str,
        list_key: str,
        start_time: int,
        end_time: int,
    ) -> tuple[list[dict[str, Any]], str]:
        method = getattr(api, method_name, None)
        if not callable(method):
            self._record_error(
                stage="api_contract",
                api=method_name,
                service=service,
                message="현재 API 구현에 필요한 VPC 조회 메서드가 없습니다.",
            )
            return [], "FAILED"

        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        previous_fingerprint: tuple[str, ...] | None = None
        service_had_error = False

        for page in range(1, self.MAX_PAGES + 1):
            response: Any = None
            try:
                response = method(
                    startDateTime=start_time,
                    endDateTime=end_time,
                    page=page,
                    countPerPage=self.PAGE_SIZE,
                    order="desc",
                )
                validate_collection_response(
                    response,
                    expected_keys=(list_key,),
                    api_name=method_name,
                )
                items = self._extract_items(response, list_key)
                invalid_count = self._invalid_item_count(response, list_key)
                if invalid_count:
                    service_had_error = True
                    self._record_error(
                        stage="response_validation",
                        api=method_name,
                        service=service,
                        page=page,
                        message=(
                            f"형식이 올바르지 않은 보안 이벤트 "
                            f"{invalid_count}건을 제외했습니다."
                        ),
                    )
            except Exception as exc:
                self._record_error(
                    stage="pagination",
                    api=method_name,
                    service=service,
                    exc=exc,
                    response=response,
                    page=page,
                )
                return normalized, "PARTIAL" if normalized else "FAILED"

            identities = tuple(self._identity(item) for item in items)
            if items and identities == previous_fingerprint:
                self._record_error(
                    stage="pagination_guard",
                    api=method_name,
                    service=service,
                    page=page,
                    message="동일한 보안 이벤트 페이지가 반복되어 수집을 중단했습니다.",
                )
                return normalized, "PARTIAL"
            previous_fingerprint = identities
            added_count = 0
            for item in items:
                identity = self._identity(item)
                if identity in seen:
                    continue
                seen.add(identity)
                try:
                    normalized.append(self.normalizer.normalize(item, service))
                    added_count += 1
                except Exception as exc:
                    service_had_error = True
                    self._record_error(
                        stage="normalization",
                        api=method_name,
                        service=service,
                        exc=exc,
                        page=page,
                    )

            if items and added_count == 0:
                self._record_error(
                    stage="pagination_guard",
                    api=method_name,
                    service=service,
                    page=page,
                    message="보안 이벤트 페이지에서 새로운 항목이 없어 수집을 중단했습니다.",
                )
                return normalized, "PARTIAL"

            total_rows = self._total_rows(response)
            if not items:
                if total_rows is not None and len(seen) < total_rows:
                    self._record_error(
                        stage="pagination_guard",
                        api=method_name,
                        service=service,
                        page=page,
                        message=(
                            "공급자 totalRows보다 적은 고유 이벤트를 받은 "
                            "상태에서 빈 페이지가 반환되었습니다."
                        ),
                    )
                    return normalized, "PARTIAL"
                if service_had_error:
                    return normalized, "PARTIAL" if normalized else "FAILED"
                return normalized, "COLLECTED" if normalized else "COLLECTED_EMPTY"
            if total_rows is not None and len(seen) >= total_rows:
                if service_had_error:
                    return normalized, "PARTIAL" if normalized else "FAILED"
                return normalized, "COLLECTED"
            if total_rows is None and len(items) < self.PAGE_SIZE:
                if service_had_error:
                    return normalized, "PARTIAL" if normalized else "FAILED"
                return normalized, "COLLECTED"

        self._record_error(
            stage="pagination_guard",
            api=method_name,
            service=service,
            page=self.MAX_PAGES,
            message=f"최대 페이지 수({self.MAX_PAGES})에 도달해 수집을 중단했습니다.",
        )
        return normalized, "PARTIAL"

    @staticmethod
    def _extract_items(
        response: Any,
        list_key: str,
    ) -> list[dict[str, Any]]:
        if not isinstance(response, Mapping):
            return []
        value = response.get(list_key)
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    @staticmethod
    def _invalid_item_count(response: Any, list_key: str) -> int:
        if not isinstance(response, Mapping):
            return 0
        value = response.get(list_key)
        if not isinstance(value, list):
            return 0
        return sum(not isinstance(item, Mapping) for item in value)

    @staticmethod
    def _total_rows(response: Any) -> int | None:
        if not isinstance(response, Mapping):
            return None
        value = response.get("totalRows")
        try:
            return max(int(value), 0) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _identity(item: Mapping[str, Any]) -> str:
        ticket_id = item.get("ticketId")
        if ticket_id is not None and str(ticket_id).strip():
            return f"ticket:{ticket_id}"
        return "row:" + json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    def _record_error(
        self,
        *,
        stage: str,
        api: str,
        service: str,
        exc: Exception | None = None,
        response: Any = None,
        page: int | None = None,
        message: str | None = None,
    ) -> None:
        issue: dict[str, Any] = {
            "collector": self.__class__.__name__,
            "stage": stage,
            "target_type": service,
            "target": service,
            "platform": "VPC",
            "api": api,
            "message": message or (
                safe_exception_message(exc)[:500]
                if exc is not None
                else "알 수 없는 Security Monitoring 수집 오류"
            ),
        }
        if page is not None:
            issue["page_no"] = page
        if exc is not None:
            issue["exception_type"] = type(exc).__name__
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                issue["status_code"] = exc.response.status_code
                response = exc.response
        provider_code = self._provider_code(response)
        if provider_code:
            issue["error_code"] = provider_code
        required_actions = extract_required_actions(response)
        if required_actions:
            issue["required_actions"] = list(required_actions)
        self.last_errors.append(issue)

    @classmethod
    def _provider_code(cls, response: Any) -> str | None:
        payload = cls._response_payload(response)
        return cls._find_provider_code(payload)

    @staticmethod
    def _response_payload(response: Any) -> Any:
        if isinstance(response, Mapping):
            return response
        if isinstance(response, requests.Response):
            try:
                return response.json()
            except ValueError:
                return None
        return None

    @classmethod
    def _find_provider_code(cls, value: Any, depth: int = 0) -> str | None:
        if depth > 4 or not isinstance(value, Mapping):
            return None
        for key in ("errorCode", "code", "returnCode"):
            candidate = value.get(key)
            if candidate not in (None, "", 0, "0", 200, "200"):
                return str(candidate)[:100]
        for child in value.values():
            if isinstance(child, Mapping):
                candidate = cls._find_provider_code(child, depth + 1)
                if candidate:
                    return candidate
        return None


__all__ = ["SecurityMonitoringCollector"]
