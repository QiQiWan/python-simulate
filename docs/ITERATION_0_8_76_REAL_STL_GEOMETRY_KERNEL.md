# 0.8.76 - Real STL Geometry Kernel and Stratigraphic Closure

This iteration hardens the production geometry-kernel path for complex real-world STL geology workflows.

## Added capabilities

- Optional Gmsh/meshio validation report with physical-group preservation records.
- Dependency-light STL repair diagnostics:
  - duplicate-node merge,
  - degenerate-face removal,
  - small boundary-loop fan patching,
  - closed-shell normal reorientation,
  - self-intersection candidate detection.
- Stratigraphic closure meshing from real STL surface tags (`top_surface_id` / `bottom_surface_id`) instead of only z-range layer cuts.
- Preserved layer / material / region / physical-group metadata in generated solid meshes.
- Local volume-mesh quality optimization / bad-cell removal.
- Workflow artifacts for geometry-kernel and complete 3D mesh reports.

## New public entrypoints

```python
from geoai_simkit.modules import meshing

meshing.optimize_project_complex_stl_surface(project)
meshing.gmsh_meshio_validation(project)
meshing.generate_stratigraphic_surface_volume_mesh(project, layers=[...])
meshing.optimize_project_volume_mesh_quality(project)
```

## New mesh generator

```text
stratigraphic_surface_volume_from_stl
```

Alias kinds:

```text
stl_stratigraphic_surfaces
surface_layered_volume_from_stl
surface_strata_tet4_from_stl
surface_strata_hex8_from_stl
```

## Scope notes

The dependency-light fallback provides deterministic geometry processing and testable solid mesh generation. CAD-grade Boolean healing, exact self-intersection repair, and high-quality conformal Tet4 generation for arbitrary complex STL shells remain gated behind optional Gmsh/meshio or a future stronger geometry kernel.
