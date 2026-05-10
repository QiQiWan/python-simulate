from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Any
import re


@dataclass(slots=True)
class ParameterIssue:
    level: str
    field: str
    message: str


def normalize_region_name(name: object) -> str:
    text = str(name or "").strip().lower()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^a-z0-9_\-:.]+", "_", text)
    return text.strip("_")


def _issue(level: str, field: str, message: str) -> ParameterIssue:
    return ParameterIssue(level=level, field=field, message=message)


def validate_stage_inputs(stage_name: str, steps: int, initial_increment: float, max_iterations: int, activate_regions: Iterable[str] = (), deactivate_regions: Iterable[str] = (), *, existing_names: Iterable[str] = (), current_name: str | None = None) -> list[ParameterIssue]:
    issues: list[ParameterIssue] = []
    name = str(stage_name or "").strip()
    if not name:
        issues.append(_issue("error", "stage_name", "Stage name is required."))
    names = [str(n) for n in existing_names]
    if name and name != current_name and name in names:
        issues.append(_issue("error", "stage_name", "Stage name already exists."))
    if int(steps) <= 0:
        issues.append(_issue("error", "stage_steps", "Stage steps must be positive."))
    if not (0.0 < float(initial_increment) <= 1.0):
        issues.append(_issue("error", "stage_initial_increment", "Initial increment must be in (0, 1]."))
    if int(max_iterations) <= 0:
        issues.append(_issue("error", "stage_max_iterations", "Maximum iterations must be positive."))
    if set(map(normalize_region_name, activate_regions)) & set(map(normalize_region_name, deactivate_regions)):
        issues.append(_issue("warning", "stage_regions", "Some regions are both activated and deactivated."))
    return issues


def validate_bc_inputs(name: str, kind: str, target: str, components: Iterable[str] = (), values: Iterable[float] = ()) -> list[ParameterIssue]:
    issues: list[ParameterIssue] = []
    if not str(name or "").strip():
        issues.append(_issue("error", "bc_name", "Boundary condition name is required."))
    if not str(kind or "").strip():
        issues.append(_issue("error", "bc_kind", "Boundary condition kind is required."))
    if not str(target or "").strip():
        issues.append(_issue("warning", "bc_target", "Boundary target is empty."))
    comps = list(components or [])
    vals = list(values or [])
    if comps and vals and len(comps) != len(vals):
        issues.append(_issue("error", "bc_values", "Component/value counts do not match."))
    return issues


def validate_load_inputs(name: str, kind: str, target: str, values: Iterable[float] = ()) -> list[ParameterIssue]:
    issues: list[ParameterIssue] = []
    if not str(name or "").strip():
        issues.append(_issue("error", "load_name", "Load name is required."))
    if not str(kind or "").strip():
        issues.append(_issue("error", "load_kind", "Load kind is required."))
    if not str(target or "").strip():
        issues.append(_issue("warning", "load_target", "Load target is empty."))
    vals = list(values or [])
    if vals and not all(isinstance(v, (int, float)) for v in vals):
        issues.append(_issue("error", "load_values", "Load values must be numeric."))
    return issues


def validate_solver_settings(settings: Any = None, **kwargs: Any) -> list[ParameterIssue]:
    issues: list[ParameterIssue] = []
    data = dict(kwargs)
    if settings is not None:
        data.update(getattr(settings, "__dict__", {}))
    tol = data.get("tolerance", data.get("tol", None))
    if tol is not None and float(tol) <= 0:
        issues.append(_issue("error", "solver_tolerance", "Solver tolerance must be positive."))
    max_iter = data.get("max_iterations", data.get("max_iter", None))
    if max_iter is not None and int(max_iter) <= 0:
        issues.append(_issue("error", "solver_max_iterations", "Maximum iterations must be positive."))
    return issues


def validate_material_parameters(name: str = "", model_type: str = "", params: Mapping[str, Any] | None = None) -> list[ParameterIssue]:
    issues: list[ParameterIssue] = []
    if not str(name or "").strip():
        issues.append(_issue("error", "name", "Material name is required."))
    if not str(model_type or "").strip():
        issues.append(_issue("error", "model_type", "Material model type is required."))
    for key, value in dict(params or {}).items():
        try:
            if isinstance(value, (int, float)) and key.lower() in {"e", "young", "density", "rho", "gamma", "cohesion", "c"} and float(value) < 0:
                issues.append(_issue("error", str(key), f"{key} must be non-negative."))
        except Exception:
            issues.append(_issue("warning", str(key), f"{key} could not be validated."))
    return issues


def validate_geometry_params(*args: Any, **kwargs: Any) -> list[ParameterIssue]:
    return []


def validate_ifc_options(*args: Any, **kwargs: Any) -> list[ParameterIssue]:
    return []
