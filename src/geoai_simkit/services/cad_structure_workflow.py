from __future__ import annotations

"""Headless helpers for structure creation and material assignment from CAD selections."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.geoproject import GeoProjectDocument, MaterialRecord

CAD_STRUCTURE_WORKFLOW_CONTRACT = "geoai_simkit_cad_structure_workflow_v7"


@dataclass(slots=True)
class StructureContextAction:
    action_id: str
    label: str
    target_kind: str
    semantic_type: str = ""
    material_category: str = ""
    enabled: bool = True
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "label": self.label,
            "target_kind": self.target_kind,
            "semantic_type": self.semantic_type,
            "material_category": self.material_category,
            "enabled": bool(self.enabled),
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


def _entity_kind(project: GeoProjectDocument, entity_id: str, fallback: str = "") -> str:
    if entity_id in project.geometry_model.points:
        return "point"
    if entity_id in project.geometry_model.curves:
        return "curve"
    if entity_id in project.geometry_model.surfaces:
        return "surface"
    if entity_id in project.geometry_model.volumes:
        return "volume"
    if project.get_structure_record(entity_id) is not None:
        return "structure"
    if entity_id in project.structure_model.structural_interfaces:
        return "interface"
    return str(fallback or "unknown")


def context_actions_for_selection(project: GeoProjectDocument, entity_id: str = "", kind: str = "", *, material_id: str = "") -> list[StructureContextAction]:
    resolved = _entity_kind(project, entity_id, kind) if entity_id else str(kind or "empty")
    actions: list[StructureContextAction] = []
    if not entity_id:
        actions.extend([
            StructureContextAction("activate_point_tool", "创建点", "empty", metadata={"tool": "point"}),
            StructureContextAction("activate_line_tool", "创建线", "empty", metadata={"tool": "line"}),
            StructureContextAction("activate_surface_tool", "创建面", "empty", metadata={"tool": "surface"}),
            StructureContextAction("activate_block_tool", "创建体", "empty", metadata={"tool": "block_box"}),
        ])
        return actions
    if resolved == "volume":
        actions.extend([
            StructureContextAction("promote_volume_soil", "设为土体/地层体", "volume", semantic_type="soil_volume", material_category="soil"),
            StructureContextAction("promote_volume_excavation", "设为开挖体", "volume", semantic_type="excavation", material_category="soil"),
            StructureContextAction("promote_volume_concrete", "设为混凝土结构体", "volume", semantic_type="concrete_block", material_category="plate"),
        ])
    elif resolved == "surface":
        actions.extend([
            StructureContextAction("promote_surface_wall", "由面创建墙/板", "surface", semantic_type="wall", material_category="plate"),
            StructureContextAction("promote_surface_interface", "由面创建接触/界面", "surface", semantic_type="interface", material_category="interface"),
            StructureContextAction("promote_surface_load", "由面创建面荷载候选", "surface", semantic_type="load_surface", material_category=""),
        ])
    elif resolved == "curve":
        actions.extend([
            StructureContextAction("promote_curve_beam", "由线创建梁/支撑", "curve", semantic_type="beam", material_category="beam"),
            StructureContextAction("promote_curve_anchor", "由线创建锚杆", "curve", semantic_type="anchor", material_category="beam"),
            StructureContextAction("promote_curve_pile", "由线创建桩/嵌入梁", "curve", semantic_type="embedded_beam", material_category="beam"),
        ])
    elif resolved == "point":
        actions.extend([
            StructureContextAction("mark_control_point", "设为控制点/监测点", "point", semantic_type="control_point"),
        ])
    if material_id:
        actions.append(StructureContextAction("assign_material", f"赋材料 {material_id}", resolved, material_category="auto", metadata={"material_id": material_id}))
    return actions


def apply_structure_context_action(project: GeoProjectDocument, entity_id: str, action_id: str, *, material_id: str = "", stage_id: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    actions = {row.action_id: row for row in context_actions_for_selection(project, entity_id, material_id=material_id)}
    action = actions.get(str(action_id))
    if action is None:
        raise ValueError(f"Unsupported structure context action: {action_id}")
    if action.semantic_type and not action.action_id.startswith("promote_surface_load"):
        return project.classify_geometry_entity(
            entity_id,
            action.semantic_type,
            material_id=material_id or None,
            stage_id=stage_id or None,
            metadata={"created_by": "cad_structure_context_menu", "action_id": action_id, **dict(metadata or {})},
        )
    if action.action_id == "assign_material" and material_id:
        return project.assign_entity_material(entity_id, material_id)
    if action.action_id == "promote_surface_load":
        surface = project.geometry_model.surfaces.get(entity_id)
        if surface is None:
            raise KeyError(f"Surface not found: {entity_id}")
        surface.metadata.update({"semantic_type": "load_surface", "load_candidate": True, **dict(metadata or {})})
        project.mark_changed(["geometry", "solver", "topology"], action="mark_load_surface", affected_entities=[entity_id])
        return {"ok": True, "entity_type": "surface", "entity_id": entity_id, "semantic_type": "load_surface", "surface": surface.to_dict()}
    raise ValueError(f"Action does not mutate project directly: {action_id}")


def ensure_default_engineering_materials(project: GeoProjectDocument) -> dict[str, Any]:
    defaults = [
        ("soil", MaterialRecord("soil_default", "默认土体", "mohr_coulomb", {"gamma_unsat": 18.0, "gamma_sat": 20.0, "E_ref": 30000.0, "nu": 0.3, "c_ref": 10.0, "phi": 30.0}, "drained", {"family": "soil"})),
        ("soil", MaterialRecord("clay_soft", "软黏土", "mohr_coulomb", {"gamma_unsat": 17.0, "gamma_sat": 19.0, "E_ref": 12000.0, "nu": 0.35, "c_ref": 18.0, "phi": 18.0}, "undrained", {"family": "soil"})),
        ("soil", MaterialRecord("sand_dense", "密砂", "mohr_coulomb", {"gamma_unsat": 19.0, "gamma_sat": 21.0, "E_ref": 45000.0, "nu": 0.28, "c_ref": 2.0, "phi": 36.0}, "drained", {"family": "soil"})),
        ("plate", MaterialRecord("concrete_c30", "C30 混凝土/墙板", "linear_elastic", {"E": 3.0e7, "nu": 0.2, "gamma": 25.0}, "not_applicable", {"family": "wall_plate"})),
        ("beam", MaterialRecord("steel_q355", "Q355 钢/梁锚杆", "linear_elastic", {"E": 2.06e8, "nu": 0.3, "gamma": 78.5}, "not_applicable", {"family": "beam_anchor"})),
        ("interface", MaterialRecord("interface_default", "默认摩擦界面", "interface_frictional", {"R_inter": 0.67, "kn": 1.0e7, "ks": 3.0e6}, "not_applicable", {"family": "interface"})),
    ]
    created: list[str] = []
    for category, material in defaults:
        if material.id not in project.material_library.material_ids():
            project.upsert_material(category, material)
            created.append(material.id)
    if created:
        project.mark_changed(["material"], action="ensure_default_engineering_materials", affected_entities=created)
    return {"ok": True, "created": created, "material_count": len(project.material_library.material_ids())}


def auto_assign_materials_by_geometry_role(project: GeoProjectDocument) -> dict[str, Any]:
    ensure_default_engineering_materials(project)
    assigned: list[dict[str, str]] = []
    for volume in project.geometry_model.volumes.values():
        role = str(volume.role or volume.metadata.get("semantic_type") or "").lower()
        if not volume.material_id:
            if role in {"soil", "geology", "rock", "stratum", "geological_volume"}:
                material_id = "soil_default"
            elif role in {"excavation"}:
                material_id = "soil_default"
            elif role in {"structure", "concrete_block", "wall"}:
                material_id = "concrete_c30"
            else:
                material_id = "soil_default"
            project.assign_entity_material(volume.id, material_id)
            assigned.append({"entity_id": volume.id, "material_id": material_id})
    for bucket, material_id in ((project.structure_model.plates, "concrete_c30"), (project.structure_model.beams, "steel_q355"), (project.structure_model.embedded_beams, "steel_q355"), (project.structure_model.anchors, "steel_q355")):
        for record in bucket.values():
            if not record.material_id:
                project.assign_entity_material(record.id, material_id)
                assigned.append({"entity_id": record.id, "material_id": material_id})
    for record in project.structure_model.structural_interfaces.values():
        if not record.material_id:
            project.assign_entity_material(record.id, "interface_default")
            assigned.append({"entity_id": record.id, "material_id": "interface_default"})
    return {"ok": True, "assigned": assigned, "assigned_count": len(assigned)}


DIRECT_MOUSE_MODELING_DIAGNOSTICS = [
    {
        "code": "display_actor_is_not_an_editor_object",
        "reason": "PyVista/VTK actors can be rendered without owning a mutable GeoProjectDocument entity. Mouse editing only works when actor/cell metadata resolves to point/curve/surface/volume IDs.",
        "required_fix": "bind every viewport primitive to entity_id, kind, topology_id and source_entity_id, then route picks through SelectionController.",
    },
    {
        "code": "tool_activation_not_visible_enough",
        "reason": "Point/line/surface/block tools existed in the runtime, but the structure workflow needed a persistent panel that shows the active creation mode and expected click sequence.",
        "required_fix": "expose direct creation buttons in the structure panel and mirror them in the right-click menu.",
    },
    {
        "code": "right_click_was_action_only",
        "reason": "Right-click actions promoted geometry only after a valid entity was already selected or picked; empty-space right-click did not make the creation workflow obvious.",
        "required_fix": "show creation actions on empty-space right-click and structure-promotion actions on selected point/curve/surface/volume.",
    },
    {
        "code": "material_assignment_not_layer_aware",
        "reason": "The older quick assignment mainly used geometry role. Recognized borehole/stratum/layer metadata should drive soil materials, while structure type should drive wall/beam/anchor/interface materials.",
        "required_fix": "derive material candidates from soil clusters, borehole layers, layer_id metadata, volume centroid depth and structure category.",
    },
]

STRUCTURE_MODELING_UI_ELEMENTS = [
    {"area": "structure_panel", "element": "direct_creation_buttons", "items": ["create_point", "create_line", "create_surface", "create_volume"], "purpose": "activate mouse tools without hunting through generic toolbar groups"},
    {"area": "structure_panel", "element": "active_tool_hint", "items": ["current_tool", "click_sequence", "workplane", "snap"], "purpose": "make the viewport state understandable before the first click"},
    {"area": "viewport_context_menu", "element": "promote_geometry_actions", "items": ["curve_to_beam", "curve_to_anchor", "surface_to_wall", "surface_to_interface", "volume_to_soil", "volume_to_structure"], "purpose": "turn raw geometry into engineering objects from the mouse"},
    {"area": "material_library", "element": "engineering_material_catalog", "items": ["soil", "wall_plate", "beam_strut_anchor", "interface"], "purpose": "manage all materials in one place"},
    {"area": "material_library", "element": "quick_assignment_buttons", "items": ["assign_to_selection", "assign_by_recognized_layer", "assign_by_structure_type"], "purpose": "quickly bind strata and structures after recognition"},
]


def _all_borehole_layers(project: GeoProjectDocument) -> list[Any]:
    layers: list[Any] = []
    for borehole in project.soil_model.boreholes.values():
        layers.extend(list(borehole.layers or []))
    return layers


def _volume_mid_z(volume: Any) -> float | None:
    bounds = getattr(volume, "bounds", None)
    if bounds and len(bounds) >= 6:
        return 0.5 * (float(bounds[4]) + float(bounds[5]))
    metadata = dict(getattr(volume, "metadata", {}) or {})
    for key in ("z", "center_z", "mid_z"):
        if key in metadata:
            try:
                return float(metadata[key])
            except Exception:
                pass
    return None


def _material_from_depth(project: GeoProjectDocument, z: float | None) -> str:
    if z is None:
        return "soil_default"
    for layer in _all_borehole_layers(project):
        top = float(getattr(layer, "top", 0.0))
        bottom = float(getattr(layer, "bottom", 0.0))
        lo, hi = min(top, bottom), max(top, bottom)
        if lo <= float(z) <= hi:
            return str(getattr(layer, "material_id", "soil_default") or "soil_default")
    return "soil_default"


def _material_from_layer_metadata(project: GeoProjectDocument, volume: Any) -> str | None:
    metadata = dict(getattr(volume, "metadata", {}) or {})
    candidates = [
        metadata.get("material_id"),
        metadata.get("layer_material_id"),
        metadata.get("stratum_material_id"),
        metadata.get("layer_id"),
        metadata.get("stratum_id"),
    ]
    for cluster in project.soil_model.soil_clusters.values():
        if volume.id in cluster.volume_ids and cluster.material_id:
            candidates.insert(0, cluster.material_id)
    material_ids = set(project.material_library.material_ids())
    for item in candidates:
        if item and str(item) in material_ids:
            return str(item)
    return None


def recommended_material_for_entity(project: GeoProjectDocument, entity_id: str, *, kind: str = "") -> dict[str, Any]:
    """Return a deterministic material recommendation for GUI previews/actions."""

    ensure_default_engineering_materials(project)
    if entity_id in project.geometry_model.volumes:
        volume = project.geometry_model.volumes[entity_id]
        role = str(volume.role or volume.metadata.get("semantic_type") or kind or "").lower()
        if role in {"structure", "wall", "concrete_block", "plate", "slab"}:
            return {"entity_id": entity_id, "entity_type": "volume", "material_id": "concrete_c30", "category": "plate", "reason": "structure_volume"}
        if role in {"excavation"}:
            return {"entity_id": entity_id, "entity_type": "volume", "material_id": "soil_default", "category": "soil", "reason": "excavation_placeholder"}
        material_id = _material_from_layer_metadata(project, volume) or _material_from_depth(project, _volume_mid_z(volume))
        return {"entity_id": entity_id, "entity_type": "volume", "material_id": material_id, "category": "soil", "reason": "recognized_layer_or_depth"}
    record = project.get_structure_record(entity_id)
    if record is not None:
        semantic = str(record.metadata.get("semantic_type") or kind or "").lower()
        if semantic in {"wall", "plate", "slab", "diaphragm_wall", "retaining_wall"}:
            return {"entity_id": entity_id, "entity_type": "structure", "material_id": "concrete_c30", "category": "plate", "reason": "plate_wall_structure"}
        return {"entity_id": entity_id, "entity_type": "structure", "material_id": "steel_q355", "category": "beam", "reason": "beam_anchor_structure"}
    if entity_id in project.structure_model.structural_interfaces:
        return {"entity_id": entity_id, "entity_type": "interface", "material_id": "interface_default", "category": "interface", "reason": "interface"}
    if entity_id in project.geometry_model.surfaces:
        surface = project.geometry_model.surfaces[entity_id]
        semantic = str(surface.kind or surface.metadata.get("semantic_type") or kind or "").lower()
        if semantic in {"wall", "plate", "slab", "diaphragm_wall", "retaining_wall"}:
            return {"entity_id": entity_id, "entity_type": "surface", "material_id": "concrete_c30", "category": "plate", "reason": "surface_wall_candidate"}
        if semantic in {"interface", "contact_interface"}:
            return {"entity_id": entity_id, "entity_type": "surface", "material_id": "interface_default", "category": "interface", "reason": "surface_interface_candidate"}
        return {"entity_id": entity_id, "entity_type": "surface", "material_id": "concrete_c30", "category": "plate", "reason": "surface_default_plate"}
    if entity_id in project.geometry_model.curves:
        curve = project.geometry_model.curves[entity_id]
        semantic = str(curve.kind or curve.metadata.get("semantic_type") or kind or "").lower()
        material_id = "steel_q355" if semantic in {"beam", "strut", "support", "pile", "embedded_beam", "anchor"} else "steel_q355"
        return {"entity_id": entity_id, "entity_type": "curve", "material_id": material_id, "category": "beam", "reason": "curve_structure_candidate"}
    return {"entity_id": entity_id, "entity_type": kind or "unknown", "material_id": "soil_default", "category": "soil", "reason": "fallback"}


def promote_geometry_to_structure(project: GeoProjectDocument, entity_id: str, semantic_type: str, *, material_id: str = "", stage_id: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Promote a raw point/curve/surface/volume to the requested engineering semantic."""

    semantic = str(semantic_type or "").strip().lower()
    if not semantic:
        raise ValueError("semantic_type is required")
    if not material_id:
        rec = recommended_material_for_entity(project, entity_id, kind=semantic)
        material_id = str(rec.get("material_id") or "")
    return project.classify_geometry_entity(
        entity_id,
        semantic,
        material_id=material_id or None,
        stage_id=stage_id or None,
        metadata={"created_by": "structure_modeling_panel", **dict(metadata or {})},
    )


