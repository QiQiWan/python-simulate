from __future__ import annotations

"""Payload builders for the integrated visual-modeling architecture."""

from typing import Any

from geoai_simkit.app.visual_modeling_system import VisualModelingSystem
from geoai_simkit.commands import CommandStack
from geoai_simkit.document import EngineeringDocument, engineering_document_from_simulation_model


def build_visual_modeling_architecture_payload(document: EngineeringDocument) -> dict[str, Any]:
    system = VisualModelingSystem(document=document, command_stack=CommandStack())
    payload = system.to_payload()
    payload["architecture_layers"] = [
        {"id": "viewport", "role": "display", "status": "integrated", "module": "geoai_simkit.app.viewport"},
        {"id": "selection", "role": "stable selection", "status": "integrated", "module": "geoai_simkit.document.selection"},
        {"id": "tool", "role": "mouse interaction state", "status": "integrated", "module": "geoai_simkit.app.tools"},
        {"id": "command", "role": "execute/undo/redo", "status": "integrated", "module": "geoai_simkit.commands"},
        {"id": "geometry_kernel", "role": "geometry generation and partition", "status": "integrated", "module": "geoai_simkit.geometry.light_block_kernel"},
        {"id": "topology_graph", "role": "block/face/contact relations", "status": "integrated", "module": "geoai_simkit.geometry.topology_graph"},
        {"id": "engineering_document", "role": "unified model state", "status": "integrated", "module": "geoai_simkit.document.engineering_document"},
        {"id": "mesh_document", "role": "mesh tags and entity mapping", "status": "integrated", "module": "geoai_simkit.mesh.mesh_document"},
        {"id": "stage_plan", "role": "staged activation", "status": "integrated", "module": "geoai_simkit.stage.stage_plan"},
        {"id": "result_package", "role": "results mapped to engineering objects", "status": "integrated", "module": "geoai_simkit.results.result_package"},
    ]
    # Backward-compatible summary keys used by older fallback views/tests.
    mesh_panel = payload.get("mesh_panel", {})
    payload["mesh_tags"] = {"cell_tags": mesh_panel.get("cell_tags", []), "entity_map_blocks": len(mesh_panel.get("block_to_cells", {}))}
    payload["stage_preview"] = document.stage_preview(document.stages.active_stage_id)
    return payload


def build_visual_modeling_payload_from_workbench_document(workbench_document: Any) -> dict[str, Any]:
    model = getattr(workbench_document, "model", None)
    if model is not None:
        doc = engineering_document_from_simulation_model(model, name=str(getattr(model, "name", "foundation-pit")))
    else:
        doc = EngineeringDocument.create_foundation_pit({}, name="foundation-pit")
    return build_visual_modeling_architecture_payload(doc)


__all__ = ["build_visual_modeling_architecture_payload", "build_visual_modeling_payload_from_workbench_document"]
