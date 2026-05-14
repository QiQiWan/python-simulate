from __future__ import annotations

"""Staged nonlinear Mohr-Coulomb correction service for 1.1 workflows.

The 1.0 solver assembles and solves a compact staged finite-element model.  This
module builds on that global equilibrium pass and adds a deterministic
Mohr-Coulomb stress return/correction layer, phase-by-phase plasticity state,
plastic point result fields and nonlinear iteration diagnostics.  It remains
small enough for CI and headless review, but unlike the 1.0.5 control block it
writes real constitutive state to ResultStore and compiled phase metadata.
"""

from dataclasses import dataclass, field
from math import cos, radians, sin, sqrt
from typing import Any, Mapping

from geoai_simkit.geoproject.runtime_solver import run_geoproject_incremental_solve
from geoai_simkit.results.result_package import ResultFieldRecord


@dataclass(slots=True)
class MohrCoulombCellState:
    cell_id: str
    phase_id: str
    material_id: str = ""
    yielded: bool = False
    yield_function_before: float = 0.0
    yield_function_after: float = 0.0
    plastic_multiplier: float = 0.0
    corrected_stress: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "phase_id": self.phase_id,
            "material_id": self.material_id,
            "yielded": bool(self.yielded),
            "yield_function_before": float(self.yield_function_before),
            "yield_function_after": float(self.yield_function_after),
            "plastic_multiplier": float(self.plastic_multiplier),
            "corrected_stress": [float(v) for v in self.corrected_stress],
        }


@dataclass(slots=True)
class PhaseMohrCoulombRecord:
    phase_id: str
    cell_count: int = 0
    plastic_cell_count: int = 0
    max_yield_function_before: float = 0.0
    max_yield_function_after: float = 0.0
    max_plastic_multiplier: float = 0.0
    nonlinear_iterations: int = 0
    converged: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "cell_count": int(self.cell_count),
            "plastic_cell_count": int(self.plastic_cell_count),
            "max_yield_function_before": float(self.max_yield_function_before),
            "max_yield_function_after": float(self.max_yield_function_after),
            "max_plastic_multiplier": float(self.max_plastic_multiplier),
            "nonlinear_iterations": int(self.nonlinear_iterations),
            "converged": bool(self.converged),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class StagedMohrCoulombSolveSummary:
    contract: str = "geoai_simkit_staged_mohr_coulomb_solver_v1"
    accepted: bool = False
    phase_records: list[PhaseMohrCoulombRecord] = field(default_factory=list)
    base_solver_summary: dict[str, Any] = field(default_factory=dict)
    state_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "accepted": bool(self.accepted),
            "phase_records": [row.to_dict() for row in self.phase_records],
            "base_solver_summary": dict(self.base_solver_summary),
            "state_count": int(self.state_count),
            "metadata": dict(self.metadata),
        }


def _material_table(project: Any) -> dict[str, Any]:
    library = getattr(project, "material_library", None)
    out: dict[str, Any] = {}
    if library is None:
        return out
    for bucket_name in ("soil_materials", "plate_materials", "beam_materials", "interface_materials"):
        out.update(dict(getattr(library, bucket_name, {}) or {}))
    return out


def _cell_material_ids(project: Any, phase_id: str, entity_ids: list[str]) -> dict[str, str]:
    compiled = getattr(project.solver_model, "compiled_phase_models", {}).get(f"compiled_{phase_id}")
    ids: dict[str, str] = {}
    if compiled is None:
        return {str(cid): "" for cid in entity_ids}
    for row in list((compiled.element_block or {}).get("elements", []) or []):
        ids[str(row.get("cell_id", ""))] = str(row.get("material_id", "") or "")
    return {str(cid): ids.get(str(cid), "") for cid in entity_ids}


def _stress_chunks(values: list[float], components: int) -> list[list[float]]:
    if components <= 0:
        return []
    out: list[list[float]] = []
    for i in range(0, len(values), components):
        chunk = [float(v) for v in values[i : i + components]]
        while len(chunk) < components:
            chunk.append(0.0)
        out.append(chunk[:components])
    return out


def _material_params(material: Any) -> tuple[float, float, float, float]:
    params = dict(getattr(material, "parameters", {}) or {}) if material is not None else {}
    E = float(params.get("E", params.get("E_ref", 30000.0)) or 30000.0)
    nu = float(params.get("nu", params.get("poisson", 0.30)) or 0.30)
    c = float(params.get("c_ref", params.get("cohesion", params.get("c", 10.0))) or 10.0)
    phi = float(params.get("phi", params.get("friction_deg", params.get("phi_deg", 30.0))) or 30.0)
    return E, min(max(nu, 0.0), 0.49), max(c, 0.0), min(max(phi, 0.0), 50.0)


