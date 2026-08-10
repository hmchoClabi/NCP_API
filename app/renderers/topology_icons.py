"""NCP 구성도 아이콘을 독립형 보고서에 안전하게 내장한다.

아이콘 경로는 이 모듈의 고정 매핑만 사용한다. 보고서 데이터에 포함된 문자열을
파일 경로로 조합하지 않으므로 경로 순회가 불가능하며, PNG 서명과 크기를 확인한
파일만 Base64 데이터 URI로 변환한다. 아이콘이 없거나 손상된 경우 호출자는 기존
도형만 렌더링할 수 있도록 ``None``을 반환한다.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_DEFAULT_ASSET_ROOT = Path(__file__).resolve().parents[2] / "ncp"

# 실제 파일이 존재하고 자원 의미가 일치하는 아이콘만 연결한다. Subnet, Target
# Group처럼 전용 아이콘이 없는 항목을 유사 아이콘으로 오인시키지 않는다.
_CATEGORY_ICON_PATHS: dict[str, tuple[str, ...]] = {
    "API_GATEWAY": ("application", "api-gateway.png"),
    "ARCHIVE_STORAGE": ("storage", "archive-storage.png"),
    "AUTO_SCALING": ("compute", "auto-scaling-server.png"),
    "BACKUP": ("storage", "backup.png"),
    "BLOCK_STORAGE": ("storage", "block-storage.png"),
    "CDN": ("content_delivery", "cdn+.png"),
    "CLOUD_CONNECT": ("networking", "cloud-connect.png"),
    "CLOUD_DB": ("database", "cloud-db.png"),
    "CLOUD_FUNCTIONS": ("compute", "cloud-function.png"),
    "CLOUD_HADOOP": ("bigdata_analysis", "cloud-hadoop.png"),
    "CONTAINER_REGISTRY": ("containers", "ncloud-container-registry.png"),
    "DATA_STREAMING": (
        "bigdata_analysis",
        "cloud-data-streaming-service.png",
    ),
    "GLOBAL_DNS": ("networking", "global-dns.png"),
    "GLOBAL_EDGE": ("content_delivery", "global-edge.png"),
    "GLOBAL_TRAFFIC_MANAGER": (
        "networking",
        "global-traffic-manager.png",
    ),
    "IPSEC_VPN": ("networking", "managed-ipsec-vpn.png"),
    "KUBERNETES": ("containers", "kubernetes.png"),
    "LOAD_BALANCER": ("networking", "load-balancer.png"),
    "NAS": ("storage", "nas.png"),
    "NAT_GATEWAY": ("networking", "nat-gateway.png"),
    "NETWORK_INTERFACE": ("other", "nic.png"),
    "OBJECT_STORAGE": ("storage", "object-storage.png"),
    "PUBLIC_IP": ("other", "public-ip.png"),
    "SEARCH_ENGINE": ("bigdata_analysis", "search-engine-service.png"),
    "SECURITY_SERVICE": ("security", "security-monitoring.png"),
    "SERVER": ("compute", "server.png"),
    "VIRTUAL_PRIVATE_GATEWAY": ("other", "vpg.png"),
    "VPC": ("networking", "vpc.png"),
    "VPC_PEERING": ("networking", "vpc-peering.png"),
}

_CLOUD_DB_ICON_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("POSTGRESQL", ("database", "cloud-db-for-postgresql.png")),
    ("MONGODB", ("database", "cloud-db-for-mongodb.png")),
    ("MSSQL", ("database", "cloud-db-for-mssql.png")),
    ("MYSQL", ("database", "mysql.png")),
    ("REDIS", ("database", "cloud-db-for-redis.png")),
    ("CACHE", ("database", "cloud-db-for-redis.png")),
)

_LOAD_BALANCER_ICON_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "NETWORK_PROXY",
        ("networking", "network-proxy-load-balancer.png"),
    ),
    (
        "NETWORKPROXY",
        ("networking", "network-proxy-load-balancer.png"),
    ),
    (
        "APPLICATION",
        ("networking", "application-load-balancer.png"),
    ),
    ("NETWORK", ("networking", "network-load-balancer.png")),
)


@dataclass(frozen=True)
class TopologyIcon:
    """SVG 정의에서 재사용할 검증된 아이콘 참조."""

    symbol_id: str
    data_uri: str


class TopologyIconLibrary:
    """허용된 NCP PNG만 읽어 구성도용 데이터 URI를 제공한다."""

    MAX_ICON_BYTES = 256 * 1024

    def __init__(self, asset_root: Path | None = None) -> None:
        self._asset_root = (asset_root or _DEFAULT_ASSET_ROOT).resolve()
        self._cache: dict[tuple[str, ...], str | None] = {}

    def data_uri_for(self, node: Mapping[str, Any]) -> str | None:
        """노드 종류에 맞는 아이콘을 반환하고 미지원 항목은 건너뛴다."""

        icon = self.icon_for(node)
        return icon.data_uri if icon is not None else None

    def icon_for(self, node: Mapping[str, Any]) -> TopologyIcon | None:
        """노드가 사용할 안전한 SVG 심벌 ID와 PNG 데이터를 반환한다."""

        icon_path = self._icon_path(node)
        if icon_path is None:
            return None
        if icon_path not in self._cache:
            self._cache[icon_path] = self._load_png_data_uri(icon_path)
        data_uri = self._cache[icon_path]
        if data_uri is None:
            return None
        digest = sha256("/".join(icon_path).encode("utf-8")).hexdigest()[:16]
        return TopologyIcon(
            symbol_id=f"ncp-topology-icon-{digest}",
            data_uri=data_uri,
        )

    @classmethod
    def _icon_path(
        cls,
        node: Mapping[str, Any],
    ) -> tuple[str, ...] | None:
        category = str(node.get("category") or "").strip().upper()
        descriptor = cls._descriptor(node)
        if category == "CLOUD_DB":
            return cls._first_matching_path(
                descriptor,
                _CLOUD_DB_ICON_PATHS,
            ) or _CATEGORY_ICON_PATHS[category]
        if category == "LOAD_BALANCER":
            return cls._first_matching_path(
                descriptor,
                _LOAD_BALANCER_ICON_PATHS,
            ) or _CATEGORY_ICON_PATHS[category]
        if category == "CDN" and "GLOBAL" in descriptor:
            return ("content_delivery", "global-cdn.png")
        return _CATEGORY_ICON_PATHS.get(category)

    @staticmethod
    def _descriptor(node: Mapping[str, Any]) -> str:
        details = node.get("details")
        detail_values: tuple[Any, ...] = ()
        if isinstance(details, Mapping):
            detail_values = tuple(
                details.get(key)
                for key in (
                    "database_engine",
                    "db_kind_code",
                    "engine_code",
                    "load_balancer_type",
                    "load_balancer_type_code",
                )
            )
        values = (
            node.get("service_name"),
            node.get("resource_type"),
            node.get("platform"),
            *detail_values,
        )
        return " ".join(str(value)[:128].upper() for value in values if value)

    @staticmethod
    def _first_matching_path(
        descriptor: str,
        choices: tuple[tuple[str, tuple[str, ...]], ...],
    ) -> tuple[str, ...] | None:
        for marker, path_parts in choices:
            if marker in descriptor:
                return path_parts
        return None

    def _load_png_data_uri(self, path_parts: tuple[str, ...]) -> str | None:
        try:
            icon_path = self._asset_root.joinpath(*path_parts).resolve()
            if (
                not icon_path.is_relative_to(self._asset_root)
                or icon_path.suffix.lower() != ".png"
            ):
                return None
            data = icon_path.read_bytes()
        except (OSError, RuntimeError):
            return None
        if (
            not data.startswith(_PNG_SIGNATURE)
            or len(data) > self.MAX_ICON_BYTES
        ):
            return None
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:image/png;base64,{encoded}"


__all__ = ["TopologyIcon", "TopologyIconLibrary"]
