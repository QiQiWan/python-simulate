from __future__ import annotations

import json
from pathlib import Path

from geoai_simkit.app.launcher_entry import _launcher_info
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.services.import_driven_model_assembly import (
    IMPORT_DRIVEN_ASSEMBLY_CONTRACT,
    build_import_driven_workflow_payload,
    run_import_driven_assembly,
)


def _write_borehole_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "borehole_id,x,y,ground_elevation,top_depth,bottom_depth,layer_id,material_id,description",
                "BH1,0,0,0,0,5,fill,fill,Fill",
                "BH1,0,0,0,5,12,clay,clay,Clay",
                "BH2,10,10,0,0,5,fill,fill,Fill",
                "BH2,10,10,0,5,12,clay,clay,Clay",
            ]
        ),
        encoding="utf-8",
    )


def test_import_driven_payload_declares_new_primary_strategy() -> None:
    payload = build_import_driven_workflow_payload()
    assert payload["contract"] == IMPORT_DRIVEN_ASSEMBLY_CONTRACT
    assert "import_geology" in payload["assembly_steps"]
    assert "boolean_subtract_structure_overlap_from_soil" in payload["assembly_steps"]
    assert "borehole_csv" in payload["supported_geology_inputs"]


def test_import_driven_assembly_cuts_soil_and_remeshes(tmp_path: Path) -> None:
    csv_path = tmp_path / "boreholes.csv"
    _write_borehole_csv(csv_path)
    project, report = run_import_driven_assembly(
        geology_source=csv_path,
        geology_source_type="borehole_csv",
        structure_specs=[{"id": "wall_a", "kind": "diaphragm_wall", "bounds": [2, 4, -1, 11, -10, 0], "material_id": "concrete_c30"}],
        options={"element_size": 2.0, "remesh": True},
        name="cut-test",
    )
    payload = report.to_dict()
    assert payload["ok"] is True
    assert payload["fallback_used"] is True
    assert payload["structure_count"] == 1
    assert payload["consumed_soil_volume_ids"]
    assert payload["generated_soil_volume_ids"]
    assert project.mesh_model.mesh_document is not None
    assert project.mesh_model.mesh_document.cell_count > 0
    assert "last_assembly_report" in project.metadata["import_driven_workflow"]


def test_gui_payload_exposes_import_assembly_panel() -> None:
    payload = build_phase_workbench_qt_payload()
    interaction = payload["geometry_interaction"]
    assert interaction["contract"] in {"phase_workbench_geometry_interaction_v11", "phase_workbench_geometry_interaction_v13"}
    assert interaction["import_driven_assembly"]["contract"] == IMPORT_DRIVEN_ASSEMBLY_CONTRACT
    assert "导入拼接" in payload["gui_cleanup"]["right_dock_tabs"]


def test_non_install_launcher_is_single_root_entry(tmp_path: Path) -> None:
    root = Path.cwd()
    info = _launcher_info(root, "start_gui.py")
    assert info["contract"] in {"geoai_simkit_gui_launcher_info_v2", "geoai_simkit_gui_launcher_info_v3", "geoai_simkit_gui_launcher_info_v4"}
    assert info["non_install_entrypoints"] == ["start_gui.py"]
    assert "run_gui.py" in info["removed_non_install_entrypoints"]
