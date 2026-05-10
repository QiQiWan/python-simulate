from __future__ import annotations

from geoai_simkit.app.tools import SelectTool, StageActivationTool, ToolContext, ToolEvent
from geoai_simkit.app.viewport import HeadlessViewport
from geoai_simkit.commands import CommandStack
from geoai_simkit.document import EngineeringDocument


def test_visual_modeling_architecture_contract() -> None:
    document = EngineeringDocument.create_foundation_pit({"dimension": "3d"}, name="test-pit")
    mesh = document.generate_preview_mesh()
    viewport = HeadlessViewport()
    viewport.load_document(document)
    stack = CommandStack()
    first_excavation = next(block_id for block_id, block in document.geometry.blocks.items() if block.role == "excavation")
    context = ToolContext(document=document, viewport=viewport, command_stack=stack)
    selected = SelectTool().on_mouse_press(ToolEvent(picked_entity_id=first_excavation, button="left"), context)
    assert selected is not None
    stage_id = next(stage for stage in document.stages.order if stage.startswith("excavate_level_"))
    result = StageActivationTool(stage_id=stage_id, active=False).commit(context)
    assert result is not None and result.ok
    assert len(document.geometry.blocks) > 0
    assert len(document.geometry.faces) > 0
    assert len(document.topology.contact_edges()) > 0
    assert "block_id" in mesh.cell_tags
    assert document.stage_preview(stage_id)["inactive_count"] >= 1
