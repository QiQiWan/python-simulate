# Iteration 0.8.58 - STL-to-3D Solid Analysis Pipeline

## Purpose

This iteration moves the project toward true 3D solid mechanics for imported STL geology by separating surface geometry from volume discretisation.

## Completed

- Added a structured solid-readiness gate.
- Marked STL imports as surface geometry requiring volume meshing.
- Prevented tri3 surface cells from being treated as solid FEM cells.
- Added dependency-light `voxel_hex8_from_stl` volume meshing.
- Added `gmsh_tet4_from_stl` registry entry with capability/health metadata and a simple tetrahedral STL fallback.
- Added tests for STL readiness, volume meshing and plugin catalog coverage.

## Current interpretation

- `tri3` STL meshes are geometry/boundary surfaces.
- `tet4`, `hex8` and compatible 3D families are solid mechanics cells.
- A model is solid-solver-ready only when it contains valid 3D volume cells.

## Next recommended iteration

0.8.59 should promote the project solver backend from staged/reference solving to a dedicated `solid_linear_static_cpu` backend that reads project MeshDocument, material bindings, boundary conditions and loads directly.
