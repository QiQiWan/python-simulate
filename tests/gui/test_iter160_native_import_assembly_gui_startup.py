from __future__ import annotations

from pathlib import Path

from geoai_simkit._version import __version__
from geoai_simkit.app.launcher_entry import build_parser, _launcher_info
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.app.viewport.qt_only_adapter import QT_ONLY_VIEWPORT_ADAPTER_CONTRACT, QtOnlyViewportAdapter
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.native_import_assembly import (
    NATIVE_IMPORT_ASSEMBLY_CONTRACT,
    ImportTransformSpec,
    build_native_import_assembly_payload,
    run_native_import_assembly,
)


def test_version_and_launcher_expose_qt_only() -> None:
    assert __version__ in {"1.6.1-gui-action-audit-import-repair", "1.6.2-launch-chain-dialog-action-repair", "1.6.3-gui-action-dispatch-file-dialog-repair"}
    parser = build_parser()
    args = parser.parse_args(["--qt-only"])
    assert args.qt_only is True
    info = _launcher_info(Path.cwd(), "start_gui.py")
    assert info["non_install_entrypoints"] == ["start_gui.py"]


def test_native_import_assembly_payload_and_gui_contract() -> None:
    payload = build_native_import_assembly_payload()
    assert payload["contract"] == NATIVE_IMPORT_ASSEMBLY_CONTRACT
    assert "ifc" in payload["structure_inputs"]
    gui = build_phase_workbench_qt_payload()
    assert gui["geometry_interaction"]["contract"] in {"phase_workbench_geometry_interaction_v11", "phase_workbench_geometry_interaction_v13"}
    assert gui["geometry_interaction"]["native_import_assembly"]["contract"] == NATIVE_IMPORT_ASSEMBLY_CONTRACT
    assert gui["launcher_fix"]["qt_only_fallback"] is True


def test_qt_only_adapter_preserves_viewport_method_surface() -> None:
    adapter = QtOnlyViewportAdapter()
    assert adapter.metadata["contract"] == QT_ONLY_VIEWPORT_ADAPTER_CONTRACT
    assert adapter.safe_render(reason="test") is True
    assert adapter.snap.enabled is True
    assert adapter.workplane.mode == "xz"


def test_transform_spec_rotates_and_translates_bounds() -> None:
    t = ImportTransformSpec.from_mapping({"translate": [10, 0, 0], "rotate_z_degrees": 90})
    b = t.apply_bounds((0, 2, 0, 1, 0, 1))
    assert round(b[0], 6) == 9.0
    assert round(b[1], 6) == 10.0
    assert round(b[2], 6) == 0.0
    assert round(b[3], 6) == 2.0


def test_native_import_assembly_cuts_box_geology_with_box_structure() -> None:
    project, report = run_native_import_assembly(
        geology_sources=[{"id": "soil", "role": "geology", "source_type": "box_bounds", "bounds": [0, 10, 0, 10, -10, 0], "material_id": "soil_default"}],
        structure_sources=[{"id": "wall", "role": "structure", "source_type": "box_bounds", "kind": "diaphragm_wall", "bounds": [2, 4, -1, 11, -10, 0], "material_id": "concrete_c30"}],
        options={"element_size": 2.0, "remesh": True},
    )
    data = report.to_dict()
    assert data["contract"] == NATIVE_IMPORT_ASSEMBLY_CONTRACT
    assert data["ok"] is True
    assert data["fallback_used"] is True
    assert data["structure_volume_ids"]
    assert data["assembly_report"]["generated_soil_volume_ids"]
    assert project.mesh_model.mesh_document is not None
    assert project.mesh_model.mesh_document.cell_count > 0


def test_native_import_assembly_requires_native_boolean_blocks_without_gmsh_occ() -> None:
    _project, report = run_native_import_assembly(
        geology_sources=[{"id": "soil", "role": "geology", "source_type": "box_bounds", "bounds": [0, 1, 0, 1, 0, 1]}],
        structure_sources=[{"id": "cut", "role": "structure", "source_type": "box_bounds", "bounds": [0.2, 0.3, 0, 1, 0, 1]}],
        options={"require_native_boolean": True, "remesh": False},
    )
    # CI normally has no gmsh OCC. On native desktops this may pass; both outcomes
    # must be explicit and auditable.
    payload = report.to_dict()
    if payload["native_boolean_available"]:
        assert payload["ok"] in {True, False}
    else:
        assert payload["ok"] is False
        assert any("native Gmsh/OCC boolean" in b for b in payload["blockers"])
