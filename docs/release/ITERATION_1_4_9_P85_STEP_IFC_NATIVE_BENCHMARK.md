# GeoAI SimKit 1.4.9 - P8.5 STEP/IFC Native Benchmark Completion

## Scope

This iteration completes the P8.5 benchmark layer for real STEP/IFC desktop validation.  The goal is to turn native CAD claims into file-driven evidence before the model is trusted for meshing and solve pre-processing.

## Added runtime entry points

- `geoai_simkit.core.step_ifc_native_benchmark`
- `geoai_simkit.services.step_ifc_native_benchmark`
- `tools/run_step_ifc_native_benchmark.py`

## What the benchmark verifies

For each `.step`, `.stp` or `.ifc` file, or each case in a JSON/JSONL manifest, the runner verifies:

1. STEP/IFC import capability and whether the run used a native backend.
2. CadShapeStore topology identity coverage for solids, faces and edges.
3. Persistent topology name stability across repeated imports.
4. CAD-FEM physical group generation and repeated-run stability.
5. Planned mesh entity map generation for downstream Gmsh/meshio tagging.
6. Solver region map generation with material-bearing physical volume groups.
7. Boolean/OCC lineage evidence when the manifest explicitly sets `require_lineage=true`.

## Native certification policy

`require_native=True` is the default.  In this mode, a case is blocked if the host does not expose the required native STEP/IFC runtime.  Fallback imports can be used with `--allow-fallback`, but those runs are reported as dry-run diagnostics and do not certify native BRep behavior.

## CLI usage

Create a manifest template:

```powershell
$env:PYTHONPATH="src"
python .\tools\run_step_ifc_native_benchmark.py --write-template .\benchmarks\step_ifc\manifest.json
```

Run real native certification:

```powershell
$env:PYTHONPATH="src"
python .\tools\run_step_ifc_native_benchmark.py .\benchmarks\step_ifc\manifest.json --output .\reports\step_ifc_native_benchmark.json
```

Run fallback dry-run diagnostics in CI or a minimal environment:

```powershell
$env:PYTHONPATH="src"
python .\tools\run_step_ifc_native_benchmark.py .\benchmarks\step_ifc --allow-fallback --output .\reports\step_ifc_native_benchmark_dryrun.json
```

## Manifest fields

Each case supports:

```json
{
  "case_id": "complex_surface_step_boolean_history",
  "source_path": "benchmarks/step_ifc/complex_surface_boolean.step",
  "category": "complex_step_surface_boolean_history",
  "require_native": true,
  "expected_min_solids": 1,
  "expected_min_faces": 8,
  "expected_min_edges": 12,
  "require_physical_groups": true,
  "require_solver_region_map": true,
  "require_mesh_entity_map": true,
  "require_lineage": true
}
```

Use `require_lineage=true` only for benchmark files that are paired with native boolean history evidence.  Import-only STEP/IFC files are expected to produce operation history, but not split/merge lineage.

## Output artifacts

The main report is written to the requested `--output` path.  Per-case artifacts are written beside the report under `step_ifc_native_benchmark_artifacts/`, including:

- `cad_fem_preprocessor.json`
- `planned_mesh_entity_map.json`
- `solver_region_map.json`
- `lineage_summary.json`
- imported shape references

## GUI contract

`build_phase_workbench_qt_payload()` now exposes `p85_step_ifc_native_benchmark` under `geometry_interaction`, so the benchmark/readiness panels can discover the service, CLI and validated evidence categories.
