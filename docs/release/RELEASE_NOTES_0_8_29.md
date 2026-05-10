# v0.8.29-gpu-resident-industrial

This version focuses on GPU-resident solver closure, industrial shell/contact benchmarks, batch triaxial inverse calibration and root-directory simplification.

## Added

- `solver/gpu_resident_linsys.py`
- `solver/gpu_newton_krylov.py`
- `solver/structural/shell_commercial_benchmarks.py`
- `solver/contact/brep_mortar_coupling.py`
- `solver/material_inverse_batch.py`
- `tests/solver/test_iter89_gpu_resident_industrial.py`

## Simplified

- Consolidated all requirements into `requirements.txt`.
- Archived old iteration notes into `docs/archive/`.
- Replaced long quick-start notes with a compact `README.md`.
