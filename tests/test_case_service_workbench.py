from geoai_simkit.app.case_service import CaseService
from geoai_simkit.app.workbench import WorkbenchService
from geoai_simkit.examples.pit_example import build_demo_case


def test_case_service_builds_block_and_stage_browser_summary():
    service = CaseService()
    model = service.prepare_case(build_demo_case())
    summary = service.build_browser_summary(model)
    assert summary.geometry_state in {'geometry', 'meshed'}
    assert {block.name for block in summary.blocks} >= {'soil_mass', 'wall'}
    assert [row.name for row in summary.stage_rows][:2] == ['initial', 'wall_activation']
    wall_block = next(block for block in summary.blocks if block.name == 'wall')
    assert wall_block.material_name == 'linear_elastic'


def test_workbench_service_includes_preprocess_overview():
    doc = WorkbenchService().document_from_case(build_demo_case(), mode='geometry')
    assert doc.preprocess is not None
    assert doc.browser.interface_count >= 1
    assert doc.preprocess.n_boundary_adjacencies >= 1
    assert doc.preprocess.n_interface_elements >= 1
