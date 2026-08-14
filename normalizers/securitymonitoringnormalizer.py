"""Security Monitoring 목록 응답을 공통 보안 이벤트 계약으로 변환한다."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo


class SecurityMonitoringNormalizer:
    """VPC 보안 이벤트에서 추적에 필요한 허용 필드만 보존한다."""

    KST = ZoneInfo("Asia/Seoul")
    SUPPORTED_SERVICES = frozenset({"ANTIVIRUS", "DDOS", "IDS", "IPS", "WAF"})

    def normalize(
        self,
        event: Mapping[str, Any],
        service: str,
    ) -> dict[str, Any]:
        normalized_service = str(service).strip().upper()
        if normalized_service not in self.SUPPORTED_SERVICES:
            raise ValueError(f"지원하지 않는 보안 서비스입니다: {service}")

        detected_at = self._timestamp_millis(event.get("date"))
        return {
            "event_id": self._text(event.get("ticketId"), 100),
            "service": normalized_service,
            "product": self._text(event.get("product"), 50),
            "detected_at": detected_at,
            "detected_at_kst": self._format_kst(detected_at),
            "event_name": self._text(event.get("eventNm"), 300),
            "attack_type": self._text(event.get("attackType"), 300),
            "report_type": self._text(event.get("reportType"), 100),
            "action_status": self._text(event.get("actionStatus"), 100),
            "attacker_ip": self._text(
                event.get("attackerIp") or event.get("attackIp"),
                100,
            ),
            "attacker_port": self._text(event.get("attackerPort"), 20),
            "target_ip": self._text(event.get("targetIp"), 100),
            "target_port": self._text(event.get("targetPort"), 20),
            "protocol": self._text(event.get("protocol"), 30),
            "detection_count": self._integer(event.get("detect")),
            "region": self._text(event.get("region"), 100),
            "zone": self._text(event.get("zoneName"), 50),
            # 이 수집기는 VPC URI만 호출한다. 공급자 응답이 비어도 범위를 명시한다.
            "platform": "VPC",
            "vpc_name": self._text(event.get("vpcName"), 200),
        }

    @staticmethod
    def _text(value: Any, limit: int) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text[:limit] if text else None

    @staticmethod
    def _integer(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _timestamp_millis(cls, value: Any) -> int | None:
        timestamp = cls._integer(value)
        if timestamp is None or timestamp <= 0:
            return None
        # 공급자 문서는 밀리초를 사용하지만 방어적으로 초 단위도 수용한다.
        if timestamp < 10_000_000_000:
            timestamp *= 1_000
        return timestamp

    @classmethod
    def _format_kst(cls, timestamp: int | None) -> str | None:
        if timestamp is None:
            return None
        value = datetime.fromtimestamp(timestamp / 1_000, tz=cls.KST)
        return value.isoformat(timespec="seconds")


__all__ = ["SecurityMonitoringNormalizer"]
