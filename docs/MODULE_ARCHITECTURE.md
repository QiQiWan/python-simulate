# Module Architecture

This project now exposes coarse subsystem facades under `geoai_simkit.modules`.
The facades do not replace the existing implementation packages.  They provide
stable update targets so a geological import, GUI modeling, solver or
postprocessing change can be made and tested without reaching through unrelated
layers.

## Module Map

| Module key | Facade | Primary responsibility | Existing implementation namespaces |
| --- | --- | --- | --- |
| `document_model` | `geoai_simkit.modules.document_model` | Shared project state, validation and document factories | `geoai_simkit.geoproject`, `geoai_simkit.document` |
| `geology_import` | `geoai_simkit.modules.geology_import` | STL/geological loading, diagnostics and conversion into a project document | `geoai_simkit.geology.importers`, `geoai_simkit.geometry.stl_loader`, `geoai_simkit.pipeline.specs` |
| `gui_modeling` | `geoai_simkit.modules.gui_modeling` | Workbench modeling session, tools, command stack and viewport state | `geoai_simkit.app`, `geoai_simkit.commands` |
| `fem_solver` | `geoai_simkit.modules.fem_solver` | Core FEM contracts, phase compilation and staged solve entrypoints | `geoai_simkit.fem`, `geoai_simkit.solver`, `geoai_simkit.geoproject.runtime_solver` |
| `postprocessing` | `geoai_simkit.modules.postprocessing` | Result summaries, result databases, packages and preview builder access | `geoai_simkit.results`, `geoai_simkit.post` |

The registry is available through:

```python
from geoai_simkit.modules import list_project_modules, module_update_map
```

Run the module facade smoke suite with:

```bash
python -m pytest tests/core/test_project_module_facades.py -q
python tools/run_project_module_smoke.py
```

## Geological Import Interface

`geology_import` now exposes a unified importer registry:

```python
from geoai_simkit.modules import geology_import

result = geology_import.import_geology("site.stl")
project = result.project
```

The current registered importers are:

| Source type | Input | Output |
| --- | --- | --- |
| `stl_geology`, `stl`, `geology_stl`, `stl_surface` | ASCII or binary STL surface file | `GeoProjectDocument` with geometry, mesh, material and quality diagnostics |
| `geology_json`, `json_geology`, `geological_model_v1`, `geojson`, `json` | Structured JSON geological model | `GeoProjectDocument` with surfaces, volumes, materials, layers and boreholes |
| `borehole_csv`, `csv_boreholes`, `borehole_log_csv`, `csv` | Engineering borehole layer table | `GeoProjectDocument` with `SoilModel.Boreholes`, layer control surfaces and initial soil volume partitions |

The structured JSON path accepts records such as:

```json
{
  "contract": "geological_model_v1",
  "name": "layered-site",
  "materials": [{"id": "clay", "model_type": "mohr_coulomb_placeholder"}],
  "surfaces": [{"id": "ground_surface", "points": [[0, 0, 0], [10, 0, 0], [10, 8, 0], [0, 8, 0]]}],
  "volumes": [{"id": "upper_clay", "bounds": [0, 10, 0, 8, -6, 0], "material_id": "clay"}],
  "layers": [{"id": "layer_clay", "volume_ids": ["upper_clay"], "material_id": "clay"}],
  "boreholes": [{"id": "bh_1", "x": 2.5, "y": 3.0, "layers": [{"top": 0, "bottom": -6, "material_id": "clay"}]}]
}
```

New data sources should implement the `GeologyImporter` protocol from
`geoai_simkit.geology.importers` and register through:

```python
geology_import.register_geology_importer(MyImporter(), replace=False)
```

The borehole CSV importer accepts common column aliases:

```text
borehole_id / bh_id / hole_id / borehole
x / easting, y / northing
z / elevation / collar_z / ground_elevation
top_depth / bottom_depth, or top / bottom
layer_id / layer / stratum
material_id / material / soil_type / lithology
description / remarks
```

By default `top` and `bottom` are treated as depths measured downward from the
borehole collar.  Use `options={"top_bottom_mode": "elevation"}` when the table
stores absolute elevations instead.

After importing borehole CSV data, layer control points can be interpolated into
continuous structured surface grids and swept into a tagged hex8 volume mesh:

```python
from geoai_simkit.geology import interpolate_project_layer_surfaces
from geoai_simkit.mesh import generate_layered_volume_mesh
from geoai_simkit.modules import geology_import

project = geology_import.create_project_from_geology("boreholes.csv")
interpolate_project_layer_surfaces(project, nx=8, ny=8)
mesh_result = generate_layered_volume_mesh(project, nx=8, ny=8)
```

The interpolation currently uses dependency-light inverse-distance weighting
and stores each grid in `SoilLayerSurface.metadata["surface_grid"]`.  The layered
mesher creates one structured hex8 cell per surface-grid quad for each initial
soil layer volume, preserving `block_id`, `layer_id`, `material_id` and `role`
cell tags.

The same workflow is exposed through the command/workbench layer:

```python
from geoai_simkit.commands import CommandStack, GenerateLayeredVolumeMeshCommand

stack = CommandStack()
result = stack.execute(GenerateLayeredVolumeMeshCommand(nx=8, ny=8), project)
```

In the desktop workbench, use `Import Borehole CSV` and then
`Generate Layered Mesh`.  The workbench service runs the same command, attaches
the generated `MeshDocument` to `GeoProjectDocument.MeshModel`, and mirrors it
into the lightweight `SimulationModel` so the viewport can render the new
volume mesh immediately.

## Update Rules

Use `geoai_simkit.modules.*` as the first import path for new workflow code and
tests.  Existing lower-level modules remain public where they already were, but
new cross-subsystem wiring should go through a facade.

The shared integration object is `GeoProjectDocument`.  Geological import writes
geometry, soil, material and mesh records into it.  GUI modeling may read and
edit it through controllers or document conversion services.  FEM solving
compiles phases from it and writes result records back to the result store.
Postprocessing reads result stores and result packages without reaching into the
solver assembly internals.

Boundary expectations:

- `geology_import` must not import GUI widgets or solver internals.
- `gui_modeling` should keep headless helpers free of Qt/PyVista imports.
- `fem_solver` must not import GUI widgets or rendering modules.
- `postprocessing` must keep heavy visualization imports lazy.
- `document_model` must remain dependency-light and usable from smoke tests.

## Minimal Workflow Example

```python
from geoai_simkit.modules import document_model, fem_solver, postprocessing

project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="demo")
fem_solver.compile_project_phases(project)
summary = postprocessing.build_project_result_summary(project)
assert summary["available"]
```

## v0.8.53 Modular contracts/service boundary update

The package now has a hardening layer for modular replacement:

```text
contracts -> adapters -> modules -> services -> app/cli
```

New stable contract package:

```text
geoai_simkit.contracts.project
geoai_simkit.contracts.geology
geoai_simkit.contracts.geometry
geoai_simkit.contracts.mesh
geoai_simkit.contracts.stage
geoai_simkit.contracts.solver
geoai_simkit.contracts.runtime
geoai_simkit.contracts.results
```

Primary interop chain:

```text
geology_import -> document_model -> meshing -> stage_planning -> fem_solver -> postprocessing
```

New module facades:

- `geoai_simkit.modules.meshing`
- `geoai_simkit.modules.stage_planning`

New service package:

- `geoai_simkit.services.job_service`
- `geoai_simkit.services.blueprint_progress`
- `geoai_simkit.services.system_readiness`

Old GUI paths for these services remain as compatibility shims. New code should import services directly.
