# GeoAI SimKit 1.2.4 Basic Tutorial

## What changed
1. The desktop launcher now opens the six-phase workbench by default, even without PyVista.
2. The Solve phase records a global Newton-Raphson Mohr-Coulomb consistent-tangent path.
3. The Mesh phase exports/imports a Gmsh/OCC physical-group manifest for native exchange auditing.
4. Hydro-mechanical results include consolidation and excess pore-pressure dissipation.
5. Interfaces include open/closed/sliding iteration fields per phase.

## Six-phase workflow
地质 → 结构 → 网格 → 阶段配置 → 求解 → 结果查看

## Acceptance
- Project: `GeoAI SimKit 1.2.4 Basic Foundation Pit`
- Release: `1.2.4-basic`
- Phases: `initial, excavation_1, support_1, excavation_2, support_2`
- Status: `accepted_1_2_4_basic`
- Accepted: `True`

## Boundary of use
1.2.4-basic is an auditable advanced workflow build.  It is not a certified commercial geotechnical solver.  Native Gmsh and desktop GUI verification should be run on the target workstation before engineering sign-off.
