# Completion Matrix

The completion matrix is generated from dependency-light core FEM smoke checks.

Run:

```bash
python tools/run_core_fem_smoke.py
```

Generated files:

```text
reports/core_fem_smoke_results.json
docs/COMPLETION_MATRIX.generated.md
```

Status terms are evidence-driven: `usable_core`, `benchmark_grade`, `research_scaffold`, `capability_probe`, `blocked`, and `not_run`.
