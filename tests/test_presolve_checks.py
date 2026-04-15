from __future__ import annotations

import pytest

pv = pytest.importorskip("pyvista")

from geoai_simkit.app.presolve import analyze_presolve_state
from geoai_simkit.core.model import AnalysisStage, BoundaryCondition, SimulationModel
from geoai_simkit.geometry.parametric import ParametricPitScene


def test_presolve_reports_risky_excavation_stage() -> None:
    model = SimulationModel(name='pit', mesh=ParametricPitScene(nx=3, ny=3, nz=3).build())
    model.ensure_regions()
    model.add_material('soil', 'mohr_coulomb', E=10e6, nu=0.3, cohesion=10000.0, friction_deg=28.0, dilation_deg=0.0, tensile_strength=0.0, rho=1800.0)
    model.add_material('wall', 'linear_elastic', E=20e9, nu=0.2, rho=2500.0)
    model.add_boundary_condition(BoundaryCondition(name='fix_bottom', kind='displacement', target='bottom', components=(0, 1, 2), values=(0.0, 0.0, 0.0)))
    model.add_stage(AnalysisStage(name='initial', steps=2, metadata={'activation_map': {'soil': True, 'wall': True}, 'initial_increment': 0.25}))
    model.add_stage(AnalysisStage(name='excavate_level_1', steps=6, metadata={'activation_map': {'soil': True, 'wall': True}, 'initial_increment': 0.25}))

    report = analyze_presolve_state(model)
    assert report.ok is True
    joined = '\n'.join(report.warnings)
    assert '开挖/卸载' in joined
    assert '初始增量' in joined


def test_presolve_blocks_when_no_supports() -> None:
    model = SimulationModel(name='pit', mesh=ParametricPitScene(nx=3, ny=3, nz=3).build())
    model.ensure_regions()
    model.add_material('soil', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_material('wall', 'linear_elastic', E=20e9, nu=0.2, rho=2500.0)
    report = analyze_presolve_state(model)
    assert report.ok is False
    assert any('位移约束' in msg for msg in report.messages)
