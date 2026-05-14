from __future__ import annotations

"""0.9 Alpha solver compiler service.

This service wraps GeoProjectDocument.compile_phase_models with validation and a
stable payload that can be consumed by the GUI, workflow tests and future solver
backends.
"""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.services.model_validation import validate_geoproject_model


@dataclass(slots=True)
class PhaseCompilerReport:
    contract: str = "geoproject_phase_solver_compiler_v1"
    ok: bool = False
    compiled_phase_count: int = 0
    blocked: bool = False
    validation: dict[str, Any] = field(default_factory=dict)
    phase_summaries: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "compiled_phase_count": int(self.compiled_phase_count),
            "blocked": bool(self.blocked),
            "validation": dict(self.validation),
            "phase_summaries": [dict(row) for row in self.phase_summaries],
            "metadata": dict(self.metadata),
        }


def _summarize_compiled(compiled: Any) -> dict[str, Any]:
    payload = compiled.to_dict() if hasattr(compiled, "to_dict") else dict(compiled or {})
    return {
        "id": str(payload.get("id", "")),
        "phase_id": str(payload.get("phase_id", "")),
        "active_cell_count": int(payload.get("active_cell_count", 0) or 0),
        "active_dof_count": int(payload.get("active_dof_count", 0) or 0),
        "material_state_count": int(payload.get("material_state_count", 0) or 0),
        "interface_count": int(payload.get("interface_count", 0) or 0),
        "has_mesh_block": bool(payload.get("MeshBlock")),
        "has_element_block": bool(payload.get("ElementBlock")),
        "has_material_block": bool(payload.get("MaterialBlock")),
        "has_boundary_block": bool(payload.get("BoundaryBlock")),
        "has_load_block": bool(payload.get("LoadBlock")),
        "has_result_request_block": bool(payload.get("ResultRequestBlock")),
    }


def compile_phase_solver_inputs(project: Any, *, block_on_errors: bool = True) -> PhaseCompilerReport:
    """Validate and compile phase solver inputs for a GeoProjectDocument."""

    validation = validate_geoproject_model(project, require_mesh=True)
    if block_on_errors and not validation.ok:
        return PhaseCompilerReport(
            ok=False,
            blocked=True,
            validation=validation.to_dict(),
            metadata={"reason": "validation_errors", "block_on_errors": bool(block_on_errors)},
        )
    compiled = project.compile_phase_models()
    summaries = [_summarize_compiled(row) for row in compiled.values()]
    return PhaseCompilerReport(
        ok=True,
        blocked=False,
        compiled_phase_count=len(summaries),
        validation=validation.to_dict(),
        phase_summaries=summaries,
        metadata={"block_on_errors": bool(block_on_errors), "compiler": "GeoProjectDocument.compile_phase_models"},
    )


__all__ = ["PhaseCompilerReport", "compile_phase_solver_inputs"]
