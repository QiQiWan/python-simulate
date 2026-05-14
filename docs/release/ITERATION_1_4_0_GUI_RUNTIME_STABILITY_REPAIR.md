# Iteration 1.4.0 Beta-2 GUI Runtime Stability Repair

## Problems found

1. Long-running Demo and solver actions executed on the Qt GUI thread.  During a full calculation the event loop could freeze, making the application look interrupted or unresponsive.
2. The unified launcher still contained legacy flat-GUI fallback paths (`modern_qt_workbench`, `main_window`, Tk fallback).  If the modern workbench failed, users could still land in old UI shells.
3. Some action failures were surfaced only in the status bar or terminal, so a user could not distinguish a running job, ignored click, failed job, or completed export.
4. `requirements.txt` listed the full stack, but tests and older install workflows expected explicit `gmsh` and `meshio` entries.  The file now keeps those dependencies explicit.

## Repairs

- Added background worker execution for the PySide-only phase workbench Demo actions:
  - run selected template complete calculation
  - run all 1.4 templates
  - guarded repeated clicks while an operation is already running
- Added background worker execution for the PyVista NextGen solver run.
- Removed default legacy flat-GUI fallbacks from `unified_workbench_window.py`; startup now launches only:
  - PyVista six-phase workbench, or
  - PySide six-phase workbench fallback if PyVista window construction fails.
- If `GEOAI_SIMKIT_LEGACY_GUI=1` is set, startup now raises a clear error instead of entering the legacy flat editor.
- Updated GUI tests to enforce the no-legacy-launcher contract and background-worker contract.

## Validation

Commands run:

```bash
PYTHONPATH=src:. pytest -q tests/gui
PYTHONPATH=src:. pytest -q tests/workflow
PYTHONPATH=src:. pytest -q tests/core
PYTHONPATH=src:. pytest -q tests/architecture tests/runtime tests/solver
PYTHONPATH=src python -m compileall -q src tests
```

Results:

- `tests/gui`: 13 passed, 1 skipped
- `tests/workflow`: 55 passed
- `tests/core`: 100 passed
- `tests/architecture + tests/runtime + tests/solver`: 138 passed
- `compileall`: passed

The single skipped GUI test is the expected no-display/headless skip.
