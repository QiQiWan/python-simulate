from __future__ import annotations

"""Result-viewer payload for the sixth phase of the PLAXIS-like workbench."""

from pathlib import Path
from typing import Any

from geoai_simkit.app.geoproject_source import get_geoproject_document, mark_geoproject_dirty
from geoai_simkit.commands import CommandStack, RunPreviewStageResultsCommand


def build_result_viewer(document: Any, *, phase_id: str | None = None, field_name: str | None = None) -> dict[str, Any]:
    project = get_geoproject_document(document)
    phases = project.phases_in_order()
    selected_phase = phase_id or project.phase_manager.active_phase_id or (phases[-1].id if phases else "")
    phase_rows = []
    field_rows = []
    metric_rows = []
    for stage in phases:
        result = project.result_store.phase_results.get(stage.id)
        phase_rows.append({
            "phase_id": stage.id,
            "name": stage.name,
            "has_result": result is not None,
            "metric_count": 0 if result is None else len(result.metrics),
            "field_count": 0 if result is None else len(result.fields),
        })
        if result is None:
            continue
        for key, value in result.metrics.items():
            metric_rows.append({"phase_id": stage.id, "name": key, "value": float(value)})
        for key, field in result.fields.items():
            field_rows.append({
                "phase_id": stage.id,
                "name": key,
                "association": field.association,
                "entity_count": len(field.entity_ids),
                "value_count": len(field.values),
                "components": field.components,
                "unit": field.metadata.get("unit", ""),
            })
    selected_result = project.result_store.phase_results.get(selected_phase)
    selected_field = None
    if selected_result is not None:
        selected_field = selected_result.fields.get(field_name or "") or next(iter(selected_result.fields.values()), None)
    return {
        "contract": "geoproject_result_viewer_v1",
        "data_source": "GeoProjectDocument.ResultStore",
        "active_phase_id": selected_phase,
        "available": bool(project.result_store.phase_results),
        "phase_rows": phase_rows,
        "metric_rows": metric_rows,
        "field_rows": field_rows,
        "curve_rows": [row.to_dict() for row in project.result_store.curves.values()],
        "section_rows": [row.to_dict() for row in project.result_store.sections.values()],
        "selected_field": None if selected_field is None else selected_field.to_dict(),
        "display_modes": ["deformed_shape", "contour", "section_cut", "probe", "curve"],
        "export_actions": ["export_legacy_vtk", "export_json_summary"],
    }


def generate_preview_results(document: Any) -> dict[str, Any]:
    project = get_geoproject_document(document)
    stack = CommandStack()
    result = stack.execute(RunPreviewStageResultsCommand(), project)
    mark_geoproject_dirty(document, project)
    return {"ok": result.ok, "command": result.to_dict(), "viewer": build_result_viewer(document)}


def export_result_summary_json(document: Any, path: str | Path) -> dict[str, Any]:
    import json

    payload = build_result_viewer(document)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(target), "phase_count": len(payload.get("phase_rows", []))}


def export_legacy_vtk(document: Any, path: str | Path, *, phase_id: str | None = None) -> dict[str, Any]:
    """Write a small ASCII legacy VTK file with mesh and phase scalar tags.

    This is deliberately conservative; richer VTK/ParaView bundles can still be
    produced by the existing export workflows.
    """

    project = get_geoproject_document(document)
    mesh = project.mesh_model.mesh_document
    if mesh is None:
        raise ValueError("No mesh is available for VTK export")
    phase = phase_id or project.phase_manager.active_phase_id or project.phase_manager.initial_phase.id
    snapshot = project.phase_manager.phase_state_snapshots.get(phase) or project.refresh_phase_snapshot(phase)
    block_ids = [str(v) for v in list(mesh.cell_tags.get("block_id", []) or [])]
    active = set(snapshot.active_volume_ids)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# vtk DataFile Version 3.0",
        f"geoai-simkit result export {phase}",
        "ASCII",
        "DATASET UNSTRUCTURED_GRID",
        f"POINTS {mesh.node_count} float",
    ]
    lines.extend(f"{x:g} {y:g} {z:g}" for x, y, z in mesh.nodes)
    total = sum(len(cell) + 1 for cell in mesh.cells)
    lines.append(f"CELLS {mesh.cell_count} {total}")
    lines.extend(" ".join([str(len(cell)), *[str(int(v)) for v in cell]]) for cell in mesh.cells)
    vtk_cell_types = {"tet4": 10, "hex8": 12, "tri3": 5, "quad4": 9, "line2": 3}
    lines.append(f"CELL_TYPES {mesh.cell_count}")
    lines.extend(str(vtk_cell_types.get(str(ct).lower(), 7)) for ct in mesh.cell_types)
    lines.append(f"CELL_DATA {mesh.cell_count}")
    lines.append("SCALARS phase_active int 1")
    lines.append("LOOKUP_TABLE default")
    lines.extend("1" if (block_ids[i] if i < len(block_ids) else "") in active else "0" for i in range(mesh.cell_count))
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(target), "cell_count": mesh.cell_count, "phase_id": phase}


__all__ = ["build_result_viewer", "generate_preview_results", "export_result_summary_json", "export_legacy_vtk"]
