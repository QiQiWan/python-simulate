from __future__ import annotations

import pytest

from geoai_simkit._version import __version__
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.commands.cad_kernel_commands import ExecuteGmshOccBooleanMeshRoundtripCommand
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.commands.interactive_geometry_commands import BooleanGeometryCommand
from geoai_simkit.examples.release_1_4_2c_workflow import run_release_1_4_2c_workflow
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.gmsh_occ_boolean_roundtrip import execute_gmsh_occ_boolean_mesh_roundtrip, probe_gmsh_occ_boolean_roundtrip
from geoai_simkit.services.release_acceptance_142c import audit_release_1_4_2c


def _two_volumes(project):
    ids = list(project.geometry_model.volumes)[:2]
    assert len(ids) >= 2
    return tuple(ids)


def test_142c_version_and_capability_contract():
    assert __version__ in {"1.4.2c-native-roundtrip", "1.4.2d-cad-shape-store", "1.4.3-step-ifc-shape-binding", "1.4.4-topology-binding", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    report = probe_gmsh_occ_boolean_roundtrip().to_dict()
    assert report["contract"] == "geoai_simkit_gmsh_occ_boolean_roundtrip_capability_v1"
    assert "native_roundtrip_possible" in report
    assert report["selected_backend"] in {"gmsh_occ_native_roundtrip", "deterministic_tet4_contract"}


def test_142c_boolean_roundtrip_contract_generates_mesh_and_physical_groups(tmp_path):
    project = load_demo_project("foundation_pit_3d_beta")
    stack = CommandStack()
    stack.execute(BooleanGeometryCommand(operation="union", target_ids=_two_volumes(project)), project)
    report = execute_gmsh_occ_boolean_mesh_roundtrip(project, output_dir=tmp_path, require_native=False, allow_contract_fallback=True)
    payload = report.to_dict()
    assert payload["contract"] == "geoai_simkit_gmsh_occ_boolean_mesh_roundtrip_v1"
    assert report.ok
    assert report.cell_count > 0
    assert report.physical_group_count > 0
    assert project.mesh_model.mesh_document is not None
    mesh = project.mesh_model.mesh_document
    assert mesh.cell_count == report.cell_count
    assert len(mesh.cell_tags["physical_volume"]) == mesh.cell_count
    assert len(mesh.cell_tags["material_id"]) == mesh.cell_count
    assert report.manifest_path


def test_142c_command_and_acceptance(tmp_path):
    project = load_demo_project("foundation_pit_3d_beta")
    stack = CommandStack()
    stack.execute(BooleanGeometryCommand(operation="union", target_ids=_two_volumes(project)), project)
    result = stack.execute(ExecuteGmshOccBooleanMeshRoundtripCommand(output_dir=str(tmp_path), require_native=False), project)
    assert result.ok
    acceptance = audit_release_1_4_2c(project)
    assert acceptance.accepted
    assert acceptance.status in {"accepted_1_4_2c_roundtrip_contract", "accepted_1_4_2c_native_roundtrip"}


def test_142c_native_required_blocks_without_native(tmp_path):
    project = load_demo_project("foundation_pit_3d_beta")
    stack = CommandStack()
    stack.execute(BooleanGeometryCommand(operation="union", target_ids=_two_volumes(project)), project)
    cap = probe_gmsh_occ_boolean_roundtrip().to_dict()
    if cap["native_roundtrip_possible"]:
        pytest.skip("Native gmsh/OCC is available in this environment; negative fallback test not applicable.")
    with pytest.raises(RuntimeError):
        execute_gmsh_occ_boolean_mesh_roundtrip(project, output_dir=tmp_path, require_native=True, allow_contract_fallback=False)


def test_142c_workflow_exports_review_bundle(tmp_path):
    result = run_release_1_4_2c_workflow(output_dir=tmp_path)
    assert result["ok"] is True
    assert result["acceptance"]["status"] in {"accepted_1_4_2c_roundtrip_contract", "accepted_1_4_2c_native_roundtrip"}
    artifacts = result["artifacts"]
    for key in ["project_path", "capability_path", "roundtrip_path", "acceptance_path", "tutorial_path", "manifest_path"]:
        assert artifacts[key]


def test_142c_gui_payload_exposes_roundtrip_status():
    payload = build_phase_workbench_qt_payload("structures")
    roundtrip = payload["geometry_interaction"]["gmsh_occ_roundtrip"]
    assert roundtrip["contract"] == "phase_workbench_gmsh_occ_roundtrip_v1"
    assert roundtrip["physical_group_roundtrip"] is True
    assert roundtrip["backend_status"]["contract"] == "geoai_simkit_gmsh_occ_boolean_roundtrip_capability_v1"
