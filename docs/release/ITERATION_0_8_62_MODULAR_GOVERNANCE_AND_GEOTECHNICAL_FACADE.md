# v0.8.62 Modular Governance and Geotechnical Facade Boundary

This iteration continues the modularization program after the production geotechnical boundary work in v0.8.61.

## Highlights

- Added dependency-light module-boundary governance contracts: `ImportBoundaryRule`, `ImportBoundaryViolation`, `ModuleBoundaryAuditReport`, and `ModuleGovernanceReport`.
- Added `geoai_simkit.services.module_governance` to scan source imports, validate modular boundary rules, and combine plugin registry counts into one report.
- Added a dedicated `geoai_simkit.modules.geotechnical` facade for production-facing geotechnical workflows:
  - `geotechnical_state()`
  - `readiness_report()`
  - `run_staged_geotechnical_analysis()`
- Registered the geotechnical facade in the project module registry so module smokes and update maps include it as a first-class module.
- Added `ModuleGovernanceActionController`, a Qt-free GUI controller for modularity status panels.
- Added architecture and core tests covering governance reports, boundary audits, geotechnical facade routing, and controller dependency cleanliness.

## Scope note

This version strengthens module governance and clean orchestration boundaries. It does not claim that all legacy implementation access has been removed; selected adapters and legacy document unwraps remain compatibility boundaries while the codebase transitions further toward strict Project Port usage.
