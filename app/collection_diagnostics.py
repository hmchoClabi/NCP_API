"""수집 진단 항목의 심각도와 NCP 상품 대상을 일관되게 표시한다.

Collector마다 API 호출에 필요한 기계용 ``target_type``은 서로 다르다.
이 모듈은 원본 필드를 보존하면서 보고서에 사용할 상품명과 대상 표시만
보강한다. 따라서 기존 스냅샷과 collector 계약을 변경하지 않는다.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.ncp_permission_hints import permission_diagnostic_fields
from app.report_options import RESOURCE_CATEGORY_LABELS


_TARGET_TYPE_LABELS = {
    "server": "Server",
    "network_interface": "Server (Network Interface)",
    "block_storage": "Block Storage",
    "block_storage_snapshot": "Block Storage Snapshot",
    "server_image": "Server Image",
    "vpc": "VPC",
    "subnet": "VPC (Subnet)",
    "route_table": "VPC (Route Table)",
    "route_table_subnet": "VPC (Route Table/Subnet)",
    "route_table_route": "VPC (Route)",
    "access_control_group": "Server (ACG)",
    "access_control_group_rule": "Server (ACG 규칙)",
    "network_acl": "VPC (Network ACL)",
    "network_acl_rule": "VPC (Network ACL 규칙)",
    "network_configuration": "VPC 네트워크 구성",
    "nat_gateway": "NAT Gateway",
    "public_ip": "Public IP",
    "vpc_peering": "VPC Peering",
    "load_balancer": "Load Balancer",
    "target_group": "Load Balancer (Target Group)",
    "nas": "NAS",
    "nas_vpc": "NAS",
    "cdb_mysql": "Cloud DB for MySQL",
    "cdb_postgresql": "Cloud DB for PostgreSQL",
    "cdb_postgres": "Cloud DB for PostgreSQL",
    "cdb_mssql": "Cloud DB for MSSQL",
    "cdb_mongodb": "Cloud DB for MongoDB",
    "cdb_cache": "Cloud DB for Cache",
    "cdb_redis": "Cloud DB for Redis",
    "cdb_serverless": "Cloud DB Serverless",
    "nks": "Ncloud Kubernetes Service",
    "kubernetes": "Ncloud Kubernetes Service",
    "global_dns": "Global DNS",
    "dns": "Global DNS",
    "web_service_monitor": "Web service Monitoring System",
    "security_monitoring": "Security Monitoring",
    "antivirus": "Security Monitoring (Anti-Virus)",
    "ddos": "Security Monitoring (Anti-DDoS)",
    "ids": "Security Monitoring (IDS)",
    "ips": "Security Monitoring (IPS)",
    "waf": "Security Monitoring (WAF)",
    "certificate": "Certificate Manager",
    "certificate_manager": "Certificate Manager",
    "object_storage": "Object Storage",
    "auto_scaling": "Auto Scaling",
    "resource_manager": "Resource Manager",
    "billing": "Billing",
    "infrastructure": "인프라 인벤토리",
    "infrastructure_metric": "Cloud Insight 인프라 모니터링",
    "event": "Cloud 이벤트",
    "cdn": "CDN",
    "global_cdn": "Global CDN",
    "cdn_plus": "CDN+",
}

_API_TARGET_PATTERNS = (
    ("cloud_postgresql", "Cloud DB for PostgreSQL"),
    ("cloud_mysql", "Cloud DB for MySQL"),
    ("cloud_mssql", "Cloud DB for MSSQL"),
    ("cloud_mongodb", "Cloud DB for MongoDB"),
    ("cloud_cache", "Cloud DB for Cache"),
    ("load_balancer", "Load Balancer"),
    ("target_group", "Load Balancer (Target Group)"),
    ("block_storage_snapshot", "Block Storage Snapshot"),
    ("block_storage", "Block Storage"),
    ("server_instance", "Server"),
    ("network_interface", "Server (Network Interface)"),
    ("global_cdn", "Global CDN"),
    ("cdn_plus", "CDN+"),
    ("nas_volume", "NAS"),
    ("nks_cluster", "Ncloud Kubernetes Service"),
    ("kubernetes", "Ncloud Kubernetes Service"),
    ("domain", "Global DNS"),
    ("certificate", "Certificate Manager"),
)


def normalize_collection_issue(
    issue: Mapping[str, Any],
    *,
    default_severity: str = "error",
) -> dict[str, Any]:
    """원본 진단 payload에 표시용 심각도와 상품 대상을 추가한다."""

    normalized = dict(issue)
    severity = _normalize_severity(
        normalized.get("severity"),
        default=default_severity,
    )
    service_name = diagnostic_service_name(normalized)
    resource_target = _first_text(
        normalized,
        "target_name",
        "target_id",
        "resource_name",
        "resource_id",
    )

    normalized["severity"] = severity
    normalized["severity_label"] = "경고" if severity == "warning" else "오류"
    normalized["service_name"] = service_name
    normalized["called_api"] = (
        _first_text(normalized, "api", "source")
        or "API 미확인 (구형 진단 데이터)"
    )
    normalized["target"] = (
        f"{service_name} · {resource_target}"
        if resource_target and resource_target != service_name
        else service_name
    )
    normalized.update(permission_diagnostic_fields(normalized))
    return normalized


def diagnostic_service_name(issue: Mapping[str, Any]) -> str:
    """진단 필드 중 가장 구체적인 값을 NCP 상품 표시명으로 변환한다."""

    product_name = _text(issue.get("product_name"))
    if product_name:
        return _product_label(product_name)

    category = _normalized_key(issue.get("category"))
    target_type = _normalized_key(issue.get("target_type"))

    if target_type == "infrastructure_metric":
        metric_product = _metric_service_label(issue)
        if metric_product:
            return metric_product

    # Cloud DB는 category보다 엔진별 target_type이 더 구체적이다.
    if target_type.startswith("cdb_"):
        return _TARGET_TYPE_LABELS.get(target_type, "Cloud DB")

    if category:
        category_label = RESOURCE_CATEGORY_LABELS.get(category.upper())
        if category_label:
            return category_label
        output_category_labels = {
            "cdb": "Cloud DB",
            "target_group": "Load Balancer (Target Group)",
            "nks": "Ncloud Kubernetes Service",
        }
        if category in output_category_labels:
            return output_category_labels[category]

    if target_type in _TARGET_TYPE_LABELS:
        label = _TARGET_TYPE_LABELS[target_type]
        if target_type == "event":
            return _event_service_label(issue)
        if target_type == "infrastructure_metric":
            return _metric_service_label(issue) or label
        return label

    api = _normalized_key(issue.get("api") or issue.get("source"))
    for token, label in _API_TARGET_PATTERNS:
        if token in api:
            return label

    collector = _normalized_key(issue.get("collector"))
    if "activitytracer" in collector:
        return "Cloud Activity Tracer"
    if "insightevent" in collector or "insightmetric" in collector:
        return "Cloud Insight"
    if "billing" in collector:
        return "Billing"

    return _text(issue.get("target")) or "대상 미확인"


def _product_label(product_name: str) -> str:
    token = _normalized_key(product_name)
    compact_token = token.replace("_", "")
    if "clouddb" in compact_token or compact_token.startswith("cdb"):
        for engine, label in (
            ("serverless", "Cloud DB Serverless"),
            ("postgresql", "Cloud DB for PostgreSQL"),
            ("postgres", "Cloud DB for PostgreSQL"),
            ("mysql", "Cloud DB for MySQL"),
            ("mssql", "Cloud DB for MSSQL"),
            ("mongodb", "Cloud DB for MongoDB"),
            ("redis", "Cloud DB for Redis"),
            ("cache", "Cloud DB for Cache"),
        ):
            if engine in compact_token:
                return label
        return "Cloud DB"
    if "targetgroup" in compact_token:
        return "Load Balancer (Target Group)"
    if "loadbalancer" in compact_token:
        return "Load Balancer"
    if "kubernetes" in compact_token or compact_token.startswith("nks"):
        return "Ncloud Kubernetes Service"
    if "objectstorage" in compact_token:
        return "Object Storage"
    if compact_token in {"nas", "nasvpc"}:
        return "NAS"
    if "globaldns" in compact_token:
        return "Global DNS"

    # Cloud Insight의 System/ 접두사는 상품명이 아니므로 표시에서 제거한다.
    label = re.sub(r"^system/", "", product_name, flags=re.IGNORECASE)
    return label.strip() or product_name


def _metric_service_label(issue: Mapping[str, Any]) -> str:
    attempted = issue.get("attempted_products")
    if isinstance(attempted, (list, tuple)):
        products = [_product_label(value) for value in attempted if _text(value)]
        if products:
            return ", ".join(dict.fromkeys(products))
    return ""


def _event_service_label(issue: Mapping[str, Any]) -> str:
    collector = _normalized_key(issue.get("collector"))
    if "activitytracer" in collector:
        return "Cloud Activity Tracer"
    if "insight" in collector:
        return "Cloud Insight"
    return "Cloud 이벤트"


def _normalize_severity(value: Any, *, default: str) -> str:
    severity = _normalized_key(value)
    if severity in {"warning", "warn", "경고"}:
        return "warning"
    if severity in {"error", "critical", "fatal", "오류"}:
        return "error"
    return "warning" if _normalized_key(default) == "warning" else "error"


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", "_", _text(value).casefold()).strip("_")


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _first_text(issue: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(issue.get(key))
        if value:
            return value
    return ""


__all__ = ["diagnostic_service_name", "normalize_collection_issue"]
