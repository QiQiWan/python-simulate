import pytest
pytest.importorskip('pyvista')

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.geometry.demo_pit import configure_demo_coupling, build_demo_stages
from geoai_simkit.solver.structural_elements import build_structural_dof_map


def _build_model():
    scene = ParametricPitScene()
    model = SimulationModel(name='pit-demo-compat', mesh=scene.build())
    model.ensure_regions()
    model.metadata['source'] = 'parametric_pit'
    model.metadata['parametric_scene'] = {
        'length': scene.length,
        'width': scene.width,
        'depth': scene.depth,
        'soil_depth': scene.soil_depth,
        'nx': scene.nx,
        'ny': scene.ny,
        'nz': scene.nz,
        'wall_thickness': scene.wall_thickness,
    }
    model.metadata['demo_enabled_support_groups'] = ['crown_beam', 'strut_level_1', 'strut_level_2']
    model.metadata['demo_enabled_interface_groups'] = ['outer', 'inner_upper', 'inner_lower']
    configure_demo_coupling(model, prefer_wall_solver=True, auto_supports=True, interface_policy='manual_like_nearest_soil')
    model.stages = build_demo_stages(model, wall_active=True)
    return model


def test_demo_auto_supports_are_translational_only():
    model = _build_model()
    auto_structs = [s for s in model.structures if s.metadata.get('source') == 'parametric_pit_auto_support']
    assert auto_structs
    assert all(s.kind.lower() == 'truss2' for s in auto_structs)


def test_demo_stage_dof_map_has_no_rotational_tail():
    model = _build_model()
    stage_structs = model.structures_for_stage('initial')
    from geoai_simkit.solver.hex8_linear import build_submesh_for_stage
    sub = build_submesh_for_stage(model, 'initial')
    dof_map = build_structural_dof_map(stage_structs, sub)
    assert dof_map.total_ndof == dof_map.trans_ndof
