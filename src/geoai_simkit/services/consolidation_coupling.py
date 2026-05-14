from __future__ import annotations

"""Pore-pressure consolidation coupling service for release 1.2.2."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.results.result_package import ResultFieldRecord
from geoai_simkit.services.hydro_mechanical import apply_pore_pressure_results


@dataclass(slots=True)
class ConsolidationPhaseRecord:
    phase_id: str
    degree_of_consolidation: float
    max_excess_pore_pressure: float
    settlement_increment: float
    converged: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "degree_of_consolidation": float(self.degree_of_consolidation),
            "max_excess_pore_pressure": float(self.max_excess_pore_pressure),
            "settlement_increment": float(self.settlement_increment),
            "converged": bool(self.converged),
        }


@dataclass(slots=True)
class ConsolidationCouplingSummary:
    contract: str = "geoai_simkit_consolidation_coupling_v1"
    ok: bool = False
    phase_count: int = 0
    coupled: bool = True
    phase_records: list[ConsolidationPhaseRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "phase_count": int(self.phase_count),
            "coupled": bool(self.coupled),
            "phase_records": [row.to_dict() for row in self.phase_records],
            "metadata": dict(self.metadata),
        }


def _values_for(stage: Any, field_name: str) -> tuple[list[str], list[float]]:
    field = getattr(stage, "fields", {}).get(field_name)
    if field is None:
        return [], []
    return list(field.entity_ids or []), [float(v) for v in list(field.values or [])]


def apply_consolidation_coupling(
    project: Any,
    *,
    drainage_factor: float = 0.35,
    write_results: bool = True,
) -> ConsolidationCouplingSummary:
    if "hydro_mechanical_state" not in project.solver_model.metadata:
        apply_pore_pressure_results(project, write_results=True)
    phase_records: list[ConsolidationPhaseRecord] = []
    phase_ids = project.phase_ids()
    for index, phase_id in enumerate(phase_ids):
        stage = project.result_store.phase_results.get(phase_id)
        if stage is None:
            continue
        entity_ids, pore_values = _values_for(stage, "pore_pressure")
        if not entity_ids:
            entity_ids = [f"cell_{i}" for i in range(len(pore_values))]
        if not pore_values:
            pore_values = [0.0] * len(entity_ids)
        degree = min(0.95, max(0.0, drainage_factor * index / max(1, len(phase_ids) - 1)))
        excess = [max(0.0, v * (1.0 - degree)) for v in pore_values]
        settlement = sum(excess) * 1.0e-5 / max(1, len(excess))
        if write_results:
            stage.add_field(ResultFieldRecord(name="excess_pore_pressure", stage_id=phase_id, association="cell", values=excess, entity_ids=entity_ids, components=1, metadata={"source": "consolidation_coupling_v1"}))
            stage.add_field(ResultFieldRecord(name="degree_of_consolidation", stage_id=phase_id, association="cell", values=[degree] * len(entity_ids), entity_ids=entity_ids, components=1, metadata={"source": "consolidation_coupling_v1"}))
            stage.metrics["degree_of_consolidation"] = float(degree)
            stage.metrics["consolidation_settlement_increment"] = float(settlement)
        phase_records.append(ConsolidationPhaseRecord(phase_id=phase_id, degree_of_consolidation=degree, max_excess_pore_pressure=max(excess) if excess else 0.0, settlement_increment=settlement))
    summary = ConsolidationCouplingSummary(ok=bool(phase_records), phase_count=len(phase_records), phase_records=phase_records, metadata={"drainage_factor": float(drainage_factor), "solver_level": "1.2.2_basic_coupled_consolidation"})
    project.solver_model.metadata["consolidation_coupling_state"] = summary.to_dict()
    project.metadata["release_1_2_2_consolidation"] = summary.to_dict()
    if hasattr(project, "mark_changed"):
        project.mark_changed(["solver", "results"], action="apply_consolidation_coupling", affected_entities=phase_ids)
    return summary


__all__ = ["ConsolidationPhaseRecord", "ConsolidationCouplingSummary", "apply_consolidation_coupling"]
