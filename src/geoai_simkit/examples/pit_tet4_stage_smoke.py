from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any

import numpy as np

from geoai_simkit.core.model import AnalysisStage, BoundaryCondition, LoadDefinition, SimulationModel
from geoai_simkit.core.types import RegionTag
from geoai_simkit.geometry.block_contact import (
    AxisAlignedBlock,
    build_contact_interface_assets,
    contact_assets_to_policy_rows,
    contact_interface_asset_summary,
    detect_axis_aligned_block_contacts,
    summarize_block_contacts,
)
from geoai_simkit.pipeline.interface_requests import build_interface_materialization_request_payload
from geoai_simkit.pipeline.contact_materializer import build_contact_solver_assembly_table, materialize_interface_requests
from geoai_simkit.pipeline.interface_ready import apply_interface_node_split
from geoai_simkit.pipeline.stage_release import attach_stage_release_index
from geoai_simkit.results.stage_package import export_stage_result_package
from geoai_simkit.solver.backends import LocalBackend
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.staging import StageManager


@dataclass(slots=True)
class _Cell:
    point_ids: np.ndarray


class PitTet4Grid:
    """Small PyVista-like Tet4 grid for headless foundation-pit stage solving."""

    def __init__(self, points: np.ndarray, cells: list[tuple[int, int, int, int]]) -> None:
        self.points = np.asarray(points, dtype=float).reshape((-1, 3))
        self._cells = tuple(np.asarray(cell, dtype=np.int64) for cell in cells)
        self.celltypes = np.asarray([10] * len(self._cells), dtype=np.int32)
        self.n_points = int(self.points.shape[0])
        self.n_cells = int(len(self._cells))
        self.point_data: dict[str, Any] = {}
        self.cell_data: dict[str, Any] = {}
        self.field_data: dict[str, Any] = {}

    def get_cell(self, cell_id: int) -> _Cell:
        return _Cell(point_ids=self._cells[int(cell_id)])

    def cast_to_unstructured_grid(self) -> 'PitTet4Grid':
        return self


_BRICK_TETS = (
    (0, 1, 2, 6),
    (0, 2, 3, 6),
    (0, 4, 5, 6),
    (0, 5, 1, 6),
    (0, 3, 7, 6),
    (0, 7, 4, 6),
)


def _add_point(point_lookup: dict[tuple[float, float, float], int], points: list[tuple[float, float, float]], xyz: tuple[float, float, float]) -> int:
    key = (round(float(xyz[0]), 9), round(float(xyz[1]), 9), round(float(xyz[2]), 9))
    existing = point_lookup.get(key)
    if existing is not None:
        return int(existing)
    point_lookup[key] = len(points)
    points.append((float(xyz[0]), float(xyz[1]), float(xyz[2])))
    return len(points) - 1


def _brick_corner_ids(
    point_lookup: dict[tuple[float, float, float], int],
    points: list[tuple[float, float, float]],
    bounds: tuple[float, float, float, float, float, float],
) -> tuple[int, ...]:
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    coords = (
        (xmin, ymin, zmin),
        (xmax, ymin, zmin),
        (xmax, ymax, zmin),
        (xmin, ymax, zmin),
        (xmin, ymin, zmax),
        (xmax, ymin, zmax),
        (xmax, ymax, zmax),
        (xmin, ymax, zmax),
    )
    return tuple(_add_point(point_lookup, points, xyz) for xyz in coords)


def _classify_block(ix: int, iy: int, iz: int) -> tuple[str, str, str]:
    # z layers: 0=deep base, 1=excavation level 2, 2=excavation level 1.
    if iz == 0:
        return 'soil_base', 'soil', 'linear_elastic'
    if ix == 1 and iy == 1:
        return ('soil_excavation_2' if iz == 1 else 'soil_excavation_1'), 'excavation', 'linear_elastic'
    if ix == 1 and iy == 2:
        return 'wall_north', 'wall', 'linear_elastic'
    if ix == 1 and iy == 0:
        return 'wall_south', 'wall', 'linear_elastic'
    if ix == 2 and iy == 1:
        return 'wall_east', 'wall', 'linear_elastic'
    if ix == 0 and iy == 1:
        return 'wall_west', 'wall', 'linear_elastic'
    return 'soil_mass', 'soil', 'linear_elastic'


