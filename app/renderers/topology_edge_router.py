from __future__ import annotations

import heapq
import math
from typing import Any, Dict, List, Mapping, Sequence


class OrthogonalEdgeRouter:
    """구성도 관계선을 장애물 밖의 결정적 직교 경로로 변환한다."""

    EDGE_CLEARANCE = 10.0
    EDGE_PORT_OFFSET = 12.0
    EDGE_BEND_PENALTY = 28.0

    def route(
        self,
        *,
        source_id: str,
        target_id: str,
        boxes: Mapping[str, tuple[float, float, float, float]],
        boundaries: Sequence[Mapping[str, Any]],
        width: float,
        height: float,
        used_segments: Sequence[
            tuple[tuple[float, float], tuple[float, float]]
        ] = (),
    ) -> tuple[str, float | None, float | None, List[tuple[float, float]]]:
        """다른 경계와 자원 영역을 침범하지 않는 직교 경로를 계산한다.

        source/target이 속한 경계 내부는 이동할 수 있지만 경계의 제목 영역은
        장애물로 유지한다. 그 외 Subnet/Zone/VPC는 전체를 장애물로 보므로
        관계선이 무관한 네트워크 영역 위를 가로지르지 않는다.
        """

        source = boxes.get(source_id)
        target = boxes.get(target_id)
        if source is None or target is None:
            return "", None, None, []

        obstacles = self._topology_edge_obstacles(
            source_id=source_id,
            target_id=target_id,
            boxes=boxes,
            boundaries=boundaries,
        )
        source_ports = self._topology_edge_ports(source, target)
        target_ports = self._topology_edge_ports(target, source)
        route = self._topology_manhattan_route(
            source_ports=source_ports,
            target_ports=target_ports,
            obstacles=obstacles,
            width=width,
            height=height,
            used_segments=used_segments,
        )
        if route:
            points = self._topology_collapse_path(route)
            path = self._topology_path_data(points)
            label_x, label_y = self._topology_edge_label_position(points)
            return path, label_x, label_y, points

        return "", None, None, []

    def _topology_edge_obstacles(
        self,
        *,
        source_id: str,
        target_id: str,
        boxes: Mapping[str, tuple[float, float, float, float]],
        boundaries: Sequence[Mapping[str, Any]],
    ) -> List[tuple[float, float, float, float]]:
        clearance = self.EDGE_CLEARANCE
        endpoint_ids = {source_id, target_id}
        boundary_ids = {
            str(boundary.get("node_id") or "") for boundary in boundaries
        }
        endpoint_centers = [
            self._topology_box_center(boxes[node_id])
            for node_id in endpoint_ids
            if node_id in boxes
        ]
        obstacles: List[tuple[float, float, float, float]] = []

        for node_id, box in boxes.items():
            if node_id in endpoint_ids or node_id in boundary_ids:
                continue
            obstacles.append(self.inflate_box(box, clearance))

        for boundary in boundaries:
            boundary_id = str(boundary.get("node_id") or "")
            box = boundary.get("box")
            if not isinstance(box, tuple) or len(box) != 4:
                continue
            is_endpoint_boundary = boundary_id in endpoint_ids
            contains_endpoint = any(
                self._topology_point_in_box(point, box)
                for point in endpoint_centers
            )
            if not is_endpoint_boundary and not contains_endpoint:
                obstacles.append(self.inflate_box(box, clearance))
                continue
            if is_endpoint_boundary:
                continue
            header_height = float(boundary.get("header_height") or 0)
            x, y, boundary_width, _ = box
            obstacles.append((
                x - clearance,
                y - clearance,
                x + boundary_width + clearance,
                y + header_height + clearance,
            ))

        valid_obstacles = []
        for left, top, right, bottom in obstacles:
            if left < right and top < bottom:
                valid_obstacles.append((left, top, right, bottom))

        # 큰 경계 장애물 안에 완전히 포함된 자원 장애물은 탐색 좌표만
        # 늘리므로 제거한다. 정렬과 중복 제거로 입력 순서와 무관하게 만든다.
        compact: List[tuple[float, float, float, float]] = []
        for candidate in sorted(
            set(valid_obstacles),
            key=lambda value: (
                -((value[2] - value[0]) * (value[3] - value[1])),
                value,
            ),
        ):
            if any(self._topology_rect_contains(item, candidate) for item in compact):
                continue
            compact.append(candidate)
        return sorted(compact)

    def _topology_edge_ports(
        self,
        box: tuple[float, float, float, float],
        other: tuple[float, float, float, float],
    ) -> List[tuple[tuple[float, float], tuple[float, float]]]:
        x, y, box_width, box_height = box
        center_x, center_y = self._topology_box_center(box)
        other_x, other_y = self._topology_box_center(other)
        offset = self.EDGE_PORT_OFFSET
        ports = {
            "left": ((x, center_y), (x - offset, center_y)),
            "right": (
                (x + box_width, center_y),
                (x + box_width + offset, center_y),
            ),
            "top": ((center_x, y), (center_x, y - offset)),
            "bottom": (
                (center_x, y + box_height),
                (center_x, y + box_height + offset),
            ),
        }
        horizontal_toward = "right" if other_x >= center_x else "left"
        horizontal_away = "left" if horizontal_toward == "right" else "right"
        vertical_toward = "bottom" if other_y >= center_y else "top"
        vertical_away = "top" if vertical_toward == "bottom" else "bottom"
        if abs(other_x - center_x) >= abs(other_y - center_y):
            order = (
                horizontal_toward,
                vertical_toward,
                vertical_away,
                horizontal_away,
            )
        else:
            order = (
                vertical_toward,
                horizontal_toward,
                horizontal_away,
                vertical_away,
            )
        return [ports[side] for side in order]

    def _topology_manhattan_route(
        self,
        *,
        source_ports: Sequence[
            tuple[tuple[float, float], tuple[float, float]]
        ],
        target_ports: Sequence[
            tuple[tuple[float, float], tuple[float, float]]
        ],
        obstacles: Sequence[tuple[float, float, float, float]],
        width: float,
        height: float,
        used_segments: Sequence[
            tuple[tuple[float, float], tuple[float, float]]
        ],
    ) -> List[tuple[float, float]]:
        margin = 4.0
        valid_sources = [
            (rank, anchor, outside)
            for rank, (anchor, outside) in enumerate(source_ports)
            if (
                margin <= outside[0] <= width - margin
                and margin <= outside[1] <= height - margin
                and not self._topology_point_blocked(outside, obstacles)
                and self.segment_clear(anchor, outside, obstacles)
            )
        ]
        valid_targets = [
            (rank, anchor, outside)
            for rank, (anchor, outside) in enumerate(target_ports)
            if (
                margin <= outside[0] <= width - margin
                and margin <= outside[1] <= height - margin
                and not self._topology_point_blocked(outside, obstacles)
                and self.segment_clear(anchor, outside, obstacles)
            )
        ]
        if not valid_sources or not valid_targets:
            return []

        x_values = {margin, width - margin}
        y_values = {margin, height - margin}
        for _, _, point in valid_sources + valid_targets:
            x_values.add(point[0])
            y_values.add(point[1])
        for left, top, right, bottom in obstacles:
            if margin <= left <= width - margin:
                x_values.add(left)
            if margin <= right <= width - margin:
                x_values.add(right)
            if margin <= top <= height - margin:
                y_values.add(top)
            if margin <= bottom <= height - margin:
                y_values.add(bottom)
        xs = sorted(round(value, 3) for value in x_values)
        ys = sorted(round(value, 3) for value in y_values)
        x_index = {value: index for index, value in enumerate(xs)}
        y_index = {value: index for index, value in enumerate(ys)}

        # 장애물 판정은 탐색 전에 압축 격자 단위로 한 번만 계산한다.
        # 이후 최단 경로 탐색에서 장애물 전체를 반복 순회하지 않는다.
        blocked_points: set[tuple[int, int]] = set()
        blocked_horizontal: set[tuple[int, int]] = set()
        blocked_vertical: set[tuple[int, int]] = set()
        epsilon = 1e-6
        for left, top, right, bottom in obstacles:
            inside_x = [
                index for index, value in enumerate(xs)
                if left + epsilon < value < right - epsilon
            ]
            inside_y = [
                index for index, value in enumerate(ys)
                if top + epsilon < value < bottom - epsilon
            ]
            horizontal_indices = [
                index for index in range(len(xs) - 1)
                if max(xs[index], left) < min(xs[index + 1], right) - epsilon
            ]
            vertical_indices = [
                index for index in range(len(ys) - 1)
                if max(ys[index], top) < min(ys[index + 1], bottom) - epsilon
            ]
            blocked_points.update(
                (ix, iy) for ix in inside_x for iy in inside_y
            )
            blocked_horizontal.update(
                (ix, iy) for ix in horizontal_indices for iy in inside_y
            )
            blocked_vertical.update(
                (ix, iy) for ix in inside_x for iy in vertical_indices
            )

        target_by_grid = {
            (x_index[round(point[0], 3)], y_index[round(point[1], 3)]): (
                rank,
                anchor,
            )
            for rank, anchor, point in valid_targets
        }
        distances: Dict[tuple[int, int, int], float] = {}
        previous: Dict[
            tuple[int, int, int],
            tuple[int, int, int] | None,
        ] = {}
        source_anchor_by_state: Dict[
            tuple[int, int, int],
            tuple[float, float],
        ] = {}
        queue: List[tuple[float, int, int, int]] = []
        for rank, anchor, point in valid_sources:
            state = (
                x_index[round(point[0], 3)],
                y_index[round(point[1], 3)],
                0,
            )
            cost = rank * 4.0
            if cost >= distances.get(state, math.inf):
                continue
            distances[state] = cost
            previous[state] = None
            source_anchor_by_state[state] = anchor
            heapq.heappush(queue, (cost, *state))

        best_state: tuple[int, int, int] | None = None
        best_target_anchor: tuple[float, float] | None = None
        best_cost = math.inf
        while queue:
            cost, ix, iy, direction = heapq.heappop(queue)
            state = (ix, iy, direction)
            if cost != distances.get(state) or cost > best_cost:
                continue
            target = target_by_grid.get((ix, iy))
            if target is not None:
                target_rank, target_anchor = target
                total_cost = cost + target_rank * 4.0
                if total_cost < best_cost:
                    best_cost = total_cost
                    best_state = state
                    best_target_anchor = target_anchor
            for next_ix, next_iy, next_direction in (
                (ix - 1, iy, 1),
                (ix + 1, iy, 1),
                (ix, iy - 1, 2),
                (ix, iy + 1, 2),
            ):
                if not (0 <= next_ix < len(xs) and 0 <= next_iy < len(ys)):
                    continue
                start = (xs[ix], ys[iy])
                end = (xs[next_ix], ys[next_iy])
                segment_blocked = (
                    (min(ix, next_ix), iy) in blocked_horizontal
                    if next_direction == 1
                    else (ix, min(iy, next_iy)) in blocked_vertical
                )
                if (next_ix, next_iy) in blocked_points or segment_blocked:
                    continue
                step_cost = abs(end[0] - start[0]) + abs(end[1] - start[1])
                if direction and direction != next_direction:
                    step_cost += self.EDGE_BEND_PENALTY
                step_cost += self._topology_used_segment_penalty(
                    start,
                    end,
                    used_segments,
                )
                next_state = (next_ix, next_iy, next_direction)
                next_cost = cost + step_cost
                if next_cost >= distances.get(next_state, math.inf):
                    continue
                distances[next_state] = next_cost
                previous[next_state] = state
                source_anchor_by_state[next_state] = source_anchor_by_state[state]
                heapq.heappush(queue, (next_cost, *next_state))

        if best_state is None or best_target_anchor is None:
            return []
        points = []
        state: tuple[int, int, int] | None = best_state
        while state is not None:
            points.append((xs[state[0]], ys[state[1]]))
            state = previous[state]
        points.reverse()
        return [source_anchor_by_state[best_state], *points, best_target_anchor]

    @staticmethod
    def _topology_box_center(
        box: tuple[float, float, float, float],
    ) -> tuple[float, float]:
        return box[0] + box[2] / 2, box[1] + box[3] / 2

    @staticmethod
    def inflate_box(
        box: tuple[float, float, float, float],
        padding: float,
    ) -> tuple[float, float, float, float]:
        return (
            box[0] - padding,
            box[1] - padding,
            box[0] + box[2] + padding,
            box[1] + box[3] + padding,
        )

    @staticmethod
    def _topology_point_in_box(
        point: tuple[float, float],
        box: tuple[float, float, float, float],
    ) -> bool:
        return (
            box[0] <= point[0] <= box[0] + box[2]
            and box[1] <= point[1] <= box[1] + box[3]
        )

    @staticmethod
    def _topology_rect_contains(
        outer: tuple[float, float, float, float],
        inner: tuple[float, float, float, float],
    ) -> bool:
        return (
            outer[0] <= inner[0]
            and outer[1] <= inner[1]
            and outer[2] >= inner[2]
            and outer[3] >= inner[3]
        )

    @staticmethod
    def _topology_point_blocked(
        point: tuple[float, float],
        obstacles: Sequence[tuple[float, float, float, float]],
    ) -> bool:
        epsilon = 1e-6
        return any(
            left + epsilon < point[0] < right - epsilon
            and top + epsilon < point[1] < bottom - epsilon
            for left, top, right, bottom in obstacles
        )

    @staticmethod
    def segment_clear(
        start: tuple[float, float],
        end: tuple[float, float],
        obstacles: Sequence[tuple[float, float, float, float]],
    ) -> bool:
        epsilon = 1e-6
        if abs(start[1] - end[1]) <= epsilon:
            y = start[1]
            segment_left, segment_right = sorted((start[0], end[0]))
            return not any(
                top + epsilon < y < bottom - epsilon
                and max(segment_left, left) < min(segment_right, right) - epsilon
                for left, top, right, bottom in obstacles
            )
        if abs(start[0] - end[0]) <= epsilon:
            x = start[0]
            segment_top, segment_bottom = sorted((start[1], end[1]))
            return not any(
                left + epsilon < x < right - epsilon
                and max(segment_top, top) < min(segment_bottom, bottom) - epsilon
                for left, top, right, bottom in obstacles
            )
        return False

    @staticmethod
    def _topology_used_segment_penalty(
        start: tuple[float, float],
        end: tuple[float, float],
        used_segments: Sequence[
            tuple[tuple[float, float], tuple[float, float]]
        ],
    ) -> float:
        penalty = 0.0
        horizontal = start[1] == end[1]
        for used_start, used_end in used_segments:
            used_horizontal = used_start[1] == used_end[1]
            if horizontal == used_horizontal:
                if horizontal and start[1] == used_start[1]:
                    overlap = min(
                        max(start[0], end[0]),
                        max(used_start[0], used_end[0]),
                    ) - max(
                        min(start[0], end[0]),
                        min(used_start[0], used_end[0]),
                    )
                elif not horizontal and start[0] == used_start[0]:
                    overlap = min(
                        max(start[1], end[1]),
                        max(used_start[1], used_end[1]),
                    ) - max(
                        min(start[1], end[1]),
                        min(used_start[1], used_end[1]),
                    )
                else:
                    overlap = 0.0
                if overlap > 0:
                    penalty += 120.0 + overlap
                continue
            horizontal_segment = (start, end) if horizontal else (used_start, used_end)
            vertical_segment = (used_start, used_end) if horizontal else (start, end)
            horizontal_y = horizontal_segment[0][1]
            vertical_x = vertical_segment[0][0]
            if (
                min(horizontal_segment[0][0], horizontal_segment[1][0]) < vertical_x
                < max(horizontal_segment[0][0], horizontal_segment[1][0])
                and min(vertical_segment[0][1], vertical_segment[1][1]) < horizontal_y
                < max(vertical_segment[0][1], vertical_segment[1][1])
            ):
                penalty += 48.0
        return penalty

    @staticmethod
    def _topology_collapse_path(
        points: Sequence[tuple[float, float]],
    ) -> List[tuple[float, float]]:
        collapsed: List[tuple[float, float]] = []
        for point in points:
            if collapsed and point == collapsed[-1]:
                continue
            if len(collapsed) >= 2:
                first, second = collapsed[-2], collapsed[-1]
                if (
                    first[0] == second[0] == point[0]
                    or first[1] == second[1] == point[1]
                ):
                    collapsed[-1] = point
                    continue
            collapsed.append(point)
        return collapsed

    @staticmethod
    def _topology_path_data(points: Sequence[tuple[float, float]]) -> str:
        if not points:
            return ""
        commands = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
        for previous, point in zip(points, points[1:]):
            if previous[1] == point[1]:
                commands.append(f"H {point[0]:.1f}")
            else:
                commands.append(f"V {point[1]:.1f}")
        return " ".join(commands)

    @staticmethod
    def _topology_edge_label_position(
        points: Sequence[tuple[float, float]],
    ) -> tuple[float | None, float | None]:
        candidates = [
            (abs(end[0] - start[0]), start, end)
            for start, end in zip(points, points[1:])
            if start[1] == end[1] and abs(end[0] - start[0]) >= 48
        ]
        if not candidates:
            return None, None
        _, start, end = max(candidates, key=lambda item: (item[0], item[1], item[2]))
        return (start[0] + end[0]) / 2, start[1] - 5

    @staticmethod
    def path_segments(
        points: Sequence[tuple[float, float]],
    ) -> List[tuple[tuple[float, float], tuple[float, float]]]:
        return list(zip(points, points[1:]))
