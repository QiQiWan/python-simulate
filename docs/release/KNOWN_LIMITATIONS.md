# Known limitations

- GPU resident solving requires CUDA and Warp. Without them, reports show `capability_missing`.
- Shell validation is benchmark-grade. It includes patch, bending, torsion, distortion and large-rotation checks, but not formal commercial certification.
- Curved wall-soil mortar coupling uses tessellated BRep-style faces. Full OpenCascade history tracking and complex BRep healing remain separate tasks.
- MC/HSS inverse calibration supports real CSV batches, but parameter uncertainty and Bayesian UQ are not yet implemented.
- Large-scale production runs still need more robust preconditioner tuning and memory profiling.
