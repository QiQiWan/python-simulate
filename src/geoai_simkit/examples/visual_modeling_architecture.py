from __future__ import annotations

"""Minimal visual-modeling architecture demo."""

from typing import Any

from geoai_simkit.app.tools import SelectTool, StageActivationTool, ToolContext, ToolEvent
from geoai_simkit.app.viewport import HeadlessViewport
from geoai_simkit.commands import AssignMaterialCommand, CommandStack
from geoai_simkit.document import EngineeringDocument


def build_visual_modeling_demo(*, dimension: str = "3d") -> dict[str, Any]:
    doc = EngineeringDocument.create_foundation_pit({"dimension": dimension}, name=f"visual-{dimension}-pit")
    mesh = doc.generate_preview_mesh()
    viewport = HeadlessViewport()
    viewport.load_document(doc)
    stack = CommandStack()

    first_excavation = next(block_id for block_id, block in doc.geometry.blocks.items() if block.role == "excavation")
    select_tool = SelectTool()
    context = ToolContext(document=doc, viewport=viewport, command_stack=stack)
    selected = select_tool.on_mouse_press(ToolEvent(picked_entity_id=first_excavation, button="left"), context)
    stage_id = next((sid for sid in doc.stages.order if sid.startswith("excavate_level_")), doc.stages.active_stage_id or doc.stages.order[0])
    activation_result = StageActivationTool(stage_id=stage_id, active=False).commit(context)

    first_soil = next(block_id for block_id, block in doc.geometry.blocks.items() if block.role == "soil")
    material_result = stack.execute(AssignMaterialCommand(first_soil, "soft_clay_demo"), doc)

    return {
        "ok": True,
        "document": {
            "name": doc.name,
            "blocks": len(doc.geometry.blocks),
            "faces": len(doc.geometry.faces),
            "contacts": len(doc.topology.contact_edges()),
            "stages": len(doc.stages.order),
            "mesh_cells": mesh.cell_count,
            "mesh_tags": list(mesh.cell_tags.keys()),
        },
        "selection": selected.to_dict() if selected is not None else None,
        "activation_result": activation_result.to_dict() if activation_result is not None else None,
        "material_result": material_result.to_dict(),
        "stage_preview": doc.stage_preview(stage_id),
        "viewport": {"primitive_count": len(viewport.state.primitives), "active_stage_id": viewport.state.active_stage_id},
        "command_stack": stack.to_dict(),
        "dirty": doc.dirty.to_dict(),
    }


__all__ = ["build_visual_modeling_demo"]
