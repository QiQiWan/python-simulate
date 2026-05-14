from pathlib import Path

from geoai_simkit._version import __version__
from geoai_simkit.examples.release_1_4_5_workflow import run_release_1_4_5_workflow
from geoai_simkit.services.native_runtime_verification import verify_native_desktop_runtime
from geoai_simkit.services.ifc_representation_expansion import expand_ifc_product_representations
from geoai_simkit.services.boolean_topology_lineage import build_boolean_topology_lineage, validate_boolean_topology_lineage
from geoai_simkit.services.topology_material_phase_binding import assign_topology_material_phase
from geoai_simkit.services.release_acceptance_145 import audit_release_1_4_5
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.commands.cad_kernel_commands import ExecuteGmshOccBooleanMeshRoundtripCommand, BuildCadShapeStoreCommand, BindTopologyMaterialPhaseCommand
from geoai_simkit.commands.interactive_geometry_commands import BooleanGeometryCommand
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload


def test_version_and_native_runtime_contract():
    assert __version__ in {"1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    report = verify_native_desktop_runtime()
    payload = report.to_dict()
    assert payload["contract"] == "geoai_simkit_native_runtime_verification_v1"
    assert "OCP.TopoDS" in payload["modules"]
    assert "ifcopenshell" in payload["modules"]
    assert "native_brep_certification_possible" in payload


def test_ifc_representation_expansion_text_scan(tmp_path):
    src = tmp_path / "sample.ifc"
    src.write_text("#1=IFCEXTRUDEDAREASOLID($,$,$,1.0);\n#2=IFCBOOLEANRESULT(.DIFFERENCE.,#1,#1);\n#3=IFCFACETEDBREP($);", encoding="utf-8")
    report = expand_ifc_product_representations(src)
    assert report.ok
    assert report.representation_counts["IfcExtrudedAreaSolid"] >= 1
    assert report.representation_counts["IfcBooleanResult"] >= 1
    assert report.representation_counts["IfcFacetedBrep"] >= 1


def test_boolean_lineage_and_direct_topology_assignment(tmp_path):
    project = load_demo_project("foundation_pit_3d_beta")
    stack = CommandStack()
    ids = list(project.geometry_model.volumes)[:2]
    assert stack.execute(BooleanGeometryCommand(operation="union", target_ids=tuple(ids)), project).ok
    assert stack.execute(ExecuteGmshOccBooleanMeshRoundtripCommand(output_dir=str(tmp_path), stem="lineage_test", require_native=False), project).ok
    assert stack.execute(BuildCadShapeStoreCommand(output_dir=str(tmp_path), include_roundtrip=True, export_references=True), project).ok
    assert stack.execute(BindTopologyMaterialPhaseCommand(), project).ok
    lineage = build_boolean_topology_lineage(project)
    assert lineage.ok
    assert lineage.face_lineage_count > 0
    validation = validate_boolean_topology_lineage(project, require_face_lineage=True)
    assert validation["ok"]
    face_id = next(tid for tid, topo in project.cad_shape_store.topology_records.items() if topo.kind == "face")
    result = assign_topology_material_phase(project, face_id, material_id="steel", phase_ids=["initial"], role="test_face")
    assert result["ok"]
    assert result["binding"]["material_id"] == "steel"
    assert "initial" in result["binding"]["phase_ids"]


def test_release_145_workflow_and_acceptance(tmp_path):
    result = run_release_1_4_5_workflow(tmp_path)
    assert result["ok"]
    assert result["acceptance"]["status"] in {"accepted_1_4_5_native_geometry_certification_contract", "accepted_1_4_5_native_brep_certified"}
    assert result["ifc_representation_expansion"]["ok"]
    assert result["boolean_topology_lineage"]["face_lineage_count"] > 0
    assert Path(result["artifacts"]["project_path"]).exists()


def test_release_145_acceptance_blocks_when_native_required(tmp_path):
    result = run_release_1_4_5_workflow(tmp_path / "contract")
    project = result["project"]
    report = audit_release_1_4_5(project, require_native_brep=True)
    if not project.cad_shape_store.summary().get("native_brep_certified_count"):
        assert not report.accepted
        assert any("Native BRep" in b for b in report.blockers)


def test_gui_payload_exposes_145_features():
    payload = build_phase_workbench_qt_payload()
    gi = payload["geometry_interaction"]
    assert "native_runtime_verification" in gi
    assert "ifc_representation_expansion" in gi
    assert "boolean_topology_lineage" in gi
    assert gi["topology_material_phase_binding"]["direct_face_edge_gui_assignment"] is True
