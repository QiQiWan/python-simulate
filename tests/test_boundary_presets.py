from __future__ import annotations

import numpy as np

from geoai_simkit.app.boundary_presets import (
    DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY,
    available_boundary_presets,
    boundary_preset_definition,
    build_boundary_conditions_from_preset,
)
from geoai_simkit.app.presolve import analyze_presolve_state, ensure_default_global_bcs
from geoai_simkit.core.model import AnalysisStage, SimulationModel
from geoai_simkit.core.types import RegionTag


class DummyGrid:
    def __init__(self, n_cells: int = 8):
        self.n_cells = n_cells
        self.celltypes = np.asarray([12] * n_cells, dtype=np.int32)

    def cast_to_unstructured_grid(self):
        return self


def test_boundary_preset_catalog_contains_expected_demo_options() -> None:
    keys = {item.key for item in available_boundary_presets()}
    assert {'pit_rigid_box', 'pit_bottom_rollers', 'bottom_only'} <= keys
    rigid = boundary_preset_definition('pit_rigid_box')
    assert '底部+四周' in rigid.label


def test_build_boundary_conditions_from_preset_marks_metadata() -> None:
    bcs = build_boundary_conditions_from_preset('pit_bottom_rollers')
    assert [bc.name for bc in bcs] == ['fix_bottom', 'roller_xmin', 'roller_xmax', 'roller_ymin', 'roller_ymax']
    assert all(bc.metadata.get('preset') for bc in bcs)
    assert all(bc.metadata.get('preset_key') == 'pit_bottom_rollers' for bc in bcs)


def test_ensure_default_global_bcs_uses_default_preset() -> None:
    model = SimulationModel(name='demo', mesh=DummyGrid())
    changed = ensure_default_global_bcs(model)
    assert changed is True
    assert model.metadata.get('boundary_preset') == DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY
    assert len(model.boundary_conditions) == 5
    assert model.boundary_conditions[0].metadata.get('auto') is True


def test_presolve_missing_support_message_mentions_presets() -> None:
    model = SimulationModel(name='pit', mesh=DummyGrid())
    model.region_tags = [RegionTag('soil_mass', np.arange(0, 8, dtype=np.int64))]
    model.add_material('soil_mass', 'mohr_coulomb', E=10e6, nu=0.3, cohesion=10000.0, friction_deg=28.0, dilation_deg=0.0, tensile_strength=0.0, rho=1800.0)
    model.add_stage(AnalysisStage(name='initial', metadata={'activation_map': {'soil_mass': True}, 'initial_increment': 0.05}))

    report = analyze_presolve_state(model)
    assert report.ok is False
    assert any('预置模板' in msg for msg in report.messages)
