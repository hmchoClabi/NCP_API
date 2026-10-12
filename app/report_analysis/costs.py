"""서로 같은 금액 기준의 비용 사실만 비교한다."""

from __future__ import annotations

import calendar
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any, Optional

from .models import Finding
from .provenance import CALCULATED, OBSERVED, UNAVAILABLE
from .support import (
    date_value,
    field,
    mapping,
    normalize_period_type,
    number,
    rounded,
)


FACT_NAMES = (
    "invoice_summary",
    "period_estimate",
    "month_to_date_estimate",
    "month_end_projection",
)

FACT_LABELS = {
    "invoice_summary": "확정 청구 금액",
    "period_estimate": "보고 기간 추정 금액",
    "month_to_date_estimate": "월 누적 추정 금액",
    "month_end_projection": "월말 추정 금액",
}

INCOMPATIBILITY_LABELS = {
    "currency": "통화",
    "amount_basis": "금액 기준",
    "confidence": "신뢰도",
    "includes_discount": "할인 포함 여부",
    "includes_vat": "VAT 포함 여부",
    "comparison_period": "비교 기간",
    "coverage": "실제 수집 범위",
}


def analyze_costs(
    report: Any,
    baseline: Any = None,
    policy: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[Finding]]:
    facts = _cost_facts(report)
    baseline_facts = _cost_facts(baseline) if baseline is not None else []
    comparison = _compare_facts(report, facts, baseline_facts)
    findings: list[Finding] = []

    if comparison.get("status") == "AVAILABLE":
        rate = number(comparison.get("rate_change"))
        warning_threshold = _cost_warning_threshold(policy)
        if rate is not None and rate >= warning_threshold:
            findings.append(
                Finding(
                    rule_id="COST_INCREASE_BASELINE",
                    severity="WARNING",
                    category="COST",
                    title="동일 기준의 비교 기간보다 비용이 증가했습니다.",
                    evidence=[
                        {
                            "label": "현재 금액",
                            "value": comparison["current_amount"],
                            "unit": comparison["currency"],
                        },
                        {
                            "label": "기준 금액",
                            "value": comparison["baseline_amount"],
                            "unit": comparison["currency"],
                        },
                        {"label": "증가율", "value": rate, "unit": "%"},
                        {"label": "경고 기준", "value": warning_threshold, "unit": "%"},
                        {"label": "금액 기준", "value": comparison["amount_basis"]},
                    ],
                    impact="비용 증가 원인이 지속되면 예산 초과 가능성이 있습니다.",
                    recommendation="서비스별 비용과 같은 기간의 자원·트래픽 변경을 확인하세요.",
                    resource={
                        "id": comparison["fact_name"],
                        "name": FACT_LABELS[comparison["fact_name"]],
                        "type": "COST",
                    },
                )
            )

    return {
        "status": "AVAILABLE" if facts else "UNAVAILABLE",
        "source_state": CALCULATED if facts else UNAVAILABLE,
        "facts": facts,
        "comparison": comparison,
    }, findings


def _cost_warning_threshold(policy: Mapping[str, Any] | None) -> float:
    if not isinstance(policy, Mapping):
        return 20.0
    thresholds = policy.get("thresholds")
    raw = (
        thresholds.get("cost_increase_warning_percent")
        if isinstance(thresholds, Mapping)
        else policy.get("cost_increase_warning_percent")
    )
    parsed = number(raw)
    return parsed if parsed is not None and parsed >= 0 else 20.0


def _cost_facts(report: Any) -> list[dict[str, Any]]:
    if report is None:
        return []
    billing = mapping(field(report, "billing", {}))
    result = []
    for name in FACT_NAMES:
        value = billing.get(name)
        if not isinstance(value, Mapping):
            continue
        amount = number(value.get("total_amount"))
        status = str(value.get("status") or "").upper()
        if status != "AVAILABLE" or amount is None:
            continue
        result.append(
            {
                "name": name,
                "label": FACT_LABELS[name],
                "cost_type": value.get("cost_type"),
                "status": status,
                "period_start": value.get("period_start"),
                "period_end": value.get("period_end"),
                "coverage_start": value.get("coverage_start"),
                "coverage_end": value.get("coverage_end"),
                "total_amount": rounded(amount),
                "currency": str(value.get("currency") or "KRW"),
                "amount_basis": value.get("amount_basis"),
                "confidence": value.get("confidence"),
                "includes_discount": value.get("includes_discount"),
                "includes_vat": value.get("includes_vat"),
                "source_api": value.get("source_api"),
                "source_state": (
                    OBSERVED
                    if name == "invoice_summary"
                    or str(value.get("cost_type") or "").upper() == "CONFIRMED"
                    else CALCULATED
                ),
            }
        )
    return result


