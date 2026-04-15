from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(slots=True)
class ParameterIssue:
    level: str
    field: str
    message: str


def _issue(level: str, field: str, message: str) -> ParameterIssue:
    return ParameterIssue(level=level, field=field, message=message)


def _as_float(value) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _as_int(value) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _in_range(value: float | None, low: float | None = None, high: float | None = None, inclusive_high: bool = True) -> bool:
    if value is None:
        return False
    if low is not None and value < low:
        return False
    if high is not None:
        if inclusive_high and value > high:
            return False
        if not inclusive_high and value >= high:
            return False
    return True



SUPPORTED_BC_TARGETS = {
    'all',
    'xmin', 'xmax', 'ymin', 'ymax', 'zmin', 'zmax',
    'left', 'right', 'front', 'back', 'bottom', 'top',
}
SUPPORTED_LOAD_KINDS = {'nodal_force', 'point_force', 'gravity_scale', 'pressure'}


def normalize_boundary_target(target: str) -> str:
    mapping = {
        'left': 'xmin',
        'right': 'xmax',
        'front': 'ymin',
        'back': 'ymax',
        'bottom': 'zmin',
        'top': 'zmax',
    }
    key = str(target or '').strip().lower()
    return mapping.get(key, key)


def normalize_load_kind(kind: str) -> str:
    key = str(kind or '').strip().lower()
    if key == 'nodal_force':
        return 'point_force'
    return key

def validate_geometry_params(params: Mapping[str, object]) -> list[ParameterIssue]:
    issues: list[ParameterIssue] = []
    req_positive = ["length", "width", "depth", "soil_depth", "wall_thickness"]
    for key in req_positive:
        value = _as_float(params.get(key))
        if value is None:
            issues.append(_issue("error", key, f"{key} 必须是数字。"))
        elif value <= 0:
            issues.append(_issue("error", key, f"{key} 必须大于 0。"))
    for key in ["nx", "ny", "nz"]:
        value = _as_int(params.get(key))
        if value is None:
            issues.append(_issue("error", key, f"{key} 必须是整数。"))
        elif value < 2:
            issues.append(_issue("error", key, f"{key} 必须至少为 2。"))
    length = _as_float(params.get("length"))
    width = _as_float(params.get("width"))
    depth = _as_float(params.get("depth"))
    soil_depth = _as_float(params.get("soil_depth"))
    wall_t = _as_float(params.get("wall_thickness"))
    if soil_depth is not None and depth is not None and soil_depth <= depth:
        issues.append(_issue("error", "soil_depth", "土层总深度必须大于基坑深度。"))
    if wall_t is not None and length is not None and width is not None and wall_t * 2 >= min(length, width):
        issues.append(_issue("error", "wall_thickness", "围护厚度过大，已超过坑体尺度的一半。"))
    if length is not None and width is not None and abs(length - width) / max(length, width) > 0.95:
        issues.append(_issue("warning", "width", "长宽比极端，建议检查网格划分是否合理。"))
    return issues


def validate_ifc_options(include_entities: str | Sequence[str], region_strategy: str, file_path: str | None = None) -> list[ParameterIssue]:
    issues: list[ParameterIssue] = []
    if isinstance(include_entities, str):
        entities = [s.strip() for s in include_entities.split(",") if s.strip()]
    else:
        entities = [str(s).strip() for s in include_entities if str(s).strip()]
    if not entities:
        issues.append(_issue("warning", "include_entities", "未指定实体类型，将导入所有支持的 IFC 实体，可能较慢。"))
    else:
        bad = [e for e in entities if not e.startswith("Ifc")]
        if bad:
            issues.append(_issue("error", "include_entities", f"以下实体名不符合 IFC 命名: {', '.join(bad[:5])}"))
    if region_strategy not in {"type_and_name", "name", "ifc_type", "storey"}:
        issues.append(_issue("error", "region_strategy", "Region strategy 不受支持。"))
    if file_path is not None and not str(file_path).lower().endswith(".ifc"):
        issues.append(_issue("warning", "file", "当前文件扩展名不是 .ifc。"))
    return issues


