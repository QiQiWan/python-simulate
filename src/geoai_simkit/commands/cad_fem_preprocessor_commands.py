from __future__ import annotations

"""Undoable commands for CAD-FEM preprocessor readiness snapshots."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.commands.command import Command, CommandResult


def _restore_document(document: Any, backup: dict[str, Any] | None) -> None:
    if backup is None:
        return
    restored = document.__class__.from_dict(backup)
    for field_name in document.__dataclass_fields__:
        setattr(document, field_name, getattr(restored, field_name))


@dataclass(slots=True)
class BuildCadFemPreprocessorCommand(Command):
    """Build CAD-derived physical groups, BC candidates and mesh controls."""

    default_element_size: float | None = None
    require_boundary_candidates: bool = True
    require_mesh_controls: bool = True
    id: str = "build_cad_fem_preprocessor"
    name: str = "Build CAD-FEM preprocessor readiness"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not hasattr(document, "cad_shape_store") or not hasattr(document, "mesh_model"):
            return CommandResult(self.id, self.name, ok=False, message="CAD-FEM preprocessing requires GeoProjectDocument with CadShapeStore and MeshModel")
        self._backup = document.to_dict() if hasattr(document, "to_dict") else None
        try:
            from geoai_simkit.services.cad_fem_preprocessor import build_cad_fem_preprocessor, validate_cad_fem_preprocessor

            report = build_cad_fem_preprocessor(document, attach=True, default_element_size=self.default_element_size)
            validation = validate_cad_fem_preprocessor(
                document,
                require_boundary_candidates=self.require_boundary_candidates,
                require_mesh_controls=self.require_mesh_controls,
            )
        except Exception as exc:
            return CommandResult(self.id, self.name, ok=False, message=f"CAD-FEM preprocessing failed: {type(exc).__name__}: {exc}")
        summary = report.summary()
        return CommandResult(
            self.id,
            self.name,
            ok=bool(validation.get("ok")),
            affected_entities=[item.id for item in report.boundary_candidates],
            message=(
                "CAD-FEM preprocessor built: "
                f"physical_groups={summary['physical_group_count']}, "
                f"boundary_candidates={summary['boundary_candidate_count']}, "
                f"mesh_controls={summary['mesh_control_count']}, status={report.status}"
            ),
            metadata={"report": report.to_dict(), "validation": validation},
        )

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True)


__all__ = ["BuildCadFemPreprocessorCommand"]
