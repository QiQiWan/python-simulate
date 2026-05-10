# GeoAI SimKit v0.8.27-industrial-solver-core

This iteration hardens the nonlinear solver core.  The focus is not more UI chrome; it is verifiable solver infrastructure:

- Warp-native Hex8 kernelized nonlinear assembly benchmark entry.
- AMG / ILU / Krylov preconditioned sparse solver chain with explicit fallback metadata.
- MITC4-style shell/plate bending formulation with local coordinates, reduced shear, drilling stabilization, and corotational diagnostics.
- Mortar-style wall-soil face search and 2x2 face integration with augmented Lagrangian projections.
- MC / HSS triaxial curve calibration pipeline with RMSE, MAE, R2, CSV/JSON/Markdown/SVG report export.
- Benchmark suite and GUI payload extended with the new industrial-solver-core checks.

## Important limitations

The GPU path contains a real Warp kernel and records whether it actually ran.  If Warp/CUDA is unavailable, the benchmark is reported as capability-missing and is not presented as a completed GPU solve.

The shell formulation is benchmark-grade MITC4 style; it is a major step beyond rotational regularization, but it is not yet a full commercial finite-rotation shell implementation.

The triaxial calibration benchmark uses a deterministic reference fixture.  The same calibration function accepts real laboratory CSV files, but real experimental validation requires the user to provide actual test curves.
