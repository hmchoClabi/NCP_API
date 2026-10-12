"""네트워크 구성 스냅샷의 범위와 보고서 표시 데이터를 관리한다."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

from app.report_options import NETWORK_CONFIGURATION_CATEGORY_OPTIONS

NETWORK_CONFIGURATION_CATEGORIES = frozenset(NETWORK_CONFIGURATION_CATEGORY_OPTIONS)


def configuration_records(
    resources: Any,
    categories: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """요청한 네트워크 구성 자원만 독립된 복사본으로 반환한다."""
    allowed = (
        NETWORK_CONFIGURATION_CATEGORIES
        if categories is None
        else NETWORK_CONFIGURATION_CATEGORIES & {str(category).upper() for category in categories}
    )
    if not isinstance(resources, Sequence) or isinstance(
        resources,
        (str, bytes, bytearray),
    ):
        return []

    result: list[dict[str, Any]] = []
    for resource in resources:
        if not isinstance(resource, Mapping):
            continue
        category = str(resource.get("category") or "").upper()
        if category not in allowed:
            continue
        normalized = deepcopy(dict(resource))
        details = normalized.get("details")
        if isinstance(details, dict):
            # 생성시점 구성 백업에 과거 존재 여부 추정값을 섞지 않는다.
            details.pop("historical_presence_confidence", None)
            details.pop("historical_presence_basis", None)
        result.append(normalized)
    return result


def replace_configuration_records(
    resources: Any,
    configuration: Any,
) -> list[dict[str, Any]]:
    """일반 인프라 목록에서 네트워크 구성 항목만 안전하게 교체한다."""
    if not isinstance(resources, Sequence) or isinstance(
        resources,
        (str, bytes, bytearray),
    ):
        resources = []
    base = [
        deepcopy(dict(resource))
        for resource in resources
        if (
            isinstance(resource, Mapping)
            and str(resource.get("category") or "").upper() not in NETWORK_CONFIGURATION_CATEGORIES
        )
    ]
    return [*base, *configuration_records(configuration)]


def snapshot_categories(snapshot: Any) -> frozenset[str]:
    """스냅샷이 정상적으로 시도한 구성 범주를 반환한다."""
    if not isinstance(snapshot, Mapping):
        return frozenset()
    selected = snapshot.get("selected_categories")
    if selected is None:
        metadata = snapshot.get("metadata")
        if isinstance(metadata, Mapping):
            selected = metadata.get("selected_categories")
    if isinstance(selected, Sequence) and not isinstance(
        selected,
        (str, bytes, bytearray),
    ):
        return frozenset(
            str(category).upper()
            for category in selected
            if str(category).upper() in NETWORK_CONFIGURATION_CATEGORIES
        )
    return frozenset(
        str(resource.get("category") or "").upper()
        for resource in configuration_records(snapshot.get("configuration"))
    )


def build_generation_snapshot(
    *,
    configuration: Any,
    selected_categories: Iterable[str],
    captured_at: str,
    collection_source: str,
    errors: Any = None,
    warnings: Any = None,
) -> dict[str, Any]:
    """보고서 생성 과정에서 관측한 현재 네트워크 구성을 봉투화한다."""
    selected = sorted(
        NETWORK_CONFIGURATION_CATEGORIES
        & {str(category).upper() for category in selected_categories}
    )
    error_count = len(errors) if isinstance(errors, list) else 0
    warning_count = len(warnings) if isinstance(warnings, list) else 0
    completeness = "PARTIAL" if error_count or warning_count else "COMPLETE_FOR_SELECTED_SCOPE"
    return {
        "schema_version": "1.0",
        "source": "REPORT_GENERATION",
        "collection_source": str(collection_source),
        "captured_at": str(captured_at),
        "selected_categories": selected,
        "configuration": configuration_records(configuration, selected),
        "collection_completeness": completeness,
        "collection_issue_count": error_count + warning_count,
        "metadata": {
            "collection_source": str(collection_source),
            "completeness": completeness,
            "collection_issue_count": error_count + warning_count,
        },
        "reused": False,
    }
