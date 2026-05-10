# Iteration 0.8.49 — GeoProjectDocument-native workflow

This iteration moves the modeling workflow from a legacy `EngineeringDocument`-driven facade to a native `GeoProjectDocument` workflow.  The goal is to make `GeoProjectDocument` the single source of truth for GUI panels, commands, material assignment, staged activation and solver compilation.

## Completed changes

### 1. VisualModelingSystem native document root

`geoai_simkit.app.visual_modeling_system.VisualModelingSystem` now owns a `GeoProjectDocument` by default.  Legacy workbench documents can still be converted through `geoproject_source`, but the facade mutates the native project root for selection, editing, meshing, compilation and result preview.

### 2. GeoProjectDocument-native geometry commands

`commands/geometry_commands.py` now exposes `GeoProjectDocumentCommand` and branches to native `GeoProjectDocument` operations when the document has `geometry_model` and `phase_manager`.  Legacy `EngineeringDocument` behavior is kept only as compatibility fallback.

Covered command families:

- material assignment
- visibility
- point / line / surface / volume creation
- support creation
- deletion
- soil layer split feature record
- excavation polygon feature record
- interface review status
- update operations for split / excavation / support features

### 3. Transaction, dirty graph and invalidation graph

New module:

```text
src/geoai_simkit/geoproject/transaction.py
```

It provides:

- `GeoProjectTransaction`
- `DirtyGraph`
- `InvalidationGraph`
- `mark_geoproject_changed()`
- `get_dirty_graph()`
- `get_invalidation_graph()`

Dirty and invalidation propagation now records affected scopes such as geometry, structure, material, phase, mesh, solver and result state.

### 4. Structure material assignment in Material Editor

`app/panels/material_editor.py` now supports:

- `assign_structure_material()`
- `assign_interface_material()`
- `assign_structure_material` action contract in the editor payload
- structure and interface assignment tables

### 5. Stage Editor extended activation controls

`app/panels/stage_editor.py` now supports:

- `set_structure_activation()`
- `set_interface_activation()`
- `set_load_activation()`
- `set_water_condition()`

Phase snapshots now include:

- active volumes
- active structures
- active interfaces
- active loads
- water condition id
- compact phase diff summary

### 6. SolverCompiler real input skeleton

`GeoProjectDocument.compile_phase_models()` now creates structured compiled phase input blocks rather than only count summaries.

Each `CompiledPhaseModel` includes:

```text
MeshBlock
ElementBlock
MaterialBlock
BoundaryBlock
LoadBlock
InterfaceBlock
StateVariableBlock
SolverControlBlock
ResultRequestBlock
```

The skeleton is not yet a full nonlinear production solver input, but it now has the correct contract for the next solver backend layer.

## Validation

Smoke script:

```bash
PYTHONPATH=src python3 -S tools/run_geoproject_native_workflow_smoke.py
```

Generated report:

```text
reports/geoproject_native_workflow_smoke.json
exports/geoproject_native_workflow_preview.geojson
```

Latest smoke summary:

```text
accepted: true
volumes: 24
structures: 5
interfaces: 83
mesh_nodes: 192
mesh_cells: 24
phases: 5
compiled_phase_models: 5
phase_results: 5
compiled skeleton missing blocks: []
```

## Remaining work

The system is now `GeoProjectDocument`-native at the workflow layer, but the following areas still need deeper implementation:

1. Real GUI widget binding for all editor payloads.
2. OCC-style persistent naming instead of engineering-level IDs only.
3. Robust topology-preserving geometry splitting.
4. Face-preserving meshing and interface element generation.
5. True nonlinear solver assembly and result field mapping.
6. End-to-end GUI behavior tests and numerical benchmark tests.
