import pytest
pytest.importorskip('pyvista')

from geoai_simkit.examples.pit_example import build_demo_model
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.warp_backend import WarpBackend


def test_demo_staged_workflow_runs_to_completion():
    model = build_demo_model()
    solved = WarpBackend().solve(model, SolverSettings(prefer_sparse=True, line_search=True, max_cutbacks=5))
    assert solved.metadata.get('solver_mode') in {'staged-linearized-hex8', 'nonlinear-hex8'}
    assert solved.metadata.get('stages_run') == ['initial', 'wall_activation', 'excavate_level_1', 'excavate_level_2']
    assert solved.field_for('U', 'excavate_level_2') is not None
    assert solved.field_for('stress', 'excavate_level_2') is not None
