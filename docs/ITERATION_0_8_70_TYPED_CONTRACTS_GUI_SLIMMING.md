# Iteration 0.8.70 - Typed Contract Hardening and Main Window Physical Slimming

## Scope

This iteration combines the 0.8.69 typed contract hardening work with the 0.8.70 GUI physical slimming work.

## 0.8.69 Typed Contract Hardening

- Added `geoai_simkit.contracts.payloads`.
- Added typed envelopes:
  - `WorkflowArtifactPayload`
  - `PluginRegistrationPayload`
  - `MeshPayload`
  - `SolverInputPayload`
  - `SolverOutputPayload`
  - `MaterialMappingPayload`
  - `QualityGatePayload`
- Removed exposed `typing.Any` annotations from public contract sources under `geoai_simkit.contracts`.
- Preserved compatibility for legacy workflow reports and manifests.
- Added typed payload rows to workflow artifact manifests.
- Added typed plugin registration payloads to external plugin load records.

## 0.8.70 Main Window Physical Slimming

- Moved the full legacy Qt implementation from `app/main_window.py` to `app/main_window_impl.py`.
- Replaced `app/main_window.py` with a thin compatibility entrypoint.
- Preserved imports for:
  - `MainWindow`
  - `SolverSettings`
  - `UIStyle`
  - `launch_main_window`
  - `resolve_app_icon`
- Tightened the GUI slimming budget to 4000 lines for `app/main_window.py`.
- Kept the direct internal import budget at zero.

## Validation

```text
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -B -m pytest tests -q
195 passed, 1 skipped
```

```text
PYTHONPATH=src python -B -m geoai_simkit --version
geoai-simkit 0.8.70
```

```text
PYTHONPATH=src python -B tools/run_core_fem_smoke.py
Core FEM smoke: 7/7 ok=True
```

```text
PYTHONPATH=src python -B -m geoai_simkit demo --profile cpu-debug
backend=headless_stage_block_backend
```
