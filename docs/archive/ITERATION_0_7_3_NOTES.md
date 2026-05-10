# Iteration 0.7.3 / iter51: foundation-pit Tet4 staged regression patch

## Purpose

This iteration moves the project from a tiny two-cell Tet4 smoke test toward a more meaningful foundation-pit staged excavation regression case. The goal is not yet a production nonlinear FEM engine. The goal is to make the stage-aware solver path, block activation, contact preflight, and JSON diagnostics work together on a compact engineering-style model.

## Main changes

### 1. Added a headless foundation-pit Tet4 stage demo

New file:

```text
src/geoai_simkit/examples/pit_tet4_stage_smoke.py
```

The demo builds a connected Tet4 model with:

- 64 nodes;
- 162 Tet4 cells;
- 8 named regions;
- 3 analysis stages: `initial`, `excavate_level_1`, `excavate_level_2`;
- staged deactivation of `soil_excavation_1` and `soil_excavation_2`;
- soil and retaining-wall material assignments;
- bottom and side displacement constraints;
- top surcharge and gravity loading.

The model is intentionally dependency-light and does not require PyVista. It uses a small PyVista-like grid adapter so the same `SimulationModel` and `LocalBackend` contracts are exercised.

### 2. Added axis-aligned block contact detection

New file:

```text
src/geoai_simkit/geometry/block_contact.py
```

The module detects face-to-face contacts between axis-aligned block boxes and classifies mesh/contact policies:

- `soil_continuity` → `merge_or_tie`;
- `wall_soil_interface` → `duplicate_contact_nodes`;
- `excavation_release_face` → `keep_split_boundary`.

This gives the GUI and preprocessing layer a lightweight preflight check before heavier geometry kernels are available.

### 3. Added a new CLI command

```bash
python -m geoai_simkit pit-tet4-smoke --out exports/pit_tet4_stage_smoke.json
```

Root-level wrapper:

```bash
python run_pit_tet4_stage_smoke.py
```

### 4. Added tests

New tests:

```text
tests/test_block_contact.py
tests/test_pit_tet4_stage_smoke.py
```

Updated:

```text
tests/test_cli_import.py
```

Validation in the current environment:

```text
5 passed in 0.31s
```

## Remaining limitations

- The reference Tet4 path is linear elastic and small-model oriented.
- Excavation deactivation is currently cell-removal style, not a full construction stress-release formulation.
- Contact detection is axis-aligned and box-based; it does not replace a real Boolean geometry/contact kernel.
- Hex8 production assembly, nonlinear Mohr-Coulomb/HSS state update, and distributed GPU solve are still the next major targets.
