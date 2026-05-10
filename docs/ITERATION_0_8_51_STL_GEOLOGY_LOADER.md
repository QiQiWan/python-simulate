# Iteration 0.8.51 — STL geological model loader

This iteration adds a dependency-light STL geological model import path for the current FEM workbench.

## Added

- `geoai_simkit.geometry.stl_loader`
  - Reads binary and ASCII STL files.
  - Merges duplicate vertices using a configurable tolerance.
  - Computes bounds, centroid, surface area, signed volume, connected components, open boundary edges, non-manifold edges, duplicate triangles and degenerate triangles.
  - Converts imported STL data into `SimpleUnstructuredGrid`, `MeshDocument`, `SimulationModel`, and `GeoProjectDocument` contracts.
- `GeometrySource(kind="stl_geology")`
  - Supports case-file based STL loading with `path`, `unit_scale`, `merge_tolerance`, `material_id`, `role`, `flip_normals`, and `center_to_origin` parameters.
- `GeoProjectDocument.from_stl_geology(...)`
  - Registers the STL surface as a geological volume placeholder with a true triangle `MeshDocument`.
  - Creates a soil cluster, default soil material, topology nodes/edges, and phase snapshot.
  - Marks whether the imported STL is an open surface requiring volume remeshing before solid FEM analysis.
- GUI workbench
  - Restores the missing `geoai_simkit.post.viewer.PreviewBuilder` module.
  - Adds **Import STL Geology…** to the File toolbar.
  - Shows STL source, triangle count, vertex count, closure status and boundary-edge count in the Properties panel.
- Smoke coverage
  - Adds unit tests for ASCII STL loading, `GeometrySource` integration and `GeoProjectDocument` registration.
  - Adds `tools/run_stl_geology_import_smoke.py` for validating a real STL file.

## Engineering note

An STL file is a triangulated surface. If it is open, the software now imports it for visualization, tagging, material assignment and preprocessing, but it is flagged as `surface_mesh_only=true`. A closed STL can be treated as a volume envelope; an open geological surface still needs surface repair, terrain extrusion or tetrahedral volume meshing before a reliable 3D solid FEM solve.
