# Iteration v0.8.0 / iter58 - Geostatic release handoff and solver evidence index

This iteration deepens the staged-excavation path beyond the v0.7.9 equivalent nodal release-load prototype. The reference backend now carries a lightweight K0 geostatic stress handoff, resolves user/stage release factors, records stage increment displacement fields, and exports solver-balance evidence for GUI/result-package inspection.

## Main changes

- Added `geoai_simkit.pipeline.geostatic`:
  - cell-wise K0 geostatic stress estimate;
  - `geostatic_stress`, `geostatic_sigma_v`, and `geostatic_depth` result fields;
  - face-pressure helper used by excavation release loads.
- Upgraded equivalent excavation release loads to `equivalent_excavation_release_load_v2`:
  - pressure is derived from the geostatic face-pressure handoff;
  - stage/model release factor controls are supported through metadata;
  - each load row stores geostatic pressure and factor provenance.
- Added stage increment displacement results:
  - `U_increment`;
  - `U_increment_magnitude`.
- Added linear solver evidence:
  - strain energy;
  - external work;
  - relative energy-balance error;
  - residual-to-RHS ratio;
  - load component summary.
- Upgraded the stage result package to `geoai-stage-result-package-v6`:
  - adds `geostatic_index.json`;
  - adds `solver_index.json`;
  - extends GUI payload with `geostatic_panel` and `solver_balance_panel`.
- ResultsService and ResultsPresenter now expose geostatic and solver-balance diagnostics for GUI integration.

## Current limitation

This is still a reference linear-elastic Tet4 implementation. It now has a more traceable staged-excavation mechanics handoff, but it is not a production nonlinear geotechnical solver. The next deep step is to turn the geostatic stress state into a true initial-stress term in the element residual and then couple it with nonlinear contact/open-close and Mohr-Coulomb/HSS state updates.
