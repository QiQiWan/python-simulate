from __future__ import annotations

"""Stage editor payload and mutation helpers for GeoProjectDocument."""

from typing import Any

from geoai_simkit.app.geoproject_source import get_geoproject_document, mark_geoproject_dirty
from geoai_simkit.geoproject import CalculationSettings, GeoProjectDocument


def build_geoproject_stage_editor(project: GeoProjectDocument) -> dict[str, Any]:
    timeline = []
    volumes = list(project.geometry_model.volumes.values())
    structures = [*project.structure_model.plates.values(), *project.structure_model.beams.values(), *project.structure_model.embedded_beams.values(), *project.structure_model.anchors.values()]
    for stage in project.phases_in_order():
        snapshot = project.phase_manager.phase_state_snapshots.get(stage.id) or project.refresh_phase_snapshot(stage.id)
        settings = project.phase_manager.calculation_settings.get(stage.id)
        timeline.append({
            "stage": stage.to_dict(),
            "snapshot": snapshot.to_dict(),
            "calculation_settings": None if settings is None else settings.to_dict(),
            "diff": {
                "inactive_volume_count": len(stage.inactive_blocks),
                "active_structure_count": len(stage.active_supports),
                "active_interface_count": len(stage.active_interfaces),
                "active_load_count": len(stage.loads),
                "water_condition_id": snapshot.water_condition_id,
            },
        })
    return {
        "contract": "geoproject_stage_editor_v2",
        "data_source": "GeoProjectDocument.PhaseManager",
        "active_phase_id": project.phase_manager.active_phase_id,
        "phases": timeline,
        "volume_palette": [{"id": v.id, "name": v.name, "role": v.role, "material_id": v.material_id} for v in volumes],
        "structure_palette": [{"id": s.id, "name": s.name, "geometry_ref": s.geometry_ref, "material_id": s.material_id} for s in structures],
        "interface_palette": [row.to_dict() for row in project.structure_model.structural_interfaces.values()],
        "load_palette": [row.to_dict() for row in project.solver_model.loads.values()],
        "water_condition_palette": [row.to_dict() for row in project.soil_model.water_conditions.values()],
        "editable_actions": [
            "add_phase",
            "clone_phase",
            "remove_phase",
            "set_active_phase",
            "set_phase_predecessor",
            "set_volume_activation",
            "set_structure_activation",
            "set_interface_activation",
            "set_load_activation",
            "set_water_condition",
            "update_calculation_settings",
        ],
    }


def build_stage_editor(document: Any) -> dict[str, Any]:
    return build_geoproject_stage_editor(get_geoproject_document(document))


def add_phase(document: Any, phase_id: str, *, name: str | None = None, predecessor_id: str | None = None) -> dict[str, Any]:
    project = get_geoproject_document(document)
    stage = project.add_phase(phase_id, name=name, predecessor_id=predecessor_id)
    project.mark_changed(["phase"], action="add_phase", affected_entities=[phase_id])
    mark_geoproject_dirty(document, project)
    return {"ok": True, "stage": stage.to_dict()}


def clone_phase(document: Any, source_phase_id: str, new_phase_id: str, *, name: str | None = None) -> dict[str, Any]:
    project = get_geoproject_document(document)
    stage = project.add_phase(new_phase_id, name=name, copy_from=source_phase_id)
    project.mark_changed(["phase"], action="clone_phase", affected_entities=[source_phase_id, new_phase_id])
    mark_geoproject_dirty(document, project)
    return {"ok": True, "stage": stage.to_dict()}


def remove_phase(document: Any, phase_id: str) -> dict[str, Any]:
    project = get_geoproject_document(document)
    result = project.remove_phase(phase_id)
    project.mark_changed(["phase"], action="remove_phase", affected_entities=[phase_id])
    mark_geoproject_dirty(document, project)
    return result


def set_active_phase(document: Any, phase_id: str) -> dict[str, Any]:
    project = get_geoproject_document(document)
    stage = project.set_active_phase(phase_id)
    mark_geoproject_dirty(document, project)
    return {"ok": True, "active_phase_id": stage.id}


def set_phase_predecessor(document: Any, phase_id: str, predecessor_id: str | None) -> dict[str, Any]:
    project = get_geoproject_document(document)
    stage = project.set_phase_predecessor(phase_id, predecessor_id)
    project.mark_changed(["phase"], action="set_phase_predecessor", affected_entities=[phase_id])
    mark_geoproject_dirty(document, project)
    return {"ok": True, "stage": stage.to_dict()}


def set_volume_activation(document: Any, phase_id: str, volume_id: str, active: bool) -> dict[str, Any]:
    project = get_geoproject_document(document)
    snapshot = project.set_phase_volume_activation(phase_id, volume_id, active)
    mark_geoproject_dirty(document, project)
    return {"ok": True, "snapshot": snapshot.to_dict()}


def set_structure_activation(document: Any, phase_id: str, structure_id: str, active: bool) -> dict[str, Any]:
    project = get_geoproject_document(document)
    snapshot = project.set_phase_structure_activation(phase_id, structure_id, active)
    mark_geoproject_dirty(document, project)
    return {"ok": True, "snapshot": snapshot.to_dict()}


def set_interface_activation(document: Any, phase_id: str, interface_id: str, active: bool) -> dict[str, Any]:
    project = get_geoproject_document(document)
    snapshot = project.set_phase_interface_activation(phase_id, interface_id, active)
    mark_geoproject_dirty(document, project)
    return {"ok": True, "snapshot": snapshot.to_dict()}


def set_load_activation(document: Any, phase_id: str, load_id: str, active: bool) -> dict[str, Any]:
    project = get_geoproject_document(document)
    snapshot = project.set_phase_load_activation(phase_id, load_id, active)
    mark_geoproject_dirty(document, project)
    return {"ok": True, "snapshot": snapshot.to_dict()}


def set_water_condition(document: Any, phase_id: str, water_condition_id: str | None = None, *, water_level: float | None = None) -> dict[str, Any]:
    project = get_geoproject_document(document)
    snapshot = project.set_phase_water_condition(phase_id, water_condition_id, water_level=water_level)
    mark_geoproject_dirty(document, project)
    return {"ok": True, "snapshot": snapshot.to_dict()}


def update_calculation_settings(document: Any, phase_id: str, **kwargs: Any) -> dict[str, Any]:
    project = get_geoproject_document(document)
    current = project.phase_manager.calculation_settings.get(phase_id) or CalculationSettings()
    payload = current.to_dict()
    payload.update(kwargs)
    payload.pop("metadata", None)
    metadata = dict(current.metadata)
    metadata.update(dict(kwargs.get("metadata", {}) or {}))
    settings = CalculationSettings.from_dict({**payload, "metadata": metadata})
    project.phase_manager.calculation_settings[phase_id] = settings
    project.mark_changed(["phase", "solver"], action="update_calculation_settings", affected_entities=[phase_id])
    mark_geoproject_dirty(document, project)
    return {"ok": True, "phase_id": phase_id, "calculation_settings": settings.to_dict()}


__all__ = [
    "build_stage_editor",
    "build_geoproject_stage_editor",
    "add_phase",
    "clone_phase",
    "remove_phase",
    "set_active_phase",
    "set_phase_predecessor",
    "set_volume_activation",
    "set_structure_activation",
    "set_interface_activation",
    "set_load_activation",
    "set_water_condition",
    "update_calculation_settings",
]
