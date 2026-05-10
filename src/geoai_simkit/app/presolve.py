from __future__ import annotations

from dataclasses import dataclass
import importlib
from time import perf_counter

import numpy as np

from geoai_simkit.app.validation import validate_model
from geoai_simkit.app.boundary_presets import DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY, build_boundary_conditions_from_preset
from geoai_simkit.core.model import BoundaryCondition, SimulationModel
from geoai_simkit.geometry.demo_pit import expected_support_groups_for_stage, expected_wall_contact_groups_for_stage, normalize_enabled_interface_groups, normalize_enabled_support_groups
from geoai_simkit.solver.staging import StageManager


@dataclass(slots=True)
class PreSolveReport:
    ok: bool
    messages: list[str]
    warnings: list[str]


def ensure_default_global_bcs(model: SimulationModel) -> bool:
    if model.boundary_conditions:
        return False
    defaults = build_boundary_conditions_from_preset(DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY)
    for bc in defaults:
        bc.metadata['auto'] = True
    model.boundary_conditions.extend(defaults)
    model.metadata['boundary_preset'] = DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY
    return True


def _cell_counts_by_region(model: SimulationModel) -> dict[str, int]:
    counts: dict[str, int] = {}
    for region in model.region_tags:
        counts[region.name] = int(len(region.cell_ids))
    return counts


def _has_any_support(model: SimulationModel) -> bool:
    for bc in model.boundary_conditions:
        if bc.kind == 'displacement' and bc.components:
            return True
    for stage in model.stages:
        for bc in stage.boundary_conditions:
            if bc.kind == 'displacement' and bc.components:
                return True
    return False


def _active_material_gaps(model: SimulationModel, active_regions: set[str]) -> list[str]:
    return sorted(name for name in active_regions if model.material_for_region(name) is None)


def _is_excavation_stage(name: str) -> bool:
    lowered = str(name).lower()
    return any(token in lowered for token in ('excavat', 'dig', 'pit', '开挖', '卸载'))


def _parametric_pit_missing_split_regions(model: SimulationModel) -> list[str]:
    if model.metadata.get('source') != 'parametric_pit':
        return []
    expected = {'soil_mass', 'soil_excavation_1', 'soil_excavation_2'}
    existing = {region.name for region in model.region_tags}
    return sorted(expected - existing)


