from geoai_simkit.geometry.demo_pit import normalize_demo_stage_metadata
from geoai_simkit.solver.compute_preferences import apply_compute_profile_metadata


def test_apply_compute_profile_metadata_overrides_gpu_flags_for_cpu_safe():
    meta = {
        'compute_profile': 'cpu-safe',
        'warp_full_gpu_linear_solve': True,
        'warp_hex8_enabled': True,
        'warp_nonlinear_enabled': True,
        'solver_strategy': 'auto',
    }
    out = apply_compute_profile_metadata(meta, cuda_available=True)
    assert out['compute_profile'] == 'cpu-safe'
    assert out['warp_full_gpu_linear_solve'] is False
    assert out['warp_hex8_enabled'] is False
    assert out['warp_nonlinear_enabled'] is False
    assert out['solver_strategy'] == 'auto'


def test_normalize_demo_stage_metadata_clamps_initial_stage_for_runthrough():
    meta = normalize_demo_stage_metadata(
        'initial',
        {
            'plaxis_like_staged': True,
            'demo_stage_workflow': 'geostatic_then_wall_then_excavation',
            'solver_preset': 'balanced',
            'initial_increment': 0.05,
            'max_load_fraction_per_step': 0.05,
            'min_load_increment': 0.00625,
            'max_iterations': 32,
            'max_cutbacks': 6,
        },
        activation_map={'soil_mass': True, 'soil_excavation_1': True, 'soil_excavation_2': True, 'wall': False},
        coupled_mode=False,
    )
    assert meta['compute_profile'] == 'cpu-safe'
    assert meta['solver_strategy'] == 'direct'
    assert meta['preconditioner'] == 'none'
    assert meta['ordering'] == 'rcm'
    assert float(meta['initial_increment']) <= 0.0125
    assert float(meta['max_load_fraction_per_step']) <= 0.0125
    assert float(meta['min_load_increment']) <= 0.0015625
    assert int(meta['max_iterations']) >= 40
    assert int(meta['max_cutbacks']) >= 8
