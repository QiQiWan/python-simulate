# Iteration 0.8.21-hardening

## Goal

This version continues the stabilization work from v0.8.20 and focuses on hardening the parts that decide whether the software is trustworthy: layered tests, consistent versioning, evidence-based blueprint progress, strict solver result policy, mesh-quality solve gates, CAD-grade drag foundations, object-level stage actions, and first-pass structural stiffness coupling.

## Implemented

1. **Layered test governance**
   - Added pytest markers: `fast`, `solver`, `gui`, `slow`, `gpu`, `meshing`.
   - Added `tests/fast/test_iter81_fast_contracts.py`.
   - Added `tests/solver/test_iter81_hardening.py`.
   - Added `tests/gui/test_iter81_gui_contracts.py`.

2. **Version and dependency cleanup**
   - Updated package version to `0.8.21`.
   - Updated replacement package label to `0.8.21-hardening`.
   - Moved SciPy out of the core dependency list and into the `solver` extra.
   - Added `requirements-solver.txt`.

3. **Strict result policy hardened**
   - `strict` mode can no longer be weakened by model metadata such as `allow_synthetic_results=True`.
   - Synthetic/demo fields remain allowed in explicit `demo` mode and opt-in `dev` mode only.

4. **Evidence-based blueprint progress**
   - Replaced hand-written optimistic progress with a scanner that scores actual file/test evidence.
   - Missing evidence is surfaced in module blockers instead of being hidden behind high percentages.

5. **Mesh quality solve gate**
   - Added `solver/mesh_quality_gate.py`.
   - Strict solves can reject known-bad mesh-quality reports before assembly.
   - The gate report is stored in model metadata and stage solver metadata.

6. **Object-level staged construction actions**
   - Added `StageAction` to the core model.
   - `AnalysisStage.actions` supports actions on blocks/regions/excavation zones.
   - `StageManager` now resolves these actions alongside legacy region activation fields.

7. **CAD-style viewport drag foundation**
   - Added working-plane drag helpers under `app/viewport/edit_tools/`.
   - Qt/PyVista drag events now use camera-aware working-plane translation instead of fixed pixel scaling.

8. **Support stiffness enters the Tet4 solve path**
   - Added `solver/structural/truss3d.py`.
   - `truss2`, `anchor2`, `strut2`, `tie2`, `cable2`, and similar two-node axial supports assemble stiffness into the Tet4 global DOF space.
   - Pretension/preload is assembled as equivalent nodal forces.
   - Non-truss beam/plate/shell structures are explicitly reported as unsupported instead of being silently ignored.

## Verified checks

```bash
python -m pytest -q tests/fast/test_iter81_fast_contracts.py tests/solver/test_iter81_hardening.py tests/gui/test_iter81_gui_contracts.py
# 8 passed

python -m pytest -q tests/test_iter80_solver_stabilization.py tests/test_iter76_gui_native_component_binding_contracts.py tests/test_iter77_modern_workspace_contracts.py
# 13 passed, 1 skipped
```

The warning about `.pytest_cache` permissions is an artifact of the sandbox path and does not affect the code checks.

## Remaining limitations

- CPU Tet4 remains the main trusted reference path.
- Truss-like supports are assembled, but full beam/plate/shell rotational coupling is still pending.
- Mesh quality gate must still be wired into the GUI Solve button state and final result-package acceptance.
- CAD interaction still needs snapping, axis handles, undo grouping and OCC-native topology history.
- GPU/Warp runtime still needs real device benchmark evidence.
