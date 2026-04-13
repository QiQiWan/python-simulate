from __future__ import annotations

from dataclasses import dataclass

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.validation_rules import (
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
        issues.append(ValidationIssue('warning', '边界/阶段', '尚未定义全局边界条件。'))
    if not model.stages:
        issues.append(ValidationIssue('warning', '边界/阶段', '尚未定义施工阶段，求解时将使用默认阶段。'))
    else:
        stage_names = [s.name for s in model.stages]
        dup = sorted({n for n in stage_names if stage_names.count(n) > 1})
        if dup:
            issues.append(ValidationIssue('error', '边界/阶段', f'存在重复 Stage 名称: {", ".join(dup[:8])}'))
        for stage in model.stages:
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
            for bc in stage.boundary_conditions:
                for item in validate_bc_inputs(bc.name, bc.kind, bc.target, bc.components, bc.values):
                    issues.append(ValidationIssue(item.level, '边界/阶段', f'{stage.name}/{bc.name}: {item.message}'))
            for ld in stage.loads:
                for item in validate_load_inputs(ld.name, ld.kind, ld.target, ld.values):
                    issues.append(ValidationIssue(item.level, '边界/阶段', f'{stage.name}/{ld.name}: {item.message}'))
    if model.metadata.get('solver_settings'):
        ss = model.metadata['solver_settings']
        for item in validate_solver_settings(ss.get('max_iterations', 24), ss.get('tolerance', 1e-5), ss.get('max_cutbacks', 5)):
            issues.append(ValidationIssue(item.level, '求解/结果', item.message))
    if not model.results:
        issues.append(ValidationIssue('info', '求解/结果', '尚未生成结果。'))
    return issues
