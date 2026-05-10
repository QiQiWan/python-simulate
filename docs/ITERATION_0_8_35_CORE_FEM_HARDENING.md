# v0.8.35 Core FEM Hardening

This iteration turns the cleanup architecture into concrete API and GUI contracts:

1. The GUI has six independent workflow pages: Modeling, Mesh, Solve, Results, Benchmark and Advanced.
2. `geoai_simkit.fem` exposes dependency-light API contracts and smoke checks for geometry, mesh, material, element, assembly, solver and result.
3. Advanced GPU/OCC/UQ remain separated from the ordinary FEM path.
4. Completion matrix data can be generated from real smoke checks using `tools/run_core_fem_smoke.py`.
5. Broad status claims are normalized into evidence-driven states.
