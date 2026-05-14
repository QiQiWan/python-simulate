from __future__ import annotations

"""Project-level validation gates for the 0.9 Alpha workflow.

The validator is intentionally dependency-light.  It checks the data contracts
that must be present before a staged 3D geotechnical model is allowed to move
from modeling to meshing, solving and results review.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(slots=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    entity_id: str = ""
    phase_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "entity_id": self.entity_id,
            "phase_id": self.phase_id,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ValidationReport:
    contract: str = "geoproject_model_validation_v1"
    status: str = "unknown"
    issues: list[ValidationIssue] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    readiness: dict[str, bool] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def ok(self) -> bool:
        return self.error_count == 0

    def add(self, severity: str, code: str, message: str, *, entity_id: str = "", phase_id: str = "", **metadata: Any) -> None:
        self.issues.append(
            ValidationIssue(
                severity=str(severity),
                code=str(code),
                message=str(message),
                entity_id=str(entity_id or ""),
                phase_id=str(phase_id or ""),
                metadata=dict(metadata),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": self.ok,
            "status": self.status,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [issue.to_dict() for issue in self.issues],
            "counts": dict(self.counts),
            "readiness": dict(self.readiness),
            "metadata": dict(self.metadata),
        }


def _material_ids(project: Any) -> set[str]:
    library = project.material_library
    ids: set[str] = set()
    for attr in ("soil_materials", "plate_materials", "beam_materials", "interface_materials"):
        ids.update(str(v) for v in getattr(library, attr, {}).keys())
    return ids


def _structure_records(project: Any) -> Iterable[Any]:
    if hasattr(project, "iter_structure_records"):
        yield from project.iter_structure_records()
        return
    model = project.structure_model
    for attr in ("plates", "beams", "embedded_beams", "anchors"):
        yield from getattr(model, attr, {}).values()


def validate_geoproject_model(project: Any, *, require_mesh: bool = False, require_results: bool = False) -> ValidationReport:
    """Return a validation report for model, mesh, phases and result readiness."""

    report = ValidationReport(metadata={"require_mesh": bool(require_mesh), "require_results": bool(require_results)})
    material_ids = _material_ids(project)
    volumes = dict(getattr(project.geometry_model, "volumes", {}) or {})
    surfaces = dict(getattr(project.geometry_model, "surfaces", {}) or {})
    curves = dict(getattr(project.geometry_model, "curves", {}) or {})
    phases = project.phases_in_order() if hasattr(project, "phases_in_order") else []
    mesh = getattr(project.mesh_model, "mesh_document", None)
    results = dict(getattr(project.result_store, "phase_results", {}) or {})

    report.counts.update(
        {
            "volume_count": len(volumes),
            "surface_count": len(surfaces),
            "curve_count": len(curves),
            "material_count": len(material_ids),
            "phase_count": len(phases),
            "mesh_cell_count": 0 if mesh is None else int(getattr(mesh, "cell_count", 0)),
            "result_phase_count": len(results),
        }
    )

    if not volumes:
        report.add("error", "NO_SOLID_VOLUMES", "No solid volumes are available for 3D staged analysis.")
    for volume in volumes.values():
        if getattr(volume, "bounds", None) is None and not getattr(volume, "surface_ids", None):
            report.add("error", "VOLUME_HAS_NO_BOUNDS_OR_SURFACES", "Volume has neither bounds nor boundary surfaces.", entity_id=volume.id)
        material_id = getattr(volume, "material_id", None)
        if not material_id:
            report.add("error", "VOLUME_MISSING_MATERIAL", "Volume has no material assignment.", entity_id=volume.id)
        elif material_id not in material_ids:
            report.add("error", "VOLUME_UNKNOWN_MATERIAL", f"Volume references unknown material '{material_id}'.", entity_id=volume.id, material_id=material_id)
        role = str(getattr(volume, "role", "") or "")
        if role in {"unknown", "sketch", ""}:
            report.add("warning", "VOLUME_UNCLASSIFIED", "Volume is present but has not been classified as soil, excavation, rock or structure.", entity_id=volume.id)

    for record in _structure_records(project):
        material_id = str(getattr(record, "material_id", "") or "")
        if not material_id:
            report.add("warning", "STRUCTURE_MISSING_MATERIAL", "Structure has no material assignment.", entity_id=record.id)
        elif material_id not in material_ids:
            report.add("warning", "STRUCTURE_UNKNOWN_MATERIAL", f"Structure references unknown material '{material_id}'.", entity_id=record.id, material_id=material_id)
        if not getattr(record, "geometry_ref", ""):
            report.add("warning", "STRUCTURE_MISSING_GEOMETRY_REF", "Structure is not linked back to a geometric entity.", entity_id=record.id)

    for iid, interface in getattr(project.structure_model, "structural_interfaces", {}).items():
        if not getattr(interface, "master_ref", "") or not getattr(interface, "slave_ref", ""):
            report.add("warning", "INTERFACE_INCOMPLETE_PAIR", "Interface does not have both master and slave references.", entity_id=iid)
        material_id = str(getattr(interface, "material_id", "") or "")
        if material_id and material_id not in material_ids:
            report.add("warning", "INTERFACE_UNKNOWN_MATERIAL", f"Interface references unknown material '{material_id}'.", entity_id=iid, material_id=material_id)

    phase_ids = [stage.id for stage in phases]
    if not phases:
        report.add("error", "NO_PHASES", "No initial/construction phase exists.")
    for index, stage in enumerate(phases):
        snapshot = project.phase_manager.phase_state_snapshots.get(stage.id) if hasattr(project, "phase_manager") else None
        if snapshot is None:
            report.add("error", "PHASE_MISSING_SNAPSHOT", "Phase has no activation snapshot.", phase_id=stage.id)
        if index > 0 and not getattr(stage, "predecessor_id", None):
            report.add("warning", "PHASE_MISSING_PREDECESSOR", "Construction phase has no predecessor.", phase_id=stage.id)
        pred = getattr(stage, "predecessor_id", None)
        if pred and pred not in phase_ids:
            report.add("error", "PHASE_BAD_PREDECESSOR", f"Phase predecessor '{pred}' does not exist.", phase_id=stage.id, predecessor_id=pred)

    if require_mesh or mesh is not None:
        if mesh is None:
            report.add("error", "MESH_MISSING", "A mesh is required but no mesh is attached.")
        else:
            if int(getattr(mesh, "cell_count", 0)) <= 0:
                report.add("error", "MESH_HAS_NO_CELLS", "Attached mesh has no cells.")
            if int(getattr(mesh, "node_count", 0)) <= 0:
                report.add("error", "MESH_HAS_NO_NODES", "Attached mesh has no nodes.")
            block_tags = list(getattr(mesh, "cell_tags", {}).get("block_id", []) or [])
            if block_tags and len(block_tags) != int(getattr(mesh, "cell_count", 0)):
                report.add("error", "MESH_BLOCK_TAG_COUNT_MISMATCH", "Mesh block_id tag count does not match cell count.", tag_count=len(block_tags), cell_count=int(getattr(mesh, "cell_count", 0)))
            if not block_tags:
                report.add("warning", "MESH_MISSING_BLOCK_TAGS", "Mesh has no block_id cell tags; phase activation will fall back to all cells.")
            quality = getattr(mesh, "quality", None) or getattr(project.mesh_model, "quality_report", None)
            bad = [] if quality is None else list(getattr(quality, "bad_cell_ids", []) or [])
            if bad:
                report.add("warning", "MESH_HAS_BAD_CELLS", "Mesh quality report contains bad cells.", bad_cell_count=len(bad))

    if require_results and not results:
        report.add("error", "RESULTS_MISSING", "Results are required but ResultStore is empty.")

    report.readiness = {
        "geometry_ready": bool(volumes) and not any(issue.code.startswith("VOLUME_HAS_NO") for issue in report.issues if issue.severity == "error"),
        "semantic_ready": not any(issue.code in {"VOLUME_MISSING_MATERIAL", "VOLUME_UNKNOWN_MATERIAL"} for issue in report.issues if issue.severity == "error"),
        "phase_ready": not any(issue.code.startswith("PHASE_") for issue in report.issues if issue.severity == "error"),
        "mesh_ready": mesh is not None and int(getattr(mesh, "cell_count", 0)) > 0 and not any(issue.code.startswith("MESH_") and issue.severity == "error" for issue in report.issues),
        "result_ready": bool(results),
    }
    if report.error_count:
        report.status = "blocked"
    elif report.warning_count:
        report.status = "ready_with_warnings"
    else:
        report.status = "ready"
    return report


__all__ = ["ValidationIssue", "ValidationReport", "validate_geoproject_model"]
