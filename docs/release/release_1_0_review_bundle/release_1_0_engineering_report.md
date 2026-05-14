# GeoAI SimKit 1.0 Basic Foundation Pit

## Release Acceptance
- Status: `accepted_1_0_basic`
- Accepted: `True`
- Blockers: `0`

## Model Scope
- Phases: `initial, excavation_1, support_1, excavation_2, support_2`
- Release: `1.0.0-basic`

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

## Findings
- No release blockers or warnings.

## Limitations
- This 1.0 Basic workflow is accepted for the built-in linear-static staged demonstration case. Use validated Gmsh/OCC meshing and calibrated constitutive models before using it for certification-grade design.
