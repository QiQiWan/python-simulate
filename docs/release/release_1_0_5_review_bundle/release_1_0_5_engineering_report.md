# GeoAI SimKit 1.0.5 Basic Foundation Pit

## Release Acceptance
- Status: `accepted_1_0_5_basic`
- Accepted: `True`
- Blockers: `0`

## Model Scope
- Phases: `initial, excavation_1, support_1, excavation_2, support_2`
- Release: `1.0.5-basic`

## Mesh
- Nodes: `24`
- Cells: `4`
- Cell types: `hex8`
- Production ready: `True`

## Solver Phase Records
| Phase | Converged | Relative residual | Max displacement | Max settlement |
|---|---:|---:|---:|---:|
| initial | True | 0 | 0 | 0 |
| excavation_1 | True | 0 | 0 | 0 |
| support_1 | True | 2.45331e-16 | 0.0129706 | 0.0129706 |
| excavation_2 | True | 1.39564e-16 | 0.0129706 | 0.0129706 |
| support_2 | True | 1.39564e-16 | 0.0129706 | 0.0129706 |

## 1.0.5 Hardening
- GUI contract: `geoai_simkit_gui_desktop_hardening_v1`; blockers `0`
- Mesh route: `shared_node_axis_aligned_hex8`; requested `gmsh_occ_tet4`; fallback `True`
- K0 states: `4`
- Mohr-Coulomb phase count: `5`

## Findings
- **warning** `gui.qt.optional_missing`: PySide6 is not installed in this environment.
- **warning** `gui.pyvista.optional_missing`: PyVista is not installed in this environment.
- **warning** `mesh.route.fallback_used`: Gmsh/OCC route fell back to shared-node Hex8 production mesh.

## Limitations
- This 1.0 Basic workflow is accepted for the built-in linear-static staged demonstration case. Use validated Gmsh/OCC meshing and calibrated constitutive models before using it for certification-grade design.
