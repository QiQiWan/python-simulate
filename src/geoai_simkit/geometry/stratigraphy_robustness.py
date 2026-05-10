from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _surface_lookup(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    surfaces = {}
    for row in list(plan.get("surfaces", []) or []):
        if isinstance(row, dict):
            name = str(row.get("name") or row.get("id") or "")
            if name:
                surfaces[name] = dict(row)
    return surfaces


def _z_values(surface: dict[str, Any]) -> list[float]:
    vals: list[float] = []
    for p in list(surface.get("interpolated_grid", []) or []):
        try:
            vals.append(float(list(p)[2]))
        except Exception:
            continue
    if not vals:
        for key in ("z_mean", "z_min", "z_max"):
            if surface.get(key) not in {None, ""}:
                vals.append(float(surface[key]))
    return vals


@dataclass(slots=True)
class StratigraphyRobustnessReport:
    contract: str = "stratigraphy_surface_boolean_robustness_v1"
    layer_rows: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    repair_actions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        severe = [i for i in self.issues if str(i.get("severity")) == "error"]
        return {
            "contract": self.contract,
            "layer_rows": list(self.layer_rows),
            "issues": list(self.issues),
            "repair_actions": list(self.repair_actions),
            "summary": {
                "layer_count": len(self.layer_rows),
                "issue_count": len(self.issues),
                "error_count": len(severe),
                "ready_for_occ_boolean": not severe,
                "fallback_recommended": bool(severe),
            },
            "supported_pathologies": ["surface_crossing", "pinch_out", "thin_lens", "missing_surface", "triangle_mismatch"],
        }


class StratigraphyRobustnessAnalyzer:
    """Detect common geological-surface problems before OCC boolean operations."""

    def analyze(self, stratigraphy_plan: dict[str, Any] | None, *, min_layer_thickness: float = 0.05) -> dict[str, Any]:
        plan = dict(stratigraphy_plan or {})
        surfaces = _surface_lookup(plan)
        layer_rows: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        for idx, layer in enumerate([dict(r) for r in list(plan.get("layer_solids", []) or []) if isinstance(r, dict)], start=1):
            name = str(layer.get("name") or f"layer_{idx:02d}")
            top_name = str(layer.get("top_surface") or "")
            bottom_name = str(layer.get("bottom_surface") or "")
            top = surfaces.get(top_name)
            bottom = surfaces.get(bottom_name) if bottom_name else None
            top_z = _z_values(top or {})
            bottom_z = _z_values(bottom or {}) if bottom else []
            if not top:
                issues.append({"layer": name, "severity": "error", "kind": "missing_surface", "message": f"Top surface {top_name!r} is missing."})
            if bottom_name and not bottom:
                issues.append({"layer": name, "severity": "error", "kind": "missing_surface", "message": f"Bottom surface {bottom_name!r} is missing."})
            thickness_values: list[float] = []
            if top_z and bottom_z and len(top_z) == len(bottom_z):
                thickness_values = [float(t - b) for t, b in zip(top_z, bottom_z)]
            elif top_z and bottom_z:
                thickness_values = [float(sum(top_z) / len(top_z) - sum(bottom_z) / len(bottom_z))]
                issues.append({"layer": name, "severity": "warning", "kind": "triangle_mismatch", "message": "Top/bottom grids have different sizes; OCC loft will use a repaired or fallback path."})
            min_thick = min(thickness_values) if thickness_values else None
            max_thick = max(thickness_values) if thickness_values else None
            crossing = bool(thickness_values and min(thickness_values) < -abs(min_layer_thickness))
            pinch = bool(thickness_values and abs(min(thickness_values)) <= abs(min_layer_thickness))
            lens = bool(thickness_values and max(thickness_values) > abs(min_layer_thickness) and min(thickness_values) < abs(min_layer_thickness) * 2.0)
            if crossing:
                issues.append({"layer": name, "severity": "error", "kind": "surface_crossing", "message": "Top surface crosses below bottom surface; split/repair before OCC fragment."})
                actions.append({"layer": name, "action": "split_crossing_surface_pair", "fallback": "fallback_layer_blocks"})
            elif pinch:
                issues.append({"layer": name, "severity": "warning", "kind": "pinch_out", "message": "Layer pinches out locally; use minimum thickness clipping or split lens volume."})
                actions.append({"layer": name, "action": "clip_minimum_thickness", "minimum_thickness": float(min_layer_thickness)})
            elif lens:
                issues.append({"layer": name, "severity": "warning", "kind": "thin_lens", "message": "Thin lens-like layer detected; use dedicated lens volume or fallback block."})
                actions.append({"layer": name, "action": "create_lens_subvolume_or_fallback", "minimum_thickness": float(min_layer_thickness)})
            layer_rows.append({"name": name, "top_surface": top_name, "bottom_surface": bottom_name, "min_thickness": min_thick, "max_thickness": max_thick, "surface_crossing": crossing, "pinch_out": pinch, "thin_lens": lens, "ready_for_occ_boolean": bool(top and (not bottom_name or bottom) and not crossing)})
        return StratigraphyRobustnessReport(layer_rows=layer_rows, issues=issues, repair_actions=actions).to_dict()


__all__ = ["StratigraphyRobustnessAnalyzer", "StratigraphyRobustnessReport"]
