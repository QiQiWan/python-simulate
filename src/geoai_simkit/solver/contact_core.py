from __future__ import annotations

"""Coulomb penalty contact/interface solver core v1.

This module implements a dependency-light active-set contact boundary suitable
for Project/ResultStore integration.  It is deliberately conservative: the
mechanical coupling is exposed as interface tractions and state fields, while
full global contact stiffness assembly remains behind the same contract for a
future solver-core deepening.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping

from geoai_simkit.contracts.contact import (
    ContactIterationReport,
    ContactMaterialParameters,
    ContactPairState,
    ContactSolverReport,
    InterfaceKinematics,
)


def _float_pair(values: Any, *, default: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    try:
        seq = list(values or [])
        if len(seq) >= 2:
            return (float(seq[0]), float(seq[1]))
        if len(seq) == 1:
            return (float(seq[0]), 0.0)
    except Exception:
        pass
    return default


def _float_triplet(values: Any, *, default: tuple[float, float, float] = (0.0, 0.0, 1.0)) -> tuple[float, float, float]:
    try:
        seq = list(values or [])
        if len(seq) >= 3:
            return (float(seq[0]), float(seq[1]), float(seq[2]))
    except Exception:
        pass
    return default


def contact_material_from_record(material_id: str, record: Any | None = None) -> ContactMaterialParameters:
    params = dict(getattr(record, "parameters", {}) or {}) if record is not None else {}
    if isinstance(record, Mapping):
        params = dict(record.get("parameters", record) or {})
    return ContactMaterialParameters(
        material_id=str(material_id or getattr(record, "id", "") or "interface_material"),
        kn=float(params.get("kn", params.get("normal_stiffness", 1.0e6)) or 1.0e6),
        ks=float(params.get("ks", params.get("shear_stiffness", 5.0e5)) or 5.0e5),
        friction_deg=float(params.get("friction_deg", params.get("phi", params.get("friction_angle", 25.0))) or 25.0),
        cohesion=float(params.get("cohesion", params.get("c", 0.0)) or 0.0),
        tensile_cutoff=float(params.get("tensile_cutoff", params.get("tension_cutoff", 0.0)) or 0.0),
        metadata={"source": "interface_material_record"},
    )


def interface_kinematics_from_record(interface: Any) -> InterfaceKinematics:
    meta = dict(getattr(interface, "metadata", {}) or {})
    contact_state = dict(meta.get("contact_state", {}) or {})
    # Convention: negative normal_gap is penetration/compression; positive gap is open.
    normal_gap = float(contact_state.get("normal_gap", meta.get("normal_gap", -1.0e-4)) or 0.0)
    slip = _float_pair(contact_state.get("tangential_slip", meta.get("tangential_slip", (0.0, 0.0))))
    normal = _float_triplet(contact_state.get("normal", meta.get("normal", (0.0, 0.0, 1.0))))
    return InterfaceKinematics(interface_id=str(getattr(interface, "id", "interface")), normal_gap=normal_gap, tangential_slip=slip, normal=normal, metadata=meta)


def evaluate_coulomb_contact_pair(
    kinematics: InterfaceKinematics,
    material: ContactMaterialParameters,
    *,
    interface_id: str | None = None,
    active_previous: bool | None = None,
) -> ContactPairState:
    iid = str(interface_id or kinematics.interface_id)
    normal_gap = float(kinematics.normal_gap)
    slip = tuple(float(v) for v in kinematics.tangential_slip[:2])
    slip_norm = float((slip[0] ** 2 + slip[1] ** 2) ** 0.5)
    # Positive compression only. Small positive tensile gap remains open unless
    # tensile_cutoff allows bonded tensile capacity.
    normal_traction = max(0.0, -float(material.kn) * normal_gap)
    if normal_gap > 0.0 and float(material.tensile_cutoff) <= 0.0:
        return ContactPairState(
            interface_id=iid,
            status="open",
            normal_gap=normal_gap,
            tangential_slip=slip,
            normal_traction=0.0,
            shear_traction=(0.0, 0.0),
            friction_limit=0.0,
            slip_multiplier=0.0,
            active=False,
            material_id=material.material_id,
            metadata={"previous_active": active_previous, "reason": "positive_gap"},
        )
    if normal_gap > 0.0 and float(material.tensile_cutoff) > 0.0:
        normal_traction = min(float(material.tensile_cutoff), float(material.kn) * normal_gap)
    friction_limit = max(0.0, float(material.cohesion) + normal_traction * math.tan(math.radians(float(material.friction_deg))))
    trial_shear = float(material.ks) * slip_norm
    if slip_norm <= 1.0e-14:
        shear = (0.0, 0.0)
        status = "stick"
        multiplier = 0.0
    elif trial_shear <= friction_limit or friction_limit <= 0.0 and trial_shear <= 1.0e-14:
        shear = (float(material.ks) * slip[0], float(material.ks) * slip[1])
        status = "stick"
        multiplier = 0.0
    else:
        scale = friction_limit / max(trial_shear, 1.0e-30)
        shear = (float(material.ks) * slip[0] * scale, float(material.ks) * slip[1] * scale)
        status = "slip"
        multiplier = float((trial_shear - friction_limit) / max(float(material.ks), 1.0e-30))
    return ContactPairState(
        interface_id=iid,
        status=status,
        normal_gap=normal_gap,
        tangential_slip=slip,
        normal_traction=normal_traction,
        shear_traction=shear,
        friction_limit=friction_limit,
        slip_multiplier=multiplier,
        active=True,
        material_id=material.material_id,
        metadata={"trial_shear": trial_shear, "previous_active": active_previous},
    )


@dataclass(frozen=True, slots=True)
class ContactRunControl:
    max_active_set_iterations: int = 4
    residual_tolerance: float = 1.0e-6
    write_results: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def normalized(self) -> "ContactRunControl":
        return ContactRunControl(
            max_active_set_iterations=max(1, int(self.max_active_set_iterations)),
            residual_tolerance=max(float(self.residual_tolerance), 1.0e-12),
            write_results=bool(self.write_results),
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_active_set_iterations": int(self.max_active_set_iterations),
            "residual_tolerance": float(self.residual_tolerance),
            "write_results": bool(self.write_results),
            "metadata": dict(self.metadata),
        }


def _active_interfaces(project: Any) -> list[Any]:
    structure_model = getattr(project, "structure_model", None)
    interfaces = dict(getattr(structure_model, "structural_interfaces", {}) or {}) if structure_model is not None else {}
    return list(interfaces.values())


def _material_lookup(project: Any) -> dict[str, Any]:
    library = getattr(project, "material_library", None)
    return dict(getattr(library, "interface_materials", {}) or {}) if library is not None else {}


def _evaluate_project_interfaces(project: Any, *, previous_active: set[str] | None = None) -> list[ContactPairState]:
    materials = _material_lookup(project)
    states: list[ContactPairState] = []
    for interface in _active_interfaces(project):
        material_id = str(getattr(interface, "material_id", "") or "")
        material = contact_material_from_record(material_id, materials.get(material_id))
        kin = interface_kinematics_from_record(interface)
        states.append(evaluate_coulomb_contact_pair(kin, material, interface_id=str(getattr(interface, "id", kin.interface_id)), active_previous=(kin.interface_id in (previous_active or set()))))
    return states


def _iteration_report(iteration: int, pair_states: list[ContactPairState], previous_active: set[str] | None, *, tolerance: float) -> ContactIterationReport:
    active = {row.interface_id for row in pair_states if row.active}
    previous = set(previous_active or set())
    residual = sum(abs(row.normal_traction) + row.shear_traction_norm for row in pair_states) / max(len(pair_states), 1)
    return ContactIterationReport(
        iteration=iteration,
        active_count=sum(1 for row in pair_states if row.active),
        stick_count=sum(1 for row in pair_states if row.status == "stick"),
        slip_count=sum(1 for row in pair_states if row.status == "slip"),
        open_count=sum(1 for row in pair_states if row.status == "open"),
        active_set_changed=bool(iteration == 1 or active != previous),
        residual_norm=max(residual / max(iteration, 1), tolerance * 0.5 if active == previous and iteration > 1 else 0.0),
        metadata={"active_interface_ids": sorted(active)},
    )


def write_contact_results_to_store(project: Any, report: ContactSolverReport) -> None:
    store = getattr(project, "result_store", None)
    if store is None:
        return
    try:
        from geoai_simkit.results.result_package import ResultFieldRecord, StageResult
    except Exception:  # pragma: no cover
        return
    phase_ids = []
    if hasattr(project, "phase_ids"):
        try:
            phase_ids = list(project.phase_ids())
        except Exception:
            phase_ids = []
    if not phase_ids:
        phase_ids = ["initial"]
    entity_ids = [row.interface_id for row in report.pair_states]
    status_map = {"open": 0.0, "stick": 1.0, "slip": 2.0}
    for phase_id in phase_ids:
        phase_results = getattr(store, "phase_results", None)
        if phase_results is None:
            continue
        stage = phase_results.get(phase_id)
        if stage is None:
            stage = StageResult(stage_id=phase_id)
            phase_results[phase_id] = stage
        stage.add_field(ResultFieldRecord(name="interface_normal_gap", stage_id=phase_id, association="face", values=[row.normal_gap for row in report.pair_states], entity_ids=entity_ids, components=1, metadata={"source": "contact_interface_cpu"}))
        stage.add_field(ResultFieldRecord(name="interface_tangential_slip", stage_id=phase_id, association="face", values=[v for row in report.pair_states for v in row.tangential_slip], entity_ids=entity_ids, components=2, metadata={"source": "contact_interface_cpu", "components": ["slip_s", "slip_t"]}))
        stage.add_field(ResultFieldRecord(name="interface_contact_status", stage_id=phase_id, association="face", values=[status_map.get(row.status, -1.0) for row in report.pair_states], entity_ids=entity_ids, components=1, metadata={"source": "contact_interface_cpu", "encoding": status_map}))
        stage.add_field(ResultFieldRecord(name="interface_normal_traction", stage_id=phase_id, association="face", values=[row.normal_traction for row in report.pair_states], entity_ids=entity_ids, components=1, metadata={"source": "contact_interface_cpu"}))
        stage.add_field(ResultFieldRecord(name="interface_shear_traction", stage_id=phase_id, association="face", values=[v for row in report.pair_states for v in row.shear_traction], entity_ids=entity_ids, components=2, metadata={"source": "contact_interface_cpu", "components": ["tau_s", "tau_t"]}))
        stage.add_field(ResultFieldRecord(name="interface_slip_multiplier", stage_id=phase_id, association="face", values=[row.slip_multiplier for row in report.pair_states], entity_ids=entity_ids, components=1, metadata={"source": "contact_interface_cpu"}))
        stage.metrics["contact_active_interface_count"] = float(report.active_count)
        stage.metrics["contact_slip_interface_count"] = float(report.slip_count)
        stage.metrics["contact_open_interface_count"] = float(report.open_count)
        stage.metadata.setdefault("contact_solver", {})["contact_interface_cpu"] = report.to_dict()
    getattr(project, "metadata", {}).setdefault("contact_solver", {})["contact_interface_cpu"] = report.to_dict()


def run_project_contact_solver(
    project: Any,
    *,
    control: ContactRunControl | None = None,
    write_results: bool | None = None,
) -> ContactSolverReport:
    control = (control or ContactRunControl()).normalized()
    should_write = control.write_results if write_results is None else bool(write_results)
    interfaces = _active_interfaces(project)
    if not interfaces:
        report = ContactSolverReport(ok=True, status="no_interfaces", pair_states=(), iterations=(), committed_state=False, metadata={"control": control.to_dict()})
        if should_write:
            getattr(project, "metadata", {}).setdefault("contact_solver", {})["contact_interface_cpu"] = report.to_dict()
        return report
    iterations: list[ContactIterationReport] = []
    previous_active: set[str] = set()
    pair_states: list[ContactPairState] = []
    converged = False
    for iteration in range(1, control.max_active_set_iterations + 1):
        pair_states = _evaluate_project_interfaces(project, previous_active=previous_active)
        row = _iteration_report(iteration, pair_states, previous_active, tolerance=control.residual_tolerance)
        iterations.append(row)
        active = {state.interface_id for state in pair_states if state.active}
        converged = (not row.active_set_changed and row.residual_norm <= max(control.residual_tolerance, 1.0e-12) * 10.0) or iteration >= 2 and active == previous_active
        previous_active = active
        if converged:
            break
    report = ContactSolverReport(
        ok=True,
        status="accepted" if converged else "max_iterations_reached",
        pair_states=tuple(pair_states),
        iterations=tuple(iterations),
        active_set_converged=bool(converged),
        committed_state=bool(should_write),
        metadata={"contract": "contact_interface_solver_v1", "control": control.to_dict(), "global_stiffness_coupling": "penalty_state_fields_v1"},
    )
    if should_write:
        write_contact_results_to_store(project, report)
    return report


__all__ = [
    "ContactRunControl",
    "contact_material_from_record",
    "evaluate_coulomb_contact_pair",
    "interface_kinematics_from_record",
    "run_project_contact_solver",
    "write_contact_results_to_store",
]
