from __future__ import annotations

import math
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Sequence

from app.infrastructure_topology import (
    InfrastructureTopologyBuilder,
    TopologyDisplayOptions,
)
from app.renderers.topology_edge_router import OrthogonalEdgeRouter
from app.renderers.topology_icons import TopologyIconLibrary
from app.report_options import ReportOptions

if TYPE_CHECKING:
    from app.report_models import ReportResult


class TopologyRenderer:
    """구성도 옵션 해석, 배치 계산, SVG와 근거 표 렌더링을 전담한다."""

    TOPOLOGY_LAYER_ORDER = {
        "PUBLIC_IP": 0,
        "GLOBAL_EDGE": 0,
        "GLOBAL_DNS": 0,
        "GLOBAL_TRAFFIC_MANAGER": 0,
        "API_GATEWAY": 0,
        "VPC": 0,
        "VPC_PEERING": 1,
        "VIRTUAL_PRIVATE_GATEWAY": 1,
        "IPSEC_VPN": 1,
        "CLOUD_CONNECT": 1,
        "SUBNET": 1,
        "NAT_GATEWAY": 2,
        "AUTO_SCALING": 2,
        "LOAD_BALANCER": 2,
        "KUBERNETES": 2,
        "SERVER": 2,
        "CLOUD_DB": 2,
        "SEARCH_ENGINE": 2,
        "DATA_STREAMING": 2,
        "CLOUD_HADOOP": 2,
        "NETWORK_INTERFACE": 3,
        "TARGET_GROUP": 3,
        "BLOCK_STORAGE": 3,
        "NAS": 3,
        "OBJECT_STORAGE": 3,
        "BLOCK_STORAGE_SNAPSHOT": 4,
        "BACKUP": 4,
        "ARCHIVE_STORAGE": 4,
    }
    # 아이콘 중심 카드가 클라우드 경계보다 시각적으로 우세해지지 않도록
    # 보고서용 고정 크기를 작게 유지한다.
    TOPOLOGY_NODE_WIDTH = 184
    TOPOLOGY_NODE_HEIGHT = 126
    def __init__(self, html_renderer: Any) -> None:
        self._html_renderer = html_renderer
        self._icon_library = TopologyIconLibrary()
        self._edge_router = OrthogonalEdgeRouter()

    @property
    def _topology_options_override(self) -> Dict[str, Any] | None:
        return getattr(self._html_renderer, "_topology_options_override", None)

    @property
    def _topology_max_nodes_override(self) -> int | None:
        return getattr(self._html_renderer, "_topology_max_nodes_override", None)

    def _records(self, value: Any) -> List[Dict[str, Any]]:
        return self._html_renderer._records(value)

    def _mapping(self, value: Any) -> Dict[str, Any]:
        return self._html_renderer._mapping(value)

    def _text(self, value: Any) -> str:
        return self._html_renderer._text(value)

    def _number(self, value: Any, decimals: int) -> str:
        return self._html_renderer._number(value, decimals)

    def _table(self, rows: List[Dict[str, Any]], columns: Any) -> str:
        return self._html_renderer._table(rows, columns)

    def _section(self, *args: Any, **kwargs: Any) -> str:
        return self._html_renderer._section(*args, **kwargs)

    def _topology_options(
        self,
        report: ReportResult,
    ) -> tuple[TopologyDisplayOptions, int]:
        raw_options = getattr(report, "report_options", None)
        if not raw_options:
            customer = report.customer if isinstance(report.customer, dict) else {}
            raw_options = customer.get("report_options")
        diagram = ReportOptions.from_value(raw_options).to_dict()["diagram"]
        if self._topology_options_override is not None:
            diagram.update(self._topology_options_override)
        max_nodes = diagram.get(
            "max_nodes",
            InfrastructureTopologyBuilder.DEFAULT_MAX_NODES,
        )
        if self._topology_max_nodes_override is not None:
            max_nodes = self._topology_max_nodes_override
        return TopologyDisplayOptions.from_mapping(diagram), max_nodes

    def _infrastructure_topology_section(
        self,
        topology: Dict[str, Any],
        options: TopologyDisplayOptions,
    ) -> str:
        nodes = self._records(topology.get("nodes"))
        edges = self._records(topology.get("edges"))
        summary = self._mapping(topology.get("summary"))
        unmapped_ids = {
            str(node_id)
            for node_id in topology.get("unmapped_node_ids", [])
            if node_id is not None
        }
        mapped_nodes = [
            node for node in nodes
            if str(node.get("node_id")) not in unmapped_ids
        ]
        unmapped_nodes = [
            node for node in nodes
            if str(node.get("node_id")) in unmapped_ids
        ]
        confidence = str(summary.get("confidence") or "UNMAPPED")
        time_basis = str(summary.get("time_basis") or "REPORT_PERIOD")
        svg = self._topology_svg(mapped_nodes, edges, options)
        if not svg:
            if confidence == "UNAVAILABLE":
                svg = (
                    '<p class="empty-state">보고 기간 안에 실제 수집된 '
                    "인프라 스냅샷이 없어 현재 구성을 대신 그리지 않았습니다.</p>"
                )
            else:
                svg = (
                    '<p class="empty-state">명시적인 리소스 ID 관계가 없어 '
                    "연결선을 그리지 않았습니다.</p>"
                )

        accuracy_class = " verified" if confidence == "VERIFIED" else " warning"
        relationship_confidence = str(
            summary.get("relationship_confidence") or "UNAVAILABLE"
        )
        relationship_coverage = str(
            summary.get("relationship_coverage") or "UNKNOWN"
        )
        inventory_completeness = str(
            summary.get("inventory_completeness") or "UNKNOWN"
        )
        edge_count = int(summary.get("verified_edge_count") or 0)
        total_edge_count = int(
            summary.get("total_verified_edge_count") or edge_count
        )
        edge_text = (
            f"{edge_count:,}/{total_edge_count:,}개"
            if edge_count != total_edge_count else f"{edge_count:,}개"
        )
        truncated_text = (
            f" · 잘림 {int(summary.get('omitted_node_count') or 0):,}개"
            if summary.get("truncated") else " · 잘림 없음"
        )
        accuracy = f"""
      <div class="topology-accuracy{accuracy_class}">
        <strong>정확성 {self._text(confidence)}</strong>
        <span>검증된 관계 {self._text(edge_text)}</span>
        <span>미매핑 자원 {self._number(summary.get('unmapped_resource_count'), 0)}개</span>
        <span>미해결 참조 {self._number(summary.get('unresolved_reference_count'), 0)}개</span>
        <span>수집 시각 {self._text(summary.get('collected_at'))}</span>
        <span>시간 기준 {self._text(summary.get('time_basis') or 'COLLECTION_TIME')}</span>
        <span>스냅샷 출처 {self._text(summary.get('snapshot_source') or 'NORMALIZED_REPORT')}</span>
        <span>표시 제한 {self._number(summary.get('max_nodes'), 0)}개{self._text(truncated_text)}</span>
        <span>관계 근거 {self._text(relationship_confidence)}</span>
        <span>관계 연결 범위 {self._text(relationship_coverage)}</span>
        <span>인벤토리 완전성 {self._text(inventory_completeness)}</span>
        <span>수집 이슈 {self._number(summary.get('collection_issue_count'), 0)}건</span>
      </div>"""

        warnings = self._records(topology.get("warnings"))
        warning_html = ""
        if warnings:
            warning_html = (
                '<ul class="topology-warnings">'
                + "".join(
                    "<li>"
                    + self._text(warning.get("message"))
                    + " <small>source="
                    + self._text(warning.get("source"))
                    + " · confidence="
                    + self._text(warning.get("confidence"))
                    + "</small></li>"
                    for warning in warnings
                )
                + "</ul>"
            )

        unmapped_html = ""
        if options.include_unmapped_resources and unmapped_nodes:
            unmapped_html = (
                "<h3 class=\"topology-subheading\">미매핑 그룹</h3>"
                '<p class="topology-note">이름·IP·CIDR로 연결을 추측하지 '
                "않았으며 명시 관계가 없는 자원만 모았습니다.</p>"
                '<div class="topology-unmapped-grid">'
                + "".join(
                    self._topology_unmapped_card(node, options)
                    for node in unmapped_nodes
                )
                + "</div>"
            )

        evidence = self._topology_evidence_table(edges, nodes, options)
        content = (
            accuracy
            + warning_html
            + '<div class="topology-canvas">'
            + svg
            + "</div>"
            + unmapped_html
            + "<h3 class=\"topology-subheading\">관계 근거</h3>"
            + evidence
        )
        topology_description = (
            "보고서 생성 시점의 현재 자원 중 보고 종료 전에 생성된 것으로 "
            "확인되는 자원을 사용했습니다. 상태·IP·연결 관계는 현재 값이며 "
            "보고 기간 당시의 정확한 구성은 아닙니다. 관계는 API 또는 "
            "Resource Manager 응답의 명시적 리소스 ID만 연결합니다."
            if time_basis == "CURRENT_STATE_FILTERED_BY_CREATE_TIME"
            else (
                "보고 기간 안에서 가장 늦게 실제 수집된 스냅샷을 기준으로, "
                "API 또는 Resource Manager 응답이 리소스 ID로 명시한 관계만 "
                "연결합니다. 이름·도메인·IP·CIDR 일치에 의한 추정 연결은 "
                "생성하지 않습니다."
            )
        )
        if options.group_by_vpc:
            topology_description += (
                " 명시적으로 확인된 VPC·Subnet 포함 관계는 연결선 대신 "
                "중첩된 경계 상자로 표현합니다."
            )
        return self._section(
            "클라우드 구성도",
            topology_description,
            content,
            int(summary.get("representative_node_count") or 0),
            warning=bool(
                confidence != "VERIFIED"
                or summary.get("unmapped_resource_count")
                or summary.get("unresolved_reference_count")
                or summary.get("truncated")
            ),
        )

    def _topology_svg(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        options: TopologyDisplayOptions,
    ) -> str:
        if not nodes or not edges:
            return ""
        node_ids = {str(node.get("node_id")) for node in nodes}
        visible_edges = sorted((
            edge for edge in edges
            if (
                str(edge.get("source_node_id")) in node_ids
                and str(edge.get("target_node_id")) in node_ids
            )
        ), key=self._topology_edge_key)
        if not visible_edges:
            return ""

        layout, width, height = self._topology_layout(
            nodes,
            visible_edges,
            options,
        )
        boxes = layout["boxes"]
        consumed_edges = layout["consumed_edges"]
        vpc_boundary_node_ids = layout.get("vpc_boundary_node_ids", set())
        boundary_node_ids = {
            boundary["node_id"] for boundary in layout["boundaries"]
        }

        boundary_shape_markup = []
        boundary_label_markup = []
        for boundary in layout["boundaries"]:
            node = boundary["node"]
            x, y, boundary_width, boundary_height = boundary["box"]
            category = str(
                boundary.get("category")
                or node.get("category")
                or "subnet"
            ).lower()
            supporting = (
                node.get("kind") != "representative"
                and category != "zone"
            )
            css_class = (
                f" topology-boundary--{category}"
                + (" topology-boundary--supporting" if supporting else "")
            )
            lines = self._topology_boundary_lines(node, options)
            title = (
                f"source={node.get('source') or '-'} · "
                f"confidence={node.get('confidence') or '-'} · "
                f"resolution={node.get('resolution') or '-'}"
            )
            display_name = (
                self._topology_short_text(node.get("name"), 34)
                if options.show_resource_name and node.get("name")
                else ""
            )
            if category == "vpc":
                heading = "VPC" + (f" · {display_name}" if display_name else "")
                tab_width = min(
                    max(104, 30 + len(heading) * 7),
                    max(104, int(boundary_width - 24)),
                )
                texts = [
                    f'<rect x="{x + 12:.1f}" y="{y + 8:.1f}" '
                    f'width="{tab_width}" height="25" rx="5" '
                    'class="topology-vpc-title-tab" />',
                    f'<text x="{x + 23:.1f}" y="{y + 25:.1f}" '
                    'class="topology-vpc-title">'
                    f"{self._text(heading)}</text>",
                ]
                detail_y = y + 47
            elif category == "zone":
                zone_name = self._topology_short_text(node.get("name"), 34)
                heading = "Zone" + (f" · {zone_name}" if zone_name else "")
                tab_width = min(
                    max(94, 30 + len(heading) * 7),
                    max(94, int(boundary_width - 24)),
                )
                texts = [
                    f'<rect x="{x + 10:.1f}" y="{y + 6:.1f}" '
                    f'width="{tab_width}" height="22" rx="3" '
                    'class="topology-zone-title-tab" />',
                    f'<text x="{x + 20:.1f}" y="{y + 21:.1f}" '
                    'class="topology-zone-title">'
                    f"{self._text(heading)}</text>",
                ]
                detail_y = y + 38
            else:
                heading = "Subnet" + (
                    f" · {display_name}" if display_name else ""
                )
                tab_width = min(
                    max(104, 30 + len(heading) * 7),
                    max(104, int(boundary_width - 24)),
                )
                texts = [
                    f'<rect x="{x + 10:.1f}" y="{y + 6:.1f}" '
                    f'width="{tab_width}" height="22" rx="3" '
                    'class="topology-subnet-title-tab" />',
                    f'<text x="{x + 20:.1f}" y="{y + 21:.1f}" '
                    'class="topology-subnet-title">'
                    f"{self._text(heading)}</text>",
                ]
                detail_y = y + 39
            for index, line in enumerate(lines[:2]):
                texts.append(
                    f'<text x="{x + 12:.1f}" '
                    f'y="{detail_y + index * 14:.1f}" '
                    f'class="topology-boundary-detail">{self._text(line)}</text>'
                )
            boundary_shape_markup.append(
                f'<g class="topology-boundary{css_class}">'
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{boundary_width:.1f}" '
                f'height="{boundary_height:.1f}" rx="9"><title>'
                f"{self._text(title)}</title></rect>"
                + "</g>"
            )
            boundary_label_markup.append(
                '<g class="topology-boundary-label">'
                + "".join(texts)
                + "</g>"
            )

        edge_markup = []
        used_edge_segments: List[
            tuple[tuple[float, float], tuple[float, float]]
        ] = []
        for edge in visible_edges:
            if self._topology_edge_key(edge) in consumed_edges:
                continue
            source = boxes.get(str(edge.get("source_node_id")))
            target = boxes.get(str(edge.get("target_node_id")))
            if source is None or target is None:
                continue
            path, label_x, label_y, route_points = (
                self._topology_routed_edge_path(
                    source_id=str(edge.get("source_node_id")),
                    target_id=str(edge.get("target_node_id")),
                    boxes=boxes,
                    boundaries=layout["boundaries"],
                    options=options,
                    width=width,
                    height=height,
                    used_segments=used_edge_segments,
                )
            )
            # 안전한 통로가 없으면 근거 표에는 관계를 남기되, 다른 자원을
            # 침범할 수 있는 추정선을 SVG에 그리지 않는다.
            if not path:
                continue
            used_edge_segments.extend(self._edge_router.path_segments(route_points))
            label = self._topology_relation_label(edge.get("relationship"))
            title = (
                f"{label} · source={edge.get('source') or '-'} · "
                f"confidence={edge.get('confidence') or 'VERIFIED'}"
            )
            edge_markup.append(
                '<g class="topology-edge">'
                f'<path d="{path}" marker-end="url(#topology-arrow)">'
                f"<title>{self._text(title)}</title></path>"
                + (
                    f'<text x="{label_x:.1f}" y="{label_y:.1f}" '
                    f'class="topology-edge-label">{self._text(label)}</text>'
                    if label_x is not None and label_y is not None
                    else ""
                )
                + "</g>"
            )

        node_markup = []
        for node in sorted(nodes, key=self._topology_node_sort_key):
            node_id = str(node.get("node_id"))
            box = boxes.get(node_id)
            if box is None or node_id in boundary_node_ids:
                continue
            x, y, node_width, node_height = box
            supporting = node.get("kind") != "representative"
            css_classes = []
            if supporting:
                css_classes.append("topology-node--supporting")
            if node_id in vpc_boundary_node_ids:
                css_classes.append("topology-node--vpc-boundary")
            css_class = (
                " " + " ".join(css_classes)
                if css_classes else ""
            )
            placement_attribute = (
                ' data-placement="vpc-boundary"'
                if node_id in vpc_boundary_node_ids else ""
            )
            display_name, lines, badges = self._topology_node_card_content(
                node,
                options,
            )
            icon = self._topology_icon(
                node,
                x=x + 10,
                y=y + 8,
                size=40,
                css_class="topology-node-icon",
            )
            title_x = x + (58 if icon else 12)
            title = (
                f"source={node.get('source') or '-'} · "
                f"confidence={node.get('confidence') or '-'} · "
                f"resolution={node.get('resolution') or '-'}"
            )
            texts = [
                f'<text x="{title_x:.1f}" y="{y + 20:.1f}" '
                'class="topology-node-title">'
                f"{self._text(node.get('category_label') or node.get('category'))}"
                "</text>"
            ]
            if display_name:
                texts.append(
                    f'<text x="{title_x:.1f}" y="{y + 38:.1f}" '
                    f'class="topology-node-name">{self._text(display_name)}</text>'
                )
            details_y = y + (54 if display_name else 46)
            for index, line in enumerate(lines[:4]):
                texts.append(
                    f'<text x="{x + 12:.1f}" '
                    f'y="{details_y + index * 15:.1f}" '
                    f'class="topology-node-detail">{self._text(line)}</text>'
                )
            badge_markup = ""
            if badges:
                badge_markup = (
                    f'<rect x="{x + 10:.1f}" y="{y + node_height - 22:.1f}" '
                    f'width="{node_width - 20:.1f}" height="15" rx="7.5" '
                    'class="topology-node-badge-bg" />'
                    f'<text x="{x + node_width / 2:.1f}" '
                    f'y="{y + node_height - 11:.1f}" '
                    'class="topology-node-badge">'
                    f"{self._text(badges)}</text>"
                )
            node_markup.append(
                f'<g class="topology-node{css_class}"{placement_attribute}>'
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{node_width}" '
                f'height="{node_height}" rx="9"><title>'
                f"{self._text(title)}</title></rect>"
                + icon
                + "".join(texts)
                + badge_markup
                + "</g>"
            )

        return (
            f'<svg class="topology-svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" '
            'role="img" aria-label="명시적으로 확인된 클라우드 자원 구성도">'
            '<defs><marker id="topology-arrow" markerWidth="8" markerHeight="8" '
            'refX="7" refY="4" orient="auto" markerUnits="strokeWidth">'
            '<path d="M 0 0 L 8 4 L 0 8 z" /></marker>'
            + self._topology_icon_definitions([
                node for node in nodes
                if str(node.get("node_id")) not in boundary_node_ids
            ])
            + "</defs>"
            + "".join(boundary_shape_markup)
            + "".join(edge_markup)
            + "".join(boundary_label_markup)
            + "".join(node_markup)
            + "</svg>"
        )

    def _topology_icon(
        self,
        node: Mapping[str, Any],
        *,
        x: float,
        y: float,
        size: int,
        css_class: str,
    ) -> str:
        """검증된 아이콘만 SVG에 넣고 없으면 기존 도형을 유지한다."""

        icon = self._icon_library.icon_for(node)
        if icon is None:
            return ""
        return (
            f'<use class="{css_class}" x="{x:.1f}" y="{y:.1f}" '
            f'width="{size}" height="{size}" href="#{icon.symbol_id}" '
            'preserveAspectRatio="xMidYMid meet" aria-hidden="true" />'
        )

    def _topology_icon_definitions(
        self,
        nodes: List[Dict[str, Any]],
    ) -> str:
        """SVG 한 개에 각 PNG를 한 번만 선언해 보고서 크기를 제한한다."""

        icons = {}
        for node in nodes:
            icon = self._icon_library.icon_for(node)
            if icon is not None:
                icons[icon.symbol_id] = icon.data_uri
        return "".join(
            f'<symbol id="{symbol_id}" viewBox="0 0 1 1">'
            f'<image width="1" height="1" href="{data_uri}" '
            'preserveAspectRatio="xMidYMid meet" /></symbol>'
            for symbol_id, data_uri in sorted(icons.items())
        )

    def _topology_layout(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        options: TopologyDisplayOptions,
    ) -> tuple[Dict[str, Any], int, int]:
        if options.group_by_vpc:
            return self._topology_compound_layout(nodes, edges, options)

        layers = defaultdict(list)
        for node in nodes:
            category = str(node.get("category") or "")
            layer = self.TOPOLOGY_LAYER_ORDER.get(category, 2)
            layers[layer].append(node)

        ordered_layers = sorted(layers)
        node_width = self.TOPOLOGY_NODE_WIDTH
        node_height = self.TOPOLOGY_NODE_HEIGHT
        horizontal_gap = 64
        vertical_gap = 16
        margin = 24
        boxes: Dict[str, tuple[float, float, float, float]] = {}
        for column, layer in enumerate(ordered_layers):
            layer_nodes = sorted(
                layers[layer],
                key=self._topology_node_sort_key,
            )
            for row, node in enumerate(layer_nodes):
                boxes[str(node.get("node_id"))] = (
                    margin + column * (node_width + horizontal_gap),
                    margin + row * (node_height + vertical_gap),
                    node_width,
                    node_height,
                )
        max_rows = max((len(value) for value in layers.values()), default=1)
        width = (
            margin * 2
            + len(ordered_layers) * node_width
            + max(0, len(ordered_layers) - 1) * horizontal_gap
        )
        height = (
            margin * 2
            + max_rows * node_height
            + max(0, max_rows - 1) * vertical_gap
        )
        return {
            "boxes": boxes,
            "boundaries": [],
            "consumed_edges": set(),
            "vpc_boundary_node_ids": set(),
        }, max(width, 320), max(height, 220)

    def _topology_compound_layout(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        options: TopologyDisplayOptions,
    ) -> tuple[Dict[str, Any], int, int]:
        """명시적으로 검증된 CONTAINS 관계만 VPC/Subnet 경계로 중첩한다.

        이름, IP, CIDR이 비슷하다는 이유로 소속을 추정하지 않는다. 부모 근거가
        여러 개이거나 VPC와 Subnet 근거가 충돌하면 잘못된 포함 관계를 만들지
        않도록 해당 자원을 경계 밖의 독립 노드로 유지한다.
        """
        node_by_id = {
            str(node.get("node_id")): node
            for node in nodes
            if node.get("node_id") is not None
        }
        vpc_ids = {
            node_id for node_id, node in node_by_id.items()
            if str(node.get("category") or "") == "VPC"
        }
        subnet_ids = {
            node_id for node_id, node in node_by_id.items()
            if str(node.get("category") or "") == "SUBNET"
        }
        vpc_parents: Dict[str, set[str]] = defaultdict(set)
        subnet_parents: Dict[str, set[str]] = defaultdict(set)
        contains_edges: Dict[tuple[str, str], Dict[str, Any]] = {}
        for edge in edges:
            if str(edge.get("relationship") or "").upper() != "CONTAINS":
                continue
            source_id = str(edge.get("source_node_id") or "")
            target_id = str(edge.get("target_node_id") or "")
            source = node_by_id.get(source_id)
            if source is None or target_id not in node_by_id:
                continue
            source_category = str(source.get("category") or "")
            if source_category == "VPC":
                vpc_parents[target_id].add(source_id)
            elif source_category == "SUBNET":
                subnet_parents[target_id].add(source_id)
            contains_edges[(source_id, target_id)] = edge

        subnet_to_vpc = {
            subnet_id: next(iter(parents))
            for subnet_id, parents in vpc_parents.items()
            if subnet_id in subnet_ids and len(parents) == 1
        }
        boundary_nat_to_vpc: Dict[str, str] = {}
        for node_id, node in sorted(
            node_by_id.items(),
            key=lambda item: self._topology_node_sort_key(item[1]),
        ):
            if str(node.get("category") or "") != "NAT_GATEWAY":
                continue
            direct_vpc_ids = vpc_parents.get(node_id, set()) & vpc_ids
            subnet_vpc_ids = {
                subnet_to_vpc[subnet_id]
                for subnet_id in subnet_parents.get(node_id, set())
                if subnet_id in subnet_to_vpc
            }
            candidate_vpc_ids = direct_vpc_ids | subnet_vpc_ids
            if len(candidate_vpc_ids) == 1:
                boundary_nat_to_vpc[node_id] = next(iter(candidate_vpc_ids))

        boundary_vpc_children: Dict[str, List[Dict[str, Any]]] = defaultdict(
            list
        )
        for node_id, vpc_id in boundary_nat_to_vpc.items():
            boundary_vpc_children[vpc_id].append(node_by_id[node_id])

        subnet_children: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        direct_vpc_children: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        assigned_ids: set[str] = set(boundary_nat_to_vpc)
        consumed_edges: set[tuple[str, str, str]] = set()

        for subnet_id, vpc_id in subnet_to_vpc.items():
            edge = contains_edges.get((vpc_id, subnet_id))
            if edge is not None:
                consumed_edges.add(self._topology_edge_key(edge))

        # NAT Gateway는 실제 관계 근거를 보존한 채 VPC 경계 배치로 표현한다.
        # 동일 VPC에 속한 Subnet 관계도 증거 표에는 남고, SVG에서는 경계 배치가
        # 소속 관계를 대신하므로 중복되는 포함선을 그리지 않는다.
        for nat_id, vpc_id in boundary_nat_to_vpc.items():
            parent_ids = set(vpc_parents.get(nat_id, set()))
            parent_ids.update(subnet_parents.get(nat_id, set()))
            for parent_id in parent_ids:
                parent_vpc_id = (
                    parent_id
                    if parent_id in vpc_ids
                    else subnet_to_vpc.get(parent_id)
                )
                if parent_vpc_id != vpc_id:
                    continue
                edge = contains_edges.get((parent_id, nat_id))
                if edge is not None:
                    consumed_edges.add(self._topology_edge_key(edge))

        candidates = sorted(
            (
                node for node_id, node in node_by_id.items()
                if (
                    node_id not in vpc_ids
                    and node_id not in subnet_ids
                    and node_id not in boundary_nat_to_vpc
                )
            ),
            key=self._topology_node_sort_key,
        )
        for node in candidates:
            node_id = str(node.get("node_id"))
            subnet_parent_ids = subnet_parents.get(node_id, set())
            vpc_parent_ids = vpc_parents.get(node_id, set())
            if len(subnet_parent_ids) == 1:
                subnet_id = next(iter(subnet_parent_ids))
                subnet_vpc_id = subnet_to_vpc.get(subnet_id)
                has_conflict = bool(
                    vpc_parent_ids
                    and (
                        subnet_vpc_id is None
                        or vpc_parent_ids != {subnet_vpc_id}
                    )
                )
                # Subnet과 VPC의 명시적 근거가 충돌하면 어느 쪽도 임의로 선택하지 않는다.
                if not has_conflict:
                    subnet_children[subnet_id].append(node)
                    assigned_ids.add(node_id)
                    edge = contains_edges.get((subnet_id, node_id))
                    if edge is not None:
                        consumed_edges.add(self._topology_edge_key(edge))
                    if subnet_vpc_id is not None:
                        edge = contains_edges.get((subnet_vpc_id, node_id))
                        if edge is not None:
                            consumed_edges.add(self._topology_edge_key(edge))
                    continue

            if len(subnet_parent_ids) > 1:
                parent_vpcs = {
                    subnet_to_vpc.get(subnet_id)
                    for subnet_id in subnet_parent_ids
                }
                # 여러 Subnet이 모두 같은 VPC에 속할 때만 VPC 직속 자원으로 배치한다.
                if None not in parent_vpcs and len(parent_vpcs) == 1:
                    vpc_id = next(iter(parent_vpcs))
                    if not vpc_parent_ids or vpc_parent_ids == {vpc_id}:
                        direct_vpc_children[vpc_id].append(node)
                        assigned_ids.add(node_id)
                        edge = contains_edges.get((vpc_id, node_id))
                        if edge is not None:
                            consumed_edges.add(self._topology_edge_key(edge))
                        continue

            if not subnet_parent_ids and len(vpc_parent_ids) == 1:
                vpc_id = next(iter(vpc_parent_ids))
                if vpc_id in vpc_ids:
                    direct_vpc_children[vpc_id].append(node)
                    assigned_ids.add(node_id)
                    edge = contains_edges.get((vpc_id, node_id))
                    if edge is not None:
                        consumed_edges.add(self._topology_edge_key(edge))

        node_width = self.TOPOLOGY_NODE_WIDTH
        node_height = self.TOPOLOGY_NODE_HEIGHT
        # 중첩 경계 사이의 빈 공간은 관계선 전용 통로로도 사용한다.
        horizontal_gap = 24
        vertical_gap = 24
        boundary_padding = 14
        outer_gap = 44
        margin = 24

        def grid_layout(
            items: List[Dict[str, Any]],
            *,
            max_columns: int,
        ) -> tuple[int, int, Dict[str, tuple[float, float, float, float]]]:
            if not items:
                return 0, 0, {}
            ordered_items = sorted(items, key=self._topology_node_sort_key)
            columns = min(max_columns, len(ordered_items))
            rows = math.ceil(len(ordered_items) / columns)
            grid_width = (
                columns * node_width + (columns - 1) * horizontal_gap
            )
            grid_height = rows * node_height + (rows - 1) * vertical_gap
            local_boxes = {}
            for index, item in enumerate(ordered_items):
                local_boxes[str(item.get("node_id"))] = (
                    (index % columns) * (node_width + horizontal_gap),
                    (index // columns) * (node_height + vertical_gap),
                    node_width,
                    node_height,
                )
            return grid_width, grid_height, local_boxes

        def variable_layout(
            groups: List[Dict[str, Any]],
            *,
            max_columns: int,
        ) -> tuple[int, int, Dict[str, tuple[float, float]]]:
            if not groups:
                return 0, 0, {}
            placements = {}
            total_width = 0
            cursor_y = 0
            for row_start in range(0, len(groups), max_columns):
                row = groups[row_start:row_start + max_columns]
                cursor_x = 0
                row_height = max(group["height"] for group in row)
                for group in row:
                    placements[group["key"]] = (cursor_x, cursor_y)
                    cursor_x += group["width"] + horizontal_gap
                total_width = max(
                    total_width,
                    cursor_x - horizontal_gap,
                )
                cursor_y += row_height + vertical_gap
            return total_width, cursor_y - vertical_gap, placements

        def subnet_group(subnet_id: str) -> Dict[str, Any]:
            subnet = node_by_id[subnet_id]
            header_height = self._topology_boundary_header_height(
                subnet,
                options,
            )
            grid_width, grid_height, child_boxes = grid_layout(
                subnet_children.get(subnet_id, []),
                max_columns=3,
            )
            width = max(228, grid_width + boundary_padding * 2)
            content_offset_y = header_height + 10
            height = header_height + boundary_padding
            if child_boxes:
                height = content_offset_y + grid_height + boundary_padding
            translated = {
                node_id: (
                    box[0] + boundary_padding,
                    box[1] + content_offset_y,
                    box[2],
                    box[3],
                )
                for node_id, box in child_boxes.items()
            }
            return {
                "key": subnet_id,
                "node": subnet,
                "width": width,
                "height": height,
                "child_boxes": translated,
            }

        subnet_groups = {
            subnet_id: subnet_group(subnet_id)
            for subnet_id in subnet_ids
        }

        def zone_group(
            vpc_id: str,
            zone_name: str,
            child_subnet_ids: List[str],
        ) -> Dict[str, Any]:
            ordered_subnets = [
                subnet_groups[subnet_id]
                for subnet_id in sorted(
                    child_subnet_ids,
                    key=lambda item: self._topology_node_sort_key(
                        node_by_id[item]
                    ),
                )
            ]
            content_width, content_height, placements = variable_layout(
                ordered_subnets,
                max_columns=3,
            )
            zone_header_height = 30
            zone_padding = 12
            zone_id = f"ZONE:{vpc_id}:{zone_name}"
            nested_boundaries = []
            child_boxes = {}
            for subnet in ordered_subnets:
                offset_x, offset_y = placements[subnet["key"]]
                subnet_x = offset_x + zone_padding
                subnet_y = offset_y + zone_header_height + zone_padding
                nested_boundaries.append({
                    "node_id": subnet["key"],
                    "node": subnet["node"],
                    "box": (
                        subnet_x,
                        subnet_y,
                        subnet["width"],
                        subnet["height"],
                    ),
                    "category": "subnet",
                    "level": 2,
                })
                for child_id, box in subnet["child_boxes"].items():
                    child_boxes[child_id] = (
                        box[0] + subnet_x,
                        box[1] + subnet_y,
                        box[2],
                        box[3],
                    )
            return {
                "key": zone_id,
                "node": {
                    "node_id": zone_id,
                    "category": "ZONE",
                    "category_label": "Zone",
                    "name": zone_name,
                    "kind": "presentation",
                    "source": "subnet.zone",
                    "confidence": "VERIFIED",
                    "resolution": "RESOLVED",
                },
                "width": max(260, content_width + zone_padding * 2),
                "height": (
                    zone_header_height
                    + zone_padding
                    + content_height
                    + zone_padding
                ),
                "nested_boundaries": nested_boundaries,
                "child_boxes": child_boxes,
            }

        def subnet_component(subnet_id: str) -> Dict[str, Any]:
            subnet = subnet_groups[subnet_id]
            return {
                "key": subnet_id,
                "node": subnet["node"],
                "width": subnet["width"],
                "height": subnet["height"],
                "nested_boundaries": [{
                    "node_id": subnet_id,
                    "node": subnet["node"],
                    "box": (0, 0, subnet["width"], subnet["height"]),
                    "category": "subnet",
                    "level": 2,
                }],
                "child_boxes": dict(subnet["child_boxes"]),
            }

        def vpc_group(vpc_id: str) -> Dict[str, Any]:
            vpc = node_by_id[vpc_id]
            header_height = self._topology_boundary_header_height(vpc, options)
            child_subnet_ids = sorted(
                (
                    subnet_id
                    for subnet_id, parent_id in subnet_to_vpc.items()
                    if parent_id == vpc_id
                ),
                key=lambda item: self._topology_node_sort_key(
                    node_by_id[item]
                ),
            )
            zone_to_subnets: Dict[str, List[str]] = defaultdict(list)
            unzoned_subnets = []
            for subnet_id in child_subnet_ids:
                zone_name = str(node_by_id[subnet_id].get("zone") or "").strip()
                if options.show_zone and zone_name:
                    zone_to_subnets[zone_name].append(subnet_id)
                else:
                    unzoned_subnets.append(subnet_id)

            components = [
                zone_group(vpc_id, zone_name, zone_to_subnets[zone_name])
                for zone_name in sorted(zone_to_subnets, key=str.casefold)
            ]
            components.extend(
                subnet_component(subnet_id)
                for subnet_id in unzoned_subnets
            )
            component_width, component_height, placements = variable_layout(
                components,
                max_columns=3,
            )
            nested_boundaries = []
            child_boxes = {}
            content_offset_y = header_height + boundary_padding
            for component in components:
                offset_x, offset_y = placements[component["key"]]
                offset_x += boundary_padding
                offset_y += content_offset_y
                if component["node"].get("category") == "ZONE":
                    nested_boundaries.append({
                        "node_id": component["key"],
                        "node": component["node"],
                        "box": (
                            offset_x,
                            offset_y,
                            component["width"],
                            component["height"],
                        ),
                        "category": "zone",
                        "level": 1,
                    })
                for boundary in component["nested_boundaries"]:
                    box = boundary["box"]
                    nested_boundaries.append({
                        **boundary,
                        "box": (
                            box[0] + offset_x,
                            box[1] + offset_y,
                            box[2],
                            box[3],
                        ),
                    })
                for child_id, box in component["child_boxes"].items():
                    child_boxes[child_id] = (
                        box[0] + offset_x,
                        box[1] + offset_y,
                        box[2],
                        box[3],
                    )

            direct_width, direct_height, direct_boxes = grid_layout(
                direct_vpc_children.get(vpc_id, []),
                max_columns=4,
            )
            direct_offset_y = content_offset_y + component_height
            if components and direct_boxes:
                direct_offset_y += vertical_gap
            for child_id, box in direct_boxes.items():
                child_boxes[child_id] = (
                    box[0] + boundary_padding,
                    box[1] + direct_offset_y,
                    box[2],
                    box[3],
                )

            content_width = max(component_width, direct_width)
            content_height = component_height
            if direct_boxes:
                content_height = (
                    direct_offset_y - content_offset_y + direct_height
                )
            width = max(320, content_width + boundary_padding * 2)
            height = (
                content_offset_y + content_height + boundary_padding
                if content_height
                else header_height + boundary_padding * 2
            )

            boundary_items = sorted(
                boundary_vpc_children.get(vpc_id, []),
                key=self._topology_node_sort_key,
            )
            outside_extent = 0.0
            if boundary_items:
                width = max(
                    width,
                    content_width
                    + boundary_padding * 2
                    + horizontal_gap
                    + node_width / 2,
                )
                boundary_stack_height = (
                    len(boundary_items) * node_height
                    + max(0, len(boundary_items) - 1) * vertical_gap
                )
                height = max(
                    height,
                    header_height
                    + boundary_padding
                    + boundary_stack_height
                    + boundary_padding,
                )
                outside_extent = node_width / 2
                boundary_x = width - node_width / 2
                boundary_y = header_height + boundary_padding
                for index, item in enumerate(boundary_items):
                    child_boxes[str(item.get("node_id"))] = (
                        boundary_x,
                        boundary_y + index * (node_height + vertical_gap),
                        node_width,
                        node_height,
                    )
            return {
                "node": vpc,
                "width": width,
                "height": height,
                "outside_extent": outside_extent,
                "nested_boundaries": nested_boundaries,
                "child_boxes": child_boxes,
            }

        vpc_groups = {vpc_id: vpc_group(vpc_id) for vpc_id in vpc_ids}
        boxes: Dict[str, tuple[float, float, float, float]] = {}
        boundaries: List[Dict[str, Any]] = []
        max_right = margin
        max_bottom = margin

        external_nodes = [
            node
            for node_id, node in node_by_id.items()
            if (
                node_id not in vpc_ids
                and node_id not in subnet_ids
                and node_id not in assigned_ids
            )
        ]
        cursor_x = margin
        if external_nodes:
            layers = defaultdict(list)
            for node in external_nodes:
                category = str(node.get("category") or "")
                layers[self.TOPOLOGY_LAYER_ORDER.get(category, 2)].append(node)
            for layer in sorted(layers):
                layer_nodes = sorted(
                    layers[layer],
                    key=self._topology_node_sort_key,
                )
                for row, node in enumerate(layer_nodes):
                    box = (
                        cursor_x,
                        margin + row * (node_height + vertical_gap),
                        node_width,
                        node_height,
                    )
                    boxes[str(node.get("node_id"))] = box
                    max_right = max(max_right, box[0] + box[2])
                    max_bottom = max(max_bottom, box[1] + box[3])
                cursor_x += node_width + 52
            cursor_x += outer_gap - 52

        for vpc_id in sorted(
            vpc_ids,
            key=lambda item: self._topology_node_sort_key(node_by_id[item]),
        ):
            group = vpc_groups[vpc_id]
            x = cursor_x
            y = margin
            vpc_box = (x, y, group["width"], group["height"])
            boxes[vpc_id] = vpc_box
            boundaries.append({
                "node_id": vpc_id,
                "node": group["node"],
                "box": vpc_box,
                "category": "vpc",
                "level": 0,
            })
            for boundary in group["nested_boundaries"]:
                box = boundary["box"]
                absolute_box = (
                    box[0] + x,
                    box[1] + y,
                    box[2],
                    box[3],
                )
                boundaries.append({**boundary, "box": absolute_box})
                boxes[boundary["node_id"]] = absolute_box
            for child_id, box in group["child_boxes"].items():
                absolute_box = (
                    box[0] + x,
                    box[1] + y,
                    box[2],
                    box[3],
                )
                boxes[child_id] = absolute_box
                max_right = max(
                    max_right,
                    absolute_box[0] + absolute_box[2],
                )
                max_bottom = max(
                    max_bottom,
                    absolute_box[1] + absolute_box[3],
                )
            max_right = max(
                max_right,
                x + group["width"] + group["outside_extent"],
            )
            max_bottom = max(max_bottom, y + group["height"])
            cursor_x += (
                group["width"] + group["outside_extent"] + outer_gap
            )

        orphan_subnet_ids = sorted(
            subnet_ids - set(subnet_to_vpc),
            key=lambda item: self._topology_node_sort_key(node_by_id[item]),
        )
        for subnet_id in orphan_subnet_ids:
            group = subnet_groups[subnet_id]
            box = (
                cursor_x,
                margin,
                group["width"],
                group["height"],
            )
            boxes[subnet_id] = box
            boundaries.append({
                "node_id": subnet_id,
                "node": group["node"],
                "box": box,
                "category": "subnet",
                "level": 2,
            })
            for child_id, child_box in group["child_boxes"].items():
                boxes[child_id] = (
                    child_box[0] + cursor_x,
                    child_box[1] + margin,
                    child_box[2],
                    child_box[3],
                )
            max_right = max(max_right, cursor_x + group["width"])
            max_bottom = max(max_bottom, margin + group["height"])
            cursor_x += group["width"] + outer_gap

        boundaries.sort(key=lambda boundary: boundary["level"])
        width = max(420, int(math.ceil(max_right + margin)))
        height = max(220, int(math.ceil(max_bottom + margin)))
        return {
            "boxes": boxes,
            "boundaries": boundaries,
            "consumed_edges": consumed_edges,
            "vpc_boundary_node_ids": set(boundary_nat_to_vpc),
        }, width, height

    def _topology_boundary_header_height(
        self,
        node: Mapping[str, Any],
        options: TopologyDisplayOptions,
    ) -> int:
        category = str(node.get("category") or "").upper()
        line_count = min(2, len(self._topology_boundary_lines(node, options)))
        if category == "VPC":
            return max(44, 42 + line_count * 14)
        if category == "SUBNET":
            return max(32, 32 + line_count * 14)
        return 34

    def _topology_boundary_lines(
        self,
        node: Mapping[str, Any],
        options: TopologyDisplayOptions,
    ) -> List[str]:
        """VPC/Subnet 헤더에는 네트워크 식별 정보만 간결하게 표시한다."""

        category = str(node.get("category") or "").upper()
        if category not in {"VPC", "SUBNET"}:
            return []
        summary_parts = []
        if options.show_network_cidr and node.get("network_cidrs"):
            summary_parts.append(
                "CIDR " + self._topology_value_list(node.get("network_cidrs"))
            )
        if category == "SUBNET" and options.show_zone and node.get("zone"):
            summary_parts.append(
                "Zone " + self._topology_short_text(node.get("zone"), 18)
            )
        lines = [" · ".join(summary_parts)] if summary_parts else []
        if options.show_resource_id and node.get("resource_id"):
            lines.append(
                "ID " + self._topology_short_text(node.get("resource_id"), 34)
            )
        return lines[:2]

    @staticmethod
    def _topology_node_sort_key(node: Mapping[str, Any]) -> tuple[str, str, str]:
        return (
            str(node.get("category") or ""),
            str(node.get("name") or "").casefold(),
            str(node.get("resource_id") or node.get("node_id") or ""),
        )

    @staticmethod
    def _topology_edge_key(edge: Mapping[str, Any]) -> tuple[str, str, str]:
        return (
            str(edge.get("source_node_id") or ""),
            str(edge.get("target_node_id") or ""),
            str(edge.get("relationship") or "").upper(),
        )

    def _topology_routed_edge_path(
        self,
        *,
        source_id: str,
        target_id: str,
        boxes: Mapping[str, tuple[float, float, float, float]],
        boundaries: Sequence[Mapping[str, Any]],
        options: TopologyDisplayOptions,
        width: float,
        height: float,
        used_segments: Sequence[
            tuple[tuple[float, float], tuple[float, float]]
        ] = (),
    ) -> tuple[str, float | None, float | None, List[tuple[float, float]]]:
        """경계 표현 정보를 순수 직교 라우터의 입력으로 변환한다."""

        routing_boundaries = []
        for boundary in boundaries:
            box = boundary.get("box")
            if not isinstance(box, tuple) or len(box) != 4:
                continue
            category = str(boundary.get("category") or "").lower()
            header_height = (
                30
                if category == "zone"
                else self._topology_boundary_header_height(
                    boundary.get("node") or {},
                    options,
                )
            )
            routing_boundaries.append({
                "node_id": str(boundary.get("node_id") or ""),
                "box": box,
                "header_height": header_height,
            })
        return self._edge_router.route(
            source_id=source_id,
            target_id=target_id,
            boxes=boxes,
            boundaries=routing_boundaries,
            width=width,
            height=height,
            used_segments=used_segments,
        )

    @staticmethod
    def _topology_edge_path(
        source: tuple[float, float, float, float],
        target: tuple[float, float, float, float],
    ) -> tuple[str, float, float]:
        sx, sy, sw, sh = source
        tx, ty, tw, th = target
        source_center_x = sx + sw / 2
        source_center_y = sy + sh / 2
        target_center_x = tx + tw / 2
        target_center_y = ty + th / 2
        delta_x = target_center_x - source_center_x
        delta_y = target_center_y - source_center_y
        horizontal = abs(delta_x) / max(sw + tw, 1) >= abs(delta_y) / max(sh + th, 1)

        if horizontal:
            if delta_x >= 0:
                start_x, start_y = sx + sw, source_center_y
                end_x, end_y = tx, target_center_y
            else:
                start_x, start_y = sx, source_center_y
                end_x, end_y = tx + tw, target_center_y
            middle_x = (start_x + end_x) / 2
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"H {middle_x:.1f} V {end_y:.1f} H {end_x:.1f}"
            )
        else:
            if delta_y >= 0:
                start_x, start_y = source_center_x, sy + sh
                end_x, end_y = target_center_x, ty
            else:
                start_x, start_y = source_center_x, sy
                end_x, end_y = target_center_x, ty + th
            middle_y = (start_y + end_y) / 2
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"V {middle_y:.1f} H {end_x:.1f} V {end_y:.1f}"
            )
        return path, (start_x + end_x) / 2, (start_y + end_y) / 2 - 5

    def _topology_node_card_content(
        self,
        node: Mapping[str, Any],
        options: TopologyDisplayOptions,
    ) -> tuple[str, List[str], str]:
        """아이콘 카드에 이름, 핵심 속성, 보조 배지를 분리해 반환한다."""

        display_name = (
            self._topology_short_text(node.get("name"), 25)
            if options.show_resource_name and node.get("name")
            else ""
        )
        details = []
        if node.get("resolution") == "UNRESOLVED":
            details.append("REFERENCE_ONLY / UNRESOLVED")

        private_ips = self._topology_node_values(
            node,
            ("private_ips", "private_ip", "all_private_ips"),
        )
        public_ips = self._topology_node_values(
            node,
            ("public_ips", "public_ip"),
        )
        if options.show_private_ip and private_ips:
            details.append("Private " + self._topology_value_list(private_ips))
        if options.show_public_ip and public_ips:
            details.append("Public " + self._topology_value_list(public_ips))
        if str(node.get("category") or "") == "SERVER":
            disk_summary = self._topology_server_disk_summary(node)
            if disk_summary:
                details.append(disk_summary)
        if options.show_network_cidr and node.get("network_cidrs"):
            details.append(
                "CIDR " + self._topology_value_list(node.get("network_cidrs"))
            )

        identifier = ""
        if options.show_resource_id and node.get("resource_id"):
            identifier = (
                "ID " + self._topology_short_text(node.get("resource_id"), 27)
            )
        if identifier:
            details = details[:3] + [identifier]
        else:
            details = details[:4]

        badges = []
        if options.show_status and node.get("status"):
            badges.append(self._topology_short_text(node.get("status"), 12))
        if options.show_zone and node.get("zone"):
            badges.append(self._topology_short_text(node.get("zone"), 12))
        if options.show_platform and node.get("platform"):
            badges.append(self._topology_short_text(node.get("platform"), 12))
        return display_name, details, " · ".join(badges)

    def _topology_node_lines(
        self,
        node: Mapping[str, Any],
        options: TopologyDisplayOptions,
    ) -> List[str]:
        lines = []
        if node.get("resolution") == "UNRESOLVED":
            lines.append("REFERENCE_ONLY / UNRESOLVED")
        if options.show_resource_name and node.get("name"):
            lines.append(self._topology_short_text(node.get("name")))
        private_ips = self._topology_node_values(
            node,
            ("private_ips", "private_ip", "all_private_ips"),
        )
        public_ips = self._topology_node_values(
            node,
            ("public_ips", "public_ip"),
        )
        if options.show_private_ip and private_ips:
            lines.append(
                "Private IP "
                + self._topology_value_list(private_ips)
            )
        if options.show_public_ip and public_ips:
            lines.append(
                "Public IP "
                + self._topology_value_list(public_ips)
            )
        if str(node.get("category") or "") == "SERVER":
            disk_summary = self._topology_server_disk_summary(node)
            if disk_summary:
                lines.append(disk_summary)
        if options.show_network_cidr and node.get("network_cidrs"):
            lines.append(
                "CIDR " + self._topology_value_list(node.get("network_cidrs"))
            )
        if options.show_resource_id and node.get("resource_id"):
            lines.append(
                "ID " + self._topology_short_text(node.get("resource_id"), 28)
            )
        if options.show_status and node.get("status"):
            lines.append("상태 " + self._topology_short_text(node.get("status")))
        if options.show_zone and node.get("zone"):
            lines.append("Zone " + self._topology_short_text(node.get("zone")))
        if options.show_platform and node.get("platform"):
            lines.append(
                "플랫폼 " + self._topology_short_text(node.get("platform"))
            )
        return lines[:8]

    @classmethod
    def _topology_node_values(
        cls,
        node: Mapping[str, Any],
        field_names: tuple[str, ...],
    ) -> List[Any]:
        """허용한 필드만 읽어 렌더링용 값 목록으로 정규화한다."""

        values = []
        for container in cls._topology_node_containers(node):
            for field_name in field_names:
                value = container.get(field_name)
                candidates = (
                    value
                    if isinstance(value, (list, tuple))
                    else [value]
                )
                for candidate in candidates:
                    if candidate is None or isinstance(candidate, Mapping):
                        continue
                    if candidate not in values:
                        values.append(candidate)
        return values

    @classmethod
    def _topology_server_disk_summary(
        cls,
        node: Mapping[str, Any],
    ) -> str:
        """서버에 병합된 디스크의 개수와 합계 용량만 표시한다."""

        count = cls._topology_nonnegative_number(
            cls._topology_node_field(node, "attached_disk_count")
        )
        total_gb = cls._topology_nonnegative_number(
            cls._topology_node_field(node, "attached_disk_total_gb")
        )
        known_capacity_count = cls._topology_nonnegative_number(
            cls._topology_node_field(
                node,
                "attached_disk_capacity_known_count",
            )
        )
        confirmed_capacity_gb = None
        attached_disks = cls._topology_node_field(node, "attached_disks")
        if isinstance(attached_disks, (list, tuple)):
            if count is None:
                count = float(len(attached_disks))
            if total_gb is None:
                sizes = [
                    cls._topology_nonnegative_number(
                        cls._topology_node_field(
                            disk,
                            "size_gb",
                            "storage_size_gb",
                            "block_storage_size_gb",
                        )
                    )
                    for disk in attached_disks
                    if isinstance(disk, Mapping)
                ]
                valid_sizes = [size for size in sizes if size is not None]
                all_capacities_known = bool(
                    sizes
                    and len(sizes) == len(attached_disks)
                    and len(valid_sizes) == len(sizes)
                    and count == float(len(sizes))
                    and (
                        known_capacity_count is None
                        or known_capacity_count == float(len(sizes))
                    )
                )
                if all_capacities_known:
                    total_gb = sum(valid_sizes)
                elif valid_sizes:
                    confirmed_capacity_gb = sum(valid_sizes)
                    if known_capacity_count is None:
                        known_capacity_count = float(len(valid_sizes))

        if not count and total_gb is None and confirmed_capacity_gb is None:
            return ""
        parts = []
        if count is not None:
            parts.append(f"디스크 {int(count):,}개")
        if total_gb is not None:
            rendered_total = f"{total_gb:,.2f}".rstrip("0").rstrip(".")
            parts.append(f"합계 {rendered_total} GB")
        elif confirmed_capacity_gb is not None:
            rendered_total = (
                f"{confirmed_capacity_gb:,.2f}".rstrip("0").rstrip(".")
            )
            known_label = (
                f" ({int(known_capacity_count):,}개 확인)"
                if known_capacity_count is not None
                else ""
            )
            parts.append(f"확인 용량 {rendered_total} GB{known_label}")
        return " · ".join(parts)

    @staticmethod
    def _topology_node_containers(
        node: Mapping[str, Any],
    ) -> List[Mapping[str, Any]]:
        containers = [node]
        for field_name in ("metadata", "raw", "details"):
            value = node.get(field_name)
            if isinstance(value, Mapping):
                containers.append(value)
        return containers

    @classmethod
    def _topology_node_field(
        cls,
        node: Mapping[str, Any],
        *field_names: str,
    ) -> Any:
        for container in cls._topology_node_containers(node):
            for field_name in field_names:
                value = container.get(field_name)
                if value is not None:
                    return value
        return None

    @staticmethod
    def _topology_nonnegative_number(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number) or number < 0:
            return None
        return number

    def _topology_unmapped_card(
        self,
        node: Mapping[str, Any],
        options: TopologyDisplayOptions,
    ) -> str:
        lines = self._topology_node_lines(node, options)
        details = " · ".join(lines) if lines else "표시 속성 없음"
        return (
            '<article class="topology-unmapped-card">'
            f"<strong>{self._text(node.get('category_label') or node.get('category'))}</strong>"
            f"<span>{self._text(details)}</span>"
            "<small>source="
            + self._text(node.get("source"))
            + " · confidence="
            + self._text(node.get("confidence"))
            + "</small></article>"
        )

    def _topology_evidence_table(
        self,
        edges: List[Dict[str, Any]],
        nodes: List[Dict[str, Any]],
        options: TopologyDisplayOptions,
    ) -> str:
        node_by_id = {
            str(node.get("node_id")): node
            for node in nodes
        }
        rows = []
        for edge in edges:
            source_node = node_by_id.get(str(edge.get("source_node_id")), {})
            target_node = node_by_id.get(str(edge.get("target_node_id")), {})
            rows.append({
                "relation": (
                    self._topology_node_reference(source_node, options)
                    + " → "
                    + self._topology_node_reference(target_node, options)
                ),
                "relationship": self._topology_relation_label(
                    edge.get("relationship")
                ),
                "source": edge.get("source"),
                "confidence": edge.get("confidence"),
            })
        return self._table(
            rows,
            (
                ("relation", "연결"),
                ("relationship", "관계"),
                ("source", "근거 source"),
                ("confidence", "신뢰도"),
            ),
        )

    def _topology_node_reference(
        self,
        node: Mapping[str, Any],
        options: TopologyDisplayOptions,
    ) -> str:
        category = str(
            node.get("category_label") or node.get("category") or "리소스"
        )
        if options.show_resource_name and node.get("name"):
            return f"{category}: {node.get('name')}"
        if options.show_resource_id and node.get("resource_id"):
            return f"{category}: {node.get('resource_id')}"
        if node.get("resolution") == "UNRESOLVED":
            return f"{category}: 미해결 참조"
        return category

    @staticmethod
    def _topology_relation_label(value: Any) -> str:
        labels = {
            "CONTAINS": "포함",
            "ATTACHED_TO": "연결",
            "ATTACHED_STORAGE": "스토리지 부착",
            "ASSIGNED_TO": "할당",
            "TARGETS": "LB 대상",
            "HAS_SNAPSHOT": "스냅샷",
            "PEERS_FROM": "피어링 원본",
            "PEERS_TO": "피어링 대상",
            "RELATED_TO": "명시 관계",
        }
        normalized = str(value or "RELATED_TO").upper()
        return labels.get(normalized, normalized.replace("_", " "))

    def _topology_value_list(self, value: Any) -> str:
        values = [
            self._topology_short_text(item, 24)
            for item in value
            if item is not None and str(item).strip()
        ] if isinstance(value, (list, tuple)) else []
        if not values:
            return "-"
        visible = values[:2]
        suffix = f" 외 {len(values) - 2}개" if len(values) > 2 else ""
        return ", ".join(visible) + suffix

    @staticmethod
    def _topology_short_text(value: Any, limit: int = 32) -> str:
        rendered = str(value or "").strip()
        if len(rendered) <= limit:
            return rendered
        return rendered[: max(1, limit - 1)] + "…"
