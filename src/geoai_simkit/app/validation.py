from __future__ import annotations

from dataclasses import dataclass

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.solver.staging import StageManager
from geoai_simkit.validation_rules import (
    normalize_region_name,
    validate_bc_inputs,
    validate_load_inputs,
    validate_solver_settings,
    validate_stage_inputs,
)


@dataclass(slots=True)
class ValidationIssue:
    level: str
    step: str
    message: str


def validate_model(model: SimulationModel | None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if model is None:
        issues.append(ValidationIssue('error', '项目', '尚未创建或导入模型。'))
        return issues
    try:
        grid = model.to_unstructured_grid()
        n_cells = int(getattr(grid, 'n_cells', 0))
        if n_cells == 0:
            issues.append(ValidationIssue('error', '几何', '当前模型没有可求解单元。'))
        else:
            try:
                cts = set(int(v) for v in getattr(grid, 'celltypes', []))
                if cts and cts.issubset({3, 5, 7, 9}):
                    issues.append(ValidationIssue('error', '几何', '当前模型仍为表面网格，请先执行网格划分（体素化或 Gmsh）。'))
            except Exception:
                pass
    except Exception:
        issues.append(ValidationIssue('error', '几何', '当前网格没有单元。'))
    model.ensure_regions()
    if not model.region_tags:
        issues.append(ValidationIssue('error', '区域/材料', '没有识别到区域。'))
    else:
        names = [r.name for r in model.region_tags]
        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            issues.append(ValidationIssue('error', '区域/材料', f'存在重复区域名称: {", ".join(dup[:8])}'))
        unassigned = [r.name for r in model.region_tags if model.material_for_region(r.name) is None]
        if unassigned:
            issues.append(ValidationIssue('warning', '区域/材料', f'以下区域尚未赋材料: {", ".join(unassigned[:8])}'))
    mat_names = [m.name for m in model.material_library]
    mat_dup = sorted({n for n in mat_names if mat_names.count(n) > 1})
    if mat_dup:
        issues.append(ValidationIssue('error', '区域/材料', f'材料库存在重复名称: {", ".join(mat_dup[:8])}'))
    if not model.boundary_conditions:
        issues.append(ValidationIssue('warning', '边界/阶段', '尚未定义全局边界条件。可在“边界条件”页直接应用预置模板。'))
    if not model.stages:
        issues.append(ValidationIssue('warning', '边界/阶段', '尚未定义施工阶段，求解时将使用默认阶段。'))
    else:
        stage_names = [s.name for s in model.stages]
        region_names = {normalize_region_name(r.name) for r in model.region_tags}
        dup = sorted({n for n in stage_names if stage_names.count(n) > 1})
        if dup:
            issues.append(ValidationIssue('error', '边界/阶段', f'存在重复 Stage 名称: {", ".join(dup[:8])}'))
        manager = StageManager(model)
        contexts = manager.iter_stages()
        previous_active: set[str] | None = None
        for stage, ctx in zip(model.stages, contexts, strict=False):
            meta = stage.metadata or {}
            for item in validate_stage_inputs(
                stage.name,
                stage.steps,
                meta.get('initial_increment', 0.25),
                meta.get('max_iterations', 24),
                stage.activate_regions,
                stage.deactivate_regions,
                existing_names=stage_names,
                current_name=stage.name,
            ):
                issues.append(ValidationIssue(item.level, '边界/阶段', f'{stage.name}: {item.message}'))
            referenced = set(stage.activate_regions) | set(stage.deactivate_regions)
            amap = meta.get('activation_map') if isinstance(meta.get('activation_map'), dict) else {}
            referenced |= {normalize_region_name(k) for k in amap.keys()}
            missing = sorted(name for name in {normalize_region_name(item) for item in referenced if str(item).strip()} if name and name not in region_names)
            if missing:
                issues.append(ValidationIssue('error', '边界/阶段', f'{stage.name}: 以下区域未在当前模型中找到: {", ".join(missing[:8])}'))
            if previous_active is not None and ctx.active_regions == previous_active and not stage.boundary_conditions and not stage.loads:
                issues.append(ValidationIssue('warning', '边界/阶段', f'{stage.name}: 当前 Stage 与上一 Stage 的激活状态完全相同，且没有附加荷载/边界变化，此阶段不会产生新的计算效果。'))
            name_lower = stage.name.lower()
            if any(token in name_lower for token in ('excavat', 'dig', 'pit', '开挖', '卸载')) and previous_active is not None and ctx.active_regions == previous_active:
                issues.append(ValidationIssue('warning', '边界/阶段', f'{stage.name}: 阶段名称暗示为开挖/卸载，但当前没有实际失活区域变化。'))
            active_missing_material = sorted(name for name in ctx.active_regions if model.material_for_region(name) is None)
            if active_missing_material:
                issues.append(ValidationIssue('error', '边界/阶段', f'{stage.name}: 当前活动区域存在未赋材料区域: {", ".join(active_missing_material[:8])}'))
            if not ctx.active_regions:
                issues.append(ValidationIssue('error', '边界/阶段', f'{stage.name}: 当前 Stage 没有任何活动区域。'))
            for bc in stage.boundary_conditions:
                for item in validate_bc_inputs(bc.name, bc.kind, bc.target, bc.components, bc.values):
                    issues.append(ValidationIssue(item.level, '边界/阶段', f'{stage.name}/{bc.name}: {item.message}'))
            for ld in stage.loads:
                for item in validate_load_inputs(ld.name, ld.kind, ld.target, ld.values):
                    issues.append(ValidationIssue(item.level, '边界/阶段', f'{stage.name}/{ld.name}: {item.message}'))
            previous_active = set(ctx.active_regions)
    if model.metadata.get('solver_settings'):
        ss = model.metadata['solver_settings']
        for item in validate_solver_settings(ss.get('max_iterations', 24), ss.get('tolerance', 1e-5), ss.get('max_cutbacks', 5)):
            issues.append(ValidationIssue(item.level, '求解/结果', item.message))
    if not model.results:
        issues.append(ValidationIssue('info', '求解/结果', '尚未生成结果。'))
    return issues
