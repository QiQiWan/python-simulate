from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ComponentParameterField:
    key: str
    label: str
    value: Any
    unit: str = ""
    field_type: str = "float"
    min_value: float | None = None
    max_value: float | None = None
    options: tuple[str, ...] = ()
    help_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "value": self.value, "unit": self.unit, "field_type": self.field_type, "min_value": self.min_value, "max_value": self.max_value, "options": list(self.options), "help_text": self.help_text}


@dataclass(slots=True)
class ComponentParameterPanel:
    component_type: str
    title: str
    fields: tuple[ComponentParameterField, ...]
    actions: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"contract": "component_parameter_panel_v2", "component_type": self.component_type, "title": self.title, "fields": [f.to_dict() for f in self.fields], "actions": list(self.actions), "metadata": dict(self.metadata)}


def _flt(payload: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(payload.get(key, default) or default)
    except Exception:
        return float(default)


def _arr(payload: dict[str, Any], key: str, default: list[float]) -> list[Any]:
    value = payload.get(key, default)
    return list(value if isinstance(value, (list, tuple)) else default)


class ComponentParameterPanelFactory:
    def wall_panel(self, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        p = dict(parameters or {})
        return ComponentParameterPanel(
            component_type="retaining_wall",
            title="Retaining wall / diaphragm wall parameters",
            fields=(
                ComponentParameterField("wall_type", "Wall type", str(p.get("wall_type", "diaphragm_wall")), "", "enum", options=("diaphragm_wall", "secant_pile_wall", "sheet_pile_wall", "soil_mixing_wall"), help_text="The entity generator still edits source wall entities and remeshes afterwards."),
                ComponentParameterField("wall_representation", "Representation", str(p.get("wall_representation", "solid")), "", "enum", options=("solid", "plate", "embedded_plate")),
                ComponentParameterField("wall_thickness", "Wall thickness", _flt(p, "wall_thickness", 0.8), "m", min_value=0.05),
                ComponentParameterField("wall_top", "Wall top elevation", _flt(p, "wall_top", 0.0), "m"),
                ComponentParameterField("wall_bottom", "Wall bottom elevation", _flt(p, "wall_bottom", -25.0), "m"),
                ComponentParameterField("wall_material_name", "Wall material", str(p.get("wall_material_name", "retaining_wall")), "", "text"),
                ComponentParameterField("wall_interface_mode", "Soil-wall interface", str(p.get("wall_interface_mode", "auto_face_set_interface")), "", "enum", options=("none", "tie", "auto_face_set_interface", "contact")),
                ComponentParameterField("wall_mesh_size", "Wall local mesh size", _flt(p, "wall_mesh_size", 0.5), "m", min_value=0.02),
            ),
            actions=("regenerate_wall_panels", "regenerate_wall_offsets", "generate_wall_interfaces", "mark_mesh_stale"),
            metadata={"edit_policy": "edit_wall_parameters_then_remesh", "mesh_editable": False},
        ).to_dict()

    def strut_support(self, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        p = dict(parameters or {})
        return ComponentParameterPanel(
            component_type="strut_support",
            title="Horizontal support / strut parameters",
            fields=(
                ComponentParameterField("support_levels", "Support levels", _arr(p, "support_levels", [-2.5, -5.5, -8.5]), "m", "array"),
                ComponentParameterField("support_axis", "Support axis", str(p.get("support_axis", "x")), "", "enum", options=("x", "y", "both")),
                ComponentParameterField("support_spacing", "Support spacing", _flt(p, "support_spacing", 6.0), "m", min_value=0.1),
                ComponentParameterField("support_inset", "Support inset", _flt(p, "support_inset", 1.0), "m", min_value=0.0),
                ComponentParameterField("support_section_type", "Section type", str(p.get("support_section_type", "steel_tube")), "", "enum", options=("steel_tube", "concrete_strut", "h_beam", "custom")),
                ComponentParameterField("support_stiffness", "Axial/beam stiffness", _flt(p, "support_stiffness", 1.0e8), "N/m", min_value=1.0),
                ComponentParameterField("support_install_offset", "Install after excavation offset", _flt(p, "support_install_offset", 0.2), "m"),
            ),
            actions=("regenerate_support_rows", "update_stage_activation", "mark_mesh_stale"),
            metadata={"edit_policy": "edit_support_parameters_then_remesh", "mesh_editable": False},
        ).to_dict()

    def anchor(self, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        p = dict(parameters or {})
        return ComponentParameterPanel(
            component_type="ground_anchor",
            title="Ground anchor parameters",
            fields=(
                ComponentParameterField("anchor_enabled", "Generate anchors", bool(p.get("anchor_enabled", False)), "", "bool"),
                ComponentParameterField("anchor_levels", "Anchor levels", _arr(p, "anchor_levels", [-3.0, -6.0]), "m", "array"),
                ComponentParameterField("anchor_spacing", "Anchor spacing", _flt(p, "anchor_spacing", 3.0), "m", min_value=0.1),
                ComponentParameterField("anchor_inclination", "Inclination below horizontal", _flt(p, "anchor_inclination", 15.0), "deg", min_value=0.0, max_value=60.0),
                ComponentParameterField("anchor_free_length", "Free length", _flt(p, "anchor_free_length", _flt(p, "free_length", 8.0)), "m", min_value=0.1),
                ComponentParameterField("anchor_bond_length", "Bond length", _flt(p, "anchor_bond_length", _flt(p, "bond_length", 10.0)), "m", min_value=0.1),
                ComponentParameterField("anchor_prestress", "Prestress", _flt(p, "anchor_prestress", _flt(p, "prestress", 200.0)), "kN", min_value=0.0),
                ComponentParameterField("anchor_wall_connection", "Wall connection", str(p.get("anchor_wall_connection", "face_set")), "", "enum", options=("face_set", "nearest_wall_panel", "manual")),
            ),
            actions=("generate_anchor_rows", "assign_anchor_stage", "generate_anchor_wall_connections", "mark_mesh_stale"),
            metadata={"edit_policy": "edit_anchor_parameters_then_remesh", "mesh_editable": False},
        ).to_dict()

    def excavation(self, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        p = dict(parameters or {})
        return ComponentParameterPanel(
            component_type="excavation_stage",
            title="Excavation and staged construction parameters",
            fields=(
                ComponentParameterField("excavation_levels", "Excavation levels", _arr(p, "excavation_levels", [-3.0, -6.0, -9.0]), "m", "array"),
                ComponentParameterField("stage_prefix", "Stage prefix", str(p.get("stage_prefix", "excavate_to")), "", "text"),
                ComponentParameterField("deactivate_soil_blocks", "Deactivate soil blocks", bool(p.get("deactivate_soil_blocks", True)), "", "bool"),
                ComponentParameterField("activate_supports_by_level", "Activate supports by level", bool(p.get("activate_supports_by_level", True)), "", "bool"),
            ),
            actions=("regenerate_excavation_blocks", "regenerate_stage_sequence", "mark_results_stale"),
            metadata={"edit_policy": "edit_stage_entities_then_remesh_and_resolve", "mesh_editable": False},
        ).to_dict()

    def validate_parameters(self, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        p = dict(parameters or {})
        issues: list[dict[str, Any]] = []
        if _flt(p, "wall_thickness", 0.8) <= 0.0:
            issues.append({"field": "wall_thickness", "severity": "error", "message": "Wall thickness must be positive."})
        if _flt(p, "wall_bottom", -25.0) >= _flt(p, "wall_top", 0.0):
            issues.append({"field": "wall_bottom", "severity": "error", "message": "Wall bottom must be below wall top."})
        if _flt(p, "support_spacing", 6.0) <= 0.0:
            issues.append({"field": "support_spacing", "severity": "error", "message": "Support spacing must be positive."})
        if _flt(p, "anchor_free_length", _flt(p, "free_length", 8.0)) <= 0.0 or _flt(p, "anchor_bond_length", _flt(p, "bond_length", 10.0)) <= 0.0:
            issues.append({"field": "anchor_length", "severity": "error", "message": "Anchor free and bond lengths must be positive."})
        return {"contract": "component_parameter_validation_v1", "issues": issues, "summary": {"issue_count": len(issues), "ready": not issues}}

    def build_all(self, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        p = dict(parameters or {})
        panels = [self.wall_panel(p), self.strut_support(p), self.anchor(p), self.excavation(p)]
        validation = self.validate_parameters(p)
        return {"contract": "component_parameter_panels_v2", "panels": panels, "validation": validation, "summary": {"panel_count": len(panels), "mesh_editable": False, "edit_policy": "edit_components_then_remesh", "ready": bool(validation.get("summary", {}).get("ready", True))}}


__all__ = ["ComponentParameterField", "ComponentParameterPanel", "ComponentParameterPanelFactory"]
