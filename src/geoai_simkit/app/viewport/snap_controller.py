from __future__ import annotations

"""Qt-free snapping helpers for interactive viewport modeling.

The controller provides deterministic grid, endpoint/midpoint, engineering
semantic snapping and lightweight constraint projection for both the PyVista
workbench and headless tests.  It deliberately works with ViewportState rather
than GUI objects so that the interaction contract can be tested without a
running Qt event loop.
"""

from dataclasses import dataclass, field
from math import sqrt
from typing import Any, Iterable, NamedTuple

from geoai_simkit.app.viewport.viewport_state import ViewportState

Vector3 = tuple[float, float, float]


def _dist(a: Vector3, b: Vector3) -> float:
    return sqrt((float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2 + (float(a[2]) - float(b[2])) ** 2)


def _round_to_grid(value: float, spacing: float) -> float:
    if spacing <= 0.0:
        return float(value)
    return float(round(float(value) / spacing) * spacing)


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return (float(a[0]) - float(b[0]), float(a[1]) - float(b[1]), float(a[2]) - float(b[2]))


def _add(a: Vector3, b: Vector3) -> Vector3:
    return (float(a[0]) + float(b[0]), float(a[1]) + float(b[1]), float(a[2]) + float(b[2]))


def _mul(a: Vector3, s: float) -> Vector3:
    return (float(a[0]) * s, float(a[1]) * s, float(a[2]) * s)


def _dot(a: Vector3, b: Vector3) -> float:
    return float(a[0]) * float(b[0]) + float(a[1]) * float(b[1]) + float(a[2]) * float(b[2])


def _norm(a: Vector3) -> float:
    return sqrt(max(_dot(a, a), 0.0))


def _unit(a: Vector3) -> Vector3:
    n = _norm(a)
    if n <= 1.0e-12:
        return (0.0, 0.0, 0.0)
    return (float(a[0]) / n, float(a[1]) / n, float(a[2]) / n)


def _project_point_to_segment(point: Vector3, a: Vector3, b: Vector3) -> tuple[Vector3, float]:
    ab = _sub(b, a)
    denom = _dot(ab, ab)
    if denom <= 1.0e-12:
        return a, _dist(point, a)
    t = max(0.0, min(1.0, _dot(_sub(point, a), ab) / denom))
    projected = _add(a, _mul(ab, t))
    return projected, _dist(point, projected)


SEMANTIC_LABELS = {
    "endpoint": "端点",
    "midpoint": "中点",
    "grid": "网格",
    "wall_endpoint": "墙端点",
    "beam_endpoint": "梁端点",
    "anchor_endpoint": "锚杆端点",
    "stratum_boundary_intersection": "地层边界交点",
    "excavation_contour_intersection": "开挖轮廓交点",
    "edge_aligned": "沿边",
    "normal_aligned": "沿法向",
    "horizontal_constraint": "水平约束",
    "vertical_constraint": "垂直约束",
}


class SnapCandidate(NamedTuple):
    point: Vector3
    mode: str
    entity_id: str
    metadata: dict[str, Any]


class LineCandidate(NamedTuple):
    start: Vector3
    end: Vector3
    mode: str
    entity_id: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class SnapResult:
    point: Vector3
    snapped: bool = False
    mode: str = "none"
    target_entity_id: str = ""
    distance: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        label = SEMANTIC_LABELS.get(self.mode, str(self.metadata.get("snap_label") or self.mode or ""))
        return {
            "point": [float(v) for v in self.point],
            "snapped": bool(self.snapped),
            "mode": self.mode,
            "snap_label": label,
            "target_entity_id": self.target_entity_id,
            "distance": float(self.distance),
            "metadata": {"contract": "viewport_snap_result_v2", **dict(self.metadata)},
        }




@dataclass(slots=True)
class ConstraintLockState:
    enabled: bool = False
    mode: str = ""
    anchor: Vector3 | None = None
    start: Vector3 | None = None
    end: Vector3 | None = None
    normal: Vector3 | None = None
    target_entity_id: str = ""
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    trail: list[Vector3] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": "viewport_constraint_lock_state_v1",
            "enabled": bool(self.enabled),
            "mode": self.mode,
            "label": self.label or SEMANTIC_LABELS.get(self.mode, self.mode),
            "anchor": None if self.anchor is None else [float(v) for v in self.anchor],
            "start": None if self.start is None else [float(v) for v in self.start],
            "end": None if self.end is None else [float(v) for v in self.end],
            "normal": None if self.normal is None else [float(v) for v in self.normal],
            "target_entity_id": self.target_entity_id,
            "metadata": dict(self.metadata),
            "trail": [[float(v) for v in point] for point in list(self.trail or [])],
            "visualization": {
                "locked_edge_highlight": self.mode == "edge_aligned" and self.start is not None and self.end is not None,
                "locked_normal_arrow": self.mode == "normal_aligned" and self.anchor is not None and self.normal is not None,
                "continuous_placement_trail": bool(self.trail),
            },
        }