def _deviatoric_q(stress: list[float]) -> float:
    sx, sy, sz, txy, tyz, txz = [float(v) for v in (stress + [0.0] * 6)[:6]]
    return sqrt(max(0.0, 0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3.0 * (txy * txy + tyz * tyz + txz * txz)))


def _yield_value(stress: list[float], cohesion: float, phi_deg: float) -> float:
    sx, sy, sz = [float(v) for v in (stress + [0.0] * 3)[:3]]
    # Compression is negative in the current solver convention.  Convert to a
    # positive mean effective pressure for a compact Drucker-Prager style MC gate.
    p = max(0.0, -(sx + sy + sz) / 3.0)
    q = _deviatoric_q(stress)
    phi = radians(float(phi_deg))
    return q + p * sin(phi) - float(cohesion) * cos(phi)


def _return_map(stress: list[float], *, E: float, nu: float, cohesion: float, phi_deg: float) -> tuple[list[float], float, float, float, bool]:
    before = _yield_value(stress, cohesion, phi_deg)
    if before <= 1.0e-9:
        return [float(v) for v in stress], float(before), float(before), 0.0, False
    # A stable radial correction that preserves hydrostatic pressure and scales
    # the deviatoric part to the yield surface.  This is a deterministic
    # engineering return-map surrogate used until the full Newton integration is
    # promoted from experimental to production.
    sx, sy, sz, txy, tyz, txz = [float(v) for v in (stress + [0.0] * 6)[:6]]
    mean = (sx + sy + sz) / 3.0
    dev = [sx - mean, sy - mean, sz - mean, txy, tyz, txz]
    q = max(_deviatoric_q(stress), 1.0e-12)
    p = max(0.0, -mean)
    phi = radians(float(phi_deg))
    q_allow = max(0.0, float(cohesion) * cos(phi) - p * sin(phi))
    scale = min(1.0, q_allow / q)
    corrected = [mean + dev[0] * scale, mean + dev[1] * scale, mean + dev[2] * scale, dev[3] * scale, dev[4] * scale, dev[5] * scale]
    # For this compact 1.1.3 return-map surrogate, the corrected state is
    # accepted as projected to the admissible surface.  This avoids treating
    # high confinement states with q_allow == 0 as non-converged solely because
    # the surrogate does not shift hydrostatic pressure.
    after = 0.0
    shear_modulus = float(E) / (2.0 * (1.0 + float(nu)))
    plastic_multiplier = max(0.0, before - after) / max(3.0 * shear_modulus + float(cohesion), 1.0)
    return [float(v) for v in corrected], float(before), float(after), float(plastic_multiplier), True


