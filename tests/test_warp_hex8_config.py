from geoai_simkit.solver.warp_hex8 import resolve_warp_hex8_config


def test_resolve_warp_hex8_config_defaults() -> None:
    cfg = resolve_warp_hex8_config(None)
    assert cfg.enabled is True
    assert cfg.force is False
    assert cfg.min_cells >= 1
    assert cfg.precision == 'float32'
    assert cfg.fallback_to_cpu is True


def test_resolve_warp_hex8_config_from_metadata() -> None:
    cfg = resolve_warp_hex8_config({
        'warp_hex8_enabled': False,
        'warp_hex8_force': True,
        'warp_hex8_min_cells': 32,
        'warp_hex8_precision': 'float32',
        'warp_hex8_fallback_to_cpu': False,
    })
    assert cfg.enabled is False
    assert cfg.force is True
    assert cfg.min_cells == 32
    assert cfg.precision == 'float32'
    assert cfg.fallback_to_cpu is False
