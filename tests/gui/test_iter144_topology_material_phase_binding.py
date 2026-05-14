from pathlib import Path

from geoai_simkit._version import __version__
from geoai_simkit.examples.release_1_4_4_workflow import run_release_1_4_4_workflow
from geoai_simkit.services.native_brep_serialization import probe_native_brep_capability, write_surrogate_brep_reference
from geoai_simkit.services.topology_material_phase_binding import bind_topology_material_phase, validate_topology_material_phase_bindings
from geoai_simkit.services.release_acceptance_144 import audit_release_1_4_4
from geoai_simkit.services.step_ifc_shape_import import import_step_ifc_solid_topology
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.geoproject.document import GeoProjectDocument
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload


def _write_step(path: Path) -> None:
    path.write_text("""ISO-10303-21;
HEADER;ENDSEC;
DATA;
#1=CARTESIAN_POINT('',(-1,-1,-1));
#2=CARTESIAN_POINT('',(2,3,4));
/* GEOAI_SIMKIT_SOLIDS: {\"solids\":[{\"id\":\"sample_solid\",\"name\":\"Sample Solid\",\"bounds\":[-1,2,-1,3,-1,4],\"role\":\"soil_volume\",\"material_id\":\"soil_upper\"}]} */
ENDSEC;
END-ISO-10303-21;
""", encoding="utf-8")


def test_version_and_native_brep_capability_contract(tmp_path):
    assert __version__ in {"1.4.4-topology-binding", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    cap = probe_native_brep_capability().to_dict()
    assert cap["contract"] == "geoai_simkit_native_brep_serialization_capability_v1"
    assert "native_brep_serialization_possible" in cap
    ref = write_surrogate_brep_reference(tmp_path / "shape.brep.json", {"shape_id": "s1"})
    assert ref["native_brep_certified"] is False
    assert Path(ref["path"]).exists()


def test_import_then_face_edge_material_phase_bindings(tmp_path):
    project = load_demo_project("foundation_pit_3d_beta")
    source = tmp_path / "sample.step"
    _write_step(source)
    report = import_step_ifc_solid_topology(project, source, output_dir=tmp_path / "import", attach=True)
    assert report.ok
    binding = bind_topology_material_phase(project)
    assert binding.ok
    assert binding.face_binding_count >= 6
    assert binding.edge_binding_count >= 12
    assert binding.material_binding_count > 0
    assert binding.phase_binding_count > 0
    validation = validate_topology_material_phase_bindings(project)
    assert validation["ok"] is True
    acceptance = audit_release_1_4_4(project)
    assert acceptance.accepted is True
    assert acceptance.status == "accepted_1_4_4_topology_binding"


def test_save_load_preserves_topology_bindings(tmp_path):
    result = run_release_1_4_4_workflow(output_dir=tmp_path / "bundle")
    assert result["ok"] is True
    path = Path(result["artifacts"]["project_path"])
    reloaded = GeoProjectDocument.load_json(path)
    assert reloaded.cad_shape_store.topology_bindings
    assert audit_release_1_4_4(reloaded).accepted is True


def test_require_native_brep_blocks_when_no_native_certification(tmp_path):
    result = run_release_1_4_4_workflow(output_dir=tmp_path / "bundle")
    project = result["project"]
    acceptance = audit_release_1_4_4(project, require_native_brep=True)
    if not acceptance.native_brep_certified:
        assert acceptance.accepted is False
        assert any("Native BRep-certified" in b for b in acceptance.blockers)


def test_gui_payload_exposes_144_topology_binding_contract():
    payload = build_phase_workbench_qt_payload()
    gi = payload["geometry_interaction"]
    assert "native_brep_serialization" in gi
    assert "topology_material_phase_binding" in gi
    assert gi["topology_material_phase_binding"]["after_step_ifc_import"] is True
    assert "CadTopologyBinding" in gi["cad_shape_store"]["stores"]
