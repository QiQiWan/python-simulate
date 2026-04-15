# v0.1.29 demo pit repair

## Fixed
- Split the parametric pit demo soil into `soil_mass`, `soil_excavation_1`, and `soil_excavation_2` so staged excavation is represented in geometry, not only in stage names.
- Rebuilt the default demo stages to perform real layer-by-layer excavation and default to a conservative `cpu-safe` nonlinear profile.
- Kept the demo retaining wall as display-only by default to avoid solving an unconnected floating wall without interfaces.
- Added solver-side aliases for boundary targets (`bottom/top/left/right/front/back`) and load kind aliases (`nodal_force` / `point_force`).
- Upgraded pre-solve checks so the old broken demo patterns are blocked instead of only warned about.

## Added safeguards
- Coarse-grid-safe demo creation: missing excavation subregions are no longer referenced by object records or stage maps.
- Regression tests for staged activation, alias compatibility, and pre-solve blocking of invalid demo configurations.