def validate_material_parameters(model_type: str, params: Mapping[str, object], name: str | None = None) -> list[ParameterIssue]:
    issues: list[ParameterIssue] = []
    if name is not None and not str(name).strip():
        issues.append(_issue("error", "name", "材料名称不能为空。"))
    p = {k: _as_float(v) for k, v in params.items()}
    def pos(field: str, label: str | None = None):
        value = p.get(field)
        if value is None:
            issues.append(_issue("error", field, f"{label or field} 必须是数字。"))
        elif value <= 0:
            issues.append(_issue("error", field, f"{label or field} 必须大于 0。"))
    if model_type == "linear_elastic":
        pos("E", "E")
        pos("rho", "rho")
        nu = p.get("nu")
        if not _in_range(nu, 0.0, 0.5, inclusive_high=False):
            issues.append(_issue("error", "nu", "泊松比 nu 必须满足 0 <= nu < 0.5。"))
    elif model_type == "mohr_coulomb":
        for field in ["E", "rho"]:
            pos(field)
        for field in ["cohesion", "tensile_strength"]:
            value = p.get(field)
            if value is None:
                issues.append(_issue("error", field, f"{field} 必须是数字。"))
            elif value < 0:
                issues.append(_issue("error", field, f"{field} 不能为负。"))
        nu = p.get("nu")
        phi = p.get("friction_deg")
        psi = p.get("dilation_deg")
        if not _in_range(nu, 0.0, 0.5, inclusive_high=False):
            issues.append(_issue("error", "nu", "泊松比 nu 必须满足 0 <= nu < 0.5。"))
        if not _in_range(phi, 0.0, 89.9, inclusive_high=False):
            issues.append(_issue("error", "friction_deg", "摩擦角 friction_deg 必须在 [0, 89.9) 内。"))
        if psi is None:
            issues.append(_issue("error", "dilation_deg", "膨胀角 dilation_deg 必须是数字。"))
        elif psi < 0:
            issues.append(_issue("warning", "dilation_deg", "膨胀角为负时通常需要额外核对。"))
        if phi is not None and psi is not None and psi > phi:
            issues.append(_issue("error", "dilation_deg", "膨胀角不能大于摩擦角。"))
    elif model_type in {"hss", "hs_small"}:
        for field in ["E50ref", "Eoedref", "Eurref", "pref", "rho", "G0ref", "gamma07"]:
            pos(field)
        nu_ur = p.get("nu_ur")
        phi = p.get("phi_deg")
        psi = p.get("psi_deg")
        m = p.get("m")
        rf = p.get("Rf")
        c = p.get("c")
        if not _in_range(nu_ur, 0.0, 0.5, inclusive_high=False):
            issues.append(_issue("error", "nu_ur", "卸载泊松比 nu_ur 必须满足 0 <= nu_ur < 0.5。"))
        if not _in_range(m, 0.0, 2.0):
            issues.append(_issue("error", "m", "应力依赖指数 m 建议在 [0, 2] 内。"))
        if not _in_range(rf, 0.0, 1.0, inclusive_high=False):
            issues.append(_issue("error", "Rf", "Rf 必须满足 0 < Rf < 1。"))
        if c is None:
            issues.append(_issue("error", "c", "黏聚力 c 必须是数字。"))
        elif c < 0:
            issues.append(_issue("error", "c", "黏聚力 c 不能为负。"))
        if not _in_range(phi, 0.0, 89.9, inclusive_high=False):
            issues.append(_issue("error", "phi_deg", "摩擦角 phi_deg 必须在 [0, 89.9) 内。"))
        if psi is None:
            issues.append(_issue("error", "psi_deg", "膨胀角 psi_deg 必须是数字。"))
        elif psi < 0:
            issues.append(_issue("warning", "psi_deg", "膨胀角为负时通常需要额外核对。"))
        if phi is not None and psi is not None and psi > phi:
            issues.append(_issue("error", "psi_deg", "膨胀角不能大于摩擦角。"))
        if p.get("G0ref") is not None and p.get("Eurref") is not None and p["G0ref"] < p["Eurref"] * 0.2:
            issues.append(_issue("warning", "G0ref", "G0ref 偏低，HSsmall 小应变刚度可能不合理。"))
        if p.get("gamma07") is not None and not _in_range(p["gamma07"], 1e-8, 1.0):
            issues.append(_issue("error", "gamma07", "gamma07 应位于 (1e-8, 1] 范围内。"))
    else:
        issues.append(_issue("warning", "model_type", f"未找到 {model_type} 的专用校验规则，将按通用数值参数处理。"))
        for key, value in p.items():
            if value is None:
                issues.append(_issue("error", key, f"{key} 必须是数字。"))
    return issues


