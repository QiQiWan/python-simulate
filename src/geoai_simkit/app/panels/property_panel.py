from __future__ import annotations

"""Property payload builder backed by GeoProjectDocument."""

from typing import Any

from geoai_simkit.app.geoproject_source import get_geoproject_document
from geoai_simkit.document.selection import SelectionRef
from geoai_simkit.geoproject import GeoProjectDocument


def _none_payload() -> dict[str, Any]:
    return {
        "title": "No selection",
        "entity": None,
        "sections": [
            {"title": "Hint", "rows": [{"name": "Action", "value": "Select a point, curve, surface, volume, phase, material, mesh item or result object."}]}
        ],
        "editable": [],
        "data_source": "GeoProjectDocument",
    }


def _selection_dict(ref: SelectionRef | Any) -> dict[str, Any]:
    if ref is None:
        return {}
    if hasattr(ref, "to_dict"):
        return dict(ref.to_dict())
    return {"entity_id": getattr(ref, "entity_id", None), "entity_type": getattr(ref, "entity_type", None), "source": getattr(ref, "source", None)}


def _rows(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"name": str(k), "value": v} for k, v in mapping.items()]


def _material_lookup(project: GeoProjectDocument, material_id: str) -> tuple[str, Any] | None:
    for category, bucket in (
        ("soil", project.material_library.soil_materials),
        ("plate", project.material_library.plate_materials),
        ("beam", project.material_library.beam_materials),
        ("interface", project.material_library.interface_materials),
    ):
        if material_id in bucket:
            return category, bucket[material_id]
    return None


def _resolve_ref(document: Any, selection: SelectionRef | None) -> SelectionRef | None:
    if selection is not None:
        return selection
    active = None
    try:
        active = getattr(getattr(document, "selection", None), "active", None)
    except Exception:
        active = None
    return active


