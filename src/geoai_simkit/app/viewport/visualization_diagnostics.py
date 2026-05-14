from __future__ import annotations

"""GUI visualization diagnostics and lightweight scene payloads.

The desktop workbench has two rendering paths:

* PyVista/VTK for the full 3D viewport.
* A PySide-only lightweight scene preview used during startup diagnostics,
  dependency validation, and fallback/error investigation.

This module is intentionally Qt-free so it can be tested in headless CI and used
by the startup/preflight screens to verify that a loaded engineering project has
actual visual primitives before the user clicks around the GUI.
"""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.app.viewport.viewport_state import ViewportState


@dataclass(slots=True)
class GuiVisualizationDiagnostic:
    contract: str = "geoai_simkit_gui_visualization_diagnostic_v1"
    ok: bool = False
    primitive_count: int = 0
    visible_primitive_count: int = 0
    block_count: int = 0
    surface_count: int = 0
    edge_count: int = 0
    point_count: int = 0
    support_count: int = 0
    contact_pair_count: int = 0
    bounds: tuple[float, float, float, float, float, float] | None = None
    warnings: list[str] = field(default_factory=list)
    primitives: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "primitive_count": int(self.primitive_count),
            "visible_primitive_count": int(self.visible_primitive_count),
            "block_count": int(self.block_count),
            "surface_count": int(self.surface_count),
            "edge_count": int(self.edge_count),
            "point_count": int(self.point_count),
            "support_count": int(self.support_count),
            "contact_pair_count": int(self.contact_pair_count),
            "bounds": list(self.bounds) if self.bounds is not None else None,
            "warnings": list(self.warnings),
            "primitives": [dict(row) for row in self.primitives],
        }


def _merge_bounds(bounds: tuple[float, float, float, float, float, float] | None, row: tuple[float, float, float, float, float, float] | None) -> tuple[float, float, float, float, float, float] | None:
    if row is None:
        return bounds
    if bounds is None:
        return tuple(float(v) for v in row)  # type: ignore[return-value]
    return (
        min(bounds[0], row[0]),
        max(bounds[1], row[1]),
        min(bounds[2], row[2]),
        max(bounds[3], row[3]),
        min(bounds[4], row[4]),
        max(bounds[5], row[5]),
    )


def build_gui_visualization_diagnostic(project: Any, *, stage_id: str | None = None) -> GuiVisualizationDiagnostic:
    """Build a renderability diagnostic for a GeoProject-like document."""

    state = ViewportState()
    try:
        state.update_from_geoproject_document(project, stage_id=stage_id)
    except Exception as exc:
        return GuiVisualizationDiagnostic(ok=False, warnings=[f"Viewport state build failed: {type(exc).__name__}: {exc}"])

    primitive_rows: list[dict[str, Any]] = []
    merged: tuple[float, float, float, float, float, float] | None = None
    counts = {"block": 0, "surface": 0, "edge": 0, "point": 0, "support": 0, "contact_pair": 0}
    visible_count = 0
    for primitive in state.primitives.values():
        if primitive.visible:
            visible_count += 1
        if primitive.kind in counts:
            counts[primitive.kind] += 1
        merged = _merge_bounds(merged, primitive.bounds)
        primitive_rows.append(
            {
                "id": primitive.id,
                "kind": primitive.kind,
                "entity_id": primitive.entity_id,
                "label": primitive.label or primitive.entity_id,
                "visible": bool(primitive.visible),
                "pickable": bool(primitive.pickable),
                "bounds": list(primitive.bounds) if primitive.bounds is not None else None,
                "style": dict(primitive.style),
                "metadata": dict(primitive.metadata),
            }
        )

    warnings: list[str] = []
    if not primitive_rows:
        warnings.append("No viewport primitives were generated from the current project.")
    if visible_count == 0 and primitive_rows:
        warnings.append("Viewport primitives exist but all are hidden.")
    if counts["block"] == 0:
        warnings.append("No block/volume primitive is available for model preview.")

    return GuiVisualizationDiagnostic(
        ok=bool(primitive_rows and visible_count > 0),
        primitive_count=len(primitive_rows),
        visible_primitive_count=visible_count,
        block_count=counts["block"],
        surface_count=counts["surface"],
        edge_count=counts["edge"],
        point_count=counts["point"],
        support_count=counts["support"],
        contact_pair_count=counts["contact_pair"],
        bounds=merged,
        warnings=warnings,
        primitives=primitive_rows,
    )


__all__ = ["GuiVisualizationDiagnostic", "build_gui_visualization_diagnostic"]
