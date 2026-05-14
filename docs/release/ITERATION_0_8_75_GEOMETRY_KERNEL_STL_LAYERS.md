# 0.8.75 - Strengthened Geometry Kernel for Real STL and Soil Layer Splitting

This release strengthens the meshing-side geometry kernel while preserving the complete modularization boundary established in 0.8.72-0.8.74.

## Highlights

- Optional Gmsh/meshio dependency health is exposed through a typed, dependency-light contract.
- STL surface optimization now merges duplicate nodes, removes degenerate triangles, and reports closure/manifold blockers before production Tet4 meshing.
- Soil-layer splitting can generate Hex8 or Tet4 solid volume meshes from STL bounds using explicit z-layer definitions.
- Generated layer meshes preserve `block_id`, `region_name`, `material_id`, `role`, boundary face sets, and interface candidates.
- Canonical workflow reports now include a `geometry_kernel` artifact when running soil-layered STL volume workflows.

## Scope

The implementation provides a robust dependency-light fallback and clean optional production-kernel boundary. Complex conformal Tet4 for arbitrary real-world STL still requires installing and validating Gmsh/meshio, but the system now exposes the correct health gates and repair diagnostics rather than silently treating damaged surfaces as solver-ready volumes.
