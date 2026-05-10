# Iteration 0.8.48 — GeoProjectDocument-driven GUI data source

## Goal

Switch the GUI-side object tree, property panel, stage editor, material editor and solver compiler to `GeoProjectDocument` as the single readable/editable project data source.

Legacy `EngineeringDocument` and `WorkbenchDocument` objects are now treated as import/fallback sources. The GUI panels normalize them through `geoai_simkit.app.geoproject_source.get_geoproject_document()` before reading data.

## New / upgraded modules

- `geoai_simkit.app.geoproject_source`
  - Resolves any supported workbench object to `GeoProjectDocument`.
  - Stores the resolved document in `document.metadata["geo_project_document"]`.
  - Provides summary and dirty-state helpers.

- `geoai_simkit.app.panels.object_tree`
  - Builds a full tree from `GeoProjectDocument`.
  - Includes ProjectSettings, SoilModel, GeometryModel, TopologyGraph, StructureModel, MaterialLibrary, MeshModel, PhaseManager, SolverModel and ResultStore.

- `geoai_simkit.app.panels.property_panel`
  - Reads selected points, curves, surfaces, volumes, materials, phases, structures, interfaces, mesh settings, compiled phase models and phase results from `GeoProjectDocument`.

- `geoai_simkit.app.panels.stage_editor`
  - Provides phase palette, volume palette, structure/interface palette, calculation settings and mutation helpers.

- `geoai_simkit.app.panels.material_editor`
  - Provides material categories, drainage/groundwater properties, assignments and mutation helpers.

- `geoai_simkit.app.panels.solver_compiler`
  - Provides phase input snapshots, calculation settings, boundary conditions, loads, runtime settings and compiled phase model payloads.

- `geoai_simkit.app.fem_workflow_pages`
  - The six Modeling / Mesh / Solve / Results / Benchmark / Advanced pages now expose GeoProjectDocument-backed panels.

- `geoai_simkit.app.workbench.WorkbenchService`
  - Adds `geo_project_document()`.
  - Rewires material assignment, phase activation, phase add/clone/remove, mesh-size change and solver planning/running to mutate `GeoProjectDocument`.

## GeoProjectDocument content filling

`GeoProjectDocument.populate_default_framework_content()` now fills a practical baseline project:

- boreholes and default stratigraphic layers;
- soil layer surfaces;
- default Mohr-Coulomb soil materials;
- soil clusters;
- structural interfaces from topology contact candidates;
- default interface material;
- bottom/lateral boundary conditions;
- surface surcharge load;
- phase snapshots and calculation settings;
- result control sections and report references;
- topology nodes/edges for volumes, materials, phases, loads and boundary conditions.

## Smoke verification

Run from the package root:

```bash
PYTHONPATH=src python tools/run_geoproject_gui_datasource_smoke.py
```

Generated files:

- `reports/geoproject_gui_datasource_smoke.json`
- `exports/geoproject_gui_datasource_preview.geojson`
