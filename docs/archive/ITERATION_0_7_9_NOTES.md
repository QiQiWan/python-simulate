# Iteration v0.7.9 / iter57 - Equivalent excavation release loads

This iteration deepens the staged-excavation path that was still incomplete in v0.7.8. The previous release index described which release boundaries opened, but it did not feed any mechanical contribution into the reference Tet4 solve. v0.7.9 adds a lightweight equivalent-release-load handoff and routes it into the stage-aware Tet4 backend.

## Completed

- Added `EquivalentReleaseLoadRow` and `build_stage_equivalent_release_loads()` in `pipeline.stage_release`.
- Converts opened `release_boundary` rows into retained-side nodal loads.
- Estimates release pressure from excavated material density, gravity, K0/friction-angle aliases, face depth and overlap area.
- Selects retained-side face nodes from the current interface-ready mesh, including duplicated region nodes.
- Injects generated release loads into `LocalBackend.advance_stage_increment()` before the Tet4 solve.
- Stores per-stage `release_load_index` in backend assembly info and `model.metadata['stage_release_load_indexes']`.
- Extends `operator_summary` with a `release_loads` section.
- Upgrades stage result package format to `geoai-stage-result-package-v5`.
- Adds `release_load_index.json` to the exported result package.
- Exposes `release_load_panel` in package GUI payload, results service and results presenter.
- Extends CLI `result-package-info` and `pit-tet4-smoke` output with release-load diagnostics.

## New solver contract

```text
release_boundary
→ released stage state
→ equivalent_excavation_release_load_v1
→ retained-side nodal loads
→ Tet4 stage solve RHS
→ release_load_index.json
```

## Current limitation

The new release load is still a reference formulation. It is not a full geostatic stress recovery or nonlinear excavation algorithm. It provides a deterministic mechanical contribution for staged excavation demos and prepares the data contract for a future production backend that can compute initial stresses and stress-release loads more rigorously.
