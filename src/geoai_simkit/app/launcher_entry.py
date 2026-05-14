from __future__ import annotations

"""Canonical desktop GUI launcher shared by root scripts and console entry points."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from geoai_simkit._version import __version__


def _ensure_runtime_dirs(root: Path) -> None:
    for name in ("exports", "autosave", "reports", "log"):
        (root / name).mkdir(parents=True, exist_ok=True)


def _launcher_info(root: Path, launcher_name: str) -> dict[str, Any]:
    import geoai_simkit

    return {
        "contract": "geoai_simkit_gui_launcher_info_v9",
        "launcher": launcher_name,
        "canonical_entrypoint": "start_gui.py",
        "non_install_entrypoints": ["start_gui.py"],
        "removed_non_install_entrypoints": ["run_gui.py", "src/start_gui.py"],
        "install_entrypoints": ["geoai-simkit-gui", "python -m geoai_simkit gui"],
        "version": __version__,
        "repo_root": str(root),
        "canonical_workbench_module": "geoai_simkit.app.shell.phase_workbench_qt",
        "legacy_workbench_window_skipped": True,
        "file_dialog_policy": "explicit_path_first_plus_dialog_action_dispatcher_plus_runtime_button_smoke",
        "gui_action_dispatch": "all production buttons registered through canonical action state and runtime smoke-checked; legacy GUI modules disabled",
        "legacy_gui_modules_disabled": ["workbench_window", "modern_qt_workbench", "main_window", "fallback_gui", "unified_workbench_window.launcher"],
        "package_file": str(Path(getattr(geoai_simkit, "__file__", "")).resolve()),
        "python": sys.executable,
        "local_src_preferred": str(Path(getattr(geoai_simkit, "__file__", "")).resolve()).startswith(str((root / "src").resolve())),
        "warning_if_old_gui": "For non-install startup use only repository-root start_gui.py. The only supported GUI window is geoai_simkit.app.shell.phase_workbench_qt.",
        "mesh_visualization": "ParaView-like extracted surface display with categorical soil_id/gmsh_physical layers, boundary wireframe, feature edges and outline",
        "fem_mesh_optimization": "layer identification, nonmanifold diagnostics, conservative mesh weight reduction and FEM quality checks",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the GeoAI SimKit desktop GUI. Non-install startup is repository-root start_gui.py only.")
    parser.add_argument("--smoke", action="store_true", help="Run a non-blocking GUI startup smoke report")
    parser.add_argument("--info", action="store_true", help="Print launcher/version/path diagnostics and exit")
    parser.add_argument("--debug", action="store_true", help="Enable geometry-kernel debug logging for this GUI run")
    parser.add_argument("--log-dir", default=None, help="Debug log directory; defaults to ./log when --debug is used")
    parser.add_argument("--skip-preflight", action="store_true", help="Developer option: skip the startup dependency preflight screen")
    parser.add_argument("--qt-only", action="store_true", help="Start the desktop workbench without PyVista/VTK OpenGL rendering")
    return parser


def main(argv: list[str] | None = None, *, repo_root: str | Path | None = None, launcher_name: str = "start_gui.py") -> int:
    args = build_parser().parse_args(list(argv or []))
    root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
    _ensure_runtime_dirs(root)
    log_dir = args.log_dir or str(root / "log")
    try:
        if args.info:
            print(json.dumps(_launcher_info(root, launcher_name), indent=2, ensure_ascii=False, default=str))
            return 0
        if args.qt_only:
            os.environ["GEOAI_SIMKIT_DISABLE_PYVISTA"] = "1"
        if args.debug:
            from geoai_simkit.diagnostics.operation_log import configure_geometry_operation_logging

            configure_geometry_operation_logging(enabled=True, debug_dir=log_dir)
        if args.smoke:
            from geoai_simkit.app.launch import build_desktop_gui_startup_report

            report = build_desktop_gui_startup_report(offscreen=True, debug=bool(args.debug), debug_dir=log_dir if args.debug else None)
            report["launcher_info"] = _launcher_info(root, launcher_name)
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return 0 if report.get("ok") else 2
        from geoai_simkit.app.launch import launch_desktop_workbench

        if args.skip_preflight:
            os.environ["GEOAI_SIMKIT_SKIP_PREFLIGHT"] = "1"
        try:
            launch_desktop_workbench(debug=bool(args.debug), debug_dir=log_dir if args.debug else None)
        except Exception as first_exc:
            if args.qt_only:
                raise
            os.environ["GEOAI_SIMKIT_LAST_LAUNCH_ERROR"] = f"{type(first_exc).__name__}: {first_exc}"
            os.environ["GEOAI_SIMKIT_DISABLE_PYVISTA"] = "1"
            os.environ["GEOAI_SIMKIT_SKIP_PREFLIGHT"] = "1"
            print("GeoAI SimKit GUI primary launch failed; retrying Qt-only workbench...")
            print(f"Primary launch error: {type(first_exc).__name__}: {first_exc}")
            launch_desktop_workbench(debug=bool(args.debug), debug_dir=log_dir if args.debug else None, preflight=False)
        return 0
    except Exception as exc:
        print("GeoAI SimKit GUI could not start:")
        print(f"{type(exc).__name__}: {exc}")
        try:
            from geoai_simkit.services.dependency_preflight import build_dependency_preflight_report, render_dependency_preflight_text

            print("")
            print(render_dependency_preflight_text(build_dependency_preflight_report()))
        except Exception:
            pass
        print("")
        print("Launcher diagnostics:")
        try:
            print(json.dumps(_launcher_info(root, launcher_name), indent=2, ensure_ascii=False, default=str))
        except Exception:
            pass
        print("")
        print("Suggested recovery:")
        print("  Run `python .\\start_gui.py --info` and confirm package_file points to this checkout's src directory.")
        print("  In a conda environment, install the full GUI/3D/meshing stack with conda-forge:")
        print("    conda install -c conda-forge numpy scipy pyside6 qtpy vtk pyvista pyvistaqt gmsh meshio ifcopenshell ocp")
        print("  Do NOT run pip --force-reinstall vtk over a conda-installed VTK package.")
        print("  After the conda stack is healthy, install project Python requirements:")
        print("    python -m pip install -r requirements.txt")
        return 2


__all__ = ["build_parser", "main"]
