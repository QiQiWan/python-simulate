from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from geoai_simkit.app.validation import validate_model
from geoai_simkit.core.model import BoundaryCondition, SimulationModel


@dataclass(slots=True)
class PreSolveReport:
    ok: bool
    messages: list[str]
    warnings: list[str]


def ensure_default_global_bcs(model: SimulationModel) -> bool:
    if model.boundary_conditions:
        return False
    defaults = [
        BoundaryCondition(name='fix_xmin', kind='displacement', target='xmin', components=(0, 1, 2), values=(0.0, 0.0, 0.0), metadata={'auto': True}),
        BoundaryCondition(name='fix_xmax', kind='displacement', target='xmax', components=(0, 1, 2), values=(0.0, 0.0, 0.0), metadata={'auto': True}),
        BoundaryCondition(name='fix_ymin', kind='displacement', target='ymin', components=(0, 1, 2), values=(0.0, 0.0, 0.0), metadata={'auto': True}),
        BoundaryCondition(name='fix_ymax', kind='displacement', target='ymax', components=(0, 1, 2), values=(0.0, 0.0, 0.0), metadata={'auto': True}),
        BoundaryCondition(name='fix_bottom', kind='displacement', target='bottom', components=(0, 1, 2), values=(0.0, 0.0, 0.0), metadata={'auto': True}),
    ]
    model.boundary_conditions.extend(defaults)
    return True


def analyze_presolve_state(model: SimulationModel) -> PreSolveReport:
    messages: list[str] = []
    warnings: list[str] = []
    for item in validate_model(model):
        text = f'[{item.step}] {item.message}'
        if item.level == 'error':
            messages.append(text)
        elif item.level == 'warning':
            warnings.append(text)
    try:
        grid = model.to_unstructured_grid()
        if int(getattr(grid, 'n_cells', 0)) == 0:
            messages.append('[几何] 当前模型没有可求解体网格，请先执行网格划分（体素化或 Gmsh）。')
        else:
            cts = set(int(v) for v in getattr(grid, 'celltypes', []))
            if cts and cts.issubset({3, 5, 7, 9}):
                messages.append('[几何] 当前仍是表面网格，请先执行网格划分（体素化或 Gmsh）。')
    except Exception as exc:
        messages.append(f'[几何] 无法生成求解网格: {exc}')
    if not model.materials:
        messages.append('[区域/材料] 当前没有任何材料赋值。')
    return PreSolveReport(ok=not messages, messages=messages, warnings=warnings)


class ProgressEtaEstimator:
    def __init__(self) -> None:
        self.start = perf_counter()

    def update(self, fraction: float) -> tuple[float, float | None]:
        elapsed = perf_counter() - self.start
        eta = None
        if fraction > 1e-6:
            total = elapsed / fraction
            eta = max(0.0, total - elapsed)
        return elapsed, eta


def format_seconds(seconds: float | None) -> str:
    if seconds is None:
        return '--:--'
    sec = int(max(0, seconds))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f'{h:d}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'
