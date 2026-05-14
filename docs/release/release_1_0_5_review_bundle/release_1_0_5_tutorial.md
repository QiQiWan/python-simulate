# GeoAI SimKit 1.0.5 Basic Tutorial

## Purpose
This tutorial walks through the accepted 1.0.5 foundation-pit workflow: geology, structures, mesh, staged configuration, solve and results.

## Workflow
1. Open the six-phase workbench and start from the Geology phase.
2. Review the demo soil volumes and material assignments.
3. Switch to Structures to inspect walls and struts.
4. Switch to Mesh and verify the Gmsh/OCC-preferred production mesh route.
5. Switch to Staging and inspect excavation/support activation snapshots.
6. Switch to Solve and review K0 initialization and staged Mohr-Coulomb controls.
7. Switch to Results and export VTK, JSON and the engineering report.

## Current demonstration project
- Project: `GeoAI SimKit 1.0.5 Basic Foundation Pit`
- Release: `1.0.5-basic`
- Phases: `initial, excavation_1, support_1, excavation_2, support_2`
- Mesh cells: `4`
- Mesh backend: `shared_node_axis_aligned_hex8`
- Gmsh/OCC fallback used: `True`
- Acceptance status: `accepted_1_0_5_basic`

## Limitations
The 1.0.5 Basic workflow has explicit K0 and staged Mohr-Coulomb control metadata, but the global solve remains the lightweight compact staged kernel. Treat the bundled result as a regression/engineering-demo result, not certification-grade design output.
