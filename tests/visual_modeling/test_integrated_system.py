from geoai_simkit.app.visual_modeling_system import VisualModelingSystem


def test_integrated_visual_modeling_system_roundtrip():
    system = VisualModelingSystem.create_default({"dimension": "3d"})
    block_id = next(iter(system.document.geometry.blocks))
    system.select_entity(block_id, "block")
    system.assign_material(block_id, "pytest_material")
    system.generate_mesh()
    system.run_results()
    payload = system.to_payload()
    assert payload["contract"] == "integrated_visual_modeling_system_v1"
    assert payload["object_tree"]["rows"]
    assert payload["mesh_panel"]["available"]
    assert "block_id" in payload["mesh_panel"]["cell_tags"]
    assert payload["result_panel"]["available"]
    assert payload["property_panel"]["title"].startswith("Block:")


def test_stage_activation_command_undo_redo():
    system = VisualModelingSystem.create_default({"dimension": "3d"})
    excavation = next(bid for bid, block in system.document.geometry.blocks.items() if block.role == "excavation")
    stage_id = system.document.stages.order[-1]
    system.select_entity(excavation, "block")
    system.set_selected_block_activation(stage_id, False)
    assert not system.document.stages.stages[stage_id].is_block_active(excavation)
    system.undo()
    assert system.document.stages.stages[stage_id].is_block_active(excavation)
    system.redo()
    assert not system.document.stages.stages[stage_id].is_block_active(excavation)
