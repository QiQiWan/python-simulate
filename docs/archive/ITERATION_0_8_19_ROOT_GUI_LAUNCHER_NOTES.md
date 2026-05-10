# Iteration 0.8.19 root GUI launcher patch

This patch adds no-install GUI entry points at the project root.

## New root entry points

- `start_gui.py` — cross-platform Python launcher, automatically adds `src/` to `sys.path`.
- `start_gui.bat` / `启动GUI.bat` — Windows launcher.
- `start_gui.sh` — Linux launcher.
- `start_gui.command` / `启动GUI.command` — macOS launcher.
- `check_gui_env.py` — dependency check entry.
- `GUI_START_HERE.md` — quick run guide.
- `_no_install_bootstrap.py` — shared no-install bootstrap.

## Behavior

The launcher does not install the package. It only injects the local `src/` directory into Python's import path, creates `logs/`, `exports/`, and `autosave/`, checks GUI dependencies, and launches the unified workbench.

Startup failures are written to `logs/gui_startup.log`.
