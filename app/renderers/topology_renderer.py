from __future__ import annotations

import math
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Mapping

from app.infrastructure_topology import (
    InfrastructureTopologyBuilder,
    TopologyDisplayOptions,
)
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
    TOPOLOGY_NODE_WIDTH = 230
    TOPOLOGY_NODE_HEIGHT = 196

    def __init__(self, html_renderer: Any) -> None:
        self._html_renderer = html_renderer
        self._icon_library = TopologyIconLibrary()

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
        boundary_node_ids = {
            boundary["node_id"] for boundary in layout["boundaries"]
        }

        boundary_shape_markup = []
        boundary_label_markup = []
        for boundary in layout["boundaries"]:
            node = boundary["node"]
            x, y, boundary_width, boundary_height = boundary["box"]
            category = (
                "vpc"
                if str(node.get("category") or "") == "VPC"
                else "subnet"
            )
            supporting = node.get("kind") != "representative"
            css_class = (
                f" topology-boundary--{category}"
                + (" topology-boundary--supporting" if supporting else "")
            )
            lines = self._topology_node_lines(node, options)
            icon = self._topology_icon(
                node,
                x=x + 16,
                y=y + 10,
                size=24,
                css_class="topology-boundary-icon",
            )
            title_x = x + (48 if icon else 16)
            title = (
                f"source={node.get('source') or '-'} · "
                f"confidence={node.get('confidence') or '-'} · "
                f"resolution={node.get('resolution') or '-'}"
            )
            texts = [
                f'<text x="{title_x:.1f}" y="{y + 27:.1f}" '
                'class="topology-boundary-title">'
                f"{self._text(node.get('category_label') or node.get('category'))}"
                "</text>"
            ]
            for index, line in enumerate(lines[:8]):
                texts.append(
                    f'<text x="{x + 16:.1f}" y="{y + 47 + index * 17:.1f}" '
                    f'class="topology-boundary-detail">{self._text(line)}</text>'
                )
            boundary_shape_markup.append(
                f'<g class="topology-boundary{css_class}">'
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{boundary_width:.1f}" '
                f'height="{boundary_height:.1f}" rx="16"><title>'
                f"{self._text(title)}</title></rect>"
                + "</g>"
            )
            boundary_label_markup.append(
                '<g class="topology-boundary-label">'
                + icon
                + "".join(texts)
                + "</g>"
            )

        edge_markup = []
        for edge in visible_edges:
            if self._topology_edge_key(edge) in consumed_edges:
                continue
            source = boxes.get(str(edge.get("source_node_id")))
            target = boxes.get(str(edge.get("target_node_id")))
            if source is None or target is None:
                continue
            path, label_x, label_y = self._topology_edge_path(
                source,
                target,
            )
            label = self._topology_relation_label(edge.get("relationship"))
            title = (
                f"{label} · source={edge.get('source') or '-'} · "
                f"confidence={edge.get('confidence') or 'VERIFIED'}"
            )
            edge_markup.append(
                '<g class="topology-edge">'
                f'<path d="{path}" marker-end="url(#topology-arrow)">'
                f"<title>{self._text(title)}</title></path>"
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" '
                f'class="topology-edge-label">{self._text(label)}</text>'
                "</g>"
            )

        node_markup = []
        for node in sorted(nodes, key=self._topology_node_sort_key):
            node_id = str(node.get("node_id"))
            box = boxes.get(node_id)
            if box is None or node_id in boundary_node_ids:
                continue
            x, y, node_width, node_height = box
            supporting = node.get("kind") != "representative"
            css_class = " topology-node--supporting" if supporting else ""
            lines = self._topology_node_lines(node, options)
            icon = self._topology_icon(
                node,
                x=x + 14,
                y=y + 9,
                size=30,
                css_class="topology-node-icon",
            )
            title_x = x + (52 if icon else 14)
            title = (
                f"source={node.get('source') or '-'} · "
                f"confidence={node.get('confidence') or '-'} · "
                f"resolution={node.get('resolution') or '-'}"
            )
            texts = [
                f'<text x="{title_x:.1f}" y="{y + 27:.1f}" '
                'class="topology-node-title">'
                f"{self._text(node.get('category_label') or node.get('category'))}"
                "</text>"
            ]
            for index, line in enumerate(lines[:8]):
                texts.append(
                    f'<text x="{x + 14:.1f}" y="{y + 46 + index * 18:.1f}" '
                    f'class="topology-node-detail">{self._text(line)}</text>'
                )
            node_markup.append(
                f'<g class="topology-node{css_class}">'
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{node_width}" '
                f'height="{node_height}" rx="12"><title>'
                f"{self._text(title)}</title></rect>"
                + icon
                + "".join(texts)
                + "</g>"
            )

        return (
            f'<svg class="topology-svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" '
            'role="img" aria-label="명시적으로 확인된 클라우드 자원 구성도">'
            '<defs><marker id="topology-arrow" markerWidth="8" markerHeight="8" '
            'refX="7" refY="4" orient="auto" markerUnits="strokeWidth">'
            '<path d="M 0 0 L 8 4 L 0 8 z" /></marker>'
            + self._topology_icon_definitions(nodes)
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
        categories = []
        for node in nodes:
            category = str(node.get("category") or "")
            if category not in categories:
                categories.append(category)
            layers[categories.index(category)].append(node)

        ordered_layers = sorted(layers)
        node_width = self.TOPOLOGY_NODE_WIDTH
        node_height = self.TOPOLOGY_NODE_HEIGHT
        horizontal_gap = 82
        vertical_gap = 32
        margin = 30
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
        subnet_children: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        direct_vpc_children: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        assigned_ids: set[str] = set()
        consumed_edges: set[tuple[str, str, str]] = set()

        for subnet_id, vpc_id in subnet_to_vpc.items():
            edge = contains_edges.get((vpc_id, subnet_id))
            if edge is not None:
                consumed_edges.add(self._topology_edge_key(edge))

        candidates = sorted(
            (
                node for node_id, node in node_by_id.items()
                if node_id not in vpc_ids and node_id not in subnet_ids
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
        inner_gap = 22
        boundary_padding = 22
        outer_gap = 34
        margin = 30

        def grid_layout(
            items: List[Dict[str, Any]],
            *,
            max_columns: int,
        ) -> tuple[int, int, Dict[str, tuple[float, float, float, float]]]:
            if not items:
                return 0, 0, {}
            columns = min(max_columns, max(1, math.ceil(math.sqrt(len(items)))))
            rows = math.ceil(len(items) / columns)
            grid_width = columns * node_width + (columns - 1) * inner_gap
            grid_height = rows * node_height + (rows - 1) * inner_gap
            local_boxes = {}
            ordered_items = sorted(items, key=self._topology_node_sort_key)
            for index, item in enumerate(ordered_items):
                local_boxes[str(item.get("node_id"))] = (
                    (index % columns) * (node_width + inner_gap),
                    (index // columns) * (node_height + inner_gap),
                    node_width,
                    node_height,
                )
            return grid_width, grid_height, local_boxes

        def subnet_group(subnet_id: str) -> Dict[str, Any]:
            subnet = node_by_id[subnet_id]
            header_height = self._topology_boundary_header_height(
                subnet,
                options,
            )
            grid_width, grid_height, child_boxes = grid_layout(
                subnet_children.get(subnet_id, []),
                max_columns=2,
            )
            width = max(280, grid_width + boundary_padding * 2)
            height = header_height + boundary_padding
            if child_boxes:
                height += grid_height + boundary_padding
            translated = {
                node_id: (
                    box[0] + boundary_padding,
                    box[1] + header_height + boundary_padding,
                    box[2],
                    box[3],
                )
                for node_id, box in child_boxes.items()
            }
            return {
                "node": subnet,
                "width": width,
                "height": height,
                "child_boxes": translated,
            }

        subnet_groups = {
            subnet_id: subnet_group(subnet_id)
            for subnet_id in subnet_ids
        }

        def vpc_group(vpc_id: str) -> Dict[str, Any]:
            vpc = node_by_id[vpc_id]
            header_height = self._topology_boundary_header_height(vpc, options)
            child_subnet_ids = sorted(
                (
                    subnet_id for subnet_id, parent_id in subnet_to_vpc.items()
                    if parent_id == vpc_id
                ),
                key=lambda node_id: self._topology_node_sort_key(
                    node_by_id[node_id]
                ),
            )
            subnet_placements = {}
            content_width = 0
            content_height = 0
            rows = [
                child_subnet_ids[index:index + 2]
                for index in range(0, len(child_subnet_ids), 2)
            ]
            current_y = header_height + boundary_padding
            for row in rows:
                current_x = boundary_padding
                row_height = max(subnet_groups[node_id]["height"] for node_id in row)
                for subnet_id in row:
                    group = subnet_groups[subnet_id]
                    subnet_placements[subnet_id] = (current_x, current_y)
                    current_x += group["width"] + inner_gap
                row_width = current_x - inner_gap + boundary_padding
                content_width = max(content_width, row_width)
                current_y += row_height + inner_gap
                content_height = current_y

            direct_items = direct_vpc_children.get(vpc_id, [])
            direct_width, direct_height, direct_boxes = grid_layout(
                direct_items,
                max_columns=3,
            )
            direct_offset_y = current_y
            if direct_boxes:
                if rows:
                    direct_offset_y += 14
                direct_offset_y += 24
                content_width = max(
                    content_width,
                    direct_width + boundary_padding * 2,
                )
                content_height = direct_offset_y + direct_height + boundary_padding
            elif rows:
                content_height = current_y - inner_gap + boundary_padding
            else:
                content_height = header_height + boundary_padding * 2

            width = max(330, content_width)
            boxes = {
                node_id: (
                    box[0] + boundary_padding,
                    box[1] + direct_offset_y,
                    box[2],
                    box[3],
                )
                for node_id, box in direct_boxes.items()
            }
            return {
                "node": vpc,
                "width": width,
                "height": content_height,
                "subnet_placements": subnet_placements,
                "child_boxes": boxes,
            }

        vpc_groups = {vpc_id: vpc_group(vpc_id) for vpc_id in vpc_ids}
        boxes: Dict[str, tuple[float, float, float, float]] = {}
        boundaries: List[Dict[str, Any]] = []
        cursor_y = margin
        max_width = 0

        def place_subnet(subnet_id: str, x: float, y: float) -> None:
            group = subnet_groups[subnet_id]
            box = (x, y, group["width"], group["height"])
            boxes[subnet_id] = box
            boundaries.append({
                "node_id": subnet_id,
                "node": group["node"],
                "box": box,
                "level": 1,
            })
            for child_id, child_box in group["child_boxes"].items():
                boxes[child_id] = (
                    child_box[0] + x,
                    child_box[1] + y,
                    child_box[2],
                    child_box[3],
                )

        for vpc_id in sorted(
            vpc_ids,
            key=lambda node_id: self._topology_node_sort_key(node_by_id[node_id]),
        ):
            group = vpc_groups[vpc_id]
            x = margin
            y = cursor_y
            vpc_box = (x, y, group["width"], group["height"])
            boxes[vpc_id] = vpc_box
            boundaries.append({
                "node_id": vpc_id,
                "node": group["node"],
                "box": vpc_box,
                "level": 0,
            })
            for subnet_id, position in group["subnet_placements"].items():
                place_subnet(subnet_id, x + position[0], y + position[1])
            for child_id, child_box in group["child_boxes"].items():
                boxes[child_id] = (
                    child_box[0] + x,
                    child_box[1] + y,
                    child_box[2],
                    child_box[3],
                )
            cursor_y += group["height"] + outer_gap
            max_width = max(max_width, group["width"])

        orphan_subnet_ids = sorted(
            subnet_ids - set(subnet_to_vpc),
            key=lambda node_id: self._topology_node_sort_key(node_by_id[node_id]),
        )
        for subnet_id in orphan_subnet_ids:
            group = subnet_groups[subnet_id]
            place_subnet(subnet_id, margin, cursor_y)
            cursor_y += group["height"] + outer_gap
            max_width = max(max_width, group["width"])

        external_nodes = [
            node for node_id, node in node_by_id.items()
            if (
                node_id not in vpc_ids
                and node_id not in subnet_ids
                and node_id not in assigned_ids
            )
        ]
        if external_nodes:
            layers = defaultdict(list)
            for node in external_nodes:
                category = str(node.get("category") or "")
                layers[self.TOPOLOGY_LAYER_ORDER.get(category, 2)].append(node)
            for column, layer in enumerate(sorted(layers)):
                layer_nodes = sorted(
                    layers[layer],
                    key=self._topology_node_sort_key,
                )
                for row, node in enumerate(layer_nodes):
                    boxes[str(node.get("node_id"))] = (
                        margin + column * (node_width + 82),
                        cursor_y + row * (node_height + 32),
                        node_width,
                        node_height,
                    )
            external_width = (
                len(layers) * node_width + max(0, len(layers) - 1) * 82
            )
            external_rows = max((len(value) for value in layers.values()), default=1)
            external_height = (
                external_rows * node_height + max(0, external_rows - 1) * 32
            )
            max_width = max(max_width, external_width)
            cursor_y += external_height + outer_gap

        boundaries.sort(key=lambda boundary: boundary["level"])
        width = max(320, int(math.ceil(max_width + margin * 2)))
        height = max(220, int(math.ceil(cursor_y - outer_gap + margin)))
        return {
            "boxes": boxes,
            "boundaries": boundaries,
            "consumed_edges": consumed_edges,
        }, width, height

    def _topology_boundary_header_height(
        self,
        node: Mapping[str, Any],
        options: TopologyDisplayOptions,
    ) -> int:
        line_count = min(8, len(self._topology_node_lines(node, options)))
        return max(62, 47 + line_count * 17)

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
            bend = max(34, abs(end_x - start_x) / 2)
            direction = 1 if end_x >= start_x else -1
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"C {start_x + direction * bend:.1f} {start_y:.1f}, "
                f"{end_x - direction * bend:.1f} {end_y:.1f}, "
                f"{end_x:.1f} {end_y:.1f}"
            )
        else:
            if delta_y >= 0:
                start_x, start_y = source_center_x, sy + sh
                end_x, end_y = target_center_x, ty
            else:
                start_x, start_y = source_center_x, sy
                end_x, end_y = target_center_x, ty + th
            bend = max(34, abs(end_y - start_y) / 2)
            direction = 1 if end_y >= start_y else -1
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"C {start_x:.1f} {start_y + direction * bend:.1f}, "
                f"{end_x:.1f} {end_y - direction * bend:.1f}, "
                f"{end_x:.1f} {end_y:.1f}"
            )
        return path, (start_x + end_x) / 2, (start_y + end_y) / 2 - 5

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
        if options.show_private_ip and node.get("private_ips"):
            lines.append(
                "Private IP "
                + self._topology_value_list(node.get("private_ips"))
            )
        if options.show_public_ip and node.get("public_ips"):
            lines.append(
                "Public IP "
                + self._topology_value_list(node.get("public_ips"))
            )
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