@dataclass(slots=True)
class SnapController:
    enabled: bool = True
    grid_enabled: bool = True
    endpoint_enabled: bool = True
    midpoint_enabled: bool = True
    wall_endpoint_enabled: bool = True
    beam_endpoint_enabled: bool = True
    anchor_endpoint_enabled: bool = True
    stratum_intersection_enabled: bool = True
    excavation_intersection_enabled: bool = True
    horizontal_constraint_enabled: bool = True
    vertical_constraint_enabled: bool = True
    along_edge_constraint_enabled: bool = True
    along_normal_constraint_enabled: bool = True
    constraint_lock: ConstraintLockState = field(default_factory=ConstraintLockState)
    spacing: float = 1.0
    tolerance: float = 0.75
    last_unlock_feedback: dict[str, Any] = field(default_factory=dict)

    def _primitive_points(self, primitive: Any) -> list[Vector3]:
        points = getattr(primitive, "metadata", {}).get("points") or []
        parsed: list[Vector3] = []
        for row in points if isinstance(points, list) else []:
            try:
                if len(row) >= 3:
                    parsed.append((float(row[0]), float(row[1]), float(row[2])))
            except Exception:
                continue
        bounds = getattr(primitive, "bounds", None)
        kind = str(getattr(primitive, "kind", "") or "")
        if kind == "point" and bounds is not None:
            x0, _x1, y0, _y1, z0, _z1 = bounds
            parsed.append((float(x0), float(y0), float(z0)))
        if kind in {"curve", "line", "edge", "support", "partition_feature", "contact_pair"} and bounds is not None and len(parsed) < 2:
            x0, x1, y0, y1, z0, z1 = [float(v) for v in bounds]
            spans = [abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)]
            axis = max(range(3), key=lambda i: spans[i])
            cx, cy, cz = ((x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5)
            if axis == 0:
                parsed.extend([(x0, cy, cz), (x1, cy, cz)])
            elif axis == 1:
                parsed.extend([(cx, y0, cz), (cx, y1, cz)])
            else:
                parsed.extend([(cx, cy, z0), (cx, cy, z1)])
        if kind in {"surface", "face"} and bounds is not None and not parsed:
            x0, x1, y0, y1, z0, z1 = [float(v) for v in bounds]
            spans = [abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)]
            axis = min(range(3), key=lambda i: spans[i])
            if axis == 0:
                x = (x0 + x1) * 0.5; parsed.extend([(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)])
            elif axis == 1:
                y = (y0 + y1) * 0.5; parsed.extend([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)])
            else:
                z = (z0 + z1) * 0.5; parsed.extend([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)])
        if kind == "block" and bounds is not None:
            x0, x1, y0, y1, z0, z1 = [float(v) for v in bounds]
            parsed.extend([
                (x0, y0, z0), (x0, y0, z1), (x0, y1, z0), (x0, y1, z1),
                (x1, y0, z0), (x1, y0, z1), (x1, y1, z0), (x1, y1, z1),
            ])
        return list(dict.fromkeys(parsed))

    def _semantic_endpoint_mode(self, primitive: Any) -> str:
        kind = str(getattr(primitive, "kind", "") or "")
        metadata = dict(getattr(primitive, "metadata", {}) or {})
        style = dict(getattr(primitive, "style", {}) or {})
        role = " ".join(str(v).lower() for v in (kind, style.get("role"), metadata.get("semantic_type"), metadata.get("support_type"), metadata.get("type"), metadata.get("family"), metadata.get("name")))
        if "anchor" in role or "锚" in role:
            return "anchor_endpoint"
        if any(token in role for token in ("beam", "strut", "support", "pile", "embedded", "梁", "支撑", "桩")):
            return "beam_endpoint"
        if any(token in role for token in ("wall", "plate", "slab", "diaphragm", "retaining", "墙", "板")):
            return "wall_endpoint"
        return "endpoint"

    def _boundary_intersection_mode(self, primitive: Any) -> str | None:
        metadata = dict(getattr(primitive, "metadata", {}) or {})
        role = " ".join(str(v).lower() for v in (getattr(primitive, "kind", ""), getattr(primitive, "label", ""), metadata.get("type"), metadata.get("semantic_type"), metadata.get("role"), metadata.get("name")))
        if any(token in role for token in ("excavation", "开挖")):
            return "excavation_contour_intersection"
        if any(token in role for token in ("horizontal_layer", "stratum", "layer", "地层", "土层")):
            return "stratum_boundary_intersection"
        return None

    def candidate_points(self, state: ViewportState | None) -> list[SnapCandidate]:
        if state is None:
            return []
        candidates: list[SnapCandidate] = []
        for primitive in state.primitives.values():
            parsed = self._primitive_points(primitive)
            entity_id = str(getattr(primitive, "entity_id", "") or "")
            metadata = dict(getattr(primitive, "metadata", {}) or {})
            boundary_mode = self._boundary_intersection_mode(primitive)
            endpoint_mode = self._semantic_endpoint_mode(primitive)
            endpoint_allowed = self.endpoint_enabled or endpoint_mode != "endpoint"
            if endpoint_mode == "wall_endpoint" and not self.wall_endpoint_enabled:
                endpoint_allowed = False
            if endpoint_mode == "beam_endpoint" and not self.beam_endpoint_enabled:
                endpoint_allowed = False
            if endpoint_mode == "anchor_endpoint" and not self.anchor_endpoint_enabled:
                endpoint_allowed = False
            if boundary_mode == "stratum_boundary_intersection" and not self.stratum_intersection_enabled:
                boundary_mode = None
            if boundary_mode == "excavation_contour_intersection" and not self.excavation_intersection_enabled:
                boundary_mode = None
            if endpoint_allowed:
                for idx, point in enumerate(parsed):
                    mode = boundary_mode or endpoint_mode
                    candidates.append(SnapCandidate(point, mode, entity_id, {"primitive_id": getattr(primitive, "id", ""), "candidate_index": idx, "snap_label": SEMANTIC_LABELS.get(mode, mode), **metadata}))
            if self.midpoint_enabled and len(parsed) >= 2:
                for idx, (a, b) in enumerate(zip(parsed[:-1], parsed[1:])):
                    candidates.append(SnapCandidate(((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5), "midpoint", entity_id, {"primitive_id": getattr(primitive, "id", ""), "segment_index": idx, "snap_label": "中点", **metadata}))
        return candidates

    def line_candidates(self, state: ViewportState | None) -> list[LineCandidate]:
        if state is None:
            return []
        lines: list[LineCandidate] = []
        for primitive in state.primitives.values():
            points = self._primitive_points(primitive)
            if len(points) < 2:
                continue
            metadata = dict(getattr(primitive, "metadata", {}) or {})
            mode = "edge_aligned"
            entity_id = str(getattr(primitive, "entity_id", "") or "")
            for idx, (a, b) in enumerate(zip(points[:-1], points[1:])):
                if _dist(a, b) <= 1.0e-12:
                    continue
                lines.append(LineCandidate(a, b, mode, entity_id, {"primitive_id": getattr(primitive, "id", ""), "segment_index": idx, "snap_label": "沿边", **metadata}))
        return lines

    def unlock_constraint(self) -> ConstraintLockState:
        old = self.constraint_lock.to_dict() if getattr(self.constraint_lock, "enabled", False) else {}
        self.last_unlock_feedback = {
            "contract": "viewport_constraint_unlock_feedback_v1",
            "unlocked": bool(old),
            "previous_lock": old,
            "message": "约束锁定已解除",
        }
        self.constraint_lock = ConstraintLockState()
        return self.constraint_lock

    def last_unlock_feedback_dict(self) -> dict[str, Any]:
        return dict(self.last_unlock_feedback or {})

    def record_constraint_placement(self, point: Vector3, *, kind: str = "", entity_id: str = "") -> dict[str, Any]:
        if not getattr(self.constraint_lock, "enabled", False):
            return {}
        p = tuple(float(v) for v in point)
        trail = list(self.constraint_lock.trail or [])
        if not trail or _dist(trail[-1], p) > 1.0e-9:
            trail.append(p)
        self.constraint_lock.trail = trail[-64:]
        self.constraint_lock.metadata = {
            **dict(self.constraint_lock.metadata or {}),
            "last_placed_kind": str(kind or ""),
            "last_placed_entity_id": str(entity_id or ""),
            "placement_count": len(self.constraint_lock.trail),
        }
        return self.constraint_lock.to_dict()

    def lock_constraint(
        self,
        mode: str,
        *,
        point: Vector3 | None = None,
        anchor: Vector3 | None = None,
        state: ViewportState | None = None,
        normal: Vector3 | None = None,
        target_entity_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ConstraintLockState:
        """Lock a persistent interaction constraint for continuous placement.

        The lock is GUI-free and can be driven by either a toolbar button using
        the current selection or a viewport right-click pick.  Creation tools use
        this state on subsequent mouse moves/clicks until it is explicitly
        cleared.
        """

        raw = str(mode or "").lower().strip()
        if raw in {"edge", "along_edge", "edge_aligned"}:
            raw = "edge_aligned"
        elif raw in {"normal", "along_normal", "normal_aligned"}:
            raw = "normal_aligned"
        elif raw in {"horizontal", "h", "horizontal_constraint"}:
            raw = "horizontal_constraint"
        elif raw in {"vertical", "v", "vertical_constraint"}:
            raw = "vertical_constraint"
        else:
            raw = raw or "none"

        p = tuple(float(v) for v in (point or anchor or (0.0, 0.0, 0.0)))  # type: ignore[arg-type]
        meta = dict(metadata or {})
        label = SEMANTIC_LABELS.get(raw, raw)

        if raw == "edge_aligned":
            best: tuple[float, Vector3, LineCandidate] | None = None
            for line in self.line_candidates(state):
                if target_entity_id and line.entity_id and str(line.entity_id) != str(target_entity_id):
                    continue
                projected, distance = _project_point_to_segment(p, line.start, line.end)
                if best is None or distance < best[0]:
                    best = (distance, projected, line)
            if best is not None:
                _distance, projected, line = best
                self.constraint_lock = ConstraintLockState(True, raw, projected, line.start, line.end, None, line.entity_id, label, {**dict(line.metadata), **meta, "lock_source": "line_candidate"}, [])
                return self.constraint_lock
            # Toolbar actions can be invoked before a valid line candidate exists.
            self.constraint_lock = ConstraintLockState(True, raw, p, p, (p[0] + 1.0, p[1], p[2]), None, target_entity_id, label, {**meta, "lock_source": "fallback_x_axis"}, [])
            return self.constraint_lock

        if raw == "normal_aligned":
            direction = _unit(tuple(float(v) for v in (normal or (0.0, 0.0, 1.0))))
            if _norm(direction) <= 1.0e-12:
                direction = (0.0, 0.0, 1.0)
            self.constraint_lock = ConstraintLockState(True, raw, p, None, None, direction, target_entity_id, label, {**meta, "lock_source": "normal"}, [])
            return self.constraint_lock

        if raw in {"horizontal_constraint", "vertical_constraint"}:
            self.constraint_lock = ConstraintLockState(True, raw, p, None, None, None, target_entity_id, label, {**meta, "lock_source": "axis_constraint"}, [])
            return self.constraint_lock

        self.constraint_lock = ConstraintLockState()
        return self.constraint_lock

    def constraint_lock_dict(self) -> dict[str, Any]:
        return self.constraint_lock.to_dict()

    def snap(self, point: Vector3, state: ViewportState | None = None, *, modifiers: Iterable[str] = ()) -> SnapResult:
        world = (float(point[0]), float(point[1]), float(point[2]))
        modset = {str(item).lower() for item in modifiers}
        if not self.enabled or "alt" in modset:
            return SnapResult(world, snapped=False, mode="disabled")
        best: tuple[float, SnapCandidate] | None = None
        for candidate in self.candidate_points(state):
            d = _dist(world, candidate.point)
            if d <= self.tolerance and (best is None or d < best[0]):
                best = (d, candidate)
        if best is not None:
            distance, candidate = best
            return SnapResult(candidate.point, snapped=True, mode=candidate.mode, target_entity_id=candidate.entity_id, distance=distance, metadata=dict(candidate.metadata))
        if self.grid_enabled and self.spacing > 0:
            snapped = (_round_to_grid(world[0], self.spacing), _round_to_grid(world[1], self.spacing), _round_to_grid(world[2], self.spacing))
            return SnapResult(snapped, snapped=snapped != world, mode="grid", distance=_dist(world, snapped), metadata={"spacing": self.spacing, "snap_label": "网格"})
        return SnapResult(world, snapped=False, mode="none")

    def constrain(self, point: Vector3, *, anchor: Vector3 | None = None, state: ViewportState | None = None, normal: Vector3 | None = None, requested: str = "", modifiers: Iterable[str] = ()) -> SnapResult:
        """Project ``point`` onto an interaction constraint.

        Requested mode wins.  Without an explicit request, an active constraint
        lock wins.  Without a lock, Shift applies a horizontal constraint and
        Ctrl applies a vertical constraint.  The method is intentionally
        deterministic and GUI-free so tests can verify the contract without a
        running interactor.
        """

        world = (float(point[0]), float(point[1]), float(point[2]))
        lock = self.constraint_lock if getattr(self.constraint_lock, "enabled", False) else None
        base_source = anchor or (lock.anchor if lock is not None else None)
        if base_source is None:
            return SnapResult(world, snapped=False, mode="none")
        base = (float(base_source[0]), float(base_source[1]), float(base_source[2]))
        modset = {str(item).lower() for item in modifiers}
        requested_raw = str(requested or "").lower().strip()
        mode = requested_raw
        if not mode and lock is not None:
            mode = str(lock.mode or "").lower().strip()
        if not mode:
            if "shift" in modset and self.horizontal_constraint_enabled:
                mode = "horizontal"
            elif "ctrl" in modset and self.vertical_constraint_enabled:
                mode = "vertical"
        if mode in {"horizontal", "h", "horizontal_constraint"} and self.horizontal_constraint_enabled:
            constrained = (world[0], base[1], base[2])
            metadata = {"anchor": list(base), "snap_label": "水平约束"}
            if lock is not None and lock.mode == "horizontal_constraint":
                metadata.update({"locked": True, "lock": lock.to_dict()})
            return SnapResult(constrained, snapped=True, mode="horizontal_constraint", target_entity_id=(lock.target_entity_id if lock else ""), distance=_dist(world, constrained), metadata=metadata)
        if mode in {"vertical", "v", "vertical_constraint"} and self.vertical_constraint_enabled:
            constrained = (base[0], base[1], world[2])
            metadata = {"anchor": list(base), "snap_label": "垂直约束"}
            if lock is not None and lock.mode == "vertical_constraint":
                metadata.update({"locked": True, "lock": lock.to_dict()})
            return SnapResult(constrained, snapped=True, mode="vertical_constraint", target_entity_id=(lock.target_entity_id if lock else ""), distance=_dist(world, constrained), metadata=metadata)
        if mode in {"edge", "along_edge", "edge_aligned"} and self.along_edge_constraint_enabled:
            if lock is not None and lock.mode == "edge_aligned" and lock.start is not None and lock.end is not None:
                constrained, distance = _project_point_to_segment(world, lock.start, lock.end)
                return SnapResult(constrained, snapped=True, mode="edge_aligned", target_entity_id=lock.target_entity_id, distance=distance, metadata={"anchor": list(base), "locked": True, "lock": lock.to_dict(), "snap_label": "沿边"})
            best: tuple[float, Vector3, LineCandidate] | None = None
            for line in self.line_candidates(state):
                projected, distance = _project_point_to_segment(world, line.start, line.end)
                if distance <= max(self.tolerance, self.spacing * 0.75) and (best is None or distance < best[0]):
                    best = (distance, projected, line)
            if best is not None:
                distance, constrained, line = best
                return SnapResult(constrained, snapped=True, mode="edge_aligned", target_entity_id=line.entity_id, distance=distance, metadata={"anchor": list(base), **dict(line.metadata)})
        if mode in {"normal", "along_normal", "normal_aligned"} and self.along_normal_constraint_enabled:
            direction = _unit((lock.normal if lock is not None and lock.mode == "normal_aligned" and lock.normal is not None else normal) or (0.0, 0.0, 1.0))
            if _norm(direction) <= 1.0e-12:
                direction = (0.0, 0.0, 1.0)
            constrained = _add(base, _mul(direction, _dot(_sub(world, base), direction)))
            metadata = {"anchor": list(base), "normal": list(direction), "snap_label": "沿法向"}
            if lock is not None and lock.mode == "normal_aligned":
                metadata.update({"locked": True, "lock": lock.to_dict()})
            return SnapResult(constrained, snapped=True, mode="normal_aligned", target_entity_id=(lock.target_entity_id if lock else ""), distance=_dist(world, constrained), metadata=metadata)
        return SnapResult(world, snapped=False, mode="none")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": "viewport_snap_controller_v4",
            "enabled": self.enabled,
            "grid_enabled": self.grid_enabled,
            "endpoint_enabled": self.endpoint_enabled,
            "midpoint_enabled": self.midpoint_enabled,
            "wall_endpoint_enabled": self.wall_endpoint_enabled,
            "beam_endpoint_enabled": self.beam_endpoint_enabled,
            "anchor_endpoint_enabled": self.anchor_endpoint_enabled,
            "stratum_intersection_enabled": self.stratum_intersection_enabled,
            "excavation_intersection_enabled": self.excavation_intersection_enabled,
            "constraints": {
                "horizontal": self.horizontal_constraint_enabled,
                "vertical": self.vertical_constraint_enabled,
                "along_edge": self.along_edge_constraint_enabled,
                "along_normal": self.along_normal_constraint_enabled,
            },
            "constraint_lock": self.constraint_lock.to_dict(),
            "last_unlock_feedback": dict(self.last_unlock_feedback or {}),
            "spacing": float(self.spacing),
            "tolerance": float(self.tolerance),
        }


__all__ = ["SnapController", "SnapResult", "Vector3", "SnapCandidate", "LineCandidate", "ConstraintLockState", "SEMANTIC_LABELS"]
