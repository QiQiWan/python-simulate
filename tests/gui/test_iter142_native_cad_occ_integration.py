from __future__ import annotations

from geoai_simkit._version import __version__
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.app.tools.base import ToolContext, ToolEvent
from geoai_simkit.app.viewport.selection_controller import SelectionController
from geoai_simkit.app.viewport.tool_runtime import default_geometry_tool_runtime
from geoai_simkit.app.viewport.viewport_state import ViewportState
from geoai_simkit.commands.cad_kernel_commands import BuildCadTopologyIndexCommand, ExecuteCadFeaturesCommand
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.commands.interactive_geometry_commands import BooleanGeometryCommand
from geoai_simkit.examples.release_1_4_2_workflow import run_release_1_4_2_workflow
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.cad_facade_kernel import build_cad_topology_index, execute_deferred_cad_features, probe_cad_facade_kernel
from geoai_simkit.services.release_acceptance_142 import audit_release_1_4_2


def _two_volumes(project):
    ids = list(project.geometry_model.volumes)[:2]
    assert len(ids) >= 2
    return tuple(ids)


def test_native_cad_occ_capability_and_topology_index_contract():
    assert __version__ in {"1.4.2a-cad-facade", "1.4.2c-native-roundtrip", "1.4.2d-cad-shape-store", "1.4.3-step-ifc-shape-binding", "1.4.4-topology-binding", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    report = probe_cad_facade_kernel().to_dict()
    assert report["contract"] == "geoai_simkit_cad_facade_capability_v1"
    assert report["fallback_available"] is True
    project = load_demo_project("foundation_pit_3d_beta")
    topology = build_cad_topology_index(project)
    assert topology.ok
    assert topology.solid_count == len(project.geometry_model.volumes)
    assert topology.face_count >= topology.solid_count * 6
    assert topology.edge_count >= topology.solid_count * 12
    assert project.geometry_model.metadata["cad_occ_topology_index"]["contract"] == "geoai_simkit_cad_facade_topology_index_v1"


def test_execute_deferred_cad_boolean_feature_generates_volume_and_persistent_names():
    project = load_demo_project("foundation_pit_3d_beta")
    ids = _two_volumes(project)
    stack = CommandStack()
    result = stack.execute(BooleanGeometryCommand(operation="union", target_ids=ids), project)
    assert result.ok
    report = execute_deferred_cad_features(project, require_native=False, allow_fallback=True)
    assert report.ok
    assert report.executed_feature_count == 1
    assert report.generated_volume_ids
    assert all(vid in project.geometry_model.volumes for vid in report.generated_volume_ids)
    for vid in ids:
        assert project.geometry_model.volumes[vid].metadata.get("visible") is False
    assert project.geometry_model.metadata["last_cad_occ_feature_execution"]["contract"] == "geoai_simkit_cad_facade_feature_execution_v1"
    assert project.geometry_model.metadata["cad_occ_topology_index"]["solid_count"] >= 1


def test_execute_cad_features_command_undo_restores_geometry_state():
    project = load_demo_project("foundation_pit_3d_beta")
    ids = _two_volumes(project)
    stack = CommandStack()
    before_ids = set(project.geometry_model.volumes)
    stack.execute(BooleanGeometryCommand(operation="union", target_ids=ids), project)
    result = stack.execute(ExecuteCadFeaturesCommand(), project)
    assert result.ok
    assert set(project.geometry_model.volumes) != before_ids
    stack.undo(project)
    assert set(project.geometry_model.volumes) == before_ids


def test_runtime_and_qt_payload_expose_native_cad_occ_tools():
    project = load_demo_project("foundation_pit_3d_beta")
    state = ViewportState(); state.update_from_geoproject_document(project)
    controller = SelectionController()
    runtime = default_geometry_tool_runtime(ToolContext(project, state, CommandStack(), metadata={"selection_controller": controller}))
    assert "apply_cad_features" in runtime.tools
    payload = build_phase_workbench_qt_payload("structures")
    interaction = payload["geometry_interaction"]
    assert "apply_cad_features" in interaction["runtime_tools"]
    assert interaction["cad_facade"]["persistent_naming"] is True
    assert "boolean_union_native_or_fallback" in interaction["solid_modeling"]


def test_142_acceptance_and_review_workflow(tmp_path):
    result = run_release_1_4_2_workflow(output_dir=tmp_path)
    assert result["ok"] is True
    assert result["acceptance"]["status"] == "accepted_1_4_2a_cad_facade"
    artifacts = result["artifacts"]
    for key in ["project_path", "capability_path", "topology_path", "feature_execution_path", "acceptance_path", "tutorial_path"]:
        assert artifacts[key]
    project = result["project"]
    acceptance = audit_release_1_4_2(project)
    assert acceptance.accepted


def test_142a_facade_acceptance_does_not_claim_native_cad():
    result = run_release_1_4_2_workflow()
    acceptance = result["acceptance"]
    assert acceptance["metadata"]["release_mode"] == "cad_facade_hardening"
    assert acceptance["metadata"]["native_cad_claimed"] is False
    assert acceptance["metadata"]["native_brep_certified"] is False
    assert acceptance["metadata"]["backend_mode"] in {"deterministic_aabb_facade", "native_passthrough_facade", "mixed_facade"}
    feature = result["feature_execution"]
    assert feature["metadata"]["release_mode"] == "cad_facade"
    assert feature["metadata"]["native_brep_certified"] is False


def test_142a_gui_payload_exposes_visible_backend_status():
    payload = build_phase_workbench_qt_payload("structures")
    facade = payload["geometry_interaction"]["cad_facade"]
    assert facade["contract"] == "phase_workbench_cad_facade_v1"
    assert facade["native_cad_claimed"] is False
    assert facade["native_brep_certified"] is False
    assert facade["gui_status_required"] is True
    assert facade["backend_status"]["contract"] == "geoai_simkit_cad_facade_capability_v1"