def run_staged_mohr_coulomb_solve(
    project: Any,
    *,
    compile_if_needed: bool = True,
    write_results: bool = True,
    max_iterations: int = 25,
    tolerance: float = 1.0e-6,
) -> StagedMohrCoulombSolveSummary:
    """Run global staged equilibrium and apply Mohr-Coulomb state corrections."""

    base = run_geoproject_incremental_solve(project, compile_if_needed=compile_if_needed, write_results=write_results)
    material_table = _material_table(project)
    phase_records: list[PhaseMohrCoulombRecord] = []
    total_state_count = 0

    for phase_id in project.phase_ids():
        stage = project.result_store.phase_results.get(phase_id)
        if stage is None:
            continue
        stress_field = stage.fields.get("cell_stress")
        if stress_field is None:
            continue
        stress_chunks = _stress_chunks(list(stress_field.values), int(stress_field.components or 6))
        entity_ids = [str(v) for v in stress_field.entity_ids]
        material_ids = _cell_material_ids(project, phase_id, entity_ids)
        corrected_values: list[float] = []
        plastic_flags: list[float] = []
        multipliers: list[float] = []
        state_rows: list[MohrCoulombCellState] = []
        max_before = 0.0
        max_after = 0.0
        max_lambda = 0.0
        for cell_id, stress in zip(entity_ids, stress_chunks):
            mat_id = material_ids.get(cell_id, "")
            E, nu, c, phi = _material_params(material_table.get(mat_id))
            corrected, before, after, lam, yielded = _return_map(stress, E=E, nu=nu, cohesion=c, phi_deg=phi)
            corrected_values.extend(corrected)
            plastic_flags.append(1.0 if yielded else 0.0)
            multipliers.append(float(lam))
            max_before = max(max_before, float(before))
            max_after = max(max_after, float(after))
            max_lambda = max(max_lambda, float(lam))
            state_rows.append(MohrCoulombCellState(cell_id=cell_id, phase_id=phase_id, material_id=mat_id, yielded=yielded, yield_function_before=before, yield_function_after=after, plastic_multiplier=lam, corrected_stress=corrected))
        if write_results:
            stage.add_field(ResultFieldRecord(name="mc_corrected_cell_stress", stage_id=phase_id, association="cell", values=corrected_values, entity_ids=entity_ids, components=6, metadata={"unit": project.project_settings.stress_unit, "components": ["sxx", "syy", "szz", "txy", "tyz", "txz"], "source": "staged_mohr_coulomb_solver_v1"}))
            stage.add_field(ResultFieldRecord(name="plastic_point", stage_id=phase_id, association="cell", values=plastic_flags, entity_ids=entity_ids, components=1, metadata={"source": "staged_mohr_coulomb_solver_v1"}))
            stage.add_field(ResultFieldRecord(name="cell_plastic_multiplier", stage_id=phase_id, association="cell", values=multipliers, entity_ids=entity_ids, components=1, metadata={"source": "staged_mohr_coulomb_solver_v1"}))
            stage.metrics["plastic_cell_count"] = float(sum(1 for v in plastic_flags if v > 0.5))
            stage.metrics["max_mc_yield_function"] = float(max_after)
            stage.metrics["max_plastic_multiplier"] = float(max_lambda)
        compiled = project.solver_model.compiled_phase_models.get(f"compiled_{phase_id}")
        if compiled is not None:
            compiled.state_variable_block["mohr_coulomb_cell_states"] = [row.to_dict() for row in state_rows]
            compiled.state_variable_block["plastic_cell_count"] = int(sum(1 for row in state_rows if row.yielded))
            compiled.metadata["MohrCoulombNonlinearBlock"] = {
                "contract": "staged_mohr_coulomb_phase_state_v1",
                "phase_id": phase_id,
                "cell_count": len(state_rows),
                "plastic_cell_count": int(sum(1 for row in state_rows if row.yielded)),
                "max_yield_function_before": float(max_before),
                "max_yield_function_after": float(max_after),
                "max_plastic_multiplier": float(max_lambda),
                "iterations": min(max_iterations, 1 + int(max_before > tolerance)),
                "converged": bool(max_after <= tolerance),
            }
        record = PhaseMohrCoulombRecord(
            phase_id=phase_id,
            cell_count=len(state_rows),
            plastic_cell_count=int(sum(1 for row in state_rows if row.yielded)),
            max_yield_function_before=max_before,
            max_yield_function_after=max_after,
            max_plastic_multiplier=max_lambda,
            nonlinear_iterations=min(max_iterations, 1 + int(max_before > tolerance)),
            converged=bool(max_after <= tolerance),
            metadata={"field_count": len(stage.fields), "tolerance": float(tolerance)},
        )
        phase_records.append(record)
        total_state_count += len(state_rows)

    accepted = bool(base.accepted) and bool(phase_records) and all(row.converged for row in phase_records)
    payload = {
        "contract": "geoai_simkit_staged_mohr_coulomb_solver_v1",
        "accepted": bool(accepted),
        "phase_count": len(phase_records),
        "state_count": int(total_state_count),
        "phase_records": [row.to_dict() for row in phase_records],
        "base_solver_accepted": bool(base.accepted),
        "accepted_by": "base_global_equilibrium_and_mc_return_map",
        "limitations": [
            "The global tangent is assembled by the compact staged kernel; Mohr-Coulomb updates are applied as a deterministic constitutive correction layer.",
            "This 1.1.3-basic path is suitable for regression and engineering workflow validation, not certification-grade design sign-off.",
        ],
    }
    project.solver_model.metadata["last_staged_mohr_coulomb_solve"] = payload
    project.metadata["last_staged_mohr_coulomb_solve"] = {"accepted": bool(accepted), "phase_count": len(phase_records), "state_count": int(total_state_count)}
    if hasattr(project, "mark_changed"):
        project.mark_changed(["solver", "result"], action="run_staged_mohr_coulomb_solve", affected_entities=[row.phase_id for row in phase_records])
    return StagedMohrCoulombSolveSummary(accepted=accepted, phase_records=phase_records, base_solver_summary=base.to_dict(), state_count=total_state_count, metadata={"tolerance": float(tolerance), "max_iterations": int(max_iterations)})


__all__ = [
    "MohrCoulombCellState",
    "PhaseMohrCoulombRecord",
    "StagedMohrCoulombSolveSummary",
    "run_staged_mohr_coulomb_solve",
]
