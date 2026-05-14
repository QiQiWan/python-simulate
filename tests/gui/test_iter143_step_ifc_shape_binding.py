from __future__ import annotations
import json
from pathlib import Path

from geoai_simkit._version import __version__
from geoai_simkit.commands.cad_kernel_commands import ImportStepIfcSolidTopologyCommand
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.geoproject.document import GeoProjectDocument
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.step_ifc_shape_import import (
    import_step_ifc_solid_topology,
    probe_step_ifc_import_capability,
    validate_step_ifc_shape_bindings,
)
from geoai_simkit.services.release_acceptance_143 import audit_release_1_4_3
from geoai_simkit.examples.release_1_4_3_workflow import run_release_1_4_3_workflow
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload


def _write_step(path: Path) -> Path:
    solids = {"solids":[{"id":"imported_box","name":"Imported Box","bounds":[1,3,2,5,-4,0],"role":"imported_step_solid","material_id":"steel"}]}
    path.write_text("ISO-10303-21;\nDATA;\n#1=CARTESIAN_POINT('',(1,2,-4));\n#2=CARTESIAN_POINT('',(3,5,0));\n/* GEOAI_SIMKIT_SOLIDS: " + json.dumps(solids) + " */\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")
    return path


def test_143_version_and_step_import_binding(tmp_path: Path):
    assert __version__ in {"1.4.3-step-ifc-shape-binding", "1.4.4-topology-binding", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    project = load_demo_project("foundation_pit_3d_beta")
    step = _write_step(tmp_path / "demo.step")
    cap = probe_step_ifc_import_capability().to_dict()
    assert cap["contract"] == "geoai_simkit_step_ifc_import_capability_v1"
    report = import_step_ifc_solid_topology(project, step, output_dir=tmp_path, attach=True)
    assert report.ok is True
    assert report.source_format == "step"
    assert report.imported_volume_ids
    validation = validate_step_ifc_shape_bindings(project)
    assert validation["ok"] is True
    imported_shape_ids = report.shape_ids
    assert imported_shape_ids
    for sid in imported_shape_ids:
        shape = project.cad_shape_store.shapes[sid]
        assert shape.serialized_ref_id in project.cad_shape_store.serialized_refs
        assert shape.topology_ids
        assert shape.backend == "step_ifc_import"


def test_143_command_and_save_load(tmp_path: Path):
    project = GeoProjectDocument.create_empty(name="ImportCommand")
    step = _write_step(tmp_path / "command.step")
    stack = CommandStack()
    result = stack.execute(ImportStepIfcSolidTopologyCommand(source_path=str(step), output_dir=str(tmp_path)), project)
    assert result.ok is True
    assert result.affected_entities
    saved = project.save_json(tmp_path / "project.geoproject.json")
    loaded = GeoProjectDocument.load_json(saved)
    assert validate_step_ifc_shape_bindings(loaded)["ok"] is True
    undo_result = stack.undo(project)
    assert undo_result.ok is True


def test_143_workflow_acceptance_and_gui_payload(tmp_path: Path):
    result = run_release_1_4_3_workflow(output_dir=tmp_path / "bundle")
    assert result["ok"] is True
    assert result["acceptance"]["status"] == "accepted_1_4_3_step_ifc_shape_binding"
    assert Path(result["artifacts"]["project_path"]).exists()
    assert Path(result["artifacts"]["import_path"]).exists()
    assert audit_release_1_4_3(result["project"]).accepted is True
    payload = build_phase_workbench_qt_payload()
    section = payload["geometry_interaction"]["step_ifc_shape_binding"]
    assert section["contract"] == "phase_workbench_step_ifc_shape_binding_v1"
    assert section["cad_shape_store_binding"] is True
