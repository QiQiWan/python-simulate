from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


def _float_list(values: Iterable[Any], default: Iterable[float] = ()) -> list[float]:
    out: list[float] = []
    for value in list(values or default):
        try:
            out.append(float(value))
        except Exception:
            continue
    return out


def _bounds_from_outline(outline: Iterable[Iterable[Any]]) -> tuple[float, float, float, float]:
    pts = [(float(p[0]), float(p[1])) for p in list(outline or []) if len(list(p)) >= 2]
    if not pts:
        return (-20.0, 20.0, -10.0, 10.0)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), max(xs), min(ys), max(ys)


@dataclass(slots=True)
class SupportComponentRealization:
    contract: str = "support_component_realization_v1"
    blocks: list[dict[str, Any]] = field(default_factory=list)
    structures: list[dict[str, Any]] = field(default_factory=list)
    stages: list[dict[str, Any]] = field(default_factory=list)
    interfaces: list[dict[str, Any]] = field(default_factory=list)
    named_selections: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "blocks": list(self.blocks),
            "structures": list(self.structures),
            "stages": list(self.stages),
            "interfaces": list(self.interfaces),
            "named_selections": list(self.named_selections),
            "issues": list(self.issues),
            "summary": {
                "block_count": len(self.blocks),
                "structure_count": len(self.structures),
                "stage_count": len(self.stages),
                "interface_count": len(self.interfaces),
                "issue_count": len(self.issues),
                "requires_remesh": True,
            },
            "edit_policy": "edit_component_parameters_then_remesh",
            "mesh_editable": False,
        }