def analyze_presolve_state(model: SimulationModel) -> PreSolveReport:
    messages: list[str] = []
    warnings: list[str] = []
    advisory_error_tokens = (
        '以下区域未在当前模型中找到',
        '阶段名称暗示为开挖/卸载，但当前没有实际失活区域变化',
        '当前 Stage 与上一 Stage 的激活状态完全相同',
        '步数必须是正整数',
    )
    for item in validate_model(model):
        text = f'[{item.step}] {item.message}'
        if item.level == 'error':
            if any(token in item.message for token in advisory_error_tokens):
                warnings.append(text)
            else:
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
    if not _has_any_support(model):
        messages.append('[边界/阶段] 当前没有任何位移约束，求解很可能出现刚体位移或奇异矩阵。可在“边界条件”页直接应用预置模板，例如“基坑-刚性箱体”或“基坑-常用简化”。')

    missing_split = _parametric_pit_missing_split_regions(model)
    if missing_split:
        messages.append(f'[几何] 当前参数化基坑缺少分阶段开挖区域: {", ".join(missing_split)}。请重新生成示例，或将土体拆分为 soil_mass / soil_excavation_1 / soil_excavation_2。')

    mesh_engine_meta = model.metadata.get('mesh_engine') if isinstance(model.metadata, dict) else None
    if model.metadata.get('source') == 'parametric_pit' and isinstance(mesh_engine_meta, dict):
        merge_groups = mesh_engine_meta.get('shared_point_weld_groups') or []
        existing_regions = {region.name for region in model.region_tags}
        if {'soil_mass', 'soil_excavation_1', 'soil_excavation_2'}.issubset(existing_regions) and 'continuum_soil' not in {str(item) for item in merge_groups}:
            messages.append('[几何/网格] 当前参数化基坑的 soil_mass / soil_excavation_1 / soil_excavation_2 没有焊接为连续土体。这样 initial 阶段会形成彼此脱开的土块并导致非线性求解停滞。请重新运行 geometry-first 网格引擎，确保土体分区使用共享点焊接。')

    cell_counts = _cell_counts_by_region(model)
    nonlinear_regions = {m.region_name for m in model.materials if str(m.material_name).lower() in {'mohr_coulomb', 'hss', 'hs_small'}}
    prev_active: set[str] | None = None
    for ctx in StageManager(model).iter_stages():
        stage = ctx.stage
        meta = stage.metadata or {}
        active_regions = set(ctx.active_regions)
        if not active_regions:
            messages.append(f'[边界/阶段] Stage {stage.name} 没有任何活动区域，无法正确计算。')
            continue
        gaps = _active_material_gaps(model, active_regions)
        if gaps:
            messages.append(f'[边界/阶段] Stage {stage.name} 的活动区域存在未赋材料区域: {", ".join(gaps[:8])}')
        active_cells = sum(cell_counts.get(name, 0) for name in active_regions)
        if active_cells <= 0:
            messages.append(f'[边界/阶段] Stage {stage.name} 没有任何活动单元。')
        stage_refs = set()
        if isinstance(meta.get('activation_map'), dict):
            stage_refs |= {str(name).strip() for name in meta.get('activation_map', {}).keys() if str(name).strip()}
        stage_refs |= {str(name).strip() for name in stage.activate_regions if str(name).strip()}
        stage_refs |= {str(name).strip() for name in stage.deactivate_regions if str(name).strip()}
        valid_stage_refs = not stage_refs or all(name in cell_counts for name in stage_refs)
        changed = prev_active is None or active_regions != prev_active or bool(stage.loads) or bool(stage.boundary_conditions)
        if not changed:
            target = messages if (_is_excavation_stage(stage.name) and valid_stage_refs) else warnings
            target.append(f'[边界/阶段] Stage {stage.name} 与上一阶段相比没有激活/失活、荷载或边界条件变化，此阶段不会产生新的计算效果。')
        deactivated = (prev_active or active_regions) - active_regions if prev_active is not None else set()
        deactivated_cells = sum(cell_counts.get(name, 0) for name in deactivated)
        previous_cells = sum(cell_counts.get(name, 0) for name in (prev_active or active_regions))
        removal_ratio = (deactivated_cells / previous_cells) if previous_cells > 0 else 0.0
        initial_increment = float(meta.get('initial_increment', 0.25) or 0.25)
        max_iterations = int(meta.get('max_iterations', 24) or 24)
        has_nonlinear = bool(active_regions & nonlinear_regions)
        advisory_nonlinear = has_nonlinear or bool(nonlinear_regions)
        if advisory_nonlinear and initial_increment > 0.15:
            warnings.append(f'[边界/阶段] Stage {stage.name} 使用非线性土体时，初始增量 {initial_increment:.3f} 偏大，建议降到 0.05~0.10。')
        if removal_ratio > 0.20 and initial_increment > 0.10:
            warnings.append(f'[边界/阶段] Stage {stage.name} 单步失活比例约 {removal_ratio:.0%}，当前初始增量 {initial_increment:.3f} 偏大，建议降到 <= 0.10。')
        if removal_ratio > 0.35 and max_iterations < 30:
            warnings.append(f'[边界/阶段] Stage {stage.name} 失活变化较大，最大迭代次数 {max_iterations} 偏低，建议提高到 30~40。')
        if _is_excavation_stage(stage.name) and removal_ratio <= 0.0 and not stage.loads and not stage.boundary_conditions:
            target = messages if valid_stage_refs else warnings
            target.append(f'[边界/阶段] Stage {stage.name} 名称暗示为开挖/卸载，但没有检测到实际失活或附加边界变化。')
        active_structs = model.structures_for_stage(stage.name)
        rotational_structs = [item for item in active_structs if str(item.kind).lower() in {'beam2', 'frame3d', 'shellquad4'}]
        has_scipy_sparse = True
        try:
            importlib.import_module('scipy.sparse')
        except Exception:
            has_scipy_sparse = False
        if rotational_structs and not has_scipy_sparse:
            kinds = ', '.join(sorted({str(item.kind) for item in rotational_structs}))
            messages.append(f'[求解/结构] Stage {stage.name} 含有旋转自由度结构单元 ({kinds})，但当前环境缺少 SciPy sparse。请安装 SciPy，或改用 truss2 / translational-only 结构。')
        if model.metadata.get('source') == 'parametric_pit':
            if 'soil' in deactivated:
                messages.append(f'[边界/阶段] Stage {stage.name} 试图整体失活 soil 区域。参数化基坑示例必须逐层失活 soil_excavation_1 / soil_excavation_2，而不能一次性删除整块土体。')
            wall_mode = str(model.metadata.get('demo_wall_mode') or 'display_only')
            if 'wall' in active_regions:
                active_ifaces = model.interfaces_for_stage(stage.name)
                wall_ifaces = [item for item in active_ifaces if item.metadata.get('source') == 'parametric_pit_auto_wall']
                active_structs = model.structures_for_stage(stage.name)
                auto_supports = [item for item in active_structs if item.metadata.get('source') == 'parametric_pit_auto_support']
                if wall_mode == 'display_only' and not wall_ifaces:
                    messages.append(f'[边界/阶段] Stage {stage.name} 当前激活了 wall，但示例围护墙仍处于 display-only 模式，且未定义 interface / tie，不能直接参与求解。请保持 wall 为 display-only，或启用自动墙-土 interface。')
                elif wall_mode in {'auto_interface', 'plaxis_like_auto'}:
                    if not wall_ifaces:
                        messages.append(f'[边界/阶段] Stage {stage.name} 当前激活了 wall，但没有任何自动墙-土 interface 处于活动状态。请重新生成示例，或检查 interface 的 active_stages。')
                    else:
                        groups = {str(item.metadata.get('wall_contact_group')) for item in wall_ifaces}
                        enabled_wall_groups = normalize_enabled_interface_groups(model.metadata.get('demo_enabled_interface_groups'))
                        expected = expected_wall_contact_groups_for_stage(stage.name, enabled_wall_groups)
                        missing_groups = sorted(expected - groups)
                        if missing_groups:
                            messages.append(f'[边界/阶段] Stage {stage.name} 已启用墙体，但自动 interface 组缺失: {", ".join(missing_groups)}。请重新生成示例或补齐 wall/soil 接触面。')
                        if 'outer' not in groups:
                            messages.append(f'[边界/阶段] Stage {stage.name} 的 wall 未检测到外侧与 soil_mass 的接触 interface，墙体会成为自由漂浮体。')
                        selection_modes = sorted({str(item.metadata.get('selection_mode') or '') for item in wall_ifaces if item.metadata.get('selection_mode')})
                        max_pair_distance = max((float(item.metadata.get('max_pair_distance') or 0.0) for item in wall_ifaces), default=0.0)
                        if 'nearest_soil_auto' in selection_modes:
                            warnings.append(f'[边界/阶段] Stage {stage.name} 的墙-土界面包含最近土层自动吸附配对。建议保留当前土层划分，不要在阶段中随意重命名 soil_mass / soil_excavation_*。')
                        if max_pair_distance > 0.75:
                            warnings.append(f'[边界/阶段] Stage {stage.name} 的墙-土最大配对距离约 {max_pair_distance:.3f}，当前界面吸附跨度偏大。建议在“界面向导 / 诊断”中改用 exact_only 检查，或适当细化土层网格。')
                    support_groups = {str(item.metadata.get('support_group')) for item in auto_supports if item.metadata.get('support_group')}
                    enabled_supports = normalize_enabled_support_groups(model.metadata.get('demo_enabled_support_groups'))
                    expected_supports = expected_support_groups_for_stage(stage.name, enabled_supports)
                    missing_supports = sorted(expected_supports - support_groups)
                    if wall_mode == 'plaxis_like_auto' and missing_supports:
                        messages.append(f'[边界/阶段] Stage {stage.name} 处于 plaxis-like 自动耦合模式，但结构支撑组缺失: {", ".join(missing_supports)}。请重新生成示例，或检查冠梁/支撑的 active_stages。')
                    elif wall_mode == 'auto_interface' and stage.name != 'initial' and not auto_supports:
                        warnings.append(f'[边界/阶段] Stage {stage.name} 当前只有墙-土 interface，没有自动冠梁/支撑结构。可继续计算，但这不是完整的多结构耦合开挖工况。')
        prev_active = active_regions

    solver_settings = model.metadata.get('solver_settings') or {}
    tol = solver_settings.get('tolerance')
    try:
        tol_f = float(tol)
    except Exception:
        tol_f = None
    if tol_f is not None and tol_f < 1.0e-7:
        warnings.append(f'[求解/结果] 当前容差 {tol_f:.1e} 非常严格，建议先用 1e-4 ~ 1e-5 跑通后再收紧。')
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
