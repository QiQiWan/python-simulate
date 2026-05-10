from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence
import math


def _xy(polyline: Iterable[Sequence[Any]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in list(polyline or []):
        vals = list(p or [])
        if len(vals) >= 2:
            out.append((float(vals[0]), float(vals[1])))
    return out


def _point_xyz(row: dict[str, Any]) -> tuple[float, float, float]:
    coords = list(row.get("coordinates", row.get("xyz", (0.0, 0.0, 0.0))) or (0.0, 0.0, 0.0))[:3]
    while len(coords) < 3:
        coords.append(0.0)
    return float(coords[0]), float(coords[1]), float(coords[2])


def _bbox(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points] or [0.0]
    ys = [p[1] for p in points] or [0.0]
    return min(xs), max(xs), min(ys), max(ys)


def _segment_bounds(a: tuple[float, float], b: tuple[float, float], thickness: float, z_top: float, z_bottom: float) -> list[float]:
    t = max(0.0, float(thickness or 0.0)) * 0.5
    xmin = min(a[0], b[0]) - t
    xmax = max(a[0], b[0]) + t
    ymin = min(a[1], b[1]) - t
    ymax = max(a[1], b[1]) + t
    if abs(xmax - xmin) < max(t * 2.0, 1.0e-6):
        xmax = xmin + max(t * 2.0, 1.0e-6)
    if abs(ymax - ymin) < max(t * 2.0, 1.0e-6):
        ymax = ymin + max(t * 2.0, 1.0e-6)
    return [float(xmin), float(xmax), float(ymin), float(ymax), float(min(z_bottom, z_top)), float(max(z_bottom, z_top))]


@dataclass(slots=True)
class PlaxisChecklistItem:
    id: str
    area: str
    label: str
    status: str
    required: bool = True
    evidence: str = ""
    action: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "area": self.area,
            "label": self.label,
            "status": self.status,
            "required": bool(self.required),
            "evidence": self.evidence,
            "action": self.action,
            "metadata": dict(self.metadata),
        }


class PlaxisLikeModelingAudit:
    """Assess whether the entity-level GUI workflow is close to a PLAXIS-style modeler."""

    def build(self, parameters: dict[str, Any] | None, *, model_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(parameters or {})
        meta = dict(model_metadata or {})
        blocks = [dict(row) for row in list(params.get("blocks", params.get("editable_blocks", [])) or []) if isinstance(row, dict)]
        splits = [dict(row) for row in list(params.get("block_splits", []) or []) if isinstance(row, dict)]
        sketch = dict(params.get("sketch", {}) or {})
        points = [dict(row) for row in list(sketch.get("points", []) or []) if isinstance(row, dict)]
        lines = [dict(row) for row in list(sketch.get("lines", []) or []) if isinstance(row, dict)]
        bindings = dict(params.get("topology_entity_bindings", {}) or {})
        mesh_controls = [dict(row) for row in list(params.get("mesh_size_controls", []) or []) if isinstance(row, dict)]
        face_sets = dict(meta.get("mesh.face_sets", params.get("mesh.face_sets", {})) or {})
        quality = dict(meta.get("mesh.quality_report", params.get("mesh_quality_report", {})) or {})
        pit = dict(params.get("pit_modeling", {}) or {})
        strat = dict(params.get("stratigraphy", {}) or {})
        checklist: list[PlaxisChecklistItem] = []

        def status(ok: bool, partial: bool = False) -> str:
            return "complete" if ok else ("partial" if partial else "missing")

        checklist.append(PlaxisChecklistItem("entity.blocks", "Entity modeling", "Editable soil / structure entities", status(bool(blocks)), evidence=f"blocks={len(blocks)}", action="Create editable blocks or apply the pit workflow."))
        checklist.append(PlaxisChecklistItem("sketch.pit_outline", "Sketch", "Closed pit outline sketch", status(bool(points) and bool(lines), bool(points)), evidence=f"points={len(points)} lines={len(lines)}", action="Use Close / Snap / Orthogonalize sketch."))
        checklist.append(PlaxisChecklistItem("sketch.offsets", "Sketch", "Wall center / inner / outer offset lines", status(bool(dict(sketch.get("wall_offsets", {}) or {}))), evidence=f"wall_offsets={bool(dict(sketch.get('wall_offsets', {}) or {}))}", action="Generate wall offsets from the pit sketch."))
        checklist.append(PlaxisChecklistItem("objects.wall_panels", "Engineering objects", "Retaining wall panel entities", status(any(str(row.get("role")) == "wall_panel" for row in blocks), any(str(row.get("role")) == "wall" for row in blocks)), evidence=f"wall_panels={sum(1 for row in blocks if str(row.get('role')) == 'wall_panel')}", action="Generate wall panels from the outline."))
        checklist.append(PlaxisChecklistItem("objects.supports", "Engineering objects", "Support / strut structure objects", status(bool(params.get("generated_support_rows")) or bool(params.get("support_layout"))), evidence=f"support_rows={len(list(params.get('generated_support_rows', []) or []))}", action="Generate support rows for selected levels."))
        checklist.append(PlaxisChecklistItem("objects.excavation_stages", "Staged construction", "Excavation blocks and sequential stages", status(bool(pit.get("summary", {}).get("excavation_stage_count")) or any(str(row.get("role")) == "excavation" for row in blocks), bool(splits)), evidence=f"excavation_blocks={sum(1 for row in blocks if str(row.get('role')) == 'excavation')}", action="Apply staged excavation from levels."))
        checklist.append(PlaxisChecklistItem("stratigraphy.layers", "Soil layers", "Interpolated layer surfaces and layer solids", status(bool(strat.get("summary", {}).get("layer_solid_count")) or any(str(row.get("role")) == "soil_layer" for row in blocks), bool(strat)), evidence=f"layer_solids={dict(strat.get('summary', {}) or {}).get('layer_solid_count', 0)}", action="Apply borehole stratigraphy or default layer template."))
        checklist.append(PlaxisChecklistItem("topology.bindings", "Attributes", "Entity-level materials / BC / load / stage bindings", status(bool(bindings), bool(params.get("selected_topology_entity"))), evidence=f"bindings={len(bindings)}", action="Bind selected faces/solids in the Selection Inspector."))
        checklist.append(PlaxisChecklistItem("mesh.controls", "Meshing", "Entity-attached mesh-size fields", status(bool(mesh_controls), bool(blocks)), evidence=f"mesh_controls={len(mesh_controls)}", action="Apply local mesh controls to walls, interfaces and excavation surfaces."))
        checklist.append(PlaxisChecklistItem("mesh.facesets", "Meshing", "Solver-ready FaceSet extraction", status(bool(face_sets.get("face_sets")) or bool(params.get("solver_face_set_rows")), bool(params.get("protected_surface_rows"))), evidence=f"face_sets={len(list(face_sets.get('face_sets', []) or params.get('solver_face_set_rows', []) or []))}", action="Regenerate OCC/Gmsh mesh to recover face sets."))
        checklist.append(PlaxisChecklistItem("mesh.quality", "Meshing", "Mesh quality report with geometry back-references", status(bool(quality), False), evidence=f"quality_contract={quality.get('contract', '')}", action="Generate mesh and review the quality panel."))
        checklist.append(PlaxisChecklistItem("presolve.audit", "Solve handoff", "Pre-solve audit gate", status(bool(params.get("geometry_dirty_state")) or bool(params.get("binding_transfer_report")) or bool(meta.get("pre_solve_geometry_check_panel")), True), evidence="audit available through Solve panel", action="Run geometry pre-solve check before calculation."))

        required = [item for item in checklist if item.required]
        complete = sum(1 for item in required if item.status == "complete")
        partial = sum(1 for item in required if item.status == "partial")
        score = (complete + 0.5 * partial) / max(1, len(required))
        missing = [item.to_dict() for item in checklist if item.status == "missing"]
        return {
            "contract": "plaxis_like_gui_modeling_checklist_v1",
            "score": float(score),
            "status": "ready" if score >= 0.85 and not missing else ("usable" if score >= 0.65 else "incomplete"),
            "items": [item.to_dict() for item in checklist],
            "missing_items": missing,
            "summary": {
                "required_count": len(required),
                "complete_count": complete,
                "partial_count": partial,
                "missing_count": len(missing),
                "plaxis_like_ready": bool(score >= 0.85 and not missing),
            },
            "next_actions": [str(item.get("action")) for item in missing[:6]],
        }


class PlaxisLikePitObjectBuilder:
    """Generate entity-level engineering objects from a pit outline.

    The generated objects are editable source entities. Mesh cells are not edited;
    after any object is changed, the model must be remeshed before solving.
    """

    def wall_panel_blocks(
        self,
        outline: Iterable[Sequence[Any]],
        *,
        thickness: float = 0.8,
        z_top: float = 0.0,
        z_bottom: float = -25.0,
        material_name: str = "retaining_wall",
        mesh_size: float | None = 0.5,
    ) -> list[dict[str, Any]]:
        pts = _xy(outline)
        if len(pts) < 3:
            return []
        rows: list[dict[str, Any]] = []
        for idx, a in enumerate(pts):
            b = pts[(idx + 1) % len(pts)]
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            if length <= 1.0e-9:
                continue
            rows.append({
                "name": f"wall_panel_{idx + 1:02d}",
                "bounds": _segment_bounds(a, b, thickness, z_top, z_bottom),
                "role": "wall_panel",
                "material_name": str(material_name or "retaining_wall"),
                "mesh_size": None if mesh_size is None else float(mesh_size),
                "active_stages": ["wall_installation"],
                "metadata": {
                    "generated_by": "PlaxisLikePitObjectBuilder",
                    "centerline_start": [float(a[0]), float(a[1]), float(z_top)],
                    "centerline_end": [float(b[0]), float(b[1]), float(z_top)],
                    "panel_length": float(length),
                    "wall_thickness": float(thickness),
                    "edit_policy": "edit_wall_panel_entity_then_remesh",
                },
            })
        return rows

    def support_rows(
        self,
        outline: Iterable[Sequence[Any]],
        *,
        levels: Iterable[float] = (-3.0,),
        axis: str = "x",
        spacing: float = 6.0,
        inset: float = 1.0,
        stiffness: float = 1.0e8,
    ) -> list[dict[str, Any]]:
        pts = _xy(outline)
        if len(pts) < 3:
            return []
        xmin, xmax, ymin, ymax = _bbox(pts)
        axis_key = str(axis or "x").lower()
        span_min, span_max = (ymin + inset, ymax - inset) if axis_key == "x" else (xmin + inset, xmax - inset)
        if span_max < span_min:
            span_min, span_max = span_max, span_min
        n = max(1, int(math.floor((span_max - span_min) / max(1.0e-6, float(spacing or 6.0)))) + 1)
        rows: list[dict[str, Any]] = []
        for level_idx, z in enumerate(list(levels or []), start=1):
            for i in range(n):
                t = 0.5 if n == 1 else i / max(1, n - 1)
                coord = span_min + (span_max - span_min) * t
                if axis_key == "x":
                    start = [xmin + inset, coord, float(z)]
                    end = [xmax - inset, coord, float(z)]
                else:
                    start = [coord, ymin + inset, float(z)]
                    end = [coord, ymax - inset, float(z)]
                rows.append({
                    "name": f"support_L{level_idx:02d}_{i + 1:02d}",
                    "kind": "two_point_structure",
                    "element_kind": "beam2",
                    "start": start,
                    "end": end,
                    "stiffness": float(stiffness),
                    "active_stages": [f"excavate_to_{abs(float(z)):.1f}m"],
                    "metadata": {"generated_by": "PlaxisLikePitObjectBuilder", "support_level": float(z), "axis": axis_key},
                })
        return rows

    def excavation_stage_names(self, levels: Iterable[float]) -> list[str]:
        names = ["initial", "wall_installation"]
        for z in sorted([float(v) for v in list(levels or [])], reverse=True):
            names.append(f"excavate_to_{abs(z):.1f}m")
        return list(dict.fromkeys(names))


def outline_from_sketch(points: Iterable[dict[str, Any]]) -> list[list[float]]:
    ordered = [dict(row) for row in list(points or []) if isinstance(row, dict)]
    ordered.sort(key=lambda r: int(r.get("index", 10**9) or 10**9))
    return [[float(_point_xyz(row)[0]), float(_point_xyz(row)[1])] for row in ordered]


__all__ = [
    "PlaxisLikeModelingAudit",
    "PlaxisLikePitObjectBuilder",
    "outline_from_sketch",
]
