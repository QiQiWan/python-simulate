# GeoAI SimKit 1.5.0 - GUI Benchmark / Readiness Panel

This iteration connects the P8.5 STEP/IFC native benchmark report to the desktop GUI and simplifies the workbench layout.

## Added

- STEP/IFC benchmark readiness loader: `geoai_simkit.app.shell.benchmark_panel.load_step_ifc_benchmark_readiness_payload`.
- GUI contract: `geoai_simkit_step_ifc_gui_readiness_panel_p90_v1`.
- Benchmark bottom tab showing per-case status, native backend use, BRep certification, persistent naming stability, physical group stability, mesh entity map stability, solver region map stability, lineage verification and topology counts.
- Fix suggestion bottom tab. Each blocker from the P8.5 report is converted into a suggested corrective action.
- Floating help/fix-detail dock. Clicking a benchmark case or fix suggestion updates this dock with blockers, warnings, artifacts and commands/actions.

## GUI cleanup

- The right dock is reduced to two operational tabs: properties and semantic/material/phase assignment.
- Workflow, demo status, diagnostics, dependency checks, logs, readiness, benchmark and fixes are consolidated into bottom tabs.
- Long workflow descriptions have been shortened to a CAD -> Mesh -> Solve preprocessor chain.

## Report expectations

The GUI reads these report paths by default:

- `reports/step_ifc_native_benchmark.json`
- `reports/step_ifc_native_benchmark_dryrun.json`
- `step_ifc_native_benchmark.json`

Use native certification mode for evidence:

```powershell
$env:PYTHONPATH="src"
python .\tools\run_step_ifc_native_benchmark.py .\benchmarks\step_ifc\manifest.json --output .\reports\step_ifc_native_benchmark.json
```

Use fallback dry-run only for workflow checks:

```powershell
$env:PYTHONPATH="src"
python .\tools\run_step_ifc_native_benchmark.py .\benchmarks\step_ifc --allow-fallback --output .\reports\step_ifc_native_benchmark_dryrun.json
```
