"""인벤토리에 명시된 값만 사용해 거버넌스 판정을 만든다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import Finding
from .provenance import CALCULATED, UNAVAILABLE
from .support import field, records


DEFAULT_POLICIES = {
    "require_block_storage_encryption": True,
    "require_kubernetes_termination_protection": False,
    "flag_public_ip": False,
    "require_owner_tag": False,
    "require_backup": False,
}


def analyze_governance(
    report: Any,
    policy: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[Finding]]:
    policies = _policies(policy)
    resources = records(field(report, "infrastructure", []))
    findings: list[Finding] = []
    checked_counts = {name: 0 for name in policies}
    eligible_counts = {name: 0 for name in policies}

    for resource in resources:
        category = str(resource.get("category") or "").upper()
        details = resource.get("details")
        if not isinstance(details, Mapping):
            details = {}
        identity = {
            "id": resource.get("resource_id"),
            "name": resource.get("resource_name") or resource.get("resource_id") or "대상 미확인",
            "type": category,
        }

        if policies["require_block_storage_encryption"] and category == "BLOCK_STORAGE":
            eligible_counts["require_block_storage_encryption"] += 1
            if "encrypted" in details:
                checked_counts["require_block_storage_encryption"] += 1
                if details.get("encrypted") is False:
                    findings.append(Finding(
                        rule_id="BLOCK_STORAGE_ENCRYPTION_DISABLED",
                        severity="WARNING",
                        category="GOVERNANCE",
                        title=f"{identity['name']} 블록 스토리지가 암호화되지 않았습니다.",
                        evidence=[{"label": "암호화", "value": False}],
                        impact="저장 데이터 보호 수준이 고객 보안 기준에 미달할 수 있습니다.",
                        recommendation="업무 영향과 NCP 지원 방식을 확인한 뒤 암호화 볼륨으로 이전하세요.",
                        resource=identity,
                    ))

        if policies["require_kubernetes_termination_protection"] and category == "KUBERNETES":
            eligible_counts["require_kubernetes_termination_protection"] += 1
            if "termination_protection" in details:
                checked_counts["require_kubernetes_termination_protection"] += 1
                if details.get("termination_protection") is False:
                    findings.append(Finding(
                        rule_id="KUBERNETES_TERMINATION_PROTECTION_DISABLED",
                        severity="WARNING",
                        category="GOVERNANCE",
                        title=f"{identity['name']} 클러스터의 반납 보호가 꺼져 있습니다.",
                        evidence=[{"label": "반납 보호", "value": False}],
                        impact="잘못된 삭제 작업으로 클러스터가 제거될 위험이 커집니다.",
                        recommendation="운영 클러스터라면 반납 보호를 활성화하고 삭제 승인 절차를 확인하세요.",
                        resource=identity,
                    ))

        if policies["flag_public_ip"] and category in {
            "SERVER", "LOAD_BALANCER", "PUBLIC_IP"
        }:
            eligible_counts["flag_public_ip"] += 1
            public_ip_known = (
                "public_ip" in details or "public_ip" in resource
                or category == "PUBLIC_IP"
            )
            public_ip = (
                details.get("public_ip")
                if "public_ip" in details
                else resource.get("public_ip")
            )
            explicit_public_ip = category == "PUBLIC_IP" or public_ip not in (None, "")
            if public_ip_known:
                checked_counts["flag_public_ip"] += 1
            if explicit_public_ip:
                findings.append(Finding(
                    rule_id="PUBLIC_IP_POLICY_REVIEW",
                    severity="WARNING",
                    category="GOVERNANCE",
                    title=f"{identity['name']}에 공인 IP 노출 근거가 있습니다.",
                    evidence=[{"label": "공인 IP", "value": public_ip or "Public IP 자원"}],
                    impact="공인 IP 자체가 취약점이라는 뜻은 아니며 고객 노출 정책 준수 여부를 확인해야 합니다.",
                    recommendation="업무상 필요한 노출인지 확인하고 ACG·방화벽·접근 제어를 검토하세요.",
                    resource=identity,
                ))

        if policies["require_owner_tag"]:
            eligible_counts["require_owner_tag"] += 1
            owner_checked, owner_missing = _explicit_owner_state(resource, details)
            if owner_checked:
                checked_counts["require_owner_tag"] += 1
            if owner_missing:
                findings.append(Finding(
                    rule_id="RESOURCE_OWNER_MISSING",
                    severity="WARNING",
                    category="GOVERNANCE",
                    title=f"{identity['name']} 자원에 소유자 정보가 없습니다.",
                    evidence=[{"label": "소유자 태그", "value": "없음"}],
                    impact="장애 또는 비용 이상 시 담당자 식별이 늦어질 수 있습니다.",
                    recommendation="고객 태그 표준에 맞춰 owner 정보를 지정하세요.",
                    resource=identity,
                ))

        backup_key = next(
            (
                name for name in (
                    "backup_configured",
                    "backup_enabled",
                    "snapshot_configured",
                )
                if name in details
            ),
            None,
        )
        if policies["require_backup"] and (
            category in {
                "SERVER", "BLOCK_STORAGE", "NAS", "CLOUD_DB", "CDB",
                "CDB_MYSQL", "CDB_POSTGRESQL",
            }
            or backup_key is not None
        ):
            eligible_counts["require_backup"] += 1
            if backup_key:
                checked_counts["require_backup"] += 1
                if details.get(backup_key) is False:
                    findings.append(Finding(
                        rule_id="RESOURCE_BACKUP_DISABLED",
                        severity="WARNING",
                        category="GOVERNANCE",
                        title=f"{identity['name']} 자원의 백업 설정이 꺼져 있습니다.",
                        evidence=[{"label": "백업 설정", "value": False}],
                        impact="장애나 오삭제 시 복구 가능한 시점이 없을 수 있습니다.",
                        recommendation="업무 복구 목표에 맞는 백업 또는 스냅샷 정책을 지정하세요.",
                        resource=identity,
                    ))

    policy_coverage = [
        {
            "policy": name,
            "enabled": enabled,
            "eligible_count": eligible_counts[name],
            "checked_count": checked_counts[name],
            "indeterminate_count": max(
                eligible_counts[name] - checked_counts[name], 0
            ),
        }
        for name, enabled in policies.items()
    ]
    indeterminate_count = sum(
        item["indeterminate_count"]
        for item in policy_coverage
        if item["enabled"]
    )
    if indeterminate_count:
        findings.append(Finding(
            rule_id="GOVERNANCE_EVIDENCE_INCOMPLETE",
            severity="WARNING",
            category="DATA_QUALITY",
            title="활성 거버넌스 정책의 판정 필드가 일부 누락되었습니다.",
            evidence=[
                {
                    "label": item["policy"],
                    "value": item["indeterminate_count"],
                    "unit": "건",
                }
                for item in policy_coverage
                if item["enabled"] and item["indeterminate_count"]
            ],
            impact="정책 위반이 없다고 확정할 수 없어 운영 상태를 정상으로 판정하지 않습니다.",
            recommendation="해당 NCP API 권한과 응답 필드를 확인한 뒤 다시 수집하세요.",
            resource={
                "id": "governance_policy_evidence",
                "name": "거버넌스 정책 판정 근거",
                "type": "DATASET",
            },
        ))

    return {
        "status": (
            "PARTIAL" if indeterminate_count
            else "AVAILABLE" if resources
            else "UNAVAILABLE"
        ),
        "source_state": CALCULATED if resources else UNAVAILABLE,
        "resource_count": len(resources),
        "policies": policies,
        "checked_counts": checked_counts,
        "eligible_counts": eligible_counts,
        "policy_coverage": policy_coverage,
        "indeterminate_count": indeterminate_count,
        "finding_count": len(findings),
        "evidence_note": "명시적으로 수집된 true/false 또는 태그 필드만 판정했습니다.",
    }, findings


def _policies(policy: Mapping[str, Any] | None) -> dict[str, bool]:
    result = dict(DEFAULT_POLICIES)
    if not isinstance(policy, Mapping):
        return result
    raw = policy.get("policies")
    if not isinstance(raw, Mapping):
        return result
    for name in result:
        if isinstance(raw.get(name), bool):
            result[name] = raw[name]
    return result


def _explicit_owner_state(
    resource: Mapping[str, Any], details: Mapping[str, Any]
) -> tuple[bool, bool]:
    for container in (resource, details):
        for name in ("owner", "owner_tag"):
            if name in container:
                return True, container.get(name) in (None, "", False)
        if "tags" in container:
            tags = container.get("tags")
            if isinstance(tags, Mapping):
                owner = tags.get("owner", tags.get("Owner"))
                return True, owner in (None, "", False)
            if isinstance(tags, (list, tuple)):
                owner_values = [
                    item.get("value")
                    for item in tags
                    if isinstance(item, Mapping)
                    and str(item.get("key") or item.get("name") or "").casefold() == "owner"
                ]
                return True, not any(value not in (None, "", False) for value in owner_values)
            return True, True
    return False, False


__all__ = ["analyze_governance"]