def auto_assign_materials_by_recognized_strata_and_structures(project: GeoProjectDocument, *, overwrite: bool = False) -> dict[str, Any]:
    """Layer-aware material assignment for soil volumes plus type-aware structure assignment."""

    ensure_default_engineering_materials(project)
    assigned: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for volume in project.geometry_model.volumes.values():
        if volume.material_id and not overwrite:
            skipped.append({"entity_id": volume.id, "reason": "existing_material"})
            continue
        recommendation = recommended_material_for_entity(project, volume.id)
        material_id = str(recommendation.get("material_id") or "soil_default")
        project.assign_entity_material(volume.id, material_id)
        assigned.append({"entity_id": volume.id, "entity_type": "volume", "material_id": material_id, "reason": str(recommendation.get("reason", ""))})

    for bucket_name, bucket in (
        ("plate", project.structure_model.plates),
        ("beam", project.structure_model.beams),
        ("embedded_beam", project.structure_model.embedded_beams),
        ("anchor", project.structure_model.anchors),
    ):
        for record in bucket.values():
            if record.material_id and not overwrite:
                skipped.append({"entity_id": record.id, "reason": "existing_material"})
                continue
            recommendation = recommended_material_for_entity(project, record.id, kind=bucket_name)
            material_id = str(recommendation.get("material_id") or ("concrete_c30" if bucket_name == "plate" else "steel_q355"))
            project.assign_entity_material(record.id, material_id, category=str(recommendation.get("category") or ("plate" if bucket_name == "plate" else "beam")))
            assigned.append({"entity_id": record.id, "entity_type": bucket_name, "material_id": material_id, "reason": str(recommendation.get("reason", ""))})

    for interface in project.structure_model.structural_interfaces.values():
        if interface.material_id and not overwrite:
            skipped.append({"entity_id": interface.id, "reason": "existing_material"})
            continue
        project.assign_entity_material(interface.id, "interface_default", category="interface")
        assigned.append({"entity_id": interface.id, "entity_type": "interface", "material_id": "interface_default", "reason": "interface"})

    return {"ok": True, "assigned": assigned, "assigned_count": len(assigned), "skipped": skipped, "skipped_count": len(skipped), "overwrite": bool(overwrite)}


