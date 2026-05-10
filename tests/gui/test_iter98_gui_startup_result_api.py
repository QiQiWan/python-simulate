from __future__ import annotations


def test_stage_result_record_public_api_available() -> None:
    from geoai_simkit.results import StageResultRecord

    row = StageResultRecord(stage_name="stage-1", field_count=2).to_dict()
    assert row["stage_name"] == "stage-1"
    assert row["field_count"] == 2


def test_gui_shell_launcher_import_path_exists() -> None:
    from geoai_simkit.app.shell.unified_workbench_window import launch_unified_workbench

    assert callable(launch_unified_workbench)


def test_stage_package_exporter_public_api_available() -> None:
    from geoai_simkit.results.stage_package import export_stage_result_package

    assert callable(export_stage_result_package)
