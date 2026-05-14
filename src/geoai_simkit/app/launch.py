from __future__ import annotations

"""Canonical desktop launch path.

1.6.4 removes legacy GUI routing from the launch chain.  Every supported GUI
entrypoint now resolves to :mod:`geoai_simkit.app.shell.phase_workbench_qt`.
PyVista/VTK are viewport adapters inside that workbench, not separate GUI
launch choices.
"""

import argparse
import os
import sys
from dataclasses import asdict, dataclass
from importlib import import_module
from typing import Any

from geoai_simkit.diagnostics.operation_log import configure_geometry_operation_logging, geometry_log_status
from geoai_simkit.services.dependency_preflight import build_dependency_preflight_report


CANONICAL_WORKBENCH_MODULE = "geoai_simkit.app.shell.phase_workbench_qt"
CANONICAL_WORKBENCH_FUNCTION = "launch_phase_workbench_qt"


@dataclass(slots=True)
class LaunchDiagnostics:
    gui_ready: bool
    message: str
    missing_feature: str | None = None
    pyvista_ready: bool = False
    fallback_available: bool = True
    canonical_workbench_module: str = CANONICAL_WORKBENCH_MODULE
    legacy_gui_disabled: bool = True


def _module_import_report(name: str) -> dict[str, Any]:
    try:
        import_module(name)
        return {"available": True, "error": None}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def validate_desktop_gui_environment() -> LaunchDiagnostics:
    """Validate only the canonical Qt shell requirement.

    The previous launcher treated PyVista/VTK readiness as a gate for starting
    the whole application.  That caused import-driven workflows and all right
    dock buttons to appear unavailable whenever the 3D adapter was unhealthy.
    The canonical workbench can start in Qt-only mode; PyVista is checked inside
    the viewport adapter and can be disabled with GEOAI_SIMKIT_DISABLE_PYVISTA=1.
    """
    report = build_dependency_preflight_report()
    if "PySide6" in getattr(report, "missing_required", []):
        return LaunchDiagnostics(False, "PySide6 is required for the desktop workbench.", missing_feature="PySide6")
    try:
        import_module("PySide6")
    except Exception as exc:
        return LaunchDiagnostics(False, f"PySide6 import failed: {type(exc).__name__}: {exc}", missing_feature="PySide6")
    pyvista_ready = False
    try:
        from geoai_simkit.services.dependency_preflight import is_pyvista_stack_ready

        pyvista_ready, _ = is_pyvista_stack_ready()
    except Exception:
        pyvista_ready = False
    return LaunchDiagnostics(True, "Canonical PhaseWorkbenchQt can start.", pyvista_ready=bool(pyvista_ready))


def build_desktop_gui_startup_report(*, offscreen: bool = True, debug: bool = False, debug_dir: str | None = None) -> dict[str, Any]:
    if offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if debug:
        configure_geometry_operation_logging(enabled=True, debug_dir=debug_dir)
    diagnostics = validate_desktop_gui_environment()
    dependency_preflight = build_dependency_preflight_report().to_dict()
    module_reports = {CANONICAL_WORKBENCH_MODULE: _module_import_report(CANONICAL_WORKBENCH_MODULE)}
    payload_report: dict[str, Any]
    try:
        from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload

        payload = build_phase_workbench_qt_payload()
        payload_report = {
            "available": True,
            "contract": payload.get("contract") if isinstance(payload, dict) else None,
            "version": payload.get("version") if isinstance(payload, dict) else None,
            "gui_action_contract": dict(payload.get("gui_action_audit", {}) or {}).get("contract") if isinstance(payload, dict) else None,
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
            qt_report = {"available": True, "created": created, "platform": QtWidgets.QApplication.platformName(), "error": None}
        except Exception as exc:
            qt_report = {"available": False, "created": False, "platform": None, "error": f"{type(exc).__name__}: {exc}"}
    imports_ok = all(row["available"] for row in module_reports.values())
    ok = bool(diagnostics.gui_ready and imports_ok and payload_report.get("available") and qt_report.get("available"))
    return {
        "ok": ok,
        "entrypoint": "start_gui.py",
        "launch_path": "phase_workbench_qt" if diagnostics.gui_ready else "blocked",
        "canonical_workbench_module": CANONICAL_WORKBENCH_MODULE,
        "legacy_workbench_window_skipped": True,
        "legacy_gui_entrypoints_disabled": True,
        "diagnostics": asdict(diagnostics),
        "dependency_preflight": dependency_preflight,
        "imports": module_reports,
        "qt_application": qt_report,
        "workbench_payload": payload_report,
        "geometry_debug_logging": geometry_log_status(),
    }


def launch_desktop_workbench(*, debug: bool = False, debug_dir: str | None = None, preflight: bool = True) -> None:
    if debug:
        configure_geometry_operation_logging(enabled=True, debug_dir=debug_dir)
    if preflight and os.environ.get("GEOAI_SIMKIT_SKIP_PREFLIGHT", "").strip() != "1":
        from geoai_simkit.app.shell.startup_dependency_dialog import run_startup_dependency_dialog

        decision = run_startup_dependency_dialog(show_success=True)
        if not decision.user_continue:
            return
    diagnostics = validate_desktop_gui_environment()
    if not diagnostics.gui_ready:
        raise RuntimeError(diagnostics.message)
    from geoai_simkit.app.shell.phase_workbench_qt import launch_phase_workbench_qt

    launch_phase_workbench_qt()


def _build_launch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the canonical GeoAI SimKit PhaseWorkbenchQt GUI")
    parser.add_argument("--debug", action="store_true", help="Enable geometry-kernel debug logging for this GUI run")
    parser.add_argument("--log-dir", default=None, help="Debug log directory; defaults to ./log when --debug is used")
    parser.add_argument("--skip-preflight", action="store_true", help="Developer option: skip the dependency preflight screen")
    parser.add_argument("--qt-only", action="store_true", help="Disable PyVista/VTK viewport adapter and run the same workbench in Qt-only mode")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_launch_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    if getattr(args, "qt_only", False):
        os.environ["GEOAI_SIMKIT_DISABLE_PYVISTA"] = "1"
    try:
        launch_desktop_workbench(debug=bool(args.debug), debug_dir=args.log_dir, preflight=not bool(args.skip_preflight))
        return 0
    except Exception as exc:
        print("GeoAI SimKit GUI could not start:")
        print(f"{type(exc).__name__}: {exc}")
        return 2


__all__ = [
    "CANONICAL_WORKBENCH_MODULE",
    "LaunchDiagnostics",
    "build_desktop_gui_startup_report",
    "launch_desktop_workbench",
    "main",
    "validate_desktop_gui_environment",
]