def build_foundation_pit_tet4_stage_model() -> SimulationModel:
    """Build a compact, connected Tet4 pit model with staged excavation regions.

    This model is designed as a regression and workflow case, not as a calibrated
    engineering model. The mesh is partitioned into named regions so the stage
    solver, block activation, contact preflight and result exporters can be tested
    without optional geometry dependencies.
    """
    xs = (-12.0, -5.0, 5.0, 12.0)
    ys = (-6.0, -3.0, 3.0, 6.0)
    zs = (-18.0, -12.0, -6.0, 0.0)
    points: list[tuple[float, float, float]] = []
    point_lookup: dict[tuple[float, float, float], int] = {}
    cells: list[tuple[int, int, int, int]] = []
    region_cells: dict[str, list[int]] = {}
    block_rows: list[dict[str, Any]] = []

    for ix in range(3):
        for iy in range(3):
            for iz in range(3):
                region_name, role, material_name = _classify_block(ix, iy, iz)
                bounds = (xs[ix], xs[ix + 1], ys[iy], ys[iy + 1], zs[iz], zs[iz + 1])
                corner_ids = _brick_corner_ids(point_lookup, points, bounds)
                first_cell = len(cells)
                for tet in _BRICK_TETS:
                    cells.append(tuple(corner_ids[j] for j in tet))
                region_cells.setdefault(region_name, []).extend(range(first_cell, first_cell + len(_BRICK_TETS)))
                block_rows.append(
                    {
                        'name': f'{region_name}_{ix}_{iy}_{iz}',
                        'region_name': region_name,
                        'role': role,
                        'material_name': material_name,
                        'bounds': [float(v) for v in bounds],
                        'active_stages': ['initial', 'excavate_level_1', 'excavate_level_2'],
                        'metadata': {'ix': ix, 'iy': iy, 'iz': iz, 'region_name': region_name},
                    }
                )

    grid = PitTet4Grid(np.asarray(points, dtype=float), cells)
    model = SimulationModel(name='foundation-pit-tet4-stage-smoke', mesh=grid)
    model.region_tags = [RegionTag(name, np.asarray(ids, dtype=np.int64), metadata={'source': 'pit_tet4_stage_smoke'}) for name, ids in sorted(region_cells.items())]
    model.set_material('soil_base', 'mohr_coulomb', E=45.0e6, nu=0.30, rho=1900.0, cohesion=18.0e3, friction_deg=34.0, dilation_deg=4.0)
    model.set_material('soil_mass', 'mohr_coulomb', E=32.0e6, nu=0.32, rho=1850.0, cohesion=12.0e3, friction_deg=30.0, dilation_deg=2.0)
    model.set_material('soil_excavation_1', 'mohr_coulomb', E=28.0e6, nu=0.32, rho=1800.0, cohesion=10.0e3, friction_deg=28.0, dilation_deg=1.0)
    model.set_material('soil_excavation_2', 'mohr_coulomb', E=35.0e6, nu=0.31, rho=1850.0, cohesion=13.0e3, friction_deg=31.0, dilation_deg=2.0)
    for wall in ('wall_north', 'wall_south', 'wall_east', 'wall_west'):
        model.set_material(wall, 'linear_elastic', E=28.0e9, nu=0.20, rho=2500.0)

    model.boundary_conditions = [
        BoundaryCondition(name='fix_bottom', kind='displacement', target='zmin', components=(0, 1, 2), values=(0.0, 0.0, 0.0)),
        BoundaryCondition(name='fix_xmin_normal', kind='displacement', target='xmin', components=(0,), values=(0.0, 0.0, 0.0)),
        BoundaryCondition(name='fix_xmax_normal', kind='displacement', target='xmax', components=(0,), values=(0.0, 0.0, 0.0)),
        BoundaryCondition(name='fix_ymin_normal', kind='displacement', target='ymin', components=(1,), values=(0.0, 0.0, 0.0)),
        BoundaryCondition(name='fix_ymax_normal', kind='displacement', target='ymax', components=(1,), values=(0.0, 0.0, 0.0)),
    ]
    all_regions = {region.name: True for region in model.region_tags}
    surface_load = LoadDefinition(name='surface_surcharge', kind='nodal', target='top', values=(0.0, 0.0, -18000.0))
    model.stages = [
        AnalysisStage(
            name='initial',
            loads=(surface_load,),
            metadata={'activation_map': all_regions, 'stage_role': 'initial-geostatic'},
        ),
        AnalysisStage(
            name='excavate_level_1',
            deactivate_regions=('soil_excavation_1',),
            loads=(surface_load,),
            metadata={'stage_role': 'excavation', 'excavation_depth': 6.0},
        ),
        AnalysisStage(
            name='excavate_level_2',
            deactivate_regions=('soil_excavation_2',),
            loads=(surface_load,),
            metadata={'stage_role': 'excavation', 'excavation_depth': 12.0},
        ),
    ]
    contact_pairs = detect_axis_aligned_block_contacts([AxisAlignedBlock.from_mapping(row, fallback_name=row['name']) for row in block_rows])
    contact_assets = build_contact_interface_assets(contact_pairs)
    policy_rows = contact_assets_to_policy_rows(contact_assets)
    interface_requests = build_interface_materialization_request_payload(
        mesh_assembly_plan={'policy_rows': policy_rows},
        stage_names=[stage.name for stage in model.stages],
    )
    contact_materialization = materialize_interface_requests(
        model,
        request_payload=interface_requests,
        exact_only=True,
        default_parameters={'kn': 8.0e8, 'ks': 1.5e8, 'friction_deg': 28.0},
    )
    interface_ready_passes = []
    interface_ready_report = None
    for _ in range(3):
        interface_ready_report = apply_interface_node_split(model, duplicate_side='slave')
        interface_ready_passes.append(interface_ready_report.to_dict())
        if not interface_ready_report.topology_after.split_plans:
            break
    if interface_ready_report is None:  # pragma: no cover - defensive guard
        interface_ready_report = apply_interface_node_split(model, duplicate_side='slave')
        interface_ready_passes.append(interface_ready_report.to_dict())
    contact_solver_assembly = build_contact_solver_assembly_table(model)
    model.metadata.update(
        {
            'geometry_state': 'meshed',
            'source': 'pit_tet4_stage_smoke',
            'block_rows': block_rows,
            'contact_preflight': summarize_block_contacts(contact_pairs),
            'contact_interface_assets': contact_interface_asset_summary(contact_assets),
            'interface_materialization_requests': interface_requests,
            'contact_materialization': contact_materialization,
            'interface_ready': interface_ready_report.to_dict(),
            'interface_ready_passes': interface_ready_passes,
            'contact_solver_assembly': contact_solver_assembly,
            'nonlinear_solver': {'enabled': True, 'max_iterations': 6, 'load_steps': 1, 'min_load_step': 0.125, 'max_cutbacks': 3, 'tolerance': 1.0e-5, 'displacement_tolerance': 2.0e-4, 'contact_active_set': 'open_close', 'accept_unconverged_final_step': True},
            'note': 'Compact Tet4 foundation-pit regression model; not calibrated for engineering design.',
        }
    )
    return model


