# GeoAI SimKit v0.8.20 Stabilization Notes

This iteration is a stabilization pass focused on making the package fail honestly, install cleanly, and execute a real finite-element smoke path.

## Implemented

1. **Solver missing modules fixed**
   - Added `geoai_simkit.solver.linsys.sparse_block`.
   - Added `geoai_simkit.solver.warp_hex8`.
   - Unblocked imports from `tet4_linear.py` and `linear_algebra.py`.

2. **Strict solver result policy**
   - `SolverSettings.result_mode` now defaults to `strict`.
   - Unsupported full-model solve paths fail instead of producing synthetic engineering results.
   - Synthetic/demo visualization fields are only allowed in explicit `demo` or compatibility fallback modes.
   - Synthetic results are marked with `synthetic_result=True` and `engineering_valid=False`.

3. **Standard packaging**
   - Added `pyproject.toml`.
   - Added dependency split files:
     - `requirements-core.txt`
     - `requirements-gui.txt`
     - `requirements-meshing.txt`
     - `requirements-gpu.txt`
     - `requirements-dev.txt`
   - Added console entry points:
     - `geoai-simkit`
     - `geoai-simkit-gui`

4. **Regression tests**
   - Added strict result-mode tests.
   - Added sparse block matrix tests.
   - Added Tet4 smoke test.
   - Added lazy GUI viewport bridge import test.
   - Added opt-in slow staged pit closed-loop smoke test.

5. **Unified GUI viewport bridge**
   - The unified workbench now initializes an optional PyVista viewport panel on the Scene page.
   - Editable blocks are rendered as pickable PyVista cube actors when GUI dependencies are installed.
   - Existing event binder connects pick, hover, box selection, context menu, and drag hooks to the unified controller.
   - Headless or missing-GUI environments degrade to a visible dependency message instead of crashing.

6. **Geometry-mesh-stage-support-solve closure**
   - The existing Tet4 smoke and staged pit smoke are now treated as strict-mode regression paths.
   - Staged pit smoke remains opt-in for normal pytest runs because it is slower than the lightweight solver tests.

## Verified commands

```bash
python -m pytest -q --import-mode=importlib tests/test_iter80_solver_stabilization.py tests/test_iter76_gui_native_component_binding_contracts.py tests/test_iter77_modern_workspace_contracts.py
```

Expected result:

```text
13 passed, 1 skipped
```

To run the slower closed-loop foundation pit smoke:

```bash
GEOAI_RUN_SLOW_TESTS=1 python -m pytest -q tests/test_iter80_solver_stabilization.py::test_pit_tet4_closed_loop_runs_in_strict_mode
```

## Install

Core only:

```bash
pip install -e .
```

GUI:

```bash
pip install -e ".[gui]"
```

Meshing:

```bash
pip install -e ".[meshing]"
```

Developer test environment:

```bash
pip install -e ".[dev,gui,meshing]"
```

## Known limitations

- The optional PyVista viewport bridge is now connected to the unified workbench, but advanced actor-level selection highlighting and camera-aware world-plane dragging still need deeper refinement.
- OCC persistent naming still has a fingerprint fallback path; true native TNaming history tracking is not yet fully implemented.
- HSS/HSsmall and strict frictional contact remain research-grade paths and should not be advertised as final production solvers.
- GPU native nonlinear assembly is still not the default verified path. The verified smoke route is Tet4 CPU/reference execution.
