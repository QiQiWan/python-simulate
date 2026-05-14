# GeoAI SimKit 1.5.3 — Structure Mouse + Material Workflow

This iteration addresses the gap between a rendered 3D scene and a mouse-operable CAD/FEM preprocessor workflow.

## Why the visual system could still feel non-interactive

A rendered VTK/PyVista actor is not sufficient for CAD editing. The click path must complete all of these steps:

1. Qt/VTK mouse event enters the viewport adapter.
2. The screen point is converted to a world point on the active workplane or picked cell.
3. The active modeling tool consumes the event.
4. The tool executes an undoable GeoProjectDocument command.
5. The command creates or modifies point/curve/surface/volume records.
6. The viewport state is rebuilt from the document.
7. Selection and property/material/phase panels are synchronized.

Earlier iterations had most runtime pieces, but the structure workflow still needed a persistent panel that exposes direct point/line/surface/volume creation and promotion-to-structure actions.

## Added GUI workflow

The right inspector now includes a **结构建模** tab with:

- Direct mouse creation buttons: 创建点, 创建线, 创建面, 创建体.
- Selected-geometry promotion buttons: volume to soil/excavation/concrete body, surface to wall/interface, curve to beam/anchor/embedded beam, point to control point.
- Material quick assignment: recommended material to current selection, and layer/structure-aware batch assignment.

## Material workflow

Material management is kept in a single catalog while exposing engineering categories:

- soil materials
- wall/plate materials
- beam/strut/anchor materials
- interface materials

Quick assignment now uses recognized layer and structure information:

- soil clusters and borehole layer material IDs when available
- volume centroid depth against borehole layers
- volume role for soil/excavation/concrete structure bodies
- structure type for walls, beams, anchors, embedded beams and interfaces

## Headless service contract

`geoai_simkit.services.cad_structure_workflow` is upgraded to v2 and now exports:

- `build_structure_mouse_interaction_payload`
- `promote_geometry_to_structure`
- `recommended_material_for_entity`
- `auto_assign_materials_by_recognized_strata_and_structures`

These functions are Qt-free and tested without a display server.
