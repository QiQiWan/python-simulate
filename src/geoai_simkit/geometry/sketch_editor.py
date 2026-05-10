from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence
import math


def _xy_from_point(row: dict[str, Any]) -> tuple[float, float, float]:
    coords = list(row.get('coordinates', row.get('xyz', (0.0, 0.0, 0.0))) or (0.0, 0.0, 0.0))[:3]
    while len(coords) < 3:
        coords.append(0.0)
    return float(coords[0]), float(coords[1]), float(coords[2])


def _distance_xy(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


@dataclass(slots=True)
class SketchEditResult:
    points: tuple[dict[str, Any], ...] = ()
    lines: tuple[dict[str, Any], ...] = ()
    operations: tuple[dict[str, Any], ...] = ()
    issues: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'contract': 'sketch_edit_result_v1',
            'points': [dict(row) for row in self.points],
            'lines': [dict(row) for row in self.lines],
            'operations': [dict(row) for row in self.operations],
            'issues': [dict(row) for row in self.issues],
            'summary': {
                'point_count': len(self.points),
                'line_count': len(self.lines),
                'operation_count': len(self.operations),
                'issue_count': len(self.issues),
            },
            'metadata': dict(self.metadata),
        }


class PitSketchEditor:
    """Edit sketch entities that define a pit outline.

    The output is still sketch/entity data. It never edits mesh cells; the mesh is
    generated later from the updated entity workflow.
    """

    def ordered_outline_from_points(self, points: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = [dict(row) for row in list(points or []) if isinstance(row, dict)]
        # Keep user order first. If indexes are present, sort by them for stable GUI behaviour.
        rows.sort(key=lambda r: int(r.get('index', 10**9) or 10**9))
        return rows

    def build_closed_polyline_lines(
        self,
        points: Iterable[dict[str, Any]],
        *,
        role: str = 'pit_outline_edge',
        close: bool = True,
    ) -> dict[str, Any]:
        rows = self.ordered_outline_from_points(points)
        issues: list[dict[str, Any]] = []
        operations: list[dict[str, Any]] = []
        if len(rows) < 3:
            issues.append({'id': 'sketch.close.too_few_points', 'severity': 'warning', 'message': 'At least three points are required to close a pit outline.'})
            return SketchEditResult(tuple(rows), (), tuple(operations), tuple(issues)).to_dict()
        names = [str(row.get('name') or f'P{idx:02d}') for idx, row in enumerate(rows, start=1)]
        lines: list[dict[str, Any]] = []
        edge_count = len(names) if close else max(0, len(names) - 1)
        for idx in range(edge_count):
            a = names[idx]
            b = names[(idx + 1) % len(names)]
            if a == b:
                issues.append({'id': 'sketch.close.duplicate_endpoint', 'severity': 'warning', 'point': a, 'message': 'Skipped a zero-length sketch edge.'})
                continue
            lines.append({
                'name': f'pit_outline_edge_{idx + 1:02d}',
                'start_point': a,
                'end_point': b,
                'role': role,
                'metadata': {'source': 'PitSketchEditor', 'closed_polyline': bool(close)},
            })
        operations.append({'id': 'sketch.close_outline', 'line_count': len(lines), 'closed': bool(close)})
        return SketchEditResult(tuple(rows), tuple(lines), tuple(operations), tuple(issues), {'edit_policy': 'edit_sketch_then_remesh'}).to_dict()

    def snap_duplicate_points(
        self,
        points: Iterable[dict[str, Any]],
        *,
        tolerance: float = 1.0e-6,
    ) -> dict[str, Any]:
        rows = [dict(row) for row in list(points or []) if isinstance(row, dict)]
        tol = max(0.0, float(tolerance or 0.0))
        operations: list[dict[str, Any]] = []
        for i, row in enumerate(rows):
            xi, yi, zi = _xy_from_point(row)
            for j in range(i):
                xj, yj, zj = _xy_from_point(rows[j])
                if _distance_xy((xi, yi), (xj, yj)) <= tol:
                    row['coordinates'] = [float(xj), float(yj), float(zi if abs(zi) > 0.0 else zj)]
                    row.setdefault('metadata', {})['snapped_to'] = str(rows[j].get('name') or f'P{j + 1:02d}')
                    operations.append({'id': 'sketch.snap_duplicate_point', 'point': row.get('name'), 'target': rows[j].get('name'), 'tolerance': tol})
                    break
        return SketchEditResult(tuple(rows), (), tuple(operations), (), {'tolerance': tol}).to_dict()


    def snap_points_to_grid(
        self,
        points: Iterable[dict[str, Any]],
        *,
        grid_size: float = 0.5,
    ) -> dict[str, Any]:
        """Snap sketch points to an engineering grid in XY.

        This edits only the sketch/entity layer. The generated mesh must be
        regenerated from the updated entities before solving.
        """
        rows = [dict(row) for row in list(points or []) if isinstance(row, dict)]
        h = max(1.0e-9, float(grid_size or 0.5))
        operations: list[dict[str, Any]] = []
        for row in rows:
            x, y, z = _xy_from_point(row)
            sx = round(x / h) * h
            sy = round(y / h) * h
            if abs(sx - x) > 1.0e-12 or abs(sy - y) > 1.0e-12:
                row['coordinates'] = [float(sx), float(sy), float(z)]
                row.setdefault('metadata', {})['snap_grid_size'] = h
                operations.append({'id': 'sketch.snap_to_grid', 'point': row.get('name'), 'from': [x, y, z], 'to': [sx, sy, z], 'grid_size': h})
        return SketchEditResult(tuple(rows), (), tuple(operations), (), {'grid_size': h, 'edit_policy': 'edit_sketch_then_remesh'}).to_dict()

    def apply_orthogonal_constraints(
        self,
        points: Iterable[dict[str, Any]],
        *,
        prefer_axis: str = 'nearest',
    ) -> dict[str, Any]:
        """Make consecutive sketch edges axis-aligned in XY.

        The method is intentionally conservative: it keeps the first point of
        each edge fixed and moves the next point either horizontally or
        vertically depending on the larger component of the original segment.
        """
        rows = self.ordered_outline_from_points(points)
        if len(rows) < 2:
            return SketchEditResult(tuple(rows), (), (), ({'id': 'sketch.orthogonal.too_few_points', 'severity': 'warning', 'message': 'At least two points are required.'},)).to_dict()
        out = [dict(row) for row in rows]
        operations: list[dict[str, Any]] = []
        for idx in range(1, len(out)):
            ax, ay, _ = _xy_from_point(out[idx - 1])
            bx, by, bz = _xy_from_point(out[idx])
            dx = abs(bx - ax)
            dy = abs(by - ay)
            axis = 'x' if dx >= dy else 'y'
            if prefer_axis in {'x', 'y'}:
                axis = prefer_axis
            newx, newy = (bx, ay) if axis == 'x' else (ax, by)
            if abs(newx - bx) > 1.0e-12 or abs(newy - by) > 1.0e-12:
                out[idx]['coordinates'] = [float(newx), float(newy), float(bz)]
                out[idx].setdefault('metadata', {})['orthogonalized_from'] = [float(bx), float(by), float(bz)]
                operations.append({'id': 'sketch.orthogonalize_edge', 'point': out[idx].get('name'), 'edge_index': idx, 'axis': axis, 'from': [bx, by, bz], 'to': [newx, newy, bz]})
        return SketchEditResult(tuple(out), (), tuple(operations), (), {'prefer_axis': prefer_axis, 'edit_policy': 'edit_sketch_then_remesh'}).to_dict()

    def offset_closed_polyline(
        self,
        points: Iterable[dict[str, Any]],
        *,
        offset: float,
        name_prefix: str = 'wall_offset',
        role: str = 'retaining_wall_alignment',
    ) -> dict[str, Any]:
        """Create a simple mitered offset of a closed pit outline in XY.

        Positive offset follows the left-hand normal of the ordered polygon;
        callers can request both +t/2 and -t/2 to obtain wall outer/inner lines.
        """
        rows = self.ordered_outline_from_points(points)
        issues: list[dict[str, Any]] = []
        if len(rows) < 3:
            issues.append({'id': 'sketch.offset.too_few_points', 'severity': 'warning', 'message': 'At least three points are required to offset a closed outline.'})
            return SketchEditResult(tuple(rows), (), (), tuple(issues)).to_dict()
        xy = [_xy_from_point(row) for row in rows]
        d = float(offset or 0.0)
        shifted: list[dict[str, Any]] = []
        n = len(xy)
        for i, row in enumerate(rows):
            p_prev = xy[(i - 1) % n]
            p = xy[i]
            p_next = xy[(i + 1) % n]
            v1 = (p[0] - p_prev[0], p[1] - p_prev[1])
            v2 = (p_next[0] - p[0], p_next[1] - p[1])
            def unit_normal(v):
                length = max(1.0e-12, math.hypot(v[0], v[1]))
                return (-v[1] / length, v[0] / length)
            n1 = unit_normal(v1)
            n2 = unit_normal(v2)
            nx = n1[0] + n2[0]
            ny = n1[1] + n2[1]
            ln = math.hypot(nx, ny)
            if ln <= 1.0e-12:
                nx, ny = n2
                ln = 1.0
            # Clamp the miter to avoid explosive corners in rough sketches.
            miter = min(4.0, 1.0 / max(0.25, ln / 2.0))
            qx = p[0] + d * (nx / ln) * miter
            qy = p[1] + d * (ny / ln) * miter
            shifted.append({
                'name': f'{name_prefix}_P{i + 1:02d}',
                'coordinates': [float(qx), float(qy), float(p[2])],
                'role': role,
                'metadata': {'source': 'PitSketchEditor.offset_closed_polyline', 'offset': d, 'source_point': row.get('name')},
            })
        lines = self.build_closed_polyline_lines(shifted, role=role, close=True).get('lines', [])
        return SketchEditResult(tuple(shifted), tuple(dict(line) for line in lines), ({'id': 'sketch.offset_closed_polyline', 'offset': d, 'point_count': len(shifted)},), tuple(issues), {'offset': d, 'edit_policy': 'edit_sketch_then_remesh'}).to_dict()

__all__ = ['PitSketchEditor', 'SketchEditResult']
