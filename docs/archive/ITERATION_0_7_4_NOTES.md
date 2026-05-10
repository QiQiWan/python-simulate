# Iteration 0.7.4 Notes — Contact assets and headless stage result package

This iteration moves the staged pit smoke case closer to a GUI/runtime handoff workflow.

## Key changes

- Removed eager PyVista imports from core model, regioning and Tet4 solver modules so headless CLI and solver workflows do not hang on systems with problematic VTK/OpenGL initialization.
- Made `geoai_simkit.examples` lightweight by lazy-loading the heavyweight foundation-pit showcase builder.
- Extended block contact preflight with aggregated contact/interface assets:
  - `node_pair_contact` for wall-soil split/contact pairs.
  - `release_boundary` for excavation release faces.
  - `continuity_tie` for soil-soil continuity candidates.
- Added conversion from contact assets to interface materialization request rows.
- Added a dependency-light stage result package exporter under `geoai_simkit.results.stage_package`.
- Extended the headless pit Tet4 smoke demo so it reports contact assets, interface materialization requests and can export a manifest-plus-array result package.
- Added CLI support for `pit-tet4-smoke --result-dir ...`.

## Why this matters

The previous version could detect block contacts and run the Tet4 staged smoke case, but the contact result was mostly a diagnostic report. This version produces serializable assets that downstream GUI, meshing and runtime code can consume.

The headless result package also gives the GUI a stable target format before the full PyVista/VTK result viewer is mature.
