# geoai-simkit v0.1.41

## Geometry-first workflow and mesh engine split
- Import IFC / CAD-style geometry as point-line-surface blocks first without forcing immediate meshing.
- Preserve imported geometry in `geometry_state=geometry` until the dedicated mesh engine is run.
- Add a standalone `MeshEngine` orchestrator that scans object records and material bindings, then meshes only the relevant geometry.

## Configurable mesh engine
- Add selectable element families: `auto`, `tet4`, `hex8`.
- Add material-aware and role-aware local refinement heuristics.
- Add density-triggered local refinement for crowded geometry regions.
- Preserve a geometry snapshot before meshing so the workflow remains auditable.

## Better UX during meshing
- Move mesh generation to a background thread with live progress / heartbeat updates.
- Improve status messaging for geometry-only models and meshing failures.
- Keep the UI responsive instead of blocking during meshing.

## Performance / layout improvements
- Run a lightweight performance audit after import / meshing.
- Auto-disable heavy edge rendering when imported object counts or mesh cell counts are large.
- Avoid running mesh-quality checks before a volume mesh actually exists.
- Show geometry bounding boxes in the region table before meshing instead of forcing expensive volume extraction.