def build_structure_mouse_interaction_payload(project: GeoProjectDocument) -> dict[str, Any]:
    ensure_default_engineering_materials(project)
    material_counts = {
        "soil": len(project.material_library.soil_materials),
        "wall_plate": len(project.material_library.plate_materials),
        "beam_strut_anchor": len(project.material_library.beam_materials),
        "interface": len(project.material_library.interface_materials),
    }
    return {
        "contract": "geoai_simkit_structure_mouse_interaction_v1",
        "why_visualization_was_not_enough": list(DIRECT_MOUSE_MODELING_DIAGNOSTICS),
        "required_ui_elements": list(STRUCTURE_MODELING_UI_ELEMENTS),
        "direct_creation_tools": [
            {"tool": "point", "label": "创建点", "click_sequence": "移动预览，左键创建", "auto_select_after_create": True},
            {"tool": "line", "label": "创建线", "click_sequence": "左键起点，再移动预览，左键终点", "auto_select_after_create": True},
            {"tool": "surface", "label": "创建面", "click_sequence": "左键逐点，移动预览，右键或 Enter 完成", "auto_select_after_create": True},
            {"tool": "block_box", "label": "创建体", "click_sequence": "左键第一角点，移动预览，左键对角点", "auto_select_after_create": True},
        ],
        "interaction_feedback": {
            "workplane_grid": ["XZ", "XY", "YZ"],
            "snap_toggle": True,
            "snap_modes": ["grid", "endpoint", "midpoint", "wall_endpoint", "beam_endpoint", "anchor_endpoint", "stratum_boundary_intersection", "excavation_contour_intersection"],
            "engineering_snap_targets": ["墙端点", "梁端点", "锚杆端点", "地层边界交点", "开挖轮廓线交点"],
            "constraint_snap_modes": ["horizontal", "vertical", "along_edge", "along_normal"],
            "constraint_gestures": {"shift": "horizontal", "ctrl": "vertical", "explicit_modes": ["along_edge", "along_normal"]},
            "constraint_locking": {
                "explicit_toolbar": ["lock_along_edge", "lock_along_normal", "unlock"],
                "right_click_menu": ["lock_along_edge", "lock_along_normal", "unlock"],
                "continuous_tools": ["point", "line", "surface", "block_box"],
                "visual_feedback": ["locked_edge_highlight", "locked_normal_arrow", "continuous_placement_trail", "unlock_feedback"],
                "status_label": True,
            },
            "grid_snap_visible_point": True,
            "endpoint_midpoint_snap_hints": True,
            "engineering_snap_hints": True,
            "constraint_snap_hints": True,
            "screen_space_crosshair": True,
            "hover_highlight": True,
            "cursor_preview": ["point", "line", "surface", "block_box"],
            "surface_right_click_completion_menu": ["finish", "undo_last_point", "cancel"],
            "right_click_selects_before_menu": True,
            "created_entity_auto_selection": True,
        },
        "right_click_promotions": {
            "point": ["control_point", "monitoring_point"],
            "curve": ["beam", "strut", "anchor", "embedded_beam"],
            "surface": ["wall", "plate", "interface", "load_surface"],
            "volume": ["soil_volume", "excavation", "concrete_block"],
        },
        "material_management": {
            "single_catalog": True,
            "categories": ["soil", "wall_plate", "beam_strut_anchor", "interface"],
            "material_counts": material_counts,
            "quick_assignment": ["recognized_strata", "structure_type", "current_selection"],
        },
    }


