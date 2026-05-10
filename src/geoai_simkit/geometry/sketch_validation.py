from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable
import math


def _coords(row: dict[str, Any]) -> tuple[float, float, float]:
    values = list(row.get('coordinates', row.get('xyz', (0.0, 0.0, 0.0))) or (0.0, 0.0, 0.0))[:3]
    while len(values) < 3:
        values.append(0.0)
    return float(values[0]), float(values[1]), float(values[2])


def _signed_area_xy(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        area += x0 * y1 - x1 * y0
    return 0.5 * area


def _segment_intersects(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float], *, eps: float = 1.0e-9) -> bool:
    def orient(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_segment(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> bool:
        return min(p[0], r[0]) - eps <= q[0] <= max(p[0], r[0]) + eps and min(p[1], r[1]) - eps <= q[1] <= max(p[1], r[1]) + eps

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    if abs(o1) <= eps and on_segment(a, c, b):
        return True
    if abs(o2) <= eps and on_segment(a, d, b):
        return True
    if abs(o3) <= eps and on_segment(c, a, d):
        return True
    if abs(o4) <= eps and on_segment(c, b, d):
        return True
    return (o1 * o2 < -eps) and (o3 * o4 < -eps)


@dataclass(slots=True)
class SketchOutlineReport:
    point_names: tuple[str, ...] = ()
    polyline: tuple[tuple[float, float], ...] = ()
    closed: bool = False
    simple: bool = False
    clockwise: bool = False
    area: float = 0.0
    duplicate_point_count: int = 0
    dangling_line_count: int = 0
    self_intersection_count: int = 0
    issues: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'contract': 'pit_outline_sketch_report_v1',
            'point_names': list(self.point_names),
            'polyline': [[float(x), float(y)] for x, y in self.polyline],
            'closed': bool(self.closed),
            'simple': bool(self.simple),
            'clockwise': bool(self.clockwise),
            'area': float(abs(self.area)),
            'signed_area': float(self.area),
            'duplicate_point_count': int(self.duplicate_point_count),
            'dangling_line_count': int(self.dangling_line_count),
            'self_intersection_count': int(self.self_intersection_count),
            'ready_for_pit_modeling': bool(self.closed and self.simple and len(self.polyline) >= 3 and abs(self.area) > 1.0e-9),
            'issues': [dict(row) for row in self.issues],
            'metadata': dict(self.metadata),
        }


class PitOutlineSketchValidator:
    """Validate sketch points/lines as an editable foundation-pit outline.

    This object intentionally works on sketch entities, not mesh cells. The
    returned polyline is used as a modeling feature and later remeshed.
    """

    def validate(self, points: Iterable[dict[str, Any]], lines: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
        point_rows = [dict(row) for row in list(points or []) if isinstance(row, dict)]
        line_rows = [dict(row) for row in list(lines or []) if isinstance(row, dict)]
        lookup = {str(row.get('name') or f'P{idx:02d}'): _coords(row) for idx, row in enumerate(point_rows, start=1)}
        issues: list[dict[str, Any]] = []
        ordered_names: list[str] = []
        if line_rows:
            adjacency: dict[str, list[str]] = {name: [] for name in lookup}
            for row in line_rows:
                a = str(row.get('start_point') or row.get('p0') or '').strip()
                b = str(row.get('end_point') or row.get('p1') or '').strip()
                if a not in lookup or b not in lookup or a == b:
                    issues.append({'id': 'pit_outline.invalid_line', 'severity': 'warning', 'line': row.get('name', ''), 'message': 'Sketch line has missing or duplicate endpoints.'})
                    continue
                adjacency.setdefault(a, []).append(b)
                adjacency.setdefault(b, []).append(a)
            dangling = sum(1 for name, nbrs in adjacency.items() if nbrs and len(nbrs) != 2)
            used = [name for name, nbrs in adjacency.items() if nbrs]
            if used:
                start = used[0]
                prev = ''
                current = start
                seen: set[str] = set()
                for _ in range(len(used) + 2):
                    ordered_names.append(current)
                    seen.add(current)
                    nbrs = [n for n in adjacency.get(current, []) if n != prev]
                    if not nbrs:
                        break
                    nxt = nbrs[0]
                    if nxt == start:
                        break
                    prev, current = current, nxt
                    if current in seen:
                        break
            else:
                dangling = 0
            dangling_count = dangling
        else:
            ordered_names = [str(row.get('name') or f'P{idx:02d}') for idx, row in enumerate(point_rows, start=1)]
            dangling_count = 0
        polyline = [(lookup[name][0], lookup[name][1]) for name in ordered_names if name in lookup]
        duplicate_count = max(0, len(polyline) - len({(round(x, 9), round(y, 9)) for x, y in polyline}))
        area = _signed_area_xy(polyline)
        self_intersections = 0
        n = len(polyline)
        if n >= 4:
            for i in range(n):
                a = polyline[i]
                b = polyline[(i + 1) % n]
                for j in range(i + 1, n):
                    if abs(i - j) <= 1 or {i, j} == {0, n - 1}:
                        continue
                    c = polyline[j]
                    d = polyline[(j + 1) % n]
                    if _segment_intersects(a, b, c, d):
                        self_intersections += 1
        closed = len(polyline) >= 3 and dangling_count == 0
        simple = self_intersections == 0 and duplicate_count == 0
        if len(polyline) < 3:
            issues.append({'id': 'pit_outline.too_few_points', 'severity': 'warning', 'message': 'At least three outline points are required.'})
        if dangling_count:
            issues.append({'id': 'pit_outline.dangling_lines', 'severity': 'warning', 'count': dangling_count, 'message': 'The outline has dangling or branching sketch lines.'})
        if duplicate_count:
            issues.append({'id': 'pit_outline.duplicate_points', 'severity': 'warning', 'count': duplicate_count, 'message': 'Duplicate XY points were detected in the outline.'})
        if self_intersections:
            issues.append({'id': 'pit_outline.self_intersection', 'severity': 'error', 'count': self_intersections, 'message': 'The outline self-intersects and cannot be used as a pit boundary.'})
        if abs(area) <= 1.0e-9 and len(polyline) >= 3:
            issues.append({'id': 'pit_outline.zero_area', 'severity': 'error', 'message': 'The outline area is zero or numerically tiny.'})
        return SketchOutlineReport(
            point_names=tuple(ordered_names),
            polyline=tuple(polyline),
            closed=bool(closed),
            simple=bool(simple),
            clockwise=bool(area < 0.0),
            area=float(area),
            duplicate_point_count=int(duplicate_count),
            dangling_line_count=int(dangling_count),
            self_intersection_count=int(self_intersections),
            issues=tuple(issues),
            metadata={'line_count': len(line_rows), 'point_count': len(point_rows), 'uses_lines': bool(line_rows)},
        ).to_dict()


__all__ = ['PitOutlineSketchValidator', 'SketchOutlineReport']
