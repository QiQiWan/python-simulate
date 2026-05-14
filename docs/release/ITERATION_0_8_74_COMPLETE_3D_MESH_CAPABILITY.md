# Iteration 0.8.74 - Complete 3D Mesh Capability

This iteration completes the dependency-light 3D mesh layer used by meshing,
workflow, GUI controllers and downstream FEM solvers.

## Added

- `geoai_simkit.contracts.mesh3d` for 3D mesh topology DTOs.
- `geoai_simkit.mesh.complete_3d` for boundary face extraction, boundary set
  classification and region/interface topology reports.
- `structured_hex8_box` and `structured_tet4_box` mesh generators.
- `geoai_simkit.services.complete_3d_mesh` aggregation service.
- Meshing facade functions:
  - `supported_3d_mesh_generators()`
  - `tag_project_3d_boundary_faces()`
  - `project_3d_boundary_faces()`
  - `complete_3d_mesh_report()`
- Workflow artifact key: `mesh3d`.
- Qt-free `Complete3DMeshActionController`.

## Validation

```text
228 passed, 1 skipped
Core FEM smoke: 7/7 ok=True
```
