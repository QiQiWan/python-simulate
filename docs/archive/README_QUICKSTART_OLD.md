# geoai-simkit quick start

Current package version: **0.7.5 / iter52**.

## 1. Install from the project root

```bash
python -m pip install -e .
```

For the desktop workbench and optional meshing tools:

```bash
python -m pip install -e ".[gui,meshing]"
```

For GPU experiments, install the GPU extra only after confirming the CUDA/Warp environment:

```bash
python -m pip install -e ".[gpu]"
```

## 2. Check the environment

```bash
python -m geoai_simkit check
# or
python run_system_check.py
```

## 3. Launch the workbench

```bash
python -m geoai_simkit gui
# or
python run_geoai_simkit.py
```

## 4. Run the built-in foundation-pit workflow demo

```bash
python -m geoai_simkit demo --profile cpu-robust --out-dir exports/demo
# or
python run_foundation_pit_demo.py
```

This workflow still uses the broader application pipeline. It is useful for checking case preparation, runtime compilation, exports, and GUI-facing data products.

## 5. Run the tiny Tet4 stage-aware solver smoke test

```bash
python -m geoai_simkit tet4-smoke --out exports/tet4_stage_smoke.json
```

This command runs a minimal two-region staged Tet4 model and writes a JSON summary. It checks the stage-aware backend contract, Tet4 assembly path, result-field writing, and activation masks.

## 6. Run the headless foundation-pit Tet4 staged excavation test

```bash
python -m geoai_simkit pit-tet4-smoke --out exports/pit_tet4_stage_smoke.json --result-dir exports/pit_tet4_results
# or
python run_pit_tet4_stage_smoke.py
```

This is the most important regression case carried forward from iter51 and strengthened in iter52. It builds a compact connected Tet4 foundation-pit model without PyVista, detects axis-aligned block contacts, runs three stages, and exports a JSON report containing:

- point / cell / region counts;
- block contact policy summary;
- aggregated contact/interface assets and materialization requests;
- a manifest-plus-array stage result package for GUI/post-processing handoff;
- active and inactive regions per stage;
- active cell masks;
- maximum displacement and von Mises stress;
- linear-system, residual, and reaction diagnostics.

## Notes on this iteration

- The CLI now exposes `check`, `gui`, `demo`, `export-case`, `tet4-smoke`, and `pit-tet4-smoke`.
- `pit-tet4-smoke` is a solver regression case, not a calibrated engineering design model.
- `pit-tet4-smoke --result-dir ...` writes `manifest.json` and per-stage NumPy arrays under an `arrays/` folder.
- Core headless imports avoid eager PyVista/VTK initialization; GUI modules still import PyVista when launched.
- The reference Tet4 backend is intended for workflow validation and small linear-elastic checks. Production-grade nonlinear FEM still requires the native/GPU backend path.
- PyVista remains optional for the new headless Tet4 smoke tests, but the GUI and general visual export paths still depend on PyVista datasets.

## 7. Contact and stage-result handoff added in v0.7.5

In v0.7.5, `pit-tet4-smoke` additionally materializes block-contact requests into model-level node-pair interfaces and writes a solver-readable contact assembly table. The reference Tet4 backend can consume non-identical split-node contact pairs as penalty spring triplets; shared-node pairs are reported as zero-length diagnostics and intentionally skipped.

The result package now uses `geoai-stage-result-package-v2` and writes GUI-friendly index files:

- `manifest.json`
- `stage_index.json`
- `field_index.json`
- `gui_index.json`
- `arrays/*.npz`

## v0.7.6 interface-ready contact smoke check

Run the foundation-pit Tet4 case with interface-ready contact splitting and a GUI-readable result package:

```bash
python -m geoai_simkit pit-tet4-smoke \
  --out exports/pit_tet4_stage_smoke.json \
  --result-dir exports/pit_tet4_results
```

The summary JSON should report an applied `interface_ready` step, zero remaining split plans, and positive `effective_pair_count` in the initial stage contact assembly.

## v0.7.7 result package and contact diagnostics

After running the staged pit smoke case:

```bash
python -m geoai_simkit pit-tet4-smoke \
  --out exports/pit_tet4_stage_smoke.json \
  --result-dir exports/pit_tet4_results
```

Inspect the GUI-ready result package:

```bash
python -m geoai_simkit result-package-info exports/pit_tet4_results
```

The result directory now includes:

```text
manifest.json
stage_index.json
field_index.json
gui_index.json
contact_index.json
arrays/*.npz
```

`contact_index.json` separates contact pairs that are physically inactive due to staged excavation from pairs that are missing because of a topology or mesh handoff problem.

## v0.7.8 staged release and result preview workflow

After running the staged foundation-pit smoke case, inspect the GUI-ready result package and preview a field without launching the desktop UI:

```bash
python -m geoai_simkit pit-tet4-smoke --out exports/pit.json --result-dir exports/pit_results
python -m geoai_simkit result-package-info exports/pit_results
python -m geoai_simkit result-preview exports/pit_results --stage excavate_level_2 --field U_magnitude --rows 8
python -m geoai_simkit result-preview exports/pit_results --stage excavate_level_2 --field U_magnitude --csv exports/u_mag_preview.csv
```

The result package format is now `geoai-stage-result-package-v4` and includes `release_index.json` plus `preview_index.json` in addition to the contact and field indexes.

## v0.7.9 staged excavation release-load check

