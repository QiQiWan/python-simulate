# GeoAI SimKit v0.7.5 / iter53

## Focus

This iteration moves the block-contact pipeline one step closer to a solver and GUI handoff:

1. Materialize contact/interface requests into model-level interface definitions.
2. Build a solver-readable node-pair contact assembly table.
3. Let the reference Tet4 backend accept node-pair penalty contact triplets when split-node pairs are available.
4. Export GUI-friendly stage result indexes next to the raw NumPy arrays.

## Key additions

### Contact request materializer

Added `geoai_simkit.pipeline.contact_materializer`:

- `materialize_interface_requests(...)`
- `build_contact_solver_assembly_table(...)`
- `penalty_contact_triplets_for_submesh(...)`

The materializer supports:

- `node_pair_contact` -> `InterfaceDefinition(kind="node_pair")`
- `release_boundary` -> staged release metadata
- solver-readable contact rows with region pair, activation scope, pair count, zero-length pair diagnostics, and penalty parameters

### Tet4 contact handoff

`solve_linear_tet4(...)` now accepts `contact_interfaces`. For non-identical split-node pairs, it assembles penalty spring triplets into the linear system. Identical/shared-node pairs are reported as zero-length pairs and skipped to avoid self-canceling stiffness.

This is still a lightweight reference path, not a full nonlinear frictional contact implementation.

### Result package v2

`export_stage_result_package(...)` now writes:

- `manifest.json`
- `stage_index.json`
- `field_index.json`
- `gui_index.json`
- `arrays/*.npz`

The manifest includes field statistics, stage summaries, preferred scalar/vector fields, and GUI-oriented field trees.

### Pit Tet4 stage demo

`pit_tet4_stage_smoke` now includes:

- contact materialization summary
- solver assembly table summary
- per-stage contact assembly diagnostics
- stage result package v2 indexes

## Known limitations

- The compact pit demo still uses a shared-node mesh, so contact rows are solver-readable but most wall-soil pairs appear as zero-length pairs until node splitting/interface-ready remapping is applied.
- Release boundaries are recorded as staged handoff metadata; true excavation unloading/history stress transfer remains future work.
- The reference Tet4 backend remains a linear-elastic workflow backend, not an engineering-grade nonlinear soil solver.