def build_cad_structure_workflow_payload(project: GeoProjectDocument) -> dict[str, Any]:
    return {
        "contract": CAD_STRUCTURE_WORKFLOW_CONTRACT,
        "structure_mouse_interaction": build_structure_mouse_interaction_payload(project),
        "actions_by_kind": {
            "empty": [row.to_dict() for row in context_actions_for_selection(project)],
            "point": [row.to_dict() for row in context_actions_for_selection(project, "__point__", "point")],
            "curve": [row.to_dict() for row in context_actions_for_selection(project, "__curve__", "curve")],
            "surface": [row.to_dict() for row in context_actions_for_selection(project, "__surface__", "surface")],
            "volume": [row.to_dict() for row in context_actions_for_selection(project, "__volume__", "volume")],
        },
        "material_categories": ["soil", "plate", "beam", "interface"],
        "quick_assignments": ["assign_material_to_selection", "auto_assign_recognized_strata_and_structures", "ensure_default_engineering_materials"],
        "diagnostics": list(DIRECT_MOUSE_MODELING_DIAGNOSTICS),
    }


__all__ = [
    "CAD_STRUCTURE_WORKFLOW_CONTRACT",
    "StructureContextAction",
    "context_actions_for_selection",
    "apply_structure_context_action",
    "ensure_default_engineering_materials",
    "auto_assign_materials_by_geometry_role",
    "auto_assign_materials_by_recognized_strata_and_structures",
    "recommended_material_for_entity",
    "promote_geometry_to_structure",
    "build_structure_mouse_interaction_payload",
    "build_cad_structure_workflow_payload",
]
