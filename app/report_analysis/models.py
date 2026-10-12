"""분석 결과의 내부 모델.

외부 저장 형식은 일반 dict로 고정하고, 이 모델은 필수 필드 누락과 표현 방식
차이를 줄이는 용도로만 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .provenance import CALCULATED
from .support import stable_fingerprint


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    category: str
    title: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    impact: str = ""
    recommendation: str = ""
    resource: dict[str, Any] = field(default_factory=dict)
    occurrence_key: Any = None

    def to_dict(self) -> dict[str, Any]:
        identity = {
            "id": self.resource.get("id"),
            "name": self.resource.get("name"),
            "type": self.resource.get("type"),
        }
        return {
            "fingerprint": stable_fingerprint(
                self.rule_id,
                self.category,
                identity,
                self.occurrence_key,
            ),
            "rule_id": self.rule_id,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "resource": {key: value for key, value in identity.items() if value not in (None, "")},
            "evidence": list(self.evidence),
            "impact": self.impact,
            "recommendation": self.recommendation,
            "status": "OPEN",
            # 규칙 finding은 원본 이벤트가 아니라 명시된 규칙의 계산 결과다.
            "source_state": CALCULATED,
        }


SEVERITY_ORDER = {
    "CRITICAL": 0,
    "WARNING": 1,
    "INFO": 2,
}


def sort_findings(findings: list[Finding]) -> list[dict[str, Any]]:
    result = [finding.to_dict() for finding in findings]
    return sorted(
        result,
        key=lambda item: (
            SEVERITY_ORDER.get(str(item.get("severity")), 99),
            str(item.get("category") or ""),
            str(item.get("fingerprint") or ""),
        ),
    )
