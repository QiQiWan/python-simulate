from __future__ import annotations

"""Semantic assignment payload and mutation helpers for raw geometry."""

from typing import Any

from geoai_simkit.app.geoproject_source import get_geoproject_document, mark_geoproject_dirty


_VOLUME_SEMANTICS = ("soil_volume", "geological_volume", "stratum", "rock", "excavation", "concrete_block")
_SURFACE_SEMANTICS = ("wall", "diaphragm_wall", "retaining_wall", "plate", "slab", "liner", "interface")
_CURVE_SEMANTICS = ("beam", "strut", "support", "anchor", "pile", "embedded_beam")
_POINT_SEMANTICS = ("borehole_point", "control_point", "monitoring_point", "load_point")


def build_semantic_assignment_panel(document: Any) -> dict[str, Any]:
    project = get_geoproject_document(document)
    raw_entities = []
    for point_id, point in project.geometry_model.points.items():
        raw_entities.append({"entity_type": "point", "entity_id": point_id, "name": point_id, "semantic_type": point.metadata.get("semantic_type", ""), "allowed_semantics": list(_POINT_SEMANTICS)})
    for curve_id, curve in project.geometry_model.curves.items():
        raw_entities.append({"entity_type": "curve", "entity_id": curve_id, "name": curve.name, "semantic_type": curve.kind, "allowed_semantics": list(_CURVE_SEMANTICS)})
    for surface_id, surface in project.geometry_model.surfaces.items():
        raw_entities.append({"entity_type": "surface", "entity_id": surface_id, "name": surface.name, "semantic_type": surface.kind, "allowed_semantics": list(_SURFACE_SEMANTICS)})
    for volume_id, volume in project.geometry_model.volumes.items():
        raw_entities.append({"entity_type": "volume", "entity_id": volume_id, "name": volume.name, "semantic_type": volume.role, "material_id": volume.material_id, "allowed_semantics": list(_VOLUME_SEMANTICS)})
    return {
        "contract": "semantic_assignment_panel_v1",
        "data_source": "GeoProjectDocument.GeometryModel + semantic layer",
        "raw_entity_count": len(raw_entities),
        "raw_entities": raw_entities,
        "structure_summary": {
            "plates": len(project.structure_model.plates),
            "beams": len(project.structure_model.beams),
            "embedded_beams": len(project.structure_model.embedded_beams),
            "anchors": len(project.structure_model.anchors),
            "interfaces": len(project.structure_model.structural_interfaces),
        },
        "soil_cluster_count": len(project.soil_model.soil_clusters),
        "editable_actions": ["assign_geometry_semantic", "assign_entity_material"],
    }


def assign_geometry_semantic(document: Any, entity_id: str, semantic_type: str, *, material_id: str | None = None, section_id: str | None = None, stage_id: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    project = get_geoproject_document(document)
    payload = project.classify_geometry_entity(entity_id, semantic_type, material_id=material_id, section_id=section_id, stage_id=stage_id, metadata=dict(metadata or {}))
    mark_geoproject_dirty(document, project)
    return payload


def assign_entity_material(document: Any, entity_id: str, material_id: str, *, category: str | None = None) -> dict[str, Any]:
    project = get_geoproject_document(document)
    payload = project.assign_entity_material(entity_id, material_id, category=category)
    mark_geoproject_dirty(document, project)
    return payload


__all__ = ["build_semantic_assignment_panel", "assign_geometry_semantic", "assign_entity_material"]
