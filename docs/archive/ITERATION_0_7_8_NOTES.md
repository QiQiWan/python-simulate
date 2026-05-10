# Iteration 0.7.8 / iter56 — staged release index and result preview

This iteration deepens the unfinished staged-excavation and result-review parts of the v0.7.x line.

## What changed

- Added `geoai_simkit.pipeline.stage_release`.
  - Converts recorded `release_boundary` requests into a stage-aware release index.
  - Classifies each release boundary as `closed`, `released`, `inactive`, or `unknown-retained-side-inactive`.
  - Exposes `solver_contract = staged_release_boundary_v1` for future stress-release/runtime handoff.
- Upgraded stage result package format to `geoai-stage-result-package-v4`.
  - Adds `release_index.json`.
  - Adds `preview_index.json`.
  - Keeps `manifest.json`, `stage_index.json`, `field_index.json`, `gui_index.json`, `contact_index.json`.
- Added `geoai_simkit.results.package_preview`.
  - Provides `build_result_field_preview()` for GUI/table previews without PyVista.
  - Provides `export_result_field_preview_csv()` for quick spreadsheet inspection.
- Extended CLI.
  - `result-package-info` now reports release and preview-panel diagnostics.
  - New `result-preview` command previews one result field and can export CSV.
- Extended the headless pit Tet4 smoke demo.
  - The summary now includes `stage_release_index` alongside contact diagnostics.

## New commands

```bash
python -m geoai_simkit pit-tet4-smoke --out exports/pit.json --result-dir exports/pit_results
python -m geoai_simkit result-package-info exports/pit_results
python -m geoai_simkit result-preview exports/pit_results --stage excavate_level_2 --field U_magnitude --rows 8
python -m geoai_simkit result-preview exports/pit_results --stage excavate_level_2 --field U_magnitude --csv exports/u_mag_preview.csv
```

## Remaining limitations

This still remains a linear Tet4 reference path. The release index is a stable handoff contract and diagnostic layer, not yet a full geostatic stress-release algorithm. The next required step is to translate `staged_release_boundary_v1` into equivalent release loads/history-stress transfer for the solver.
