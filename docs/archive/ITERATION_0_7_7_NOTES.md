# Iteration 0.7.7 / iter55 - Stage-aware contact diagnostics and GUI result-package handoff

## Focus

This iteration continues the interface-ready contact work from v0.7.6 and closes two practical gaps:

1. Contact pairs that disappeared after staged excavation were previously counted as generic `missing_pair_count`.
2. The stage result package had enough arrays for post-processing, but not enough structured metadata for a GUI result panel and contact diagnostics panel.

## Main changes

### Stage-aware contact classification

`build_contact_solver_assembly_table()` now accepts `active_regions` and classifies contact pairs into:

- `effective_pair_count`: both sides are present in the active submesh and can be assembled.
- `inactive_region_pair_count`: a pair is inactive because one side belongs to a region deactivated by the current stage.
- `missing_geometry_pair_count`: a pair is missing even though both regions should be active; this is a real topology/mesh issue.
- `missing_pair_count`: retained for backward compatibility as the total missing count from the local active submesh filter.

The Tet4 reference backend passes active regions into both the solver contact table and the penalty contact triplet builder.

### Cleaner penalty-contact assembly diagnostics

`penalty_contact_triplets_for_submesh()` now reports:

- `skipped_inactive_region_pair_count`
- `skipped_missing_geometry_pair_count`
- `skipped_missing_node_pair_count`
- `skipped_same_node_pair_count`
- `used_pair_count`

This prevents normal excavation deactivation from being mixed with real contact topology errors.

### Result package v3

The stage result package format is upgraded to:

```text
geoai-stage-result-package-v3
```

In addition to the previous files, it now writes:

```text
contact_index.json
```

The package now contains GUI-oriented information for:

- stage browser;
- field browser;
- preferred scalar/vector fields;
- contact diagnostics panel;
- stage-wise contact activation/deactivation status;
- contact warnings and next-review hints.

### GUI/package loading helpers

New helpers were added:

```python
load_stage_result_package(path)
build_stage_package_gui_payload(path)
```

`ResultsService` and `ResultsPresenter` can now read a stage result package from document metadata and expose a `stage_result_package` and `contact_diagnostics` payload for the results workspace.

### CLI helper

New command:

```bash
python -m geoai_simkit result-package-info exports/pit_tet4_results
```

It prints package format, stage/field counts, and summarized contact diagnostics.

## Limitations

This is still a reference linear Tet4 workflow. The contact model is a node-pair penalty contact handoff, not a full nonlinear frictional contact solver. Excavation is represented by active-submesh filtering; true stress-release history and constitutive state transfer still need the next iterations.
