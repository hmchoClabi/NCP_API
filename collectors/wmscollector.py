"""Web service Monitoring System 기간 가용성 수집기."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests

from normalizers.wmsnormalizer import WMSNormalizer
from utils.common_rest import safe_exception_message
from utils.provider_permissions import (
    extract_provider_code,
    extract_required_actions,
)
from utils.response_validation import validate_collection_response


class WMSCollector:
    """WMS 시나리오별 가용성과 응답시간을 독립적으로 수집한다."""

    AGGREGATION_TYPES = frozenset({"RAW", "MIN5", "MIN30", "HOUR2", "DAY1"})

    def __init__(self, api_factory: Any):
        self.api_factory = api_factory
        self.normalizer = WMSNormalizer()
        self.last_errors: list[dict[str, Any]] = []
        self.last_dataset_status = "NOT_COLLECTED"

    def collect(
        self,
        start_time: int,
        end_time: int,
        aggregation: str = "MIN5",
    ) -> list[dict[str, Any]]:
        """보고 기간(밀리초)을 WMS 조회 규격(초)으로 변환해 수집한다."""

        self.last_errors = []
        self.last_dataset_status = "NOT_COLLECTED"
        aggregation = str(aggregation).strip().upper()
        if aggregation not in self.AGGREGATION_TYPES:
            raise ValueError(f"지원하지 않는 WMS 집계 유형입니다: {aggregation}")
        if (
            isinstance(start_time, bool)
            or isinstance(end_time, bool)
            or not isinstance(start_time, int)
            or not isinstance(end_time, int)
            or start_time > end_time
        ):
            raise ValueError("WMS 조회 기간은 올바른 밀리초 정수 범위여야 합니다.")

        try:
            api = self.api_factory.get("web_service_monitor")
            response = api.get_wms_monitor_list()
            validate_collection_response(
                response,
                expected_keys=("scenarios",),
                allow_list=True,
                api_name="get_wms_monitor_list",
            )
            scenarios = self._extract_scenarios(response)
            invalid_scenarios = self._invalid_scenario_count(response)
            if invalid_scenarios:
                self._record_error(
                    stage="scenario_validation",
                    api="get_wms_monitor_list",
                    message=(
                        f"형식이 올바르지 않은 시나리오 {invalid_scenarios}건을 제외했습니다."
                    ),
                )
        except Exception as exc:
            self._record_error(
                stage="scenario_list",
                api="get_wms_monitor_list",
                exc=exc,
                response=response if "response" in locals() else None,
            )
            self.last_dataset_status = "FAILED"
            return []

        if not scenarios:
            self.last_dataset_status = "FAILED" if self.last_errors else "COLLECTED_EMPTY"
            return []

        from_seconds = start_time // 1_000
        to_seconds = end_time // 1_000
        normalized: list[dict[str, Any]] = []

        for scenario in scenarios:
            scenario_id = scenario.get("scenarioId")
            if scenario_id is None or not str(scenario_id).strip():
                self._record_error(
                    stage="scenario_validation",
                    api="get_wms_monitor_result",
                    message="시나리오 ID가 없어 기간 결과 조회를 생략했습니다.",
                )
                continue

            result_response: Any = None
            try:
                result_response = api.get_wms_monitor_result(
                    str(scenario_id),
                    from_seconds,
                    to_seconds,
                    aggregation,
                )
                validate_collection_response(
                    result_response,
                    expected_keys=(
                        "results",
                        "availability",
                        "totalCount",
                    ),
                    api_name="get_wms_monitor_result",
                )
                if not isinstance(result_response, Mapping):
                    raise ValueError("WMS 기간 결과가 object 형식이 아닙니다.")
                raw_results = result_response.get("results")
                if isinstance(raw_results, list):
                    invalid_results = sum(not isinstance(item, Mapping) for item in raw_results)
                    if invalid_results:
                        self._record_error(
                            stage="result_validation",
                            api="get_wms_monitor_result",
                            target=str(scenario_id),
                            message=(
                                f"형식이 올바르지 않은 WMS 결과 {invalid_results}건을 제외했습니다."
                            ),
                        )
                normalized.append(self.normalizer.normalize(scenario, result_response))
            except Exception as exc:
                self._record_error(
                    stage="scenario_result",
                    api="get_wms_monitor_result",
                    exc=exc,
                    response=result_response,
                    target=str(scenario_id),
                )

        observation_count = sum(self._observation_count(item) for item in normalized)
        if not normalized and self.last_errors:
            self.last_dataset_status = "FAILED"
        elif self.last_errors:
            self.last_dataset_status = "PARTIAL"
        elif observation_count:
            self.last_dataset_status = "COLLECTED"
        else:
            self.last_dataset_status = "COLLECTED_EMPTY"
        return normalized

    @staticmethod
    def _observation_count(item: Mapping[str, Any]) -> int:
        """시나리오 설정 수가 아니라 기간 내 실제 관측 건수를 센다."""

        total = item.get("total_count")
        try:
            return max(int(total), 0) if total is not None else len(item.get("results") or [])
        except (TypeError, ValueError):
            return len(item.get("results") or [])

    @staticmethod
    def _extract_scenarios(response: Any) -> list[dict[str, Any]]:
        if isinstance(response, list):
            return [dict(item) for item in response if isinstance(item, Mapping)]
        if not isinstance(response, Mapping):
            return []
        value = response.get("scenarios")
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    @staticmethod
    def _invalid_scenario_count(response: Any) -> int:
        value = (
            response
            if isinstance(response, list)
            else (response.get("scenarios") if isinstance(response, Mapping) else [])
        )
        if not isinstance(value, list):
            return 0
        return sum(not isinstance(item, Mapping) for item in value)

    def _record_error(
        self,
        *,
        stage: str,
        api: str,
        exc: Exception | None = None,
        response: Any = None,
        target: str | None = None,
        message: str | None = None,
    ) -> None:
        issue: dict[str, Any] = {
            "collector": self.__class__.__name__,
            "stage": stage,
            "target_type": "web_service_monitor",
            "api": api,
            "message": message
            or (
                safe_exception_message(exc)[:500] if exc is not None else "알 수 없는 WMS 수집 오류"
            ),
        }
        if target:
            issue["target"] = target[:100]
        if exc is not None:
            issue["exception_type"] = type(exc).__name__
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                issue["status_code"] = exc.response.status_code
                response = exc.response
        provider_code = extract_provider_code(response)
        if provider_code:
            issue["error_code"] = provider_code
        required_actions = extract_required_actions(response)
        if required_actions:
            issue["required_actions"] = list(required_actions)
        self.last_errors.append(issue)


__all__ = ["WMSCollector"]
