from geoai_simkit.app.visual_modeling_system import VisualModelingSystem


def test_stage_activation_undo_redo_restores_inherited_active_block():
    system = VisualModelingSystem.create_default({"dimension": "3d"})
    stage_id = system.document.stages.order[-1]
    block_id = "excavation_stage_01"

    system.select_entity(block_id, "block")
    system.set_selected_block_activation(stage_id, False)
    assert not system.document.stages.stages[stage_id].is_block_active(block_id)

    system.undo()
    assert system.document.stages.stages[stage_id].is_block_active(block_id)

    system.redo()
    assert not system.document.stages.stages[stage_id].is_block_active(block_id)


def test_stage_activation_undo_keeps_preexisting_explicit_inactive_block_inactive():
    system = VisualModelingSystem.create_default({"dimension": "3d"})
    stage_id = system.document.stages.order[-1]
    block_id = "excavation_stage_03"
    assert not system.document.stages.stages[stage_id].is_block_active(block_id)

    system.select_entity(block_id, "block")
    system.set_selected_block_activation(stage_id, False)
    system.undo()

    assert not system.document.stages.stages[stage_id].is_block_active(block_id)
