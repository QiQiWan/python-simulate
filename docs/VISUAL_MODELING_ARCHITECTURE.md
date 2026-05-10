# Visual Modeling Architecture

This version introduces a PLAXIS/Abaqus-style visual modeling architecture.  The goal is to keep the GUI, geometry, mesh, staged construction and results synchronized through stable engineering entities instead of ad-hoc view payloads.

## Implemented layers

| Layer | Module | Responsibility |
|---|---|---|
| Viewport | `geoai_simkit.app.viewport` | Display scene primitives and expose picking state without requiring PyVista. |
| Selection | `geoai_simkit.document.selection` | Stable references for blocks, faces, mesh cells, stages and result entities. |
| Tool | `geoai_simkit.app.tools` | Mouse/keyboard interaction state machines. |
| Command | `geoai_simkit.commands` | Execute, undo and redo model edits. |
| Geometry Kernel | `geoai_simkit.geometry.kernel`, `geoai_simkit.geometry.light_block_kernel` | Generate and partition engineering geometry. |
| Topology Graph | `geoai_simkit.geometry.topology_graph` | Store block-face-contact-stage relations. |
| EngineeringDocument | `geoai_simkit.document.engineering_document` | Unified model state for GUI and solver handoff. |
| MeshDocument | `geoai_simkit.mesh.mesh_document` | Mesh tags and entity maps. |
| StagePlan | `geoai_simkit.stage.stage_plan` | Stage activation and deactivation state. |
| ResultPackage | `geoai_simkit.results.result_package` | Stage results and engineering metrics mapped back to objects. |

## Smoke test

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONNOUSERSITE=1 PYTHONPATH=src python tools/run_visual_modeling_architecture_smoke.py
```

The smoke creates a 3D block pit, generates a tagged preview mesh, loads a headless viewport, selects an excavation block, deactivates it in an excavation stage and checks that topology, mesh tags and stage state remain consistent.
