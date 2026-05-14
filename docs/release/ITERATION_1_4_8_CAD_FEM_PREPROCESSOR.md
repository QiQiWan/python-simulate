# Iteration 1.4.8 - CAD-FEM Preprocessor Bridge

This iteration moves the CAD workbench beyond topology identity and into the
minimum data contract required before finite-element meshing and solving.

## Added

- `geoai_simkit.core.cad_fem_preprocessor`
  - `CadFemPhysicalGroup`
  - `CadFemBoundaryCandidate`
  - `CadFemMeshControl`
  - `CadFemReadinessReport`
- `geoai_simkit.services.cad_fem_preprocessor`
  - `build_cad_fem_preprocessor(project)`
  - `validate_cad_fem_preprocessor(project)`
- `BuildCadFemPreprocessorCommand`
- Phase workbench payload entry for the CAD-FEM preprocessor bridge.

## Why this matters

CAD interaction needs a stable route into solver preprocessing.  A picked face
or edge is not enough for FEM.  The system must also know which physical group,
material, phase, mesh control and boundary/load/interface role that topology can
carry.  This iteration generates those records from the canonical P7 topology
identity index.

## Scope

The implementation is headless and dependency-light.  It does not call native
OCC, Gmsh, VTK or Qt.  It prepares the metadata required by those backends.
Native meshing and exact geometry certification remain separate runtime gates.
