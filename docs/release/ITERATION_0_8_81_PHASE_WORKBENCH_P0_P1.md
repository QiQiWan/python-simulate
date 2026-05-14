# Iteration 0.8.81 - Phase Workbench P0/P1

## Scope

This iteration starts the PLAXIS-like six-phase workbench migration and connects the existing headless viewport tool runtime to the PyVista shell.

## P0 - Phase-driven GUI shell

- Added a GUI-facing `phase_workbench_ui_state_v1` contract.
- Added runtime-tool mapping metadata to phase ribbon tools.
- Updated the PyVista NextGen workbench so the top shell uses:
  - one work-phase toolbar: `地质 / 结构 / 网格 / 阶段配置 / 求解 / 结果查看`
  - one dynamic phase ribbon rebuilt from `WorkbenchPhaseService`
  - a small project quick toolbar for file-level actions only
- Routed phase ribbon commands to existing workbench handlers where available.
- Added phase-specific left/right panel synchronization.

## P1 - PyVista viewport runtime bridge

- Added `WorkPlaneController` for XZ/XY/YZ/custom surface projection.
- Added `PyVistaViewportAdapter` to translate PyVista/VTK mouse and key events into `ToolEvent` objects.
- Connected `ViewportToolRuntime` to the PyVista workbench with command-stack-backed point/line/surface/box creation.
- Added preview rendering support for point, line, surface and box tool outputs.
- Rendered `ViewportState` primitives from `GeoProjectDocument` so interactive geometry is visible even when no prepared solver mesh exists.

## Verification

- `PYTHONPATH=src pytest -q tests/core/test_iter80_phase_workbench_and_viewport_runtime.py`
- `PYTHONPATH=src pytest -q tests/core/test_iter81_p0_p1_phase_shell_and_pyvista_adapter.py`
- `PYTHONPATH=src pytest -q tests/gui/test_start_gui_startup_smoke.py`
- `PYTHONPATH=src pytest -q tests/visual_modeling/test_geoproject_document_framework.py tests/visual_modeling/test_geometry_editor_smoke.py tests/visual_modeling/test_mouse_geometry_interaction_smoke.py`
