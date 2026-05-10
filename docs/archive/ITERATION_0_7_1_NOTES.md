# Iteration 0.7.1 usability and runtime-stability patch

## Main problems found

1. The package entry point was broken: `python -m geoai_simkit` imported `geoai_simkit.cli`, but that module did not exist.
2. Several solver modules were referenced across the GUI, runtime, pipeline, and examples but were absent from the source tree.
3. The project root lacked standard packaging files and direct run scripts, making the system difficult to install or launch from the main directory.
4. GPU detection was treated as an imported capability, but the actual probing layer was missing. This caused environment checks and compute-profile controls to fail early.
5. Staged excavation validation depended on `StageManager`, but the staged activation resolver was missing.

## What was added

- `geoai_simkit.cli`: command-line interface for environment checks, GUI launch, demo run, and case export.
- `geoai_simkit.solver.base`: shared `SolverSettings` dataclass.
- `geoai_simkit.solver.gpu_runtime`: optional CUDA probing with CPU-safe fallback.
- `geoai_simkit.solver.staging`: cumulative stage activation resolver.
- `geoai_simkit.solver.backends`: local backend wrapper and deterministic full-model fallback.
- `geoai_simkit.solver.warp_backend`: legacy-compatible backend facade.
- `geoai_simkit.solver.hex8_linear`, `warp_hex8`, and `linsys.sparse_block`: compatibility utilities required by existing Tet4 and linear algebra code.
- Root-level `pyproject.toml`, `requirements.txt`, and run scripts.
- PyVista moved into core dependencies because geometry, preview, and export paths all operate on PyVista datasets.

## Delivery status after this patch

- Installation/launch usability: improved from fragile to usable.
- Solver-entry stability: missing-import failures repaired.
- Stage validation: cumulative activation logic restored.
- GPU discovery: optional and safe; no hard crash when CUDA/Warp is absent.
- Production FEM accuracy: still not complete. The fallback backend is for workflow validation and visualization, not final engineering-grade calculation.

## Recommended next iteration

1. Replace the deterministic fallback with a real Hex8/Tet4 stage-aware linear-elastic path for small and medium models.
2. Move Mohr-Coulomb/HSS constitutive update into the runtime stage executor.
3. Add integration tests for `check`, `demo`, stage activation, case serialization, and runtime compilation.
4. Add a visible geometry-editing command layer for point-line-face block splitting, with persistent block IDs and automatic contact-pair generation.
