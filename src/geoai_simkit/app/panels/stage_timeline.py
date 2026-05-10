from __future__ import annotations

"""Stage timeline payloads backed by GeoProjectDocument.PhaseManager."""

from typing import Any

from geoai_simkit.app.geoproject_source import get_geoproject_document
from geoai_simkit.geoproject import GeoProjectDocument


def build_geoproject_stage_timeline(project: GeoProjectDocument) -> dict[str, Any]:
    all_volumes = set(project.geometry_model.volumes.keys())
    items: list[dict[str, Any]] = []
    for index, stage in enumerate(project.phases_in_order()):
        snapshot = project.phase_manager.phase_state_snapshots.get(stage.id) or project.refresh_phase_snapshot(stage.id)
        active = set(snapshot.active_volume_ids)
        inactive = all_volumes - active
        excavated = sorted(vid for vid in inactive if project.geometry_model.volumes.get(vid) is not None and project.geometry_model.volumes[vid].role == "excavation")
        settings = project.phase_manager.calculation_settings.get(stage.id)
        items.append({
            "index": index,
            "id": stage.id,
            "name": stage.name,
            "active": stage.id == project.phase_manager.active_phase_id,
            "predecessor_id": stage.predecessor_id,
            "active_volume_count": len(active),
            "inactive_volume_count": len(inactive),
            "excavated_volumes": excavated,
            "active_structure_count": len(snapshot.active_structure_ids),
            "active_interface_count": len(snapshot.active_interface_ids),
            "water_level": stage.water_level,
            "calculation_settings": None if settings is None else settings.to_dict(),
            "snapshot": snapshot.to_dict(),
            "metadata": dict(stage.metadata),
        })
    return {
        "contract": "geoproject_phase_timeline_v1",
        "data_source": "GeoProjectDocument.PhaseManager",
        "active_phase_id": project.phase_manager.active_phase_id,
        "count": len(items),
        "items": items,
    }


def build_stage_timeline(document: Any) -> dict[str, Any]:
    return build_geoproject_stage_timeline(get_geoproject_document(document))


__all__ = ["build_stage_timeline", "build_geoproject_stage_timeline"]
