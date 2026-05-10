# Iteration v0.8.47 — GeoProjectDocument framework root

This iteration adds a PLAXIS-style project-document backbone that binds the previously separated visual modeling, topology, material, mesh, phase, solver and result records into one auditable root object.

## Added

- `geoai_simkit.geoproject.GeoProjectDocument`
  - `ProjectSettings`
  - `SoilModel`
    - `SoilContour`
    - `Boreholes`
    - `SoilLayerSurfaces`
    - `SoilClusters`
    - `WaterConditions`
  - `GeometryModel`
    - `Points`
    - `Curves`
    - `Surfaces`
    - `Volumes`
    - `ParametricFeatures`
  - `TopologyGraph`
    - ownership relations
    - adjacency relations
    - contact/interface candidates
    - generated-by relations
  - `StructureModel`
    - `Plates`
    - `Beams`
    - `EmbeddedBeams`
    - `Anchors`
    - `StructuralInterfaces`
  - `MaterialLibrary`
    - `SoilMaterials`
    - `PlateMaterials`
    - `BeamMaterials`
    - `InterfaceMaterials`
    - drainage / groundwater properties
  - `MeshModel`
    - `MeshSettings`
    - `MeshDocument`
    - `MeshEntityMap`
    - `QualityReport`
  - `PhaseManager`
    - `InitialPhase`
    - `ConstructionPhases`
    - `CalculationSettings`
    - `PhaseStateSnapshots`
  - `SolverModel`
    - `CompiledPhaseModels`
    - `BoundaryConditions`
    - `Loads`
    - `RuntimeSettings`
  - `ResultStore`
    - `PhaseResults`
    - `EngineeringMetrics`
    - `Curves`
    - `Sections`
    - `Reports`

## Engineering behavior

- Converts the current `EngineeringDocument` into a full `GeoProjectDocument`.
- Infers soil clusters, structural plates/beams/interfaces and default material records from existing geometry roles.
- Preserves mesh tags, mesh-entity mappings, quality report and deterministic preview stage results.
- Adds generated-by topology relations for parametric features and ownership relations for soil clusters.
- Adds `compile_phase_models()` as a dependency-light compiler contract that prepares per-phase solver payload summaries.
- Adds JSON persistence through `save_json()` and `load_json()`.

## Smoke verification

Run:

```bash
python tools/run_geoproject_document_smoke.py
```

The smoke writes:

```text
reports/geoproject_document_preview.json
reports/geoproject_document_smoke.json
```

Current smoke outcome:

```text
accepted: true
volumes: 24
contact candidates: 83
mesh cells: 24
phases: 5
compiled phase models: 5
phase results: 5
engineering metrics: 35
```

## Current limitation

This is a strong document and compilation backbone, not yet a full PLAXIS-equivalent CAD/solver kernel. The next layer should wire this root document into the GUI object tree, phase editor, material editor and solver compiler as the single source of truth.
