from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any

import numpy as np

from geoai_simkit.core.model import AnalysisStage, BoundaryCondition, LoadDefinition, SimulationModel
from geoai_simkit.core.types import RegionTag
from geoai_simkit.solver.backends import LocalBackend
from geoai_simkit.solver.base import SolverSettings


@dataclass(slots=True)
class _Cell:
    point_ids: np.ndarray


class TinyTet4Grid:
    """Minimal PyVista-like grid used for dependency-light solver smoke tests."""

    def __init__(self) -> None:
        self.points = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [1.0, 1.0, 1.0],
            ],
            dtype=float,
        )
        self._cells = (
            np.asarray([0, 1, 2, 3], dtype=np.int64),
            np.asarray([1, 2, 3, 4], dtype=np.int64),
        )
        self.celltypes = np.asarray([10, 10], dtype=np.int32)
        self.n_points = int(self.points.shape[0])
        self.n_cells = int(len(self._cells))
        self.point_data: dict[str, Any] = {}
        self.cell_data: dict[str, Any] = {}

    def get_cell(self, cell_id: int) -> _Cell:
        return _Cell(point_ids=self._cells[int(cell_id)])

    def cast_to_unstructured_grid(self) -> 'TinyTet4Grid':
        return self


def build_tiny_tet4_stage_model() -> SimulationModel:
    model = SimulationModel(name='tiny-tet4-stage-smoke', mesh=TinyTet4Grid())
    model.region_tags = [
        RegionTag('soil_core', np.asarray([0], dtype=np.int64)),
        RegionTag('excavation_block', np.asarray([1], dtype=np.int64)),
    ]
    model.set_material('soil_core', 'linear_elastic', E=30.0e6, nu=0.30, rho=1800.0)
    model.set_material('excavation_block', 'linear_elastic', E=20.0e6, nu=0.32, rho=1750.0)
    model.boundary_conditions = [
        BoundaryCondition(name='fix_bottom', kind='displacement', target='zmin', components=(0, 1, 2), values=(0.0, 0.0, 0.0)),
    ]
    model.stages = [
        AnalysisStage(
            name='initial',
            loads=(LoadDefinition(name='top_load', kind='nodal', target='top', values=(0.0, 0.0, -5000.0)),),
            metadata={'activation_map': {'soil_core': True, 'excavation_block': True}},
        ),
        AnalysisStage(
            name='excavate_block',
            deactivate_regions=('excavation_block',),
            loads=(LoadDefinition(name='top_load', kind='nodal', target='top', values=(0.0, 0.0, -5000.0)),),
        ),
    ]
    return model


def run_tiny_tet4_stage_smoke(out_path: str | Path | None = None) -> dict[str, Any]:
    model = build_tiny_tet4_stage_model()
    backend = LocalBackend()
    settings = SolverSettings(gravity=(0.0, 0.0, -9.81), prefer_sparse=False)
    diagnostics = backend.stage_execution_diagnostics(model, settings)
    state = backend.initialize_runtime_state(model, settings)
    stage_rows: list[dict[str, Any]] = []
    active_regions = {'soil_core', 'excavation_block'}
    for index, stage in enumerate(model.stages):
        active_regions |= set(stage.activate_regions)
        active_regions -= set(stage.deactivate_regions)
        result = backend.advance_stage_increment(
            model,
            settings,
            state,
            stage_name=stage.name,
            active_regions=tuple(sorted(active_regions)),
            bcs=tuple(model.boundary_conditions) + tuple(stage.boundary_conditions),
            loads=tuple(stage.loads),
            load_factor=1.0,
            increment_index=1,
            stage_metadata={'topo_order_index': index, 'source': 'tiny-tet4-smoke'},
        )
        backend.commit_stage(model, state, stage_name=stage.name, increment_result=result, history_rows=[], step_trace_rows=[])
        u = model.field_for('U_magnitude', stage.name)
        vm = model.field_for('von_mises', stage.name)
        active = model.field_for('active_cell_mask', stage.name)
        stage_rows.append(
            {
                'stage': stage.name,
                'status': result.status,
                'active_cell_count': int(result.active_cell_count),
                'max_displacement': float(np.max(u.values)) if u is not None and np.asarray(u.values).size else 0.0,
                'max_von_mises': float(np.max(vm.values)) if vm is not None and np.asarray(vm.values).size else 0.0,
                'active_cell_mask': np.asarray(active.values, dtype=int).tolist() if active is not None else [],
            }
        )
    summary = {
        'case_name': model.name,
        'backend': model.metadata.get('last_solver_backend', 'reference-linear-tet4'),
        'diagnostics': diagnostics,
        'stages': stage_rows,
        'result_labels': model.list_result_labels(),
    }
    if out_path is not None:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
        summary['out_path'] = str(path)
    return summary
