# GeoAI SimKit FEM Scope and Roadmap

This document separates the ordinary responsibilities of a general-purpose finite-element program from research extensions such as GPU residency, OCC history tracking, and Bayesian material calibration. It is intentionally direct: a feature is not marked usable_core unless it has a clear numerical path, a benchmark, and result-package evidence.

## 1. What a general finite-element program must do

A general FEM program is mainly responsible for the following pipeline:

1. **Geometry and topology**
   - points, curves, surfaces, solids, blocks, interfaces;
   - robust Boolean split / merge / healing;
   - persistent entity naming after geometry operations.

2. **Meshing and model attribution**
   - generate valid Tet4 / Hex8 / shell / beam / interface meshes;
   - assign materials, sections, loads, boundary conditions, stages, and contact pairs;
   - check mesh quality before solving.

3. **Element library**
   - continuum elements such as Tet4 and Hex8;
   - structural elements such as truss, beam, plate, and shell;
   - interface/contact elements.

4. **Material library**
   - linear elasticity;
   - Mohr-Coulomb and related plasticity models;
   - advanced soil models such as HS/HSS/HSsmall;
   - material state variables and consistent tangents.

5. **Global assembly and constraints**
   - DOF numbering;
   - sparse global matrix/vector assembly;
   - constraints and stage activation/deactivation;
   - reaction recovery and energy checks.

6. **Linear and nonlinear solution**
   - direct or iterative sparse linear solvers;
   - Newton / modified Newton / line search;
   - contact active set or augmented Lagrangian;
   - convergence diagnostics.

7. **Verification and validation**
   - patch tests;
   - beam/plate/shell benchmarks;
   - material point benchmarks;
   - mesh convergence;
   - comparison to analytical, published, or experimental data.

8. **Post-processing and reporting**
   - displacement, stress, strain, plastic state, contact state;
   - result package acceptance;
   - reproducible solver settings and provenance.

## 2. What is research/acceleration on top of general FEM

The following are not basic FEM requirements, but advanced implementation directions:

1. **GPU-resident solvers**
   - keep CSR matrices, vectors, preconditioners, and Krylov workspaces on GPU;
   - execute SpMV, dot products, reductions, axpy, preconditioning, Arnoldi, and Givens updates on GPU;
   - avoid CPU-hosted Krylov loops except for launch control and convergence metadata.

2. **GPU-resident nonlinear mechanics**
   - Hex8 element kernels, contact kernels, material-state update kernels, and Krylov kernels must share device-resident state;
   - no silent CPU fallback is allowed when a benchmark is marked `gpu_strict`.

3. **OCC-native persistent naming**
   - use OpenCascade TNaming / BRepTools_History for true topology evolution;
   - fallback fingerprint ledgers are useful, but they are not equivalent to native OCC history.

4. **Bayesian material inversion**
   - calibrate MC/HSS parameters from triaxial data;
   - quantify uncertainty, posterior correlation, and credible intervals;
   - validate against external experiments.

## 3. Current status categories

The project uses explicit feature levels:

| Level | Meaning |
|---|---|
| `usable_core` | Has executable implementation, benchmark, metadata, and failure gate. |
| `benchmark_grade` | Numerically useful for regression, but not yet certification-grade complete. |
| `research_grade` | Useful research scaffold; needs more validation and external data. |
| `capability_probe` | Detects optional dependency/hardware; does not claim runtime execution. |
| `fallback` | CPU or simplified path; must be explicitly labeled. |

## 4. Simplified module map

| Module group | FEM role | Current responsibility |
|---|---|---|
| `geometry/` | geometry, topology, meshing | blocks, BRep-like docs, mesh quality, OCC fallback paths |
| `materials/` | constitutive models | elastic, MC, HSS/HSsmall state update and tangents |
| `solver/hex8_global.py` | continuum element solver | Hex8 assembly and nonlinear smoke tests |
| `solver/structural/` | beam/plate/shell | structural stiffness and shell benchmark suites |
| `solver/contact/` | interface/contact | mortar-style face pairing, contact history, OCC bridge |
| `solver/gpu_*` | acceleration research | GPU capability, resident CSR/Krylov contracts, coupled gates |
| `solver/material_*` | calibration and UQ | triaxial calibration, Bayesian/UQ reports |
| `results/` | result acceptance | result-package acceptance gate |
| `app/` | GUI | workbench, fallback GUI, benchmark panel |

## 5. Important honesty rules

1. A CPU reference run is not a GPU run.
2. A tessellated fallback ledger is not native OCC TNaming.
3. A lightweight benchmark book is not a complete certification-grade benchmark comparison.
4. Synthetic/demo results must never be marked engineering-valid.
5. Any solver result must report fallback, hardware capability, benchmark status, and acceptance status.
