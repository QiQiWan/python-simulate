# GeoAI SimKit v0.8.26-sparse-gpu-gui-benchmark

This hardening iteration extends v0.8.25 with six focused upgrades:

1. Hex8 sparse nonlinear global solve benchmark using triplet/CSR assembly and SciPy CSR when available.
2. Mindlin-Q4 plate/shell bending benchmark replacing pure rotational regularization.
3. Augmented-Lagrangian node-pair/mortar wall-soil interface benchmark with Coulomb projection.
4. Mohr-Coulomb and HSS/HSsmall material reference-curve reports with CSV/SVG export.
5. GPU native nonlinear assembly benchmark entry with explicit Warp/CUDA capability reporting.
6. GUI Benchmark tab with Refresh, Open report, Open folder and Open JSON actions.

Important limitation: GPU support is capability-gated. On systems without Warp/CUDA, the benchmark suite records `capability_missing` and does not claim native GPU execution.
