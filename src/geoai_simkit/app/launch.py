from __future__ import annotations

import os
from dataclasses import dataclass
from dataclasses import asdict
from importlib import import_module
from typing import Any

from geoai_simkit._optional import require_optional_dependency


@dataclass(slots=True)
class LaunchDiagnostics:
    gui_ready: bool
    message: str
    missing_feature: str | None = None
    pyvista_ready: bool = False
    fallback_available: bool = True


def _module_available(name: str) -> bool:
    try:
        import_module(name)
        return True
    except Exception:
        return False


def _module_import_report(name: str) -> dict[str, Any]:
    try:
        import_module(name)
        return {"available": True, "error": None}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def _prefer_qt_only_workbench() -> bool:
    platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    return platform in {"offscreen", "minimal"} or os.environ.get("GEOAI_SIMKIT_DISABLE_PYVISTA", "").strip() == "1"


def validate_desktop_gui_environment() -> LaunchDiagnostics:
    """Validate the GUI stack.

    PySide6 is required for the full Qt workbench.  PyVista/pyvistaqt are now
    optional: without them the GUI still opens and shows a non-3D scene panel.
    """
    try:
        require_optional_dependency('PySide6', feature='The desktop GUI', extra='gui')
    except RuntimeError as exc:
        return LaunchDiagnostics(False, str(exc), missing_feature='PySide6', pyvista_ready=False)
    pyvista_ready = _module_available('pyvista') and _module_available('pyvistaqt')
    msg = 'Desktop GUI dependencies are available.' if pyvista_ready else 'PySide6 is available; PyVista viewport is disabled until pyvista/pyvistaqt are installed.'
    return LaunchDiagnostics(True, msg, pyvista_ready=pyvista_ready)


def build_desktop_gui_startup_report(*, offscreen: bool = True) -> dict[str, Any]:
    """Return a non-blocking startup report for the root GUI launcher.

    The regular GUI path enters a Qt event loop, so automated verification needs
    a side-effect-light check that still exercises the same runtime contract:
    dependency validation, workbench module imports, Qt application creation, and
    unified workbench payload construction.
    """

    if offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    diagnostics = validate_desktop_gui_environment()
    required_modules = [
        "geoai_simkit.app.shell.unified_workbench_window",
        "geoai_simkit.app.modern_qt_workbench",
        "geoai_simkit.app.fallback_gui",
    ]
    pyvista_launch_ready = diagnostics.pyvista_ready and not _prefer_qt_only_workbench()
    if pyvista_launch_ready:
        required_modules.append("geoai_simkit.app.workbench_window")

    module_reports = {name: _module_import_report(name) for name in required_modules}

    payload_report: dict[str, Any] = {"available": False, "error": None}
    try:
        from geoai_simkit.app.shell.unified_workbench_window import build_unified_workbench_payload

        payload = build_unified_workbench_payload()
        pages = payload.get("pages", {}) if isinstance(payload, dict) else {}
        payload_report = {
            "available": True,
            "contract": payload.get("contract") if isinstance(payload, dict) else None,
            "page_count": len(pages) if isinstance(pages, dict) else 0,
            "has_visual_modeling": bool(payload.get("visual_modeling")) if isinstance(payload, dict) else False,
            "has_benchmark_panel": bool(payload.get("benchmark_panel")) if isinstance(payload, dict) else False,
            "error": None,
        }
    except Exception as exc:
        payload_report = {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    qt_report: dict[str, Any] = {"available": False, "created": False, "platform": None, "error": None}
    if diagnostics.gui_ready:
        try:
            from PySide6 import QtWidgets

            app = QtWidgets.QApplication.instance()
            created = app is None
            if app is None:
                app = QtWidgets.QApplication([])
            qt_report = {
                "available": True,
                "created": created,
                "platform": QtWidgets.QApplication.platformName(),
                "error": None,
            }
        except Exception as exc:
            qt_report = {"available": False, "created": False, "platform": None, "error": f"{type(exc).__name__}: {exc}"}

    imports_ok = all(row["available"] for row in module_reports.values())
    ok = bool(diagnostics.gui_ready and imports_ok and payload_report["available"] and qt_report["available"])
    if pyvista_launch_ready:
        launch_path = "pyvista_workbench"
    elif diagnostics.gui_ready:
        launch_path = "modern_qt_workbench"
    else:
        launch_path = "tk_fallback"

    return {
        "ok": ok,
        "entrypoint": "start_gui.py",
        "launch_path": launch_path,
        "diagnostics": asdict(diagnostics),
        "imports": module_reports,
        "qt_application": qt_report,
        "workbench_payload": payload_report,
    }


def launch_desktop_workbench() -> None:
    diagnostics = validate_desktop_gui_environment()
    if diagnostics.gui_ready:
        from geoai_simkit.app.shell.unified_workbench_window import launch_unified_workbench
        launch_unified_workbench()
        return
    from geoai_simkit.app.fallback_gui import launch_tk_fallback_workbench
    launch_tk_fallback_workbench(diagnostics.message)


def main() -> int:
    try:
        launch_desktop_workbench()
        return 0
    except Exception as exc:
        print('GeoAI SimKit GUI could not start:')
        print(exc)
        try:
            from geoai_simkit.app.fallback_gui import launch_tk_fallback_workbench
            launch_tk_fallback_workbench(str(exc))
            return 0
        except Exception:
            return 2
