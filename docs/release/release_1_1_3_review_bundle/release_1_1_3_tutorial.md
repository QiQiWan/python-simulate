# GeoAI SimKit 1.1.3 Basic Tutorial

## Purpose
This tutorial reviews the 1.1.3 workflow additions: Tet4 Gmsh/OCC project-mesh contract, staged Mohr-Coulomb nonlinear correction, GUI interaction hardening, groundwater/pore pressure fields and contact interface state.

## Workflow
1. Open the six-phase workbench and load the 1.1.3 demonstration project.
2. Inspect geology/structure entities and the generated wall-soil interfaces.
3. Open the Mesh phase and verify the Tet4 physical-volume tags.
4. Open the Staging phase and review water condition drawdown per phase.
5. Open the Solve phase and inspect staged Mohr-Coulomb nonlinear records.
6. Open the Results phase and review plastic points, pore pressure, effective stress and interface force fields.

## Demonstration project
- Project: `GeoAI SimKit 1.1.3 Basic Foundation Pit`
- Release: `1.1.3-basic`
- Phases: `initial, excavation_1, support_1, excavation_2, support_2`
- Mesh cells: `20`
- Mesh backend: `deterministic_occ_tet4_surrogate`
- Acceptance status: `accepted_1_1_3_basic`

## Boundary of use
1.1.3-basic is an auditable engineering workflow build.  It has a real Tet4 compiler contract, pore-pressure fields and Mohr-Coulomb return-map state, but remains below certified commercial geotechnical solver status.
