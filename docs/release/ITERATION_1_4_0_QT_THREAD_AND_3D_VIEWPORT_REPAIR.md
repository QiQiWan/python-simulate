# Iteration 1.4.0 Beta-2 — Qt Thread Safety and 3D Viewport Repair

## Problem

The desktop workbench could print repeated Qt runtime warnings on Windows/PySide6:

- `QBasicTimer::start: Timers cannot be started from another thread`
- `QObject: Cannot create children for a parent that is in a different thread`
- `QThread::wait: Thread tried to wait on itself`

The PySide-only phase workbench also displayed a 2D projection-style preview. For the foundation-pit demo this was misleading: the engineering model is 3D and the visual modeling area must show a 3D model.

## Root causes

1. Long-running GUI actions used `QThread` and connected worker signals to nested Python callbacks. On some PySide/Windows builds, these callbacks could execute in the worker thread and update `QTextEdit`, status bars or message boxes outside the GUI thread.
2. Cleanup called `thread.wait()` from a callback that could run on the worker thread, causing self-wait warnings.
3. The fallback phase workbench used `QGraphicsView` to draw an X-Z projection. That confirmed object counts but was not a 3D viewport.

## Fixes

1. Replaced GUI `QThread` background dispatch in both workbenches with:
   - `ThreadPoolExecutor(max_workers=1)` for pure calculation/export work.
   - A main-thread `QTimer` to poll completion and update widgets safely.
   - No worker thread directly touches Qt widgets.
2. Removed `thread.wait()` and `worker.moveToThread()` from the long-running task path.
3. Reworked the PySide phase workbench center panel to embed a real `pyvistaqt.QtInteractor`.
4. The existing method name `_render_lightweight_model_scene()` is retained for compatibility, but now renders the current `ViewportState` into PyVista/VTK as 3D blocks, surfaces, supports and interfaces.
5. The old 2D projection text and `QGraphicsView` preview were removed from the production path.

## Expected behavior

- Starting the GUI should no longer print repeated `QBasicTimer` or cross-thread `QTextDocument` warnings.
- Running the selected template or all templates should keep the GUI responsive.
- The foundation-pit demo should display 3D soil volumes, excavation volumes, walls/supports and interfaces in the model visualization area.
- Logs and status messages should update only after background tasks complete on the GUI thread.

## Verification

Targeted tests passed:

- `tests/gui/test_gui_thread_safety_and_3d_viewport_contract.py`
- `tests/gui/test_gui_runtime_interruption_and_legacy_cleanup.py`
- `tests/gui/test_gui_visualization_diagnostics_and_actions.py`
- `tests/workflow/test_iter140_release_1_4_0_multi_template_workflow.py`
- `tests/core/test_iter81_p0_p1_phase_shell_and_pyvista_adapter.py`

Additional grouped regressions passed for workflow and core subsets. `compileall` passed.
