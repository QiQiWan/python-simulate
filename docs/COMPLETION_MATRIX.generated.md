# Completion matrix

Generated from the same JSON artifacts written by `tools/run_core_fem_smoke.py` and `run_solver_benchmarks.py`.

Core smoke suite: `core_fem_numerical_smoke`
Core smoke passed: **7/7**
Solver benchmark suite: `not_run`
Solver benchmarks passed: **0/0**

| Module | Namespace | Numerical smoke | Status |
|---|---|---:|---|
| Geometry | `geoai_simkit.geometry` | True | benchmark_grade |
| Mesh | `geoai_simkit.geometry.mesh_engine` | True | benchmark_grade |
| Material | `geoai_simkit.materials` | True | benchmark_grade |
| Element | `geoai_simkit.solver` | True | benchmark_grade |
| Assembly | `geoai_simkit.solver.linsys` | True | benchmark_grade |
| Solver | `geoai_simkit.solver` | True | benchmark_grade |
| Result | `geoai_simkit.results` | True | benchmark_grade |

## Advanced capability-gated modules

| Module | Namespace | Status |
|---|---|---|
| gpu_native | `geoai_simkit.solver.gpu_native` | capability_gated |
| occ_native | `geoai_simkit.geometry.occ_native_naming` | capability_gated |
| uq | `geoai_simkit.advanced.uq` | capability_gated |
