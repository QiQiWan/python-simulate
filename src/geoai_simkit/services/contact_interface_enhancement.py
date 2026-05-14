from __future__ import annotations

"""Contact/interface enhancement service for 1.1 staged excavation workflows."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.geoproject.document import StructuralInterfaceRecord


@dataclass(slots=True)
class ContactInterfaceEnhancementReport:
    contract: str = "geoai_simkit_contact_interface_enhancement_v1"
    ok: bool = False
    interface_count: int = 0
    materialized_count: int = 0
    active_phase_count: int = 0
    findings: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "interface_count": int(self.interface_count),
            "materialized_count": int(self.materialized_count),
            "active_phase_count": int(self.active_phase_count),
            "findings": [dict(row) for row in self.findings],
            "metadata": dict(self.metadata),
        }


def configure_wall_soil_contact_interfaces(
    project: Any,
    *,
    interface_material_id: str = "alpha_wall_soil_interface",
    activate_from_phase: str = "excavation_1",
) -> ContactInterfaceEnhancementReport:
    """Create wall-soil interface records and activate them in construction phases."""

    phase_ids = list(project.phase_ids())
    if activate_from_phase in phase_ids:
        start_index = phase_ids.index(activate_from_phase)
    else:
        start_index = 0
    active_phases = phase_ids[start_index:]
    soil_volume_ids = [vid for vid, volume in project.geometry_model.volumes.items() if str(getattr(volume, "role", "")).lower() in {"soil", "excavation"}]
    wall_records = [row for row in project.structure_model.plates.values() if "wall" in str(row.id).lower() or "wall" in str(row.metadata.get("semantic_type", "")).lower()]
    findings: list[dict[str, Any]] = []
    created = 0
    for wall in wall_records:
        target_soil = "soil_upper" if "soil_upper" in soil_volume_ids else (soil_volume_ids[0] if soil_volume_ids else "")
        if not target_soil:
            findings.append({"severity": "warning", "code": "contact.no_soil", "message": f"No soil volume was available for wall {wall.id}."})
            continue
        iid = f"interface_{wall.id}_{target_soil}"
        record = project.structure_model.structural_interfaces.get(iid)
        if record is None:
            record = StructuralInterfaceRecord(id=iid, name=f"{wall.name} / {target_soil} interface", master_ref=wall.geometry_ref or wall.id, slave_ref=target_soil, material_id=interface_material_id, contact_mode="frictional", active_stage_ids=list(active_phases), metadata={"source": "contact_interface_enhancement_v1", "wall_id": wall.id, "soil_volume_id": target_soil, "R_inter": 0.70})
            project.structure_model.structural_interfaces[iid] = record
            created += 1
        else:
            record.material_id = record.material_id or interface_material_id
            record.contact_mode = "frictional"
            record.active_stage_ids = sorted(set(record.active_stage_ids) | set(active_phases))
            record.metadata.update({"source": "contact_interface_enhancement_v1", "wall_id": wall.id, "soil_volume_id": target_soil})
        for phase_id in active_phases:
            try:
                project.set_phase_interface_activation(phase_id, iid, True)
            except Exception as exc:
                findings.append({"severity": "warning", "code": "contact.phase_activation", "message": str(exc), "interface_id": iid, "phase_id": phase_id})
    for phase_id in phase_ids:
        project.refresh_phase_snapshot(phase_id)
    project.metadata["contact_interface_enhancement_topology"] = {"interface_count": len(project.structure_model.structural_interfaces), "active_phases": active_phases}
    report = ContactInterfaceEnhancementReport(ok=bool(project.structure_model.structural_interfaces), interface_count=len(project.structure_model.structural_interfaces), materialized_count=created, active_phase_count=len(active_phases), findings=findings, metadata={"active_phases": active_phases, "interface_material_id": interface_material_id})
    project.solver_model.metadata["contact_interface_enhancement"] = report.to_dict()
    project.metadata["contact_interface_enhancement"] = {"interface_count": report.interface_count, "active_phase_count": report.active_phase_count}
    if hasattr(project, "mark_changed"):
        project.mark_changed(["topology", "phase"], action="configure_wall_soil_contact_interfaces", affected_entities=list(project.structure_model.structural_interfaces))
    return report


__all__ = ["ContactInterfaceEnhancementReport", "configure_wall_soil_contact_interfaces"]
