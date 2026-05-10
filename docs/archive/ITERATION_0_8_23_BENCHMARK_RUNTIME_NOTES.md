# GeoAI SimKit v0.8.23-benchmark-runtime

This iteration extends v0.8.22 from Tet4-focused smoke verification to a broader benchmark/runtime layer.

## Added benchmark gates

- Hex8 affine patch test at the element center.
- Truss axial closed-form benchmark.
- 3D Euler-Bernoulli beam cantilever single-element benchmark.
- Plate4 membrane affine patch benchmark.
- Wall-soil Coulomb interface open/stick/slip benchmark.
- Mohr-Coulomb material-point regression for elastic compression, tension cutoff and triaxial loading.
- HSS/HSsmall material-point state-variable regression.
- Tet4 cantilever mesh convergence trend benchmark.
- JSON, Markdown and CSV benchmark report export.

## Cross-platform no-install runtime

Root-level launchers were added:

- `run_gui_no_install.py`
- `run_gui_no_install.bat`
- `run_gui_no_install.sh`
- `run_gui_no_install.command`
- `run_solver_benchmarks.py`
- `run_solver_benchmarks.bat`
- `run_solver_benchmarks.sh`

The launchers add `./src` to `sys.path` and do not install the current package. Runtime dependencies such as PySide6, pyvista, pyvistaqt, gmsh, meshio, or scipy are still installed separately when needed.

## Current limitations

The new Hex8, beam and plate checks are element-level benchmarks. They do not yet mean that the full production nonlinear Hex8 solver, full shell bending formulation, native GPU nonlinear assembly, or complete HSsmall engineering validation is finished.
