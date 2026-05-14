from __future__ import annotations

from geoai_simkit.app.launch import build_desktop_gui_startup_report
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.app.shell.startup_dependency_dialog import build_startup_dependency_payload
from geoai_simkit.services.dependency_preflight import (
    DependencySpec,
    build_dependency_preflight_report,
    render_dependency_preflight_text,
)


def test_dependency_preflight_reports_missing_required_with_install_hints() -> None:
    report = build_dependency_preflight_report(
        [
            DependencySpec("missing_required", "Missing Required", "geoai_missing_required_runtime", "geoai-missing-required", "desktop_gui", True, None, "test required"),
            DependencySpec("missing_optional", "Missing Optional", "geoai_missing_optional_runtime", "geoai-missing-optional", "optional", False, None, "test optional"),
        ]
    )
    payload = report.to_dict()
    assert payload["contract"] == "geoai_simkit_dependency_preflight_v1"
    assert payload["ok"] is False
    assert payload["blocking"] is True
    assert payload["missing_required"] == ["missing_required"]
    assert payload["missing_optional"] == ["missing_optional"]
    assert payload["next_action"] == "show_missing_dependency_prompt"
    assert "python -m pip install geoai-missing-required" in payload["install_commands"]


def test_dependency_preflight_passes_for_builtin_module() -> None:
    report = build_dependency_preflight_report(
        [DependencySpec("json", "json", "json", "json", "core", True, None, "builtin json", "python -m pip install json")]
    )
    payload = report.to_dict()
    assert payload["ok"] is True
    assert payload["blocking"] is False
    assert payload["next_action"] == "enter_main_workbench"
    assert payload["missing_required"] == []


def test_startup_dependency_screen_payload_is_main_gate() -> None:
    payload = build_startup_dependency_payload()
    assert payload["contract"] == "geoai_simkit_startup_dependency_screen_v1"
    assert payload["main_workbench"] == "six_phase_workbench"
    assert payload["legacy_fallback"] is False
    assert payload["report"]["contract"] == "geoai_simkit_dependency_preflight_v1"
    if payload["report"]["ok"]:
        assert payload["auto_enter_main"] is True
        assert payload["status"] == "passed"
    else:
        assert payload["auto_enter_main"] is False
        assert payload["status"] == "blocked"
        assert payload["install_commands"]


def test_phase_workbench_payload_exposes_startup_dependency_state() -> None:
    payload = build_phase_workbench_qt_payload("solve")
    assert payload["contract"] == "phase_workbench_qt_payload_v1"
    assert payload["startup_dependency_screen"]["contract"] == "geoai_simkit_startup_dependency_screen_v1"
    assert payload["dependency_preflight"]["contract"] == "geoai_simkit_dependency_preflight_v1"
    assert payload["launcher_fix"]["legacy_flat_editor_default"] is False


def test_desktop_startup_smoke_contains_preflight_report() -> None:
    report = build_desktop_gui_startup_report(offscreen=True)
    assert report["entrypoint"] == "start_gui.py"
    assert report["startup_dependency_screen"]["contract"] == "geoai_simkit_startup_dependency_screen_v1"
    assert report["dependency_preflight"]["contract"] == "geoai_simkit_dependency_preflight_v1"
    assert "numpy" in {row["key"] for row in report["dependency_preflight"]["checks"]}


def test_dependency_preflight_text_mentions_install_suggestions() -> None:
    report = build_dependency_preflight_report(
        [DependencySpec("missing_text", "Missing Text", "geoai_missing_text_runtime", "geoai-missing-text", "core", True, None, "text rendering")]
    )
    text = render_dependency_preflight_text(report)
    assert "GeoAI SimKit 启动依赖检查" in text
    assert "MISSING" in text
    assert "python -m pip install geoai-missing-text" in text


def test_dependency_preflight_detects_broken_numpy_api(monkeypatch) -> None:
    import sys
    import types

    fake_numpy = types.ModuleType("numpy")
    fake_numpy.__version__ = "1.26.0"
    fake_numpy.__file__ = "E:/OneDrive/python/research/python_simu/numpy.py"
    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)

    report = build_dependency_preflight_report(
        [DependencySpec("numpy", "NumPy", "numpy", "numpy", "core", True, "1.24", "numerical arrays", "python -m pip install --upgrade --force-reinstall numpy>=1.24", ("ndarray", "array"))]
    )
    payload = report.to_dict()
    assert payload["ok"] is False
    assert payload["missing_required"] == ["numpy"]
    check = payload["checks"][0]
    assert "missing required API attribute" in check["error"]
    assert "ndarray" in check["error"]
    assert check["module_file"].endswith("numpy.py")
    assert "--force-reinstall numpy" in payload["install_commands"][0]


def test_dependency_preflight_detects_broken_vtk_submodule() -> None:
    report = build_dependency_preflight_report(
        [
            DependencySpec(
                "vtk",
                "VTK",
                "json",
                "json",
                "three_d_viewport",
                True,
                None,
                "vtk runtime check",
                "python -m pip install --upgrade --force-reinstall vtk>=9.2",
                (),
                ("geoai_missing_vtkmodules_vtkCommonMath",),
            )
        ]
    )
    payload = report.to_dict()
    assert payload["ok"] is False
    assert payload["missing_required"] == ["vtk"]
    assert "Required runtime submodule import failed" in payload["checks"][0]["error"]
    assert "vtk" in payload["install_commands"][0]


def test_optional_broken_vtk_does_not_block_qt_only_workbench() -> None:
    from geoai_simkit.services.dependency_preflight import DependencySpec, build_dependency_preflight_report

    report = build_dependency_preflight_report(
        specs=(
            DependencySpec("pyside6_ok", "PySide6", "math", "math", "desktop_gui", True, None, "qt shell"),
            DependencySpec(
                "vtk_optional_broken",
                "VTK Optional Broken",
                "math",
                "vtk",
                "three_d_viewport",
                False,
                None,
                "3D viewport optional",
                "conda install -c conda-forge vtk pyvista pyvistaqt",
                (),
                ("geoai_missing_vtkmodules_vtkCommonMath",),
            ),
        )
    ).to_dict()
    assert report["ok"] is True
    assert report["blocking"] is False
    assert report["missing_required"] == []
    assert report["missing_optional"] == ["vtk_optional_broken"]
    assert report["next_action"] == "enter_main_workbench"
