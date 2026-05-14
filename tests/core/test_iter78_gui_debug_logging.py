from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path


def test_geometry_debug_config_uses_local_log_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEOAI_SIMKIT_GEOMETRY_DEBUG", raising=False)
    monkeypatch.delenv("GEOAI_SIMKIT_DEBUG", raising=False)
    monkeypatch.delenv("GEOAI_SIMKIT_GEOMETRY_LOG_DIR", raising=False)

    from geoai_simkit.diagnostics.operation_log import (
        configure_geometry_operation_logging,
        geometry_log_status,
        log_geometry_operation,
    )

    config = configure_geometry_operation_logging(enabled=True)
    assert config["enabled"] is True
    assert Path(str(config["debug_dir"])).name == "log"
    assert Path(str(config["debug_dir"])).parent == tmp_path
    assert geometry_log_status()["enabled"] is True
    assert Path(str(geometry_log_status()["debug_dir"])) == tmp_path / "log"

    log_geometry_operation("iter78.debug_smoke", input_state={"a": 1}, output_state={"b": 2})
    log_path = tmp_path / "log" / "geometry_kernel.jsonl"
    assert log_path.exists()
    row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["operation"] == "iter78.debug_smoke"
    assert row["input_state"] == {"a": 1}


def test_geoai_cli_gui_debug_passes_launch_options(monkeypatch, tmp_path):
    from geoai_simkit import cli
    import geoai_simkit.app.launch as launch

    calls: list[dict[str, object]] = []

    def fake_launch_desktop_workbench(*, debug: bool = False, debug_dir: str | None = None) -> None:
        calls.append({"debug": debug, "debug_dir": debug_dir})

    monkeypatch.setattr(launch, "launch_desktop_workbench", fake_launch_desktop_workbench)
    rc = cli._cmd_gui(Namespace(debug=True, log_dir=str(tmp_path / "mylog")))
    assert rc == 0
    assert calls == [{"debug": True, "debug_dir": str(tmp_path / "mylog")}]


def test_start_gui_debug_sets_current_directory_log(monkeypatch, tmp_path):
    import start_gui
    import geoai_simkit.app.launch as launch

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEOAI_SIMKIT_GEOMETRY_DEBUG", raising=False)
    monkeypatch.delenv("GEOAI_SIMKIT_DEBUG", raising=False)
    monkeypatch.delenv("GEOAI_SIMKIT_GEOMETRY_LOG_DIR", raising=False)

    calls: list[dict[str, object]] = []

    def fake_launch_desktop_workbench(*, debug: bool = False, debug_dir: str | None = None) -> None:
        calls.append({"debug": debug, "debug_dir": debug_dir})

    monkeypatch.setattr(launch, "launch_desktop_workbench", fake_launch_desktop_workbench)
    assert start_gui.main(["--debug"]) == 0
    assert calls == [{"debug": True, "debug_dir": str(tmp_path / "log")}]
    assert Path(tmp_path / "log").is_dir()


def test_requirements_enable_production_gmsh_meshio_dependencies():
    text = Path("requirements.txt").read_text(encoding="utf-8")
    assert "\ngmsh\n" in text
    assert "\nmeshio\n" in text