def _compare_facts(
    report: Any,
    current_facts: list[dict[str, Any]],
    baseline_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    preferred = _preferred_fact_names(report)
    period = mapping(field(report, "period", {}))
    period_type = normalize_period_type(period.get("period_type"))
    current_fact: Optional[dict[str, Any]] = None
    first_incompatible: Optional[tuple[dict[str, Any], dict[str, Any], list[str]]] = None
    for name in preferred:
        current = _fact_by_name(current_facts, name)
        if current_fact is None and current is not None:
            current_fact = current
        previous = _fact_by_name(baseline_facts, name)
        if not current or not previous:
            continue
        incompatibility = _incompatibility(
            current,
            previous,
            period_type=period_type,
        )
        if incompatibility:
            if first_incompatible is None:
                first_incompatible = (current, previous, incompatibility)
            continue
        current_amount = number(current.get("total_amount"))
        baseline_amount = number(previous.get("total_amount"))
        if current_amount is None or baseline_amount is None:
            continue
        amount_change = current_amount - baseline_amount
        rate_change: Optional[float] = None
        if baseline_amount != 0:
            rate_change = amount_change / abs(baseline_amount) * 100
        return {
            "status": "AVAILABLE",
            "source_state": CALCULATED,
            "reason": (
                "조회 기간·실제 수집 범위와 금액 기준·신뢰도·할인·VAT "
                "범위가 같은 비용 사실을 비교했습니다."
            ),
            **_comparison_context(current, previous),
            "amount_change": rounded(amount_change),
            "rate_change": rounded(rate_change),
        }
    if first_incompatible is not None:
        current, previous, incompatible_fields = first_incompatible
        incompatible_fields = sorted(incompatible_fields)
        labels = ", ".join(INCOMPATIBILITY_LABELS.get(name, name) for name in incompatible_fields)
        return {
            "status": "INCOMPATIBLE",
            "source_state": CALCULATED,
            "reason": (f"다음 비교 조건이 일치하지 않아 증감은 계산하지 않았습니다: {labels}."),
            **_comparison_context(current, previous),
            "incompatible_fields": incompatible_fields,
        }
    if current_fact is not None:
        return {
            "status": "UNAVAILABLE",
            "source_state": UNAVAILABLE,
            "reason": (
                "현재 보고 기간 비용은 수집됐지만 직전 비교 기간의 같은 "
                "비용 항목은 사용할 수 없습니다."
            ),
            **_comparison_context(current_fact),
        }
    return {
        "status": "UNAVAILABLE",
        "source_state": UNAVAILABLE,
        "reason": "현재 보고서와 이전 보고서에 공통 비용 항목이 없습니다.",
    }


def _comparison_context(
    current: Mapping[str, Any],
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    previous = previous or {}
    return {
        "fact_name": current.get("name"),
        "current_amount": current.get("total_amount"),
        "baseline_amount": previous.get("total_amount"),
        "amount_change": None,
        "rate_change": None,
        "currency": current.get("currency"),
        "amount_basis": current.get("amount_basis"),
        "confidence": current.get("confidence"),
        "includes_discount": current.get("includes_discount"),
        "includes_vat": current.get("includes_vat"),
        "current_period_start": current.get("period_start"),
        "current_period_end": current.get("period_end"),
        "current_coverage_start": current.get("coverage_start"),
        "current_coverage_end": current.get("coverage_end"),
        "baseline_period_start": previous.get("period_start"),
        "baseline_period_end": previous.get("period_end"),
        "baseline_coverage_start": previous.get("coverage_start"),
        "baseline_coverage_end": previous.get("coverage_end"),
    }


def _preferred_fact_names(report: Any) -> tuple[str, ...]:
    period = mapping(field(report, "period", {}))
    period_type = normalize_period_type(period.get("period_type"))
    if period_type == "MONTHLY":
        return (
            "invoice_summary",
            "period_estimate",
            "month_to_date_estimate",
            "month_end_projection",
        )
    if period_type in {"DAILY", "WEEKLY", "RANGE"}:
        return ("period_estimate",)
    return (
        "period_estimate",
        "month_to_date_estimate",
        "month_end_projection",
        "invoice_summary",
    )


def _fact_by_name(facts: list[dict[str, Any]], name: str) -> Optional[dict[str, Any]]:
    return next((fact for fact in facts if fact.get("name") == name), None)


def _incompatibility(
    current: Mapping[str, Any],
    previous: Mapping[str, Any],
    *,
    period_type: str = "UNKNOWN",
) -> list[str]:
    fields = (
        "currency",
        "amount_basis",
        "confidence",
        "includes_discount",
        "includes_vat",
    )
    differences = [name for name in fields if current.get(name) != previous.get(name)]
    current_period = _date_range(current.get("period_start"), current.get("period_end"))
    previous_period = _date_range(previous.get("period_start"), previous.get("period_end"))
    # 두 보고서가 같은 확정 청구월을 그대로 재사용하면 0% 증감처럼
    # 보일 수 있다. 양쪽 기간이 명시되고 서로 다른 경우에만 비교한다.
    if (
        current_period is None
        or previous_period is None
        or current_period == previous_period
        or not _periods_are_comparable(
            current_period,
            previous_period,
            period_type=period_type,
        )
    ):
        differences.append("comparison_period")
    elif not _coverage_is_comparable(
        current,
        previous,
        current_period=current_period,
        previous_period=previous_period,
    ):
        differences.append("coverage")
    return differences


def _date_range(start: Any, end: Any) -> Optional[tuple[date, date]]:
    parsed_start = date_value(start)
    parsed_end = date_value(end)
    if parsed_start is None or parsed_end is None or parsed_start > parsed_end:
        return None
    return parsed_start, parsed_end


def _periods_are_comparable(
    current: tuple[date, date],
    previous: tuple[date, date],
    *,
    period_type: str,
) -> bool:
    current_start, current_end = current
    previous_start, previous_end = previous
    current_days = (current_end - current_start).days
    previous_days = (previous_end - previous_start).days

    if period_type == "DAILY":
        return (
            current_days == previous_days == 0 and previous_end + timedelta(days=1) == current_start
        )
    if period_type == "MONTHLY":
        if (
            current_start.day != 1
            or previous_start.day != 1
            or current_start.year * 12 + current_start.month
            != previous_start.year * 12 + previous_start.month + 1
            or current_start.month != current_end.month
            or current_start.year != current_end.year
            or previous_start.month != previous_end.month
            or previous_start.year != previous_end.year
        ):
            return False
        current_full = (
            current_end.day == calendar.monthrange(current_end.year, current_end.month)[1]
        )
        previous_full = (
            previous_end.day == calendar.monthrange(previous_end.year, previous_end.month)[1]
        )
        return (current_full and previous_full) or (
            not current_full and not previous_full and current_days == previous_days
        )
    return current_days == previous_days and previous_end + timedelta(days=1) == current_start


def _coverage_is_comparable(
    current: Mapping[str, Any],
    previous: Mapping[str, Any],
    *,
    current_period: tuple[date, date],
    previous_period: tuple[date, date],
) -> bool:
    current_coverage = _date_range(current.get("coverage_start"), current.get("coverage_end"))
    previous_coverage = _date_range(previous.get("coverage_start"), previous.get("coverage_end"))
    if current_coverage is None or previous_coverage is None:
        return False

    def coverage_shape(
        period: tuple[date, date], coverage: tuple[date, date]
    ) -> Optional[tuple[bool, int, int]]:
        period_start, period_end = period
        coverage_start, coverage_end = coverage
        if not (period_start <= coverage_start <= coverage_end <= period_end):
            return None
        return (
            coverage == period,
            (coverage_start - period_start).days,
            (coverage_end - period_start).days,
        )

    current_shape = coverage_shape(current_period, current_coverage)
    previous_shape = coverage_shape(previous_period, previous_coverage)
    if current_shape is None or previous_shape is None:
        return False
    if current_shape[0] or previous_shape[0]:
        return current_shape[0] and previous_shape[0]
    return current_shape[1:] == previous_shape[1:]


__all__ = ["analyze_costs"]