def validate_stage_inputs(name: str, steps: object, initial_increment: object, max_iterations: object, activate_regions: Sequence[str], deactivate_regions: Sequence[str], existing_names: Iterable[str] = (), current_name: str | None = None) -> list[ParameterIssue]:
    issues: list[ParameterIssue] = []
    if not str(name).strip():
        issues.append(_issue("error", "stage_name", "Stage 名称不能为空。"))
    existing = {str(n) for n in existing_names if str(n)}
    if str(name).strip() and str(name).strip() in existing and str(name).strip() != str(current_name or ""):
        issues.append(_issue("error", "stage_name", "Stage 名称重复。"))
    steps_i = _as_int(steps)
    if steps_i is None or steps_i <= 0:
        issues.append(_issue("error", "stage_steps", "步数必须是正整数。"))
    inc = _as_float(initial_increment)
    if not _in_range(inc, 1e-6, 1.0):
        issues.append(_issue("error", "stage_initial_increment", "初始增量必须在 (0, 1] 范围内。"))
    max_it = _as_int(max_iterations)
    if max_it is None or max_it <= 0:
        issues.append(_issue("error", "stage_max_iterations", "最大迭代次数必须是正整数。"))
    overlap = sorted(set(activate_regions) & set(deactivate_regions))
    if overlap:
        issues.append(_issue("error", "stage_regions", f"同一 Stage 中不能同时激活和失活同一区域: {', '.join(overlap[:6])}"))
    if not activate_regions and not deactivate_regions:
        issues.append(_issue("warning", "stage_regions", "当前 Stage 未定义任何激活/失活区域。"))
    return issues


def validate_bc_inputs(name: str, kind: str, target: str, components: Sequence[int], values: Sequence[float]) -> list[ParameterIssue]:
    issues: list[ParameterIssue] = []
    if not str(name).strip():
        issues.append(_issue("error", "bc_name", "边界条件名称不能为空。"))
    if kind not in {"displacement", "roller", "symmetry"}:
        issues.append(_issue("error", "bc_kind", "边界条件类型不受支持。"))
    normalized_target = normalize_boundary_target(target)
    if not str(target).strip():
        issues.append(_issue("error", "bc_target", "边界条件目标不能为空。"))
    elif normalized_target not in SUPPORTED_BC_TARGETS and normalized_target != 'all':
        issues.append(_issue("error", "bc_target", "边界条件目标不受支持。可用目标包括 xmin/xmax/ymin/ymax/zmin/zmax 及其 left/right/front/back/bottom/top 别名。"))
    if not components:
        issues.append(_issue("error", "bc_components", "至少需要一个分量。"))
    if any((c < 0 or c > 5) for c in components):
        issues.append(_issue("error", "bc_components", "分量索引必须位于 0..5。"))
    if len(set(components)) != len(tuple(components)):
        issues.append(_issue("error", "bc_components", "分量索引不能重复。"))
    if len(values) not in {1, len(components)}:
        issues.append(_issue("error", "bc_values", "数值个数必须为 1 或与分量数一致。"))
    if kind in {"roller", "symmetry"} and any(abs(v) > 1e-12 for v in values):
        issues.append(_issue("warning", "bc_values", f"{kind} 通常不需要非零位移值。"))
    return issues


def validate_load_inputs(name: str, kind: str, target: str, values: Sequence[float]) -> list[ParameterIssue]:
    issues: list[ParameterIssue] = []
    if not str(name).strip():
        issues.append(_issue("error", "load_name", "荷载名称不能为空。"))
    normalized_kind = normalize_load_kind(kind)
    if normalized_kind not in SUPPORTED_LOAD_KINDS:
        issues.append(_issue("error", "load_kind", "荷载类型不受支持。"))
    if not str(target).strip():
        issues.append(_issue("error", "load_target", "荷载目标不能为空。"))
    if not values:
        issues.append(_issue("error", "load_values", "至少需要一个荷载值。"))
        return issues
    if normalized_kind == "gravity_scale":
        if len(values) != 1:
            issues.append(_issue("error", "load_values", "gravity_scale 只接受 1 个值。"))
        elif values[0] <= 0:
            issues.append(_issue("error", "load_values", "gravity_scale 必须大于 0。"))
    elif normalized_kind == "pressure":
        if len(values) not in {1, 3}:
            issues.append(_issue("error", "load_values", "pressure 建议输入 1 个标量或 3 个分量。"))
    elif normalized_kind == "point_force":
        if len(values) not in {1, 3}:
            issues.append(_issue("error", "load_values", "nodal_force / point_force 建议输入 1 个标量或 3 个分量。"))
    return issues


def validate_solver_settings(max_iterations: object, tolerance: object, max_cutbacks: object) -> list[ParameterIssue]:
    issues: list[ParameterIssue] = []
    mi = _as_int(max_iterations)
    tol = _as_float(tolerance)
    mc = _as_int(max_cutbacks)
    if mi is None or mi <= 0:
        issues.append(_issue("error", "solver_max_iterations", "Max iterations 必须是正整数。"))
    if tol is None:
        issues.append(_issue("error", "solver_tolerance", "Tolerance 必须是数字。"))
    elif not (0.0 < tol < 1.0):
        issues.append(_issue("error", "solver_tolerance", "Tolerance 应位于 (0, 1) 范围内。"))
    if mc is None or mc < 0:
        issues.append(_issue("error", "solver_max_cutbacks", "Max cutbacks 不能为负。"))
    return issues