def build_geoproject_property_payload(project: GeoProjectDocument, ref: SelectionRef | None = None) -> dict[str, Any]:
    if ref is None:
        return _none_payload()
    etype = str(ref.entity_type)
    eid = str(ref.entity_id)
    entity = _selection_dict(ref)

    if etype == "point" and eid in project.geometry_model.points:
        point = project.geometry_model.points[eid]
        return {"title": f"Point: {point.id}", "entity": entity, "data_source": "GeoProjectDocument.GeometryModel.Points", "sections": [
            {"title": "Coordinates", "rows": _rows({"x": point.x, "y": point.y, "z": point.z})},
            {"title": "Metadata", "rows": _rows(point.metadata)},
        ], "editable": ["x", "y", "z", "move_point"]}

    if etype in {"curve", "edge"} and eid in project.geometry_model.curves:
        curve = project.geometry_model.curves[eid]
        coords = []
        for pid in curve.point_ids:
            point = project.geometry_model.points.get(pid)
            if point is not None:
                coords.append({"name": pid, "value": [point.x, point.y, point.z]})
        return {"title": f"Curve: {curve.name}", "entity": entity, "data_source": "GeoProjectDocument.GeometryModel.Curves", "sections": [
            {"title": "Definition", "rows": _rows({"Kind": curve.kind, "Point IDs": list(curve.point_ids)})},
            {"title": "Coordinates", "rows": coords},
            {"title": "Metadata", "rows": _rows(curve.metadata)},
        ], "editable": ["kind", "point_ids"]}

    if etype == "surface" and eid in project.geometry_model.surfaces:
        surface = project.geometry_model.surfaces[eid]
        return {"title": f"Surface: {surface.name}", "entity": entity, "data_source": "GeoProjectDocument.GeometryModel.Surfaces", "sections": [
            {"title": "Definition", "rows": _rows({"Kind": surface.kind, "Point IDs": list(surface.point_ids), "Curve IDs": list(surface.curve_ids)})},
            {"title": "Metadata", "rows": _rows(surface.metadata)},
        ], "editable": ["kind", "point_ids", "curve_ids"]}

    if etype in {"volume", "block"} and eid in project.geometry_model.volumes:
        volume = project.geometry_model.volumes[eid]
        adjacent = project.topology_graph.adjacent_blocks(eid)
        active_in = []
        for stage in project.phases_in_order():
            snapshot = project.phase_manager.phase_state_snapshots.get(stage.id) or project.refresh_phase_snapshot(stage.id)
            if eid in snapshot.active_volume_ids:
                active_in.append(stage.id)
        material = _material_lookup(project, volume.material_id or "") if volume.material_id else None
        return {"title": f"Block: {volume.name}", "entity": entity, "data_source": "GeoProjectDocument.GeometryModel.Volumes", "sections": [
            {"title": "Geometry", "rows": _rows({"Role": volume.role, "Bounds": list(volume.bounds) if volume.bounds is not None else None, "Surface IDs": list(volume.surface_ids)})},
            {"title": "Engineering", "rows": _rows({"Material": volume.material_id or "<unassigned>", "Material category": None if material is None else material[0], "Adjacent volumes": adjacent})},
            {"title": "Construction phases", "rows": _rows({"Active in": active_in, "Current phase active": project.phase_manager.active_phase_id in active_in})},
            {"title": "Metadata", "rows": _rows(volume.metadata)},
        ], "editable": ["material_id", "visible", "stage_activation", "role"]}

    if etype in {"material", "soil_material", "plate_material", "beam_material", "interface_material"}:
        category = str(ref.metadata.get("category", "")) if getattr(ref, "metadata", None) else ""
        lookup = _material_lookup(project, eid)
        if lookup is not None:
            category, mat = lookup
            return {"title": f"Material: {mat.name}", "entity": entity, "data_source": f"GeoProjectDocument.MaterialLibrary.{category}", "sections": [
                {"title": "Definition", "rows": _rows({"ID": mat.id, "Name": mat.name, "Category": category, "Model type": mat.model_type, "Drainage": mat.drainage})},
                {"title": "Parameters", "rows": _rows(mat.parameters)},
                {"title": "Metadata", "rows": _rows(mat.metadata)},
            ], "editable": ["name", "model_type", "drainage", "parameters"]}

    if etype in {"stage", "phase"}:
        try:
            stage = project.get_phase(eid)
        except KeyError:
            stage = None
        if stage is not None:
            snapshot = project.phase_manager.phase_state_snapshots.get(stage.id) or project.refresh_phase_snapshot(stage.id)
            settings = project.phase_manager.calculation_settings.get(stage.id)
            return {"title": f"Phase: {stage.name}", "entity": entity, "data_source": "GeoProjectDocument.PhaseManager", "sections": [
                {"title": "Sequence", "rows": _rows({"ID": stage.id, "Predecessor": stage.predecessor_id, "Active": stage.id == project.phase_manager.active_phase_id, "Water level": stage.water_level})},
                {"title": "Snapshot", "rows": _rows({"Active volumes": len(snapshot.active_volume_ids), "Active structures": len(snapshot.active_structure_ids), "Active interfaces": len(snapshot.active_interface_ids), "Water condition": snapshot.water_condition_id})},
                {"title": "Calculation", "rows": [] if settings is None else _rows(settings.to_dict())},
                {"title": "Activation sets", "rows": _rows({"Inactive volumes": sorted(stage.inactive_blocks), "Explicit active volumes": sorted(stage.active_blocks), "Active supports": sorted(stage.active_supports), "Active interfaces": sorted(stage.active_interfaces), "Loads": sorted(stage.loads)})},
            ], "editable": ["stage_name", "predecessor_id", "water_level", "activation", "calculation_settings"]}

    if etype in {"plate", "beam", "embedded_beam", "anchor"}:
        bucket = {
            "plate": project.structure_model.plates,
            "beam": project.structure_model.beams,
            "embedded_beam": project.structure_model.embedded_beams,
            "anchor": project.structure_model.anchors,
        }[etype]
        if eid in bucket:
            row = bucket[eid]
            return {"title": f"Structure: {row.name}", "entity": entity, "data_source": "GeoProjectDocument.StructureModel", "sections": [
                {"title": "Definition", "rows": _rows({"Geometry ref": row.geometry_ref, "Material": row.material_id, "Active stages": list(row.active_stage_ids), "Release policy": row.release_policy})},
                {"title": "Metadata", "rows": _rows(row.metadata)},
            ], "editable": ["geometry_ref", "material_id", "active_stage_ids", "release_policy"]}

    if etype in {"interface", "structural_interface"} and eid in project.structure_model.structural_interfaces:
        row = project.structure_model.structural_interfaces[eid]
        return {"title": f"Interface: {row.name}", "entity": entity, "data_source": "GeoProjectDocument.StructureModel.StructuralInterfaces", "sections": [
            {"title": "Contact pair", "rows": _rows({"Master": row.master_ref, "Slave": row.slave_ref, "Material": row.material_id, "Mode": row.contact_mode})},
            {"title": "Activation", "rows": _rows({"Active stages": list(row.active_stage_ids)})},
            {"title": "Metadata", "rows": _rows(row.metadata)},
        ], "editable": ["master_ref", "slave_ref", "material_id", "contact_mode", "active_stage_ids"]}

    if etype in {"mesh", "mesh_settings"}:
        mesh = project.mesh_model.mesh_document
        return {"title": "Mesh model", "entity": entity, "data_source": "GeoProjectDocument.MeshModel", "sections": [
            {"title": "Settings", "rows": _rows(project.mesh_model.mesh_settings.to_dict())},
            {"title": "Mesh document", "rows": _rows({"Nodes": 0 if mesh is None else mesh.node_count, "Cells": 0 if mesh is None else mesh.cell_count})},
            {"title": "Quality", "rows": _rows(project.mesh_model.quality_report.to_dict())},
        ], "editable": ["global_size", "element_family", "local_size_fields", "preserve_interfaces"]}

    if etype in {"compiled_phase_model", "compiled"} and eid in project.solver_model.compiled_phase_models:
        compiled = project.solver_model.compiled_phase_models[eid]
        return {"title": f"Compiled phase: {compiled.phase_id}", "entity": entity, "data_source": "GeoProjectDocument.SolverModel.CompiledPhaseModels", "sections": [
            {"title": "Counts", "rows": _rows(compiled.to_dict())},
        ], "editable": []}

    if etype in {"result", "phase_result"} and eid in project.result_store.phase_results:
        result = project.result_store.phase_results[eid]
        return {"title": f"Result: {result.stage_id}", "entity": entity, "data_source": "GeoProjectDocument.ResultStore.PhaseResults", "sections": [
            {"title": "Engineering metrics", "rows": _rows(result.metrics)},
            {"title": "Support forces", "rows": _rows(result.support_forces)},
            {"title": "Fields", "rows": [{"name": key, "value": field.association} for key, field in result.fields.items()]},
        ], "editable": []}

    return {"title": getattr(ref, "display_name", None) or eid, "entity": entity, "data_source": "GeoProjectDocument", "sections": [{"title": "Raw metadata", "rows": _rows(dict(getattr(ref, "metadata", {}) or {}))}], "editable": []}


def build_property_payload(document: Any, selection: SelectionRef | None = None) -> dict[str, Any]:
    project = get_geoproject_document(document)
    return build_geoproject_property_payload(project, _resolve_ref(document, selection))


__all__ = ["build_property_payload", "build_geoproject_property_payload"]
