from geoai_simkit.validation_rules import (
    validate_bc_inputs,
    validate_geometry_params,
    validate_material_parameters,
    validate_stage_inputs,
)


def test_material_validation_detects_bad_mc_values():
    issues = validate_material_parameters(
        'mohr_coulomb',
        {
            'E': -1.0,
            'nu': 0.7,
            'cohesion': -1.0,
            'friction_deg': 95.0,
            'dilation_deg': 40.0,
            'tensile_strength': -2.0,
            'rho': 0.0,
        },
        '',
    )
    fields = {i.field for i in issues if i.level == 'error'}
    assert {'name', 'E', 'nu', 'cohesion', 'friction_deg', 'tensile_strength', 'rho'} <= fields


def test_stage_validation_flags_overlap_and_bad_increment():
    issues = validate_stage_inputs('s1', 0, 2.0, 0, ['soil'], ['soil'])
    fields = {i.field for i in issues}
    assert {'stage_steps', 'stage_initial_increment', 'stage_max_iterations', 'stage_regions'} <= fields


def test_geometry_and_bc_validation_basic():
    geom = validate_geometry_params({'length': 10, 'width': 8, 'depth': 12, 'soil_depth': 10, 'wall_thickness': 6, 'nx': 1, 'ny': 10, 'nz': 10})
    assert any(i.field == 'soil_depth' and i.level == 'error' for i in geom)
    assert any(i.field == 'wall_thickness' and i.level == 'error' for i in geom)
    assert any(i.field == 'nx' and i.level == 'error' for i in geom)
    bc = validate_bc_inputs('b1', 'roller', 'bottom', (0, 0), (1.0,))
    assert any(i.field == 'bc_components' and i.level == 'error' for i in bc)
    assert any(i.field == 'bc_values' and i.level == 'warning' for i in bc)
