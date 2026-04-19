from __future__ import annotations

import pytest

pv = pytest.importorskip('pyvista')

import numpy as np

from geoai_simkit.core.model import (
    AnalysisStage,
    BoundaryCondition,
    InterfaceDefinition,
    SimulationModel,
    StructuralElementDefinition,
)
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.backends import ReferenceBackend


def _single_tet_grid() -> pv.UnstructuredGrid:
    points = np.asarray([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=float)
    cells = np.asarray([4, 0, 1, 2, 3], dtype=np.int64)
    celltypes = np.asarray([int(pv.CellType.TETRA)], dtype=np.uint8)
    grid = pv.UnstructuredGrid(cells, celltypes, points)
    grid.cell_data['region_name'] = np.asarray(['soil'])
    return grid


def _first_point_pair_along_x(grid) -> tuple[int, int, np.ndarray]:
    points = np.asarray(grid.points, dtype=float)
    for master in range(points.shape[0]):
        for slave in range(points.shape[0]):
            if master == slave:
                continue
            delta = points[slave] - points[master]
            if abs(float(delta[1])) <= 1.0e-9 and abs(float(delta[2])) <= 1.0e-9 and float(delta[0]) > 1.0e-9:
                normal = delta / max(float(np.linalg.norm(delta)), 1.0e-12)
                return int(master), int(slave), normal
    raise AssertionError('expected at least one point pair aligned with +x')


def test_reference_backend_solves_linear_hex8_case() -> None:
    model = SimulationModel(name='ref-hex8', mesh=ParametricPitScene(nx=5, ny=5, nz=5).build())
    model.ensure_regions()
    model.add_material('soil_mass', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_material('soil_excavation_1', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_material('soil_excavation_2', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_material('wall', 'linear_elastic', E=20e9, nu=0.2, rho=2500.0)
    model.add_boundary_condition(BoundaryCondition(name='fix_bottom', kind='displacement', target='bottom', components=(0, 1, 2), values=(0.0, 0.0, 0.0)))
    solved = ReferenceBackend().solve(model, SolverSettings())
    assert solved.metadata['solver_backend'] == 'reference'
    assert solved.metadata['solver_mode'] == 'linear-hex8'
    assert solved.metadata['stages_run'] == ['default']
    assert 'U' in solved.mesh.point_data
    assert 'residual' in solved.mesh.point_data
    assert 'reaction' in solved.mesh.point_data
    assert any(field.name == 'dU' for field in solved.results_for_stage('default'))
    assert any(field.name == 'residual' for field in solved.results_for_stage('default'))
    assert any(field.name == 'reaction' for field in solved.results_for_stage('default'))
    assert float(np.min(np.asarray(solved.mesh.point_data['U'])[:, 2])) <= 0.0


def test_reference_backend_solves_linear_tet4_stage_sequence() -> None:
    model = SimulationModel(name='ref-tet4', mesh=_single_tet_grid())
    model.ensure_regions()
    model.add_material('soil', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_boundary_condition(BoundaryCondition(name='fix_bottom', kind='displacement', target='bottom', components=(0, 1, 2), values=(0.0, 0.0, 0.0)))
    model.add_stage(AnalysisStage(name='empty_stage', deactivate_regions=('soil',)))
    model.add_stage(AnalysisStage(name='soil_stage', activate_regions=('soil',)))
    solved = ReferenceBackend().solve(model, SolverSettings())
    assert solved.metadata['solver_backend'] == 'reference'
    assert solved.metadata['solver_mode'] == 'linear-tet4'
    assert solved.metadata['stages_run'] == ['empty_stage', 'soil_stage']
    warnings = list(solved.metadata.get('solver_warnings', []) or [])
    assert any('no active Tet4 cells' in str(item) for item in warnings)


def test_reference_backend_falls_back_for_nonlinear_materials() -> None:
    class FakeFallback:
        def solve(self, model, settings):
            model.metadata['solver_mode'] = 'fallback'
            model.metadata['stages_run'] = ['default']
            return model

    model = SimulationModel(name='fallback-case', mesh=ParametricPitScene(nx=3, ny=3, nz=3).build())
    model.ensure_regions()
    model.add_material('soil_mass', 'mohr_coulomb', E=10e6, nu=0.3, rho=1800.0, cohesion=1.0, friction_deg=20.0)
    model.add_material('wall', 'linear_elastic', E=20e9, nu=0.2, rho=2500.0)
    solved = ReferenceBackend(fallback=FakeFallback()).solve(model, SolverSettings())
    assert solved.metadata['solver_mode'] == 'fallback'
    assert 'reference-fallback->warp' in solved.metadata['solver_backend_chain']
    assert any('Reference backend fallback' in str(item) for item in solved.metadata.get('solver_warnings', []))


def test_reference_backend_supports_translational_structures_and_node_pair_interfaces() -> None:
    grid = ParametricPitScene(nx=5, ny=5, nz=5).build()
    model = SimulationModel(name='ref-hex8-coupled', mesh=grid)
    model.ensure_regions()
    model.add_material('soil_mass', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_material('soil_excavation_1', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_material('soil_excavation_2', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_material('wall', 'linear_elastic', E=20e9, nu=0.2, rho=2500.0)
    model.add_boundary_condition(
        BoundaryCondition(
            name='fix_bottom',
            kind='displacement',
            target='bottom',
            components=(0, 1, 2),
            values=(0.0, 0.0, 0.0),
        )
    )
    master_gid, slave_gid, normal = _first_point_pair_along_x(model.to_unstructured_grid())
    model.add_structure(
        StructuralElementDefinition(
            name='crown_strut',
            kind='truss2',
            point_ids=(master_gid, slave_gid),
            parameters={'E': 2.1e11, 'A': 1.0e-3, 'prestress': 1.0e4},
            metadata={'support_group': 'test_support'},
        )
    )
    model.add_interface(
        InterfaceDefinition(
            name='soil_wall_open_pair',
            kind='node_pair',
            slave_point_ids=(slave_gid,),
            master_point_ids=(master_gid,),
            parameters={'normal': tuple(float(v) for v in normal), 'kn': 1.0e6, 'ks': 1.0e5, 'friction_deg': 20.0},
            metadata={'wall_contact_group': 'test_interface'},
        )
    )

    backend = ReferenceBackend()
    diagnostics = backend.stage_execution_diagnostics(model, SolverSettings())
    assert diagnostics['supported'] is True
    assert diagnostics['supports_structures'] is True
    assert diagnostics['supports_interfaces'] is True

    solved = backend.solve(model, SolverSettings())
    assert solved.metadata['solver_backend'] == 'reference'
    stage_meta = dict(solved.metadata.get('linear_element_assembly', {}) or {})['default']
    operator_summary = dict(stage_meta.get('operator_summary', {}) or {})
    assert operator_summary['active_structure_count'] == 1
    assert operator_summary['active_interface_count'] == 1
    assert operator_summary['structural']['active_structure_count'] == 1
    assert operator_summary['interface']['active_interface_count'] == 1
    assert operator_summary['contact']['active_contact_pair_count'] == 1
    assert operator_summary['boundary']['boundary_condition_count'] >= 1


def test_reference_backend_rejects_rotational_structures_on_rebuilt_path() -> None:
    model = SimulationModel(name='ref-hex8-rotational-unsupported', mesh=ParametricPitScene(nx=4, ny=4, nz=4).build())
    model.ensure_regions()
    model.add_material('soil_mass', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_material('soil_excavation_1', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_material('soil_excavation_2', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_material('wall', 'linear_elastic', E=20e9, nu=0.2, rho=2500.0)
    model.add_boundary_condition(
        BoundaryCondition(
            name='fix_bottom',
            kind='displacement',
            target='bottom',
            components=(0, 1, 2),
            values=(0.0, 0.0, 0.0),
        )
    )
    model.add_structure(
        StructuralElementDefinition(
            name='crown_beam',
            kind='frame3d',
            point_ids=(0, 1),
            parameters={'E': 2.1e11, 'A': 1.0e-3, 'Iy': 1.0e-6, 'Iz': 1.0e-6, 'J': 1.0e-6},
        )
    )
    diagnostics = ReferenceBackend().stage_execution_diagnostics(model, SolverSettings())
    assert diagnostics['supported'] is False
    assert 'frame3d' in diagnostics['unsupported_structure_kinds']
