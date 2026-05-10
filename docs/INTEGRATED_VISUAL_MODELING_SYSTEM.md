# Integrated visual modeling system

This version turns the previous architecture skeleton into a single integrated workbench contract.

## Main runtime path

```text
VisualModelingSystem
  ├── EngineeringDocument
  ├── HeadlessViewport / PySide section viewport
  ├── SelectionRef / SelectionSet
  ├── ToolContext / SelectTool / StageActivationTool
  ├── CommandStack / undo / redo
  ├── LightBlockKernel / foundation pit block geometry
  ├── TopologyGraph / contact edges
  ├── MeshDocument / tagged preview mesh
  ├── StagePlan / stage activation preview
  └── ResultPackage / engineering result curves
```

## What is integrated

- Object tree built from the engineering document.
- Property panel driven by stable selection references.
- Stage timeline driven by `StagePlan`.
- Section viewport primitives driven by the same `EngineeringDocument`.
- Mesh generation writes `block_id`, `role`, `material_id`, `layer_id`, and active-stage tags.
- Preview solve writes result curves back to `ResultPackage`.
- Undo and redo operate through `CommandStack`.

## Smoke command

```bash
PYTHONPATH=src python tools/run_visual_modeling_system_smoke.py
```
