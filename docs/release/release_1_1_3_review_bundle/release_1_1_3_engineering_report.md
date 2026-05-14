# GeoAI SimKit 1.1.3 Basic Foundation Pit

## Release Acceptance
- Status: `accepted_1_1_3_basic`
- Accepted: `True`
- Blockers: `0`

## Model Scope
- Phases: `initial, excavation_1, support_1, excavation_2, support_2`
- Release: `1.1.3-basic`

## Mesh
- Nodes: `24`
- Cells: `20`
- Cell types: `tet4`
- Production ready: `True`

## Solver Phase Records
| Phase | Converged | Relative residual | Max displacement | Max settlement |
|---|---:|---:|---:|---:|
| initial | True | 0 | 0 | 0 |
| excavation_1 | True | 0 | 0 | 0 |
| support_1 | True | 0 | 0 | 0 |
| excavation_2 | True | 0 | 0 | 0 |
| support_2 | True | 0 | 0 | 0 |

## Findings
- **warning** `1_0_5.gui.qt.optional_missing`: PySide6 is not installed in this environment.
- **warning** `1_0_5.gui.pyvista.optional_missing`: PyVista is not installed in this environment.
- **warning** `1_0_5.mesh.route.fallback_used`: Gmsh/OCC route fell back to shared-node Hex8 production mesh.
- **warning** `mesh.gmsh_occ_project_fallback`: Native Gmsh/OCC was not used; deterministic Tet4 surrogate is recorded.

## Limitations
- This 1.0 Basic workflow is accepted for the built-in linear-static staged demonstration case. Use validated Gmsh/OCC meshing and calibrated constitutive models before using it for certification-grade design.
