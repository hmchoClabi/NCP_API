"""Web service Monitoring System 응답을 안전한 보고서 계약으로 변환한다."""

from __future__ import annotations

from typing import Any, Mapping


class WMSNormalizer:
    """시나리오 설정과 기간 집계 결과에서 허용된 필드만 보존한다."""

    _RESULT_FIELDS = {
        "result_id": "_id",
        "scenario_id": "scenarioId",
        "location_code": "locationTypeCode",
        "status": "resultStatus",
        "avg_load_time_ms": "avgLoadTime",
        "avg_run_time_ms": "avgRunTime",
        "collected_at": "collectTime",
        "success_count": "successCount",
        "error_count": "errorCount",
        "total_count": "totalCount",
    }

    def normalize(
        self,
        scenario: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        """연락처, 알림 설정, 웹훅, 대상 URL과 원문 응답을 제외한다."""

        normalized_results = []
        raw_results = result.get("results")
        if isinstance(raw_results, list):
            normalized_results = [
                self._normalize_result(item) for item in raw_results if isinstance(item, Mapping)
            ]

        return {
            "scenario_id": self._text(scenario.get("scenarioId"), 100),
            "name": self._text(scenario.get("name"), 200),
            "monitoring_type": self._text(
                scenario.get("monitoringType"),
                50,
            ),
            "service_type": self._text(scenario.get("serviceType"), 50),
            "enabled": self._boolean(scenario.get("serviceYn")),
            "method_type": self._text(scenario.get("methodType"), 20),
            "interval_minutes": self._number(scenario.get("interval")),
            "request_timeout_ms": self._number(scenario.get("requestTimeout")),
            "run_timeout_ms": self._number(scenario.get("runTimeout")),
            "availability_percent": self._number(result.get("availability")),
            "avg_load_time_ms": self._number(result.get("avgLoadTime")),
            "avg_run_time_ms": self._number(result.get("avgRunTime")),
            "success_count": self._integer(result.get("successCount")),
            "error_count": self._integer(result.get("errorCount")),
            "total_count": self._integer(result.get("totalCount")),
            "results": normalized_results,
        }

    def _normalize_result(self, item: Mapping[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for output_name, source_name in self._RESULT_FIELDS.items():
            value = item.get(source_name)
            if output_name in {
                "avg_load_time_ms",
                "avg_run_time_ms",
            }:
                normalized[output_name] = self._number(value)
            elif output_name in {
                "collected_at",
                "success_count",
                "error_count",
                "total_count",
            }:
                normalized[output_name] = self._integer(value)
            else:
                normalized[output_name] = self._text(value, 100)
        return normalized

    @staticmethod
    def _text(value: Any, limit: int) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text[:limit] if text else None

    @staticmethod
    def _boolean(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y"}:
                return True
            if normalized in {"false", "0", "no", "n"}:
                return False
        return None

    @staticmethod
    def _number(value: Any) -> int | float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return int(number) if number.is_integer() else number

    @classmethod
    def _integer(cls, value: Any) -> int | None:
        number = cls._number(value)
        return int(number) if number is not None else None


__all__ = ["WMSNormalizer"]
