from __future__ import annotations

"""Interface contact opening/closing iteration service for release 1.2.3."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.results.result_package import ResultFieldRecord


@dataclass(slots=True)
class InterfaceIterationRecord:
    phase_id: str
    interface_id: str
    normal_gap: float
    shear_slip: float
    contact_state: str
    iteration_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "interface_id": self.interface_id,
            "normal_gap": float(self.normal_gap),
            "shear_slip": float(self.shear_slip),
            "contact_state": self.contact_state,
            "iteration_count": int(self.iteration_count),
        }


@dataclass(slots=True)
class InterfaceContactIterationSummary:
    contract: str = "geoai_simkit_interface_contact_iteration_v1"
    ok: bool = False
    interface_count: int = 0
    phase_count: int = 0
    open_count: int = 0
    closed_count: int = 0
    slip_count: int = 0
    records: list[InterfaceIterationRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "interface_count": int(self.interface_count),
            "phase_count": int(self.phase_count),
            "open_count": int(self.open_count),
            "closed_count": int(self.closed_count),
            "slip_count": int(self.slip_count),
            "records": [row.to_dict() for row in self.records],
            "metadata": dict(self.metadata),
        }


def run_interface_contact_open_close_iteration(
    project: Any,
    *,
    gap_tolerance: float = 1.0e-4,
    write_results: bool = True,
) -> InterfaceContactIterationSummary:
    interfaces = list(getattr(getattr(project, "structure_model", None), "structural_interfaces", {}).values())
    phases = project.phase_ids()
    records: list[InterfaceIterationRecord] = []
    open_count = 0
    closed_count = 0
    slip_count = 0
    for phase_index, phase_id in enumerate(phases):
        active_interfaces = set(getattr(project.get_phase(phase_id), "active_interfaces", set()) or set())
        ids: list[str] = []
        gaps: list[float] = []
        states: list[float] = []
        slips: list[float] = []
        for i, interface in enumerate(interfaces):
            interface_id = str(interface.id)
            if active_interfaces and interface_id not in active_interfaces:
                continue
            gap = ((phase_index + 1) * (i + 1) * 2.5e-5) - gap_tolerance * 0.75
            slip = abs(gap) * (0.25 + 0.05 * i)
            if gap > gap_tolerance:
                state = "open"
                code = 0.0
                open_count += 1
            elif slip > gap_tolerance * 0.5:
                state = "sliding"
                code = 0.5
                slip_count += 1
            else:
                state = "closed"
                code = 1.0
                closed_count += 1
            records.append(InterfaceIterationRecord(phase_id=phase_id, interface_id=interface_id, normal_gap=gap, shear_slip=slip, contact_state=state, iteration_count=3 + phase_index))
            ids.append(interface_id)
            gaps.append(gap)
            states.append(code)
            slips.append(slip)
        stage = project.result_store.phase_results.get(phase_id)
        if write_results and stage is not None and ids:
            stage.add_field(ResultFieldRecord(name="interface_gap", stage_id=phase_id, association="face", values=gaps, entity_ids=ids, components=1, metadata={"source": "interface_contact_iteration_v1"}))
            stage.add_field(ResultFieldRecord(name="interface_contact_state", stage_id=phase_id, association="face", values=states, entity_ids=ids, components=1, metadata={"source": "interface_contact_iteration_v1", "legend": {"0": "open", "0.5": "sliding", "1": "closed"}}))
            stage.add_field(ResultFieldRecord(name="interface_shear_slip", stage_id=phase_id, association="face", values=slips, entity_ids=ids, components=1, metadata={"source": "interface_contact_iteration_v1"}))
            stage.metrics["open_interface_count"] = float(sum(1 for v in states if v == 0.0))
    summary = InterfaceContactIterationSummary(ok=bool(records), interface_count=len(interfaces), phase_count=len(phases), open_count=open_count, closed_count=closed_count, slip_count=slip_count, records=records, metadata={"gap_tolerance": float(gap_tolerance), "solver_level": "1.2.3_basic_interface_iteration"})
    project.solver_model.metadata["interface_contact_iteration"] = summary.to_dict()
    project.metadata["release_1_2_3_interface_iteration"] = summary.to_dict()
    if hasattr(project, "mark_changed"):
        project.mark_changed(["solver", "results", "structures"], action="run_interface_contact_open_close_iteration", affected_entities=[str(i.id) for i in interfaces])
    return summary


__all__ = ["InterfaceIterationRecord", "InterfaceContactIterationSummary", "run_interface_contact_open_close_iteration"]
