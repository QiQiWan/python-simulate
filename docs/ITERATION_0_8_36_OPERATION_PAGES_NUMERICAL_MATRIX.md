# Iteration 0.8.36 — operation pages, numerical smoke, and matrix linkage

## Completed changes

1. GUI workflow spaces now use six canonical operation pages: `modeling`, `mesh`, `solve`, `results`, `benchmark`, and `advanced`.
2. Legacy internal spaces `project`, `model`, `diagnostics`, and `delivery` are retained only as compatibility aliases.
3. Each core FEM facade now calls a numerical smoke check rather than only checking imports.
4. `tools/run_core_fem_smoke.py` writes `reports/core_fem_smoke_results.json` and regenerates `docs/COMPLETION_MATRIX.generated.md/json`.
5. `run_solver_benchmarks.py` is wired to mirror benchmark JSON into `reports/benchmark_report.json` and regenerate the same completion matrix.
6. Legacy test names using old production/commercial/fully_resident wording were moved to status-gated / residency-gated vocabulary.

## Validation snapshot

- Core FEM numerical smoke: 7/7 passed.
- Six operation pages expose panels and operations, not only table rows.
- Completion matrix is generated from smoke/benchmark JSON artifacts.
- Full solver benchmark suite is still environment-sensitive; if it is not run, the generated matrix records `benchmark: not_run` honestly.
