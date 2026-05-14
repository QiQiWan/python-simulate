# GeoAI SimKit 1.5.2 — GUI Module Matrix and OpenGL Guard

## Scope

This iteration expands the CAD desktop workbench from a compact CAD/FEM bridge into a full workflow-module matrix.  The GUI now carries headless contracts for the controls required by project setup, CAD authoring, native topology, materials, construction stages, CAD-FEM preprocessing, meshing, solver setup, results, benchmark/readiness, and runtime diagnostics.

The iteration also hardens the PyVista/VTK viewport against the Windows VTK warning:

```text
vtkWin32OpenGLRenderWindow: wglMakeCurrent failed in MakeCurrent(), error: The operation completed successfully.(code 0)
```

## GUI module matrix

`geoai_simkit.core.gui_workflow_module_spec` now exposes contract `geoai_simkit_gui_workflow_module_spec_v2` with these modules:

1. Project / data intake
2. Structure / geometry modeling
3. Native CAD / topology identity
4. Material library / quick assignment
5. Construction stages / activation-deactivation
6. Topology / FEM preprocessing
7. Meshing / quality check
8. Solver setup / run
9. Results / reporting
10. Benchmark / readiness / repair suggestions
11. Runtime diagnostics / logs

Each module defines required elements, actions, data bindings, outputs, readiness checks, panel region, and lifecycle order.  The bottom GUI tab `模块界面` displays the same module matrix.

## OpenGL guard

New module:

```text
src/geoai_simkit/app/viewport/opengl_context_guard.py
```

It provides:

- `QtVTKOpenGLRuntimePolicy`
- `OpenGLContextGuardState`
- `apply_qt_vtk_opengl_policy`
- `widget_exposure_state`

The launcher now applies Qt OpenGL policy before creating `QApplication`:

- `AA_ShareOpenGLContexts`
- conservative `QSurfaceFormat`
- optional software OpenGL through `GEOAI_SIMKIT_QT_OPENGL=software`

The PyVista adapter now skips renders while the widget is hidden, closing, disabled, or not exposed.  It suspends repeated renders after a VTK/OpenGL context exception and exposes guard state in the 3D diagnostics tab.

## Operational fallback

When the workstation OpenGL stack is unstable, launch with:

```powershell
$env:GEOAI_SIMKIT_DISABLE_PYVISTA="1"
python .\start_gui.py
```

For RDP or driver issues, try:

```powershell
$env:GEOAI_SIMKIT_QT_OPENGL="software"
python .\start_gui.py
```

## Tests

Added:

```text
tests/gui/test_iter152_gui_module_matrix_opengl_guard.py
```

Updated:

```text
tests/gui/test_iter151_cad_gui_interaction_materials.py
```
