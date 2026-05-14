from __future__ import annotations

from pathlib import Path

from geoai_simkit._version import __version__
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.services.import_driven_model_assembly import create_geology_project_from_source
from geoai_simkit.services.native_import_assembly import run_native_import_assembly


def _write_tetra_stl(path: Path) -> None:
    path.write_text(
        """
solid tetra
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 1 0 0
      vertex 0 1 0
    endloop
  endfacet
  facet normal 0 -1 0
    outer loop
      vertex 0 0 0
      vertex 0 0 1
      vertex 1 0 0
    endloop
  endfacet
  facet normal 1 1 1
    outer loop
      vertex 1 0 0
      vertex 0 0 1
      vertex 0 1 0
    endloop
  endfacet
  facet normal -1 0 0
    outer loop
      vertex 0 0 0
      vertex 0 1 0
      vertex 0 0 1
    endloop
  endfacet
endsolid tetra
""".strip(),
        encoding="utf-8",
    )


def test_version_and_payload_expose_gui_action_audit() -> None:
    assert __version__ in {"1.6.1-gui-action-audit-import-repair", "1.6.2-launch-chain-dialog-action-repair", "1.6.3-gui-action-dispatch-file-dialog-repair", "1.6.6-runtime-action-smoke"}
    payload = build_phase_workbench_qt_payload()
    assert payload["geometry_interaction"]["contract"] in {"phase_workbench_geometry_interaction_v11", "phase_workbench_geometry_interaction_v12", "phase_workbench_geometry_interaction_v13"}
    audit = payload["gui_action_audit"]
    assert audit["contract"] in {"geoai_simkit_gui_action_audit_v1", "geoai_simkit_gui_action_audit_v2"}
    assert "import_geology_model" in audit["critical_actions"]
    native = payload["geometry_interaction"]["native_import_assembly"]
    assert "import_structure_model" in native["direct_import_buttons"]
    assert "交互自检" in payload["gui_cleanup"]["bottom_tabs"]


def test_geology_stl_import_service_creates_project_volume(tmp_path: Path) -> None:
    stl = tmp_path / "geology.stl"
    _write_tetra_stl(stl)
    project = create_geology_project_from_source(stl, source_type="stl_geology", name="stl-geology-test")
    assert project.geometry_model.volumes
    volume = next(iter(project.geometry_model.volumes.values()))
    assert volume.bounds is not None
    assert volume.metadata.get("source") == "stl_geology_loader"
    assert project.mesh_model.mesh_document is not None


def test_structure_stl_native_import_registers_cutter(tmp_path: Path) -> None:
    stl = tmp_path / "wall.stl"
    _write_tetra_stl(stl)
    project, report = run_native_import_assembly(
        geology_sources=[{"id": "soil", "role": "geology", "source_type": "box_bounds", "bounds": [-1, 2, -1, 2, -1, 2], "material_id": "soil_default"}],
        structure_sources=[{"id": "wall", "role": "structure", "source_type": "stl", "path": str(stl), "kind": "diaphragm_wall", "material_id": "concrete_c30"}],
        options={"remesh": False},
    )
    payload = report.to_dict()
    assert payload["ok"] is True
    assert payload["structure_volume_ids"]
    cutter = project.geometry_model.volumes[payload["structure_volume_ids"][0]]
    assert cutter.metadata.get("boolean_cutter") is True
    assert cutter.metadata.get("stl_summary", {}).get("triangle_count") == 4


def test_phase_workbench_source_declares_direct_import_button_handlers() -> None:
    source = Path("src/geoai_simkit/app/shell/phase_workbench_qt.py").read_text(encoding="utf-8")
    for action_id in [
        "import_geology_model",
        "import_structure_model",
        "run_import_driven_assembly",
        "run_native_import_assembly",
        "refresh_gui_action_audit",
    ]:
        assert action_id in source
    assert "_run_gui_action" in source
    assert "_maybe_get_import_path" in source
    assert "_select_import_file_then_run" in source
    assert "dialog.exec()" not in source