def _field_max(model: SimulationModel, field_name: str, stage_name: str) -> float:
    field = model.field_for(field_name, stage_name)
    if field is None:
        return 0.0
    values = np.asarray(field.values, dtype=float)
    return float(np.max(values)) if values.size else 0.0


def _field_list(model: SimulationModel, field_name: str, stage_name: str) -> list[Any]:
    field = model.field_for(field_name, stage_name)
    if field is None:
        return []
    return np.asarray(field.values).tolist()


def run_foundation_pit_tet4_stage_smoke(out_path: str | Path | None = None, result_dir: str | Path | None = None) -> dict[str, Any]:
    model = build_foundation_pit_tet4_stage_model()
    backend = LocalBackend()
    settings = SolverSettings(
        gravity=(0.0, 0.0, -9.81),
        prefer_sparse=False,
        metadata={
            'case': 'foundation-pit-tet4-stage-smoke',
            'nonlinear': {'enabled': True, 'max_iterations': 6, 'load_steps': 1, 'min_load_step': 0.125, 'max_cutbacks': 3, 'tolerance': 1.0e-5, 'displacement_tolerance': 2.0e-4, 'contact_active_set': 'open_close', 'accept_unconverged_final_step': True},
        },
    )
    diagnostics = backend.stage_execution_diagnostics(model, settings)
    state = backend.initialize_runtime_state(model, settings)
    manager = StageManager(model)
    stage_rows: list[dict[str, Any]] = []

    for ctx in manager.iter_stages():
        stage = ctx.stage
        result = backend.advance_stage_increment(
            model,
            settings,
            state,
            stage_name=stage.name,
            active_regions=tuple(sorted(ctx.active_regions)),
            bcs=tuple(model.boundary_conditions) + tuple(stage.boundary_conditions),
            loads=tuple(stage.loads),
            load_factor=1.0,
            increment_index=1,
            stage_metadata={
                'topo_order_index': ctx.index,
                'source': 'foundation-pit-tet4-stage-smoke',
                'activated_regions': sorted(ctx.activated_regions),
                'deactivated_regions': sorted(ctx.deactivated_regions),
            },
        )
        commit = backend.commit_stage(model, state, stage_name=stage.name, increment_result=result, history_rows=[], step_trace_rows=[])
        assembly = dict(commit.get('assembly_info', {}) or result.assembly_info)
        linear_summary = dict((assembly.get('operator_summary') or {}).get('linear_system', {}) or assembly.get('linear_system_summary', {}) or {})
        contact_summary = dict((assembly.get('operator_summary') or {}).get('contact_assembly', {}) or (assembly.get('contact_assembly_table', {}) or {}).get('summary', {}) or {})
        operator_summary = dict(assembly.get('operator_summary') or {})
        release_load_summary = dict(operator_summary.get('release_loads', {}) or {})
        energy_summary = dict(assembly.get('energy_summary', {}) or operator_summary.get('energy', {}) or {})
        increment_summary = dict(assembly.get('increment_summary', {}) or {})
        geostatic_summary = dict(operator_summary.get('geostatic', {}) or {})
        initial_stress_summary = dict(operator_summary.get('initial_stress', {}) or {})
        nonlinear_summary = dict(operator_summary.get('nonlinear', {}) or assembly.get('nonlinear_summary', {}) or {})
        nonlinear_material_residual_summary = dict(operator_summary.get('nonlinear_material_residual', {}) or assembly.get('nonlinear_material_residual_summary', {}) or {})
        load_summary = dict(assembly.get('load_summary', {}) or operator_summary.get('loads', {}) or {})
        stage_rows.append(
            {
                'stage': stage.name,
                'status': result.status,
                'active_regions': sorted(ctx.active_regions),
                'inactive_regions': sorted(ctx.inactive_regions),
                'activated_regions': sorted(ctx.activated_regions),
                'deactivated_regions': sorted(ctx.deactivated_regions),
                'active_cell_count': int(result.active_cell_count),
                'active_cell_mask': _field_list(model, 'active_cell_mask', stage.name),
                'max_displacement': _field_max(model, 'U_magnitude', stage.name),
                'max_von_mises': _field_max(model, 'von_mises', stage.name),
                'max_increment_displacement': _field_max(model, 'U_increment_magnitude', stage.name),
                'contact_assembly': contact_summary,
                'release_loads': release_load_summary,
                'energy': energy_summary,
                'increment': increment_summary,
                'geostatic': geostatic_summary,
                'initial_stress': initial_stress_summary,
                'nonlinear': nonlinear_summary,
                'nonlinear_material_residual': nonlinear_material_residual_summary,
                'yielded_cell_count': int(nonlinear_summary.get('yielded_cell_count', 0) or 0),
                'accepted_step_count': int(nonlinear_summary.get('accepted_step_count', 0) or 0),
                'cutback_count': int(nonlinear_summary.get('cutback_count', 0) or 0),
                'loads': load_summary,
                'solver_acceptance': dict(assembly.get('solver_acceptance', {}) or {}),
                'linear_system': {
                    'matrix_shape': list(linear_summary.get('matrix_shape', linear_summary.get('shape', [])) or []),
                    'rhs_norm': float(linear_summary.get('rhs_norm', 0.0) or 0.0),
                    'solution_norm': float(linear_summary.get('solution_norm', 0.0) or 0.0),
                    'residual_norm': float(linear_summary.get('residual_norm', 0.0) or 0.0),
                    'reaction_norm': float(linear_summary.get('reaction_norm', 0.0) or 0.0),
                    'fixed_dof_count': int(linear_summary.get('fixed_dof_count', 0) or 0),
                    'free_dof_count': int(linear_summary.get('free_dof_count', 0) or 0),
                    'sparse_enabled': bool(linear_summary.get('sparse_enabled', False)),
                },
            }
        )
    model.metadata['stage_contact_diagnostics'] = [
        {
            'stage': row.get('stage'),
            'status': row.get('status'),
            'active_cell_count': row.get('active_cell_count'),
            'active_regions': row.get('active_regions', []),
            'inactive_regions': row.get('inactive_regions', []),
            'contact_assembly': dict(row.get('contact_assembly', {}) or {}),
            'release_loads': dict(row.get('release_loads', {}) or {}),
            'linear_system': dict(row.get('linear_system', {}) or {}),
            'energy': dict(row.get('energy', {}) or {}),
            'increment': dict(row.get('increment', {}) or {}),
            'geostatic': dict(row.get('geostatic', {}) or {}),
            'initial_stress': dict(row.get('initial_stress', {}) or {}),
            'nonlinear': dict(row.get('nonlinear', {}) or {}),
            'nonlinear_material_residual': dict(row.get('nonlinear_material_residual', {}) or {}),
            'loads': dict(row.get('loads', {}) or {}),
            'solver_acceptance': dict(row.get('solver_acceptance', {}) or {}),
        }
        for row in stage_rows
    ]
    stage_release_index = attach_stage_release_index(model)
    backend.finalize_runtime_state(model, settings, state)
    contact = dict(model.metadata.get('contact_preflight', {}) or {})
    contact_assets = dict(model.metadata.get('contact_interface_assets', {}) or {})
    interface_requests = dict(model.metadata.get('interface_materialization_requests', {}) or {})
    contact_materialization = dict(model.metadata.get('contact_materialization', {}) or {})
    interface_ready = dict(model.metadata.get('interface_ready', {}) or model.metadata.get('pipeline.interface_ready', {}) or {})
    contact_solver_assembly = dict(model.metadata.get('contact_solver_assembly', {}) or {})
    result_package = None
    if result_dir is not None:
        result_package = export_stage_result_package(model, result_dir)
    summary = {
        'case_name': model.name,
        'backend': model.metadata.get('last_solver_backend', 'reference-linear-tet4'),
        'diagnostics': diagnostics,
        'grid': {'point_count': int(model.mesh.n_points), 'cell_count': int(model.mesh.n_cells), 'region_count': len(model.region_tags)},
        'regions': [{'name': row.name, 'cell_count': int(len(row.cell_ids))} for row in model.region_tags],
        'contact_summary': {
            'pair_count': int(contact.get('pair_count', 0) or 0),
            'by_contact_mode': dict(contact.get('by_contact_mode', {}) or {}),
            'by_mesh_policy': dict(contact.get('by_mesh_policy', {}) or {}),
            'total_overlap_area': float(contact.get('total_overlap_area', 0.0) or 0.0),
            'sample_pairs': list(contact.get('pairs', []) or [])[:20],
        },
        'contact_interface_assets': {
            'asset_count': int(contact_assets.get('asset_count', 0) or 0),
            'materializable_count': int(contact_assets.get('materializable_count', 0) or 0),
            'review_count': int(contact_assets.get('review_count', 0) or 0),
            'by_request_type': dict(contact_assets.get('by_request_type', {}) or {}),
            'by_solver_policy': dict(contact_assets.get('by_solver_policy', {}) or {}),
            'sample_assets': list(contact_assets.get('assets', []) or [])[:20],
        },
        'interface_materialization_requests': {
            'summary': dict(interface_requests.get('summary', {}) or {}),
            'sample_requests': list(interface_requests.get('requests', []) or [])[:20],
        },
        'contact_materialization': {
            'summary': dict(contact_materialization.get('summary', {}) or {}),
            'sample_rows': list(contact_materialization.get('rows', []) or [])[:20],
        },
        'interface_ready': {
            'applied': bool(interface_ready.get('applied', False)),
            'duplicate_side': str(interface_ready.get('duplicate_side', 'slave')),
            'duplicated_point_count': int(interface_ready.get('duplicated_point_count', 0) or 0),
            'updated_interface_count': int(interface_ready.get('updated_interface_count', 0) or 0),
            'n_points_before': int((interface_ready.get('metadata', {}) or {}).get('n_points_before', 0) or 0),
            'n_points_after': int((interface_ready.get('metadata', {}) or {}).get('n_points_after', 0) or 0),
            'remaining_split_plans': int((interface_ready.get('metadata', {}) or {}).get('n_remaining_split_plans', 0) or 0),
            'pruned_identical_pair_count': int((interface_ready.get('metadata', {}) or {}).get('pruned_identical_pair_count', 0) or 0),
            'pruned_interface_count': int((interface_ready.get('metadata', {}) or {}).get('pruned_interface_count', 0) or 0),
        },
        'contact_solver_assembly': {
            'summary': dict(contact_solver_assembly.get('summary', {}) or {}),
            'sample_rows': list(contact_solver_assembly.get('rows', []) or [])[:20],
        },
        'stage_release_loads': {
            'load_count': int(sum(int((row.get('release_loads', {}) or {}).get('load_count', 0) or 0) for row in stage_rows)),
            'total_force_norm_sum': float(sum(float((row.get('release_loads', {}) or {}).get('total_force_norm', 0.0) or 0.0) for row in stage_rows)),
            'sample_indexes': list(model.metadata.get('stage_release_load_indexes', []) or [])[:3],
        },
        'stage_initial_stress': {
            'enabled_stage_count': int(sum(1 for row in stage_rows if (row.get('initial_stress', {}) or {}).get('enabled'))),
            'rhs_contribution_norm_sum': float(sum(float((row.get('initial_stress', {}) or {}).get('rhs_contribution_norm', 0.0) or 0.0) for row in stage_rows)),
            'solver_contract': 'initial_stress_residual_tet4_v1',
        },
        'stage_material_state': dict(model.metadata.get('material_state_summary', {}) or {}),
        'stage_release_index': {
            'format': stage_release_index.get('format'),
            'release_boundary_count': int(stage_release_index.get('release_boundary_count', 0) or 0),
            'diagnostic_counts': dict(stage_release_index.get('diagnostic_counts', {}) or {}),
            'issues': list(stage_release_index.get('issues', []) or []),
            'sample_events': list(stage_release_index.get('release_events', []) or [])[:20],
        },
        'result_package': result_package,
        'stages': stage_rows,
        'result_labels': model.list_result_labels(),
        'warnings': list(model.metadata.get('stage_backend_warnings', []) or []),
    }
    if out_path is not None:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
        summary['out_path'] = str(path)
    return summary


__all__ = [
    'PitTet4Grid',
    'build_foundation_pit_tet4_stage_model',
    'run_foundation_pit_tet4_stage_smoke',
]
