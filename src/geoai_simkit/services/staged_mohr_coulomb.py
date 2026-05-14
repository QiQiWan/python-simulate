from __future__ import annotations

"""Staged Mohr-Coulomb control metadata for 1.0.5 workflows.

This service does not replace the global nonlinear solver.  It creates a
versioned control block that binds the existing Mohr-Coulomb material records,
phase calculation settings and solver summary into an auditable staged-plasticity
readiness payload.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StagedMohrCoulombControlReport:
    contract: str = "geoai_simkit_staged_mohr_coulomb_control_v1"
    ok: bool = False
    phase_count: int = 0
    material_count: int = 0
    control_mode: str = "engineering_preview"
    findings: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "phase_count": int(self.phase_count),
            "material_count": int(self.material_count),
            "control_mode": self.control_mode,
            "findings": [dict(row) for row in self.findings],
            "metadata": dict(self.metadata),
        }


def _soil_materials(project: Any) -> list[Any]:
    return list(dict(getattr(getattr(project, "material_library", None), "soil_materials", {}) or {}).values())


def configure_staged_mohr_coulomb_controls(
    project: Any,
    *,
    control_mode: str = "engineering_preview",
    max_iterations: int = 35,
    tolerance: float = 1.0e-6,
    use_k0_initial_stress: bool = True,
) -> StagedMohrCoulombControlReport:
    """Attach a staged Mohr-Coulomb control block to the project."""

    report = StagedMohrCoulombControlReport(control_mode=str(control_mode))
    phase_ids = list(project.phase_ids() if hasattr(project, "phase_ids") else [])
    materials = _soil_materials(project)
    usable: list[str] = []
    for material in materials:
        params = dict(getattr(material, "parameters", {}) or {})
        missing = [name for name in ("E_ref", "nu", "c_ref", "phi") if name not in params]
        if str(getattr(material, "model_type", "")).lower() != "mohr_coulomb":
            report.findings.append({"severity": "warning", "code": "mc.material.model_type", "message": f"Material {material.id} is not marked mohr_coulomb."})
            material.model_type = "mohr_coulomb"
        if missing:
            report.findings.append({"severity": "blocker", "code": "mc.material.params", "message": f"Material {material.id} is missing {missing}.", "material_id": material.id})
        else:
            usable.append(str(material.id))
        material.metadata["release_1_0_5_constitutive_path"] = "staged_mohr_coulomb"
    for phase_id in phase_ids:
        settings = project.phase_manager.calculation_settings.get(phase_id)
        if settings is None:
            from geoai_simkit.geoproject.document import CalculationSettings

            settings = CalculationSettings()
            project.phase_manager.calculation_settings[phase_id] = settings
        settings.calculation_type = "staged_mohr_coulomb"
        settings.max_iterations = int(max_iterations)
        settings.tolerance = float(tolerance)
        settings.metadata.update(
            {
                "release_1_0_5": "staged_mohr_coulomb_control",
                "control_mode": str(control_mode),
                "use_k0_initial_stress": bool(use_k0_initial_stress),
            }
        )
        if hasattr(project, "refresh_phase_snapshot"):
            project.refresh_phase_snapshot(phase_id)
    payload = {
        "contract": "geoai_simkit_staged_mohr_coulomb_control_payload_v1",
        "control_mode": str(control_mode),
        "phase_ids": phase_ids,
        "material_ids": usable,
        "max_iterations": int(max_iterations),
        "tolerance": float(tolerance),
        "use_k0_initial_stress": bool(use_k0_initial_stress),
        "limitations": [
            "Global equilibrium solve remains the 1.0 compact linear-static kernel in this basic release.",
            "Mohr-Coulomb state is tracked through staged control metadata and material readiness gates.",
        ],
    }
    project.solver_model.metadata["staged_mohr_coulomb_control"] = payload
    project.metadata["staged_mohr_coulomb_control"] = {"phase_count": len(phase_ids), "material_count": len(usable), "control_mode": str(control_mode)}
    report.phase_count = len(phase_ids)
    report.material_count = len(usable)
    report.ok = bool(phase_ids) and bool(usable) and not any(row.get("severity") == "blocker" for row in report.findings)
    report.metadata = {"phase_ids": phase_ids, "material_ids": usable}
    return report


__all__ = ["StagedMohrCoulombControlReport", "configure_staged_mohr_coulomb_controls"]
