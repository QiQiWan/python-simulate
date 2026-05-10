# Iteration 0.8.65 - GUI Legacy Import Extraction, Project Port v3 and Verified 3D Quality Gates

## Highlights

- Extracted legacy GUI implementation imports behind `services.legacy_gui_backends`.
- Restored headless importability of `geoai_simkit.app.main_window`.
- Added `solver.staging.StageManager` compatibility.
- Added Project Port v3 engineering-state aggregate DTOs.
- Added `WorkflowArtifactManifest` lineage records.
- Added headless mesh/material/geotechnical quality gates.
- Added deterministic verified 3D tetra-column and multi-region examples.

## Validation

```text
166 passed, 1 skipped
geoai-simkit 0.8.65
Core FEM smoke: 7/7 ok=True
```
