# Iteration 1.2.4 Basic

This release advances the 1.1.3 nonlinear/hydro/contact workbench to a 1.2.4 basic engineering workflow and fixes the desktop launcher so that starting the software opens the six-phase workbench instead of the old flat interactive editor.

## Highlights

- Default GUI fallback is now `launch_phase_workbench_qt`.
- PyVista path still opens the NextGen phase workbench when available.
- Legacy flat editor is available only through `GEOAI_SIMKIT_LEGACY_GUI=1`.
- Added global Mohr-Coulomb Newton-Raphson consistent-tangent audit path.
- Added Gmsh/OCC physical-group exchange manifest and native-runtime detection.
- Added consolidation coupling fields: excess pore pressure and degree of consolidation.
- Added interface open/closed/sliding iteration fields.
- Added 1.2.4 acceptance gate, tutorial, report and review bundle.

## Known limitations

- Native Gmsh and full desktop PyVista verification depend on the target workstation runtime.
- The 1.2.4 nonlinear service is an auditable engineering mainline, not a certified commercial geotechnical solver.
