from __future__ import annotations

"""Groundwater, pore-pressure and effective-stress utilities for 1.1 workflows."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.results.result_package import ResultFieldRecord


@dataclass(slots=True)
class HydroMechanicalPhaseRecord:
    phase_id: str
    water_condition_id: str = ""
    water_level: float | None = None
    cell_count: int = 0
    max_pore_pressure: float = 0.0
    min_effective_stress_zz: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "water_condition_id": self.water_condition_id,
            "water_level": self.water_level,
            "cell_count": int(self.cell_count),
            "max_pore_pressure": float(self.max_pore_pressure),
            "min_effective_stress_zz": float(self.min_effective_stress_zz),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class HydroMechanicalReport:
    contract: str = "geoai_simkit_hydro_mechanical_state_v1"
    ok: bool = False
    phase_records: list[HydroMechanicalPhaseRecord] = field(default_factory=list)
    gamma_water: float = 9.81
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "phase_records": [row.to_dict() for row in self.phase_records],
            "gamma_water": float(self.gamma_water),
            "metadata": dict(self.metadata),
        }


def _compiled_cell_centroids(project: Any, phase_id: str) -> dict[str, tuple[float, float, float]]:
    compiled = project.solver_model.compiled_phase_models.get(f"compiled_{phase_id}")
    if compiled is None:
        return {}
    nodes = [tuple(float(v) for v in row[:3]) for row in list((compiled.mesh_block or {}).get("node_coordinates", []) or [])]
    out: dict[str, tuple[float, float, float]] = {}
    for element in list((compiled.element_block or {}).get("elements", []) or []):
        cid = str(element.get("cell_id", ""))
        conn = [int(v) for v in list(element.get("connectivity", []) or [])]
        if not conn or not nodes:
            continue
        pts = [nodes[i] for i in conn if 0 <= i < len(nodes)]
        if not pts:
            continue
        out[cid] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), sum(p[2] for p in pts) / len(pts))
    return out


def _water_for_phase(project: Any, phase_id: str) -> tuple[str, float | None, dict[str, Any]]:
    snapshot = project.phase_manager.phase_state_snapshots.get(phase_id)
    water_id = ""
    if snapshot is not None and snapshot.water_condition_id:
        water_id = str(snapshot.water_condition_id)
    phase = project.get_phase(phase_id) if hasattr(project, "get_phase") else None
    if not water_id and phase is not None:
        water_id = str(getattr(phase, "metadata", {}).get("water_condition_id", "") or "")
    condition = project.soil_model.water_conditions.get(water_id) if water_id else None
    if condition is not None:
        return water_id, condition.level, dict(condition.metadata or {})
    level = None if phase is None else getattr(phase, "water_level", None)
    return water_id, None if level is None else float(level), {}


def apply_pore_pressure_results(project: Any, *, gamma_water: float = 9.81, write_results: bool = True) -> HydroMechanicalReport:
    """Compute phase pore pressure/effective stress fields from water levels."""

    records: list[HydroMechanicalPhaseRecord] = []
    for phase_id in project.phase_ids():
        stage = project.result_store.phase_results.get(phase_id)
        if stage is None:
            continue
        centroids = _compiled_cell_centroids(project, phase_id)
        cell_ids = [str(v) for v in (stage.fields.get("cell_stress_zz").entity_ids if stage.fields.get("cell_stress_zz") else centroids.keys())]
        water_id, water_level, water_meta = _water_for_phase(project, phase_id)
        pressure_values: list[float] = []
        head_values: list[float] = []
        for cid in cell_ids:
            z = centroids.get(str(cid), (0.0, 0.0, 0.0))[2]
            if water_level is None:
                pressure = 0.0
                head = 0.0
            else:
                pressure = max(0.0, float(gamma_water) * (float(water_level) - float(z)))
                head = float(water_level) - float(z)
            pressure_values.append(float(pressure))
            head_values.append(float(head))
        stress_zz_field = stage.fields.get("cell_stress_zz")
        stress_zz = [float(v) for v in (stress_zz_field.values if stress_zz_field else [0.0] * len(cell_ids))]
        while len(stress_zz) < len(cell_ids):
            stress_zz.append(0.0)
        # Current solver uses negative stress for compression.  Positive pore
        # pressure reduces compression magnitude, hence sigma' = sigma + u.
        effective_zz = [float(s + u) for s, u in zip(stress_zz, pressure_values)]
        if write_results:
            stage.add_field(ResultFieldRecord(name="pore_pressure", stage_id=phase_id, association="cell", values=pressure_values, entity_ids=cell_ids, components=1, metadata={"unit": project.project_settings.stress_unit, "source": "hydro_mechanical_state_v1"}))
            stage.add_field(ResultFieldRecord(name="hydraulic_head", stage_id=phase_id, association="cell", values=head_values, entity_ids=cell_ids, components=1, metadata={"unit": project.project_settings.length_unit, "source": "hydro_mechanical_state_v1"}))
            stage.add_field(ResultFieldRecord(name="effective_stress_zz", stage_id=phase_id, association="cell", values=effective_zz, entity_ids=cell_ids, components=1, metadata={"unit": project.project_settings.stress_unit, "source": "hydro_mechanical_state_v1"}))
            stage.metrics["max_pore_pressure"] = max(pressure_values, default=0.0)
            stage.metrics["min_effective_stress_zz"] = min(effective_zz, default=0.0)
        records.append(HydroMechanicalPhaseRecord(phase_id=phase_id, water_condition_id=water_id, water_level=water_level, cell_count=len(cell_ids), max_pore_pressure=max(pressure_values, default=0.0), min_effective_stress_zz=min(effective_zz, default=0.0), metadata={"water_metadata": water_meta}))
    payload = {"contract": "geoai_simkit_hydro_mechanical_state_v1", "phase_count": len(records), "phase_records": [row.to_dict() for row in records], "gamma_water": float(gamma_water)}
    project.solver_model.metadata["hydro_mechanical_state"] = payload
    project.metadata["hydro_mechanical_state"] = {"phase_count": len(records), "gamma_water": float(gamma_water)}
    return HydroMechanicalReport(ok=bool(records), phase_records=records, gamma_water=float(gamma_water))


__all__ = ["HydroMechanicalPhaseRecord", "HydroMechanicalReport", "apply_pore_pressure_results"]