class SupportComponentRealizer:
    """Realize wall panels, struts and anchors as source entities."""

    def build(self, parameters: dict[str, Any] | None) -> dict[str, Any]:
        p = dict(parameters or {})
        outline = p.get("pit_outline") or p.get("polyline") or []
        xmin, xmax, ymin, ymax = _bounds_from_outline(outline)
        wall_t = max(0.05, float(p.get("wall_thickness", 0.8) or 0.8))
        wall_top = float(p.get("wall_top", 0.0) or 0.0)
        wall_bottom = float(p.get("wall_bottom", -25.0) or -25.0)
        wall_mesh = p.get("wall_mesh_size", None)
        wall_mat = str(p.get("wall_material_name") or "retaining_wall")
        zlo, zhi = min(wall_bottom, wall_top), max(wall_bottom, wall_top)
        blocks = [
            {"name": "wall_panel_north", "bounds": [xmin - wall_t, xmax + wall_t, ymax, ymax + wall_t, zlo, zhi], "role": "wall_panel", "material_name": wall_mat, "mesh_size": wall_mesh, "active_stages": ["wall_installation"], "metadata": {"component": "retaining_wall", "side": "north"}},
            {"name": "wall_panel_south", "bounds": [xmin - wall_t, xmax + wall_t, ymin - wall_t, ymin, zlo, zhi], "role": "wall_panel", "material_name": wall_mat, "mesh_size": wall_mesh, "active_stages": ["wall_installation"], "metadata": {"component": "retaining_wall", "side": "south"}},
            {"name": "wall_panel_east", "bounds": [xmax, xmax + wall_t, ymin, ymax, zlo, zhi], "role": "wall_panel", "material_name": wall_mat, "mesh_size": wall_mesh, "active_stages": ["wall_installation"], "metadata": {"component": "retaining_wall", "side": "east"}},
            {"name": "wall_panel_west", "bounds": [xmin - wall_t, xmin, ymin, ymax, zlo, zhi], "role": "wall_panel", "material_name": wall_mat, "mesh_size": wall_mesh, "active_stages": ["wall_installation"], "metadata": {"component": "retaining_wall", "side": "west"}},
        ]
        support_levels = _float_list(p.get("support_levels", []))
        spacing = max(0.5, float(p.get("support_spacing", 8.0) or 8.0))
        inset = max(0.0, float(p.get("support_inset", 1.5) or 1.5))
        structures: list[dict[str, Any]] = []
        for li, z in enumerate(support_levels, start=1):
            y = ymin + inset
            idx = 1
            while y <= ymax - inset + 1.0e-9:
                structures.append({"kind": "strut", "name": f"strut_L{li:02d}_{idx:02d}", "start": [xmin + inset, y, z], "end": [xmax - inset, y, z], "parameters": {"EA": float(p.get("support_stiffness", 2.0e8) or 2.0e8), "section_type": p.get("support_section_type", "steel_pipe")}, "active_stages": [f"install_support_L{li:02d}"], "metadata": {"component": "strut_support", "level": li}}
                )
                y += spacing
                idx += 1
        anchor_levels = _float_list(p.get("anchor_levels", []))
        anchor_spacing = max(0.5, float(p.get("anchor_spacing", 6.0) or 6.0))
        free_len = max(0.0, float(p.get("anchor_free_length", p.get("free_length", 8.0)) or 8.0))
        bond_len = max(0.0, float(p.get("anchor_bond_length", p.get("bond_length", 10.0)) or 10.0))
        total_len = free_len + bond_len
        for li, z in enumerate(anchor_levels, start=1):
            x = xmin + anchor_spacing * 0.5
            idx = 1
            while x <= xmax - anchor_spacing * 0.5 + 1.0e-9:
                structures.append({"kind": "ground_anchor", "name": f"anchor_N_L{li:02d}_{idx:02d}", "start": [x, ymax, z], "end": [x, ymax + total_len, z - total_len * 0.25], "parameters": {"free_length": free_len, "bond_length": bond_len, "prestress": float(p.get("anchor_prestress", p.get("prestress", 0.0)) or 0.0)}, "active_stages": [f"install_anchor_L{li:02d}"], "metadata": {"component": "ground_anchor", "side": "north", "level": li}})
                structures.append({"kind": "ground_anchor", "name": f"anchor_S_L{li:02d}_{idx:02d}", "start": [x, ymin, z], "end": [x, ymin - total_len, z - total_len * 0.25], "parameters": {"free_length": free_len, "bond_length": bond_len, "prestress": float(p.get("anchor_prestress", p.get("prestress", 0.0)) or 0.0)}, "active_stages": [f"install_anchor_L{li:02d}"], "metadata": {"component": "ground_anchor", "side": "south", "level": li}})
                x += anchor_spacing
                idx += 1
        stages = [{"name": "wall_installation", "activate_regions": [row["name"] for row in blocks], "deactivate_regions": [], "metadata": {"component_realization": True}}]
        for li, _ in enumerate(support_levels, start=1):
            stages.append({"name": f"install_support_L{li:02d}", "activate_structures": [row["name"] for row in structures if f"_L{li:02d}_" in row["name"] and row["kind"] == "strut"], "metadata": {"component_realization": True}})
        for li, _ in enumerate(anchor_levels, start=1):
            stages.append({"name": f"install_anchor_L{li:02d}", "activate_structures": [row["name"] for row in structures if f"_L{li:02d}_" in row["name"] and row["kind"] == "ground_anchor"], "metadata": {"component_realization": True}})
        interfaces = [{"name": f"interface_{row['name']}", "kind": "wall_soil", "target_entity": f"solid:{row['name']}", "active_stages": ["wall_installation"], "metadata": {"component": "retaining_wall", "mode": p.get("wall_interface_mode", "contact_interface")}} for row in blocks]
        selections = [
            {"name": "retaining_wall_panels", "kind": "solid", "entity_ids": [f"solid:{row['name']}" for row in blocks]},
            {"name": "support_structures", "kind": "structure", "entity_ids": [row["name"] for row in structures if row["kind"] == "strut"]},
            {"name": "anchor_structures", "kind": "structure", "entity_ids": [row["name"] for row in structures if row["kind"] == "ground_anchor"]},
        ]
        return SupportComponentRealization(blocks=blocks, structures=structures, stages=stages, interfaces=interfaces, named_selections=selections).to_dict()


__all__ = ["SupportComponentRealizer", "SupportComponentRealization"]