The pit Tet4 smoke command now writes a v5 result package with `release_load_index.json`:

```bash
python -m geoai_simkit pit-tet4-smoke --out exports/pit.json --result-dir exports/pit_results
python -m geoai_simkit result-package-info exports/pit_results
python -m geoai_simkit result-preview exports/pit_results --stage excavate_level_2 --field U_magnitude --rows 8
```

The release-load path is a lightweight reference handoff:

```text
release_boundary -> equivalent_release_load -> Tet4 RHS -> stage results
```

It is intended for workflow validation and small regression cases. Production-grade excavation analysis still requires geostatic initialization, stress history transfer and nonlinear contact/material iterations.

## v0.8.0 geostatic release and solver-evidence check

The staged pit smoke case now exports a v6 result package with geostatic and solver-balance indexes:

```bash
python -m geoai_simkit pit-tet4-smoke \
  --out exports/pit_tet4_stage_smoke.json \
  --result-dir exports/pit_tet4_results

python -m geoai_simkit result-package-info exports/pit_tet4_results
python -m geoai_simkit result-preview exports/pit_tet4_results --stage excavate_level_2 --field U_increment_magnitude --rows 8
```

Expected new index files:

```text
geostatic_index.json
solver_index.json
release_load_index.json
```

The reference solver now reports K0 geostatic stress fields, equivalent excavation release-load provenance, stage displacement increments, and energy/residual balance diagnostics. These diagnostics are intended to support GUI inspection and regression checks; they are not a substitute for a full nonlinear geostatic initialization procedure.

## v0.8.1 initial-stress residual check

The staged pit smoke case now exports a v7 result package with `initial_stress_index.json` and point fields for the assembled initial-stress residual:

```bash
python -m geoai_simkit pit-tet4-smoke \
  --out exports/pit_tet4_stage_smoke.json \
  --result-dir exports/pit_tet4_results

python -m geoai_simkit result-package-info exports/pit_tet4_results
python -m geoai_simkit result-preview exports/pit_tet4_results \
  --stage excavate_level_2 \
  --field initial_stress_residual_magnitude \
  --rows 8
```

The new reference-solver handoff is:

```text
K0 geostatic stress -> integral(B.T @ sigma0 dV) -> initial-stress RHS residual -> Tet4 stage solve
```

This is still a linear reference path, but the initial stress now participates in the assembled right-hand side instead of remaining only a diagnostic field.

## v0.8.2 nonlinear staged Tet4 solver check

This version adds a reference nonlinear staged Tet4 path. The foundation-pit smoke case now assigns Mohr-Coulomb soil materials and enables the nonlinear Picard/contact active-set loop by default.

```bash
python -m geoai_simkit pit-tet4-smoke \
  --out exports/pit_tet4_stage_smoke.json \
  --result-dir exports/pit_tet4_results

python -m geoai_simkit result-package-info exports/pit_tet4_results
python -m geoai_simkit result-preview exports/pit_tet4_results --stage excavate_level_2 --field eq_plastic_strain --rows 8
```

Expected result package format:

```text
geoai-stage-result-package-v8
```

New solver fields include:

- `yield_flag`
- `eq_plastic_strain`
- `yield_margin`
- `nonlinear_index.json`

## v0.8.3 stateful nonlinear solver check

This version keeps the reference Tet4 solver on the small headless foundation-pit case, but adds a stateful nonlinear handoff:

```bash
python -m geoai_simkit pit-tet4-smoke --out exports/pit.json --result-dir exports/pit_results
python -m geoai_simkit result-package-info exports/pit_results
python -m geoai_simkit result-preview exports/pit_results --stage excavate_level_2 --field eq_plastic_strain --rows 8
```

The result package now writes `material_state_index.json` and the nonlinear index uses the `nonlinear_tet4_stateful_cutback_mc_contact_v3` contract. This tracks committed cell material states across stages, accepted nonlinear load steps, cutback counts, yielded cells, and equivalent plastic strain summaries.

## v0.8.4 solver acceptance hardening check

The staged nonlinear reference solver now exports explicit solver acceptance rows instead of reporting every stage as converged. Run:

```bash
python -m geoai_simkit pit-tet4-smoke --out exports/pit.json --result-dir exports/pit_results
python -m geoai_simkit result-package-info exports/pit_results
```

Expected result package format:

```text
geoai-stage-result-package-v10
```

Additional package file:

```text
solver_acceptance_index.json
```

The acceptance panel separates these statuses:

```text
converged
accepted-with-warnings
failed
```

This makes nonlinear cutback warnings, incomplete load levels, residual warnings and contact missing-geometry issues visible to the CLI and GUI payload.

## v0.8.5 nonlinear material-residual solver check

This iteration adds a material-stress equilibrium residual to the staged nonlinear Tet4 reference solver.  The nonlinear solver now assembles

```text
f_int(sigma) = integral(B^T sigma dV)
R_material = f_external - f_int(sigma)
```

and records it in the stage diagnostics and result package.  This is stricter than checking only the tangent linear-system residual.

```bash
python -m geoai_simkit pit-tet4-smoke --out exports/pit.json --result-dir exports/pit_results
python -m geoai_simkit result-package-info exports/pit_results
python -m geoai_simkit result-preview exports/pit_results --stage excavate_level_2 --field nonlinear_material_residual_magnitude --rows 8
```

Expected package format:

```text
geoai-stage-result-package-v11
```

New package index:

```text
nonlinear_material_residual_index.json
```
