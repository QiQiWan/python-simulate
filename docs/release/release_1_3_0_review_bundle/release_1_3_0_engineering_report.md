# GeoAI SimKit 1.3.0 Beta Foundation Pit Demo

## Release Acceptance
- Status: `blocked_1_3_0_beta`
- Accepted: `False`
- Blockers: `1`

## Model Scope
- Phases: `initial, excavation_1, support_1, excavation_2, support_2`
- Release: `1.3.0-beta`

## Mesh
- Nodes: `24`
- Cells: `20`
- Cell types: `tet4`
- Production ready: `True`

## Solver Phase Records
| Phase | Converged | Relative residual | Max displacement | Max settlement |
|---|---:|---:|---:|---:|

## Findings
- **warning** `1_2_4.1_1_3.1_0_5.gui.qt.optional_missing`: PySide6 is not installed in this environment.
- **warning** `1_2_4.1_1_3.1_0_5.gui.pyvista.optional_missing`: PyVista is not installed in this environment.
- **warning** `1_2_4.1_1_3.1_0_5.mesh.route.fallback_used`: Gmsh/OCC route fell back to shared-node Hex8 production mesh.
- **warning** `1_2_4.1_1_3.mesh.gmsh_occ_project_fallback`: Native Gmsh/OCC was not used; deterministic Tet4 surrogate is recorded.
- **warning** `1_2_4.gmsh_native_exchange.fallback`: Native gmsh runtime was not available; physical-group manifest surrogate was used.
- **blocker** `artifacts.missing`: One-click demo did not export all required artifacts.

## Limitations
- This 1.0 Basic workflow is accepted for the built-in linear-static staged demonstration case. Use validated Gmsh/OCC meshing and calibrated constitutive models before using it for certification-grade design.
