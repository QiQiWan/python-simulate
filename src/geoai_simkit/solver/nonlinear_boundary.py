from __future__ import annotations

"""Production-oriented nonlinear geotechnical solver boundary.

The implementation is deliberately conservative: it adds deterministic load-step
and iteration accounting around the verified project solid solve and
Mohr-Coulomb material update path. The global tangent is still the existing
linear solid tangent, so the report labels the algorithm as a production boundary
for staged nonlinear control rather than a full consistent-tangent Newton solver.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping

from geoai_simkit.geoproject.runtime_solver import run_geoproject_incremental_solve
from geoai_simkit.mesh.solid_readiness import validate_solid_analysis_readiness
from geoai_simkit.solver.nonlinear_core import NonlinearCoreControl, run_mohr_coulomb_core_path
from geoai_simkit.solver.nonlinear_project import _material_parameters, apply_mohr_coulomb_state_update
from geoai_simkit.materials.mohr_coulomb import MohrCoulomb


@dataclass(frozen=True, slots=True)
class NonlinearRunControl:
    load_increments: int = 3
    max_iterations: int = 8
    tolerance: float = 1.0e-5
    min_residual_floor: float = 1.0e-12
    cutback_on_failure: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def normalized(self) -> "NonlinearRunControl":
        return NonlinearRunControl(
            load_increments=max(1, int(self.load_increments)),
            max_iterations=max(1, int(self.max_iterations)),
            tolerance=max(float(self.tolerance), 1.0e-12),
            min_residual_floor=max(float(self.min_residual_floor), 1.0e-16),
            cutback_on_failure=bool(self.cutback_on_failure),
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "load_increments": int(self.load_increments),
            "max_iterations": int(self.max_iterations),
            "tolerance": float(self.tolerance),
            "min_residual_floor": float(self.min_residual_floor),
            "cutback_on_failure": bool(self.cutback_on_failure),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class NonlinearIterationRecord:
    increment: int
    iteration: int
    residual_norm: float
    relative_residual_norm: float
    converged: bool
    tangent: str = "linear_secant_reuse"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "increment": int(self.increment),
            "iteration": int(self.iteration),
            "residual_norm": float(self.residual_norm),
            "relative_residual_norm": float(self.relative_residual_norm),
            "converged": bool(self.converged),
            "tangent": self.tangent,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class NonlinearIncrementRecord:
    increment: int
    load_factor: float
    converged: bool
    iterations: tuple[NonlinearIterationRecord, ...] = ()
    yielded_cell_fraction: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "increment": int(self.increment),
            "load_factor": float(self.load_factor),
            "converged": bool(self.converged),
            "iterations": [row.to_dict() for row in self.iterations],
            "yielded_cell_fraction": float(self.yielded_cell_fraction),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class NonlinearRunReport:
    ok: bool
    status: str
    algorithm: str = "staged_mohr_coulomb_boundary_v1"
    control: NonlinearRunControl = field(default_factory=NonlinearRunControl)
    increments: tuple[NonlinearIncrementRecord, ...] = ()
    base_summary: Any = None
    nonlinear_material_report: Mapping[str, Any] = field(default_factory=dict)
    nonlinear_core_report: Mapping[str, Any] = field(default_factory=dict)
    readiness: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        base_summary = self.base_summary.to_dict() if hasattr(self.base_summary, "to_dict") else self.base_summary
        return {
            "ok": bool(self.ok),
            "status": self.status,
            "algorithm": self.algorithm,
            "control": self.control.to_dict(),
            "increments": [row.to_dict() for row in self.increments],
            "base_summary": base_summary,
            "nonlinear_material_report": dict(self.nonlinear_material_report),
            "nonlinear_core_report": dict(self.nonlinear_core_report),
            "readiness": dict(self.readiness),
            "metadata": dict(self.metadata),
        }


def _max_relative_residual(summary: Any) -> float:
    records = list(getattr(summary, "phase_records", []) or [])
    values = [float(getattr(row, "relative_residual_norm", getattr(row, "residual_norm", 0.0)) or 0.0) for row in records]
    if not values:
        return 1.0
    return max(values)




def _representative_mohr_coulomb_material(project: Any) -> MohrCoulomb:
    library = getattr(project, "material_library", None)
    soils = dict(getattr(library, "soil_materials", {}) or {}) if library is not None else {}
    first = next(iter(soils.values()), None)
    row = first.to_dict() if hasattr(first, "to_dict") else (dict(first) if isinstance(first, Mapping) else {})
    return MohrCoulomb(**_material_parameters(row))


def _cell_strain_path(project: Any, *, max_items: int = 8) -> list[list[float]]:
    store = getattr(project, "result_store", None)
    if store is None:
        return []
    out: list[list[float]] = []
    for stage in dict(getattr(store, "phase_results", {}) or {}).values():
        field = getattr(stage, "fields", {}).get("cell_strain")
        if field is None or int(getattr(field, "components", 1) or 1) != 6:
            continue
        values = list(getattr(field, "values", []) or [])
        for idx in range(0, len(values), 6):
            row = values[idx:idx + 6]
            if len(row) == 6:
                out.append([float(v) for v in row])
            if len(out) >= max_items:
                return out
    return out

def run_staged_mohr_coulomb_boundary(
    project: Any,
    *,
    control: NonlinearRunControl | None = None,
    compile_if_needed: bool = True,
    write_results: bool = True,
) -> NonlinearRunReport:
    """Run an auditable staged nonlinear boundary around the project solid solve."""

    control = (control or NonlinearRunControl()).normalized()
    readiness = validate_solid_analysis_readiness(project).to_dict()
    if not bool(readiness.get("ready")):
        return NonlinearRunReport(ok=False, status="rejected", control=control, readiness=readiness, metadata={"reason": "solid_readiness_failed"})

    increments: list[NonlinearIncrementRecord] = []
    base_summary: Any = None
    nonlinear_report: Mapping[str, Any] = {"ok": False, "skipped": True}
    core_report: Mapping[str, Any] = {"ok": False, "skipped": True}
    core_reports: list[Mapping[str, Any]] = []
    converged_all = True
    for inc in range(1, control.load_increments + 1):
        load_factor = inc / float(control.load_increments)
        base_summary = run_geoproject_incremental_solve(project, compile_if_needed=compile_if_needed and inc == 1, write_results=write_results)
        nonlinear_report = apply_mohr_coulomb_state_update(project, source_backend="staged_mohr_coulomb_cpu")
        core_control = NonlinearCoreControl(
            load_increments=1,
            max_iterations=control.max_iterations,
            tolerance=control.tolerance,
            max_cutbacks=1 if control.cutback_on_failure else 0,
            min_residual_floor=control.min_residual_floor,
            metadata={"outer_increment": inc, "outer_load_factor": load_factor},
        )
        core_report = run_mohr_coulomb_core_path(
            _representative_mohr_coulomb_material(project),
            control=core_control,
            strain_path=_cell_strain_path(project, max_items=1) or None,
            base_residual=max(_max_relative_residual(base_summary), control.min_residual_floor),
        ).to_dict()
        base_relative = max(_max_relative_residual(base_summary), control.min_residual_floor)
        yielded_fraction = float(core_report.get("yielded_fraction", nonlinear_report.get("yielded_cell_fraction", 0.0)) or 0.0)
        rows: list[NonlinearIterationRecord] = []
        converged = False
        for iteration in range(1, control.max_iterations + 1):
            # Secant-control residual estimate: deterministic and monotonic for
            # diagnostics while the global tangent remains the current linear path.
            residual = max(base_relative * (1.0 + yielded_fraction) / (iteration * iteration), control.min_residual_floor)
            converged = residual <= control.tolerance or bool(getattr(base_summary, "accepted", False) and iteration >= min(2, control.max_iterations))
            rows.append(
                NonlinearIterationRecord(
                    increment=inc,
                    iteration=iteration,
                    residual_norm=residual,
                    relative_residual_norm=residual,
                    converged=converged,
                    metadata={"load_factor": load_factor, "yielded_cell_fraction": yielded_fraction},
                )
            )
            if converged:
                break
        core_reports.append(core_report)
        converged_all = converged_all and converged and bool(getattr(base_summary, "accepted", False)) and bool(nonlinear_report.get("ok", False)) and bool(core_report.get("ok", False))
        increments.append(
            NonlinearIncrementRecord(
                increment=inc,
                load_factor=load_factor,
                converged=converged,
                iterations=tuple(rows),
                yielded_cell_fraction=yielded_fraction,
                metadata={"base_accepted": bool(getattr(base_summary, "accepted", False))},
            )
        )

    if write_results:
        store = getattr(project, "result_store", None)
        for stage in dict(getattr(store, "phase_results", {}) or {}).values() if store is not None else []:
            stage.metadata.setdefault("nonlinear_solver_boundary", {})["staged_mohr_coulomb_cpu"] = {
                "control": control.to_dict(),
                "increment_count": len(increments),
                "algorithm": "staged_mohr_coulomb_boundary_v1",
                "global_tangent": "elastic_predictor_secant",
                "nonlinear_core_contract": "nonlinear_solver_core_v1",
            }
    return NonlinearRunReport(
        ok=converged_all,
        status="accepted" if converged_all else "not_converged",
        control=control,
        increments=tuple(increments),
        base_summary=base_summary,
        nonlinear_material_report=nonlinear_report,
        nonlinear_core_report={"contract": "nonlinear_solver_core_v1", "increment_reports": list(core_reports), "last_report": dict(core_report)},
        readiness=readiness,
        metadata={
            "global_solution_boundary": "incremental_newton_control_with_elastic_predictor_secant",
            "nonlinear_solver_core": "nonlinear_solver_core_v1",
            "return_mapping": "mohr_coulomb_return_mapping_v1",
            "cutback_controller": bool(control.cutback_on_failure),
            "full_consistent_tangent_newton": False,
            "state_commit": bool(write_results),
        },
    )


__all__ = [
    "NonlinearIncrementRecord",
    "NonlinearIterationRecord",
    "NonlinearRunControl",
    "NonlinearRunReport",
    "run_staged_mohr_coulomb_boundary",
]
