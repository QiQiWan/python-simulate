from __future__ import annotations

"""Material editor payload and mutation helpers for GeoProjectDocument."""

from typing import Any

from geoai_simkit.app.geoproject_source import get_geoproject_document, mark_geoproject_dirty
from geoai_simkit.geoproject import GeoProjectDocument, MaterialRecord


def _bucket(project: GeoProjectDocument, category: str) -> dict[str, MaterialRecord]:
    category = category.lower().strip()
    if category in {"soil", "soil_material", "soil_materials"}:
        return project.material_library.soil_materials
    if category in {"plate", "plate_material", "plate_materials"}:
        return project.material_library.plate_materials
    if category in {"beam", "beam_material", "beam_materials", "embedded_beam", "anchor"}:
        return project.material_library.beam_materials
    if category in {"interface", "interface_material", "interface_materials"}:
        return project.material_library.interface_materials
    raise ValueError(f"Unknown material category: {category}")


def build_geoproject_material_editor(project: GeoProjectDocument) -> dict[str, Any]:
    categories = []
    for category, bucket in (
        ("soil", project.material_library.soil_materials),
        ("plate", project.material_library.plate_materials),
        ("beam", project.material_library.beam_materials),
        ("interface", project.material_library.interface_materials),
    ):
        categories.append({
            "category": category,
            "count": len(bucket),
            "materials": [{"category": category, **record.to_dict()} for record in bucket.values()],
        })
    assignments = []
    for volume in project.geometry_model.volumes.values():
        assignments.append({"entity_type": "volume", "entity_id": volume.id, "name": volume.name, "role": volume.role, "material_id": volume.material_id})
    for collection_name, bucket in (
        ("plate", project.structure_model.plates),
        ("beam", project.structure_model.beams),
        ("embedded_beam", project.structure_model.embedded_beams),
        ("anchor", project.structure_model.anchors),
    ):
        for item in bucket.values():
            assignments.append({"entity_type": collection_name, "entity_id": item.id, "name": item.name, "geometry_ref": item.geometry_ref, "material_id": item.material_id})
    for item in project.structure_model.structural_interfaces.values():
        assignments.append({"entity_type": "interface", "entity_id": item.id, "name": item.name, "master_ref": item.master_ref, "slave_ref": item.slave_ref, "material_id": item.material_id})
    return {
        "contract": "geoproject_material_editor_v2",
        "data_source": "GeoProjectDocument.MaterialLibrary",
        "categories": categories,
        "drainage_groundwater_properties": [row.to_dict() for row in project.material_library.drainage_groundwater_properties.values()],
        "assignments": assignments,
        "editable_actions": ["upsert_material", "delete_material", "assign_volume_material", "assign_structure_material", "assign_interface_material"],
    }


def build_material_editor(document: Any) -> dict[str, Any]:
    return build_geoproject_material_editor(get_geoproject_document(document))


def upsert_material(document: Any, category: str, material_id: str, *, name: str | None = None, model_type: str = "mohr_coulomb", parameters: dict[str, Any] | None = None, drainage: str = "drained", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    project = get_geoproject_document(document)
    material = MaterialRecord(id=str(material_id), name=name or str(material_id), model_type=str(model_type), parameters=dict(parameters or {}), drainage=str(drainage), metadata=dict(metadata or {}))
    project.upsert_material(category, material)
    project.mark_changed(["material"], action="upsert_material", affected_entities=[material.id])
    mark_geoproject_dirty(document, project)
    return {"ok": True, "category": category, "material": material.to_dict()}


def delete_material(document: Any, category: str, material_id: str) -> dict[str, Any]:
    project = get_geoproject_document(document)
    bucket = _bucket(project, category)
    removed = bucket.pop(str(material_id), None)
    project.mark_changed(["material"], action="delete_material", affected_entities=[material_id])
    mark_geoproject_dirty(document, project)
    return {"ok": removed is not None, "category": category, "material_id": material_id}


def assign_volume_material(document: Any, volume_id: str, material_id: str) -> dict[str, Any]:
    project = get_geoproject_document(document)
    volume = project.set_volume_material(volume_id, material_id)
    mark_geoproject_dirty(document, project)
    return {"ok": True, "volume": volume.to_dict()}


def assign_structure_material(document: Any, structure_id: str, material_id: str, *, category: str | None = None) -> dict[str, Any]:
    project = get_geoproject_document(document)
    record = project.set_structure_material(structure_id, material_id, category=category)
    mark_geoproject_dirty(document, project)
    return {"ok": True, "structure": record.to_dict(), "category": category}


def assign_interface_material(document: Any, interface_id: str, material_id: str) -> dict[str, Any]:
    project = get_geoproject_document(document)
    interface = project.set_interface_material(interface_id, material_id)
    mark_geoproject_dirty(document, project)
    return {"ok": True, "interface": interface.to_dict()}


__all__ = [
    "build_material_editor",
    "build_geoproject_material_editor",
    "upsert_material",
    "delete_material",
    "assign_volume_material",
    "assign_structure_material",
    "assign_interface_material",
]
