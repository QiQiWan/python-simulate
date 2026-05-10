from __future__ import annotations

"""Smoke test for the GeoProjectDocument-native workflow.

The test avoids GUI event loops and verifies the native document, command,
transaction, editor and solver-compiler contracts directly.
"""

import json
from pathlib import Path

from geoai_simkit.app.panels.material_editor import assign_structure_material, build_geoproject_material_editor
from geoai_simkit.app.panels.solver_compiler import build_geoproject_solver_compiler
from geoai_simkit.app.panels.stage_editor import (
    build_geoproject_stage_editor,
    set_interface_activation,
    set_load_activation,
    set_structure_activation,
    set_water_condition,
)
from geoai_simkit.app.visual_modeling_system import VisualModelingSystem
from geoai_simkit.commands import GeneratePreviewMeshCommand, RunPreviewStageResultsCommand
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.geoproject import GeoProjectDocument, GeometryCurve, StructureRecord, get_dirty_graph, get_invalidation_graph


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
EXPORTS = ROOT / "exports"
REPORTS.mkdir(exist_ok=True)
EXPORTS.mkdir(exist_ok=True)


def _first(values: list[str]) -> str | None:
    return values[0] if values else None


def main() -> int:
    document = GeoProjectDocument.create_foundation_pit({"dimension": "3d", "depth": 9.0}, name="native-smoke-geoproject")
    document.populate_default_framework_content()

    # Verify the visual facade is now typed around GeoProjectDocument without opening a GUI.
    visual_default_type = type(VisualModelingSystem.__dataclass_fields__["document"].default_factory()).__name__  # type: ignore[attr-defined]

    support_axis_id = "support_axis_smoke"
    support_id = "beam_smoke_strut"
    document.geometry_model.curves[support_axis_id] = GeometryCurve(
        id=support_axis_id,
        name="Smoke support axis",
        point_ids=[],
        kind="support_axis",
        metadata={"start": [-12.0, 0.0, -3.0], "end": [12.0, 0.0, -3.0]},
    )
    document.structure_model.beams[support_id] = StructureRecord(
        id=support_id,
        name="Smoke concrete strut",
        geometry_ref=support_axis_id,
        material_id="support_beam",
        active_stage_ids=["excavate_level_01"],
        metadata={"support_type": "strut"},
    )
    document.mark_changed(["geometry", "structure"], action="smoke_create_support", affected_entities=[support_id, support_axis_id])

    CommandStack().execute(GeneratePreviewMeshCommand(), document)

    interface_id = _first(list(document.structure_model.structural_interfaces.keys()))
    load_id = _first(list(document.solver_model.loads.keys()))
    water_id = _first(list(document.soil_model.water_conditions.keys()))

    structure_assignment = assign_structure_material(document, support_id, "strut_concrete", category="beam")
    structure_activation = set_structure_activation(document, "excavate_level_01", support_id, True)
    interface_activation = set_interface_activation(document, "excavate_level_01", interface_id, True) if interface_id else None
    load_activation = set_load_activation(document, "excavate_level_01", load_id, True) if load_id else None
    water_change = set_water_condition(document, "excavate_level_01", water_id) if water_id else None

    solver_payload = build_geoproject_solver_compiler(document, compile_now=True)
    CommandStack().execute(RunPreviewStageResultsCommand(), document)

    material_payload = build_geoproject_material_editor(document)
    stage_payload = build_geoproject_stage_editor(document)
    first_model = max(document.solver_model.compiled_phase_models.values(), key=lambda row: row.active_cell_count)
    first_dict = first_model.to_dict()
    required_blocks = [
        "MeshBlock",
        "ElementBlock",
        "MaterialBlock",
        "BoundaryBlock",
        "LoadBlock",
        "InterfaceBlock",
        "StateVariableBlock",
        "SolverControlBlock",
        "ResultRequestBlock",
    ]
    missing_blocks = [name for name in required_blocks if name not in first_dict]

    report = {
        "accepted": not missing_blocks
        and visual_default_type == "GeoProjectDocument"
        and material_payload["contract"] == "geoproject_material_editor_v2"
        and stage_payload["contract"] == "geoproject_stage_editor_v2"
        and solver_payload["contract"] == "geoproject_solver_compiler_v2"
        and structure_assignment.get("ok") is True
        and structure_activation.get("ok") is True
        and len(document.solver_model.compiled_phase_models) > 0
        and len(document.result_store.phase_results) > 0,
        "version_target": "0.8.49",
        "visual_modeling_document_type": visual_default_type,
        "contracts": {
            "material_editor": material_payload["contract"],
            "stage_editor": stage_payload["contract"],
            "solver_compiler": solver_payload["contract"],
        },
        "counts": {
            "volumes": len(document.geometry_model.volumes),
            "structures": len(list(document.iter_structure_records())),
            "interfaces": len(document.structure_model.structural_interfaces),
            "mesh_nodes": len(document.mesh_model.mesh_document.nodes) if document.mesh_model.mesh_document else 0,
            "mesh_cells": len(document.mesh_model.mesh_document.cells) if document.mesh_model.mesh_document else 0,
            "phases": len(document.phase_ids()),
            "compiled_phase_models": len(document.solver_model.compiled_phase_models),
            "phase_results": len(document.result_store.phase_results),
        },
        "mutations": {
            "assign_structure_material": structure_assignment,
            "set_structure_activation": structure_activation,
            "set_interface_activation": interface_activation,
            "set_load_activation": load_activation,
            "set_water_condition": water_change,
        },
        "compiled_input_skeleton": {
            "missing_blocks": missing_blocks,
            "mesh_nodes": len(first_model.mesh_block.get("node_coordinates", [])),
            "elements": len(first_model.element_block.get("elements", [])),
            "materials": len(first_model.material_block.get("materials", [])),
            "boundary_conditions": len(first_model.boundary_block.get("boundary_conditions", [])),
            "loads": len(first_model.load_block.get("loads", [])),
            "interfaces": len(first_model.interface_block.get("interfaces", [])),
            "state_variable_count": first_model.state_variable_block.get("cell_state_variables", {}).get("count", 0),
            "result_request_groups": len(first_model.result_request_block),
        },
        "dirty_graph": get_dirty_graph(document).to_dict(),
        "invalidation_graph": get_invalidation_graph(document).to_dict(),
    }

    (REPORTS / "geoproject_native_workflow_smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    document.save_json(EXPORTS / "geoproject_native_workflow_preview.geojson")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    import os

    os._exit(main())
