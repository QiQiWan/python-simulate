from __future__ import annotations

"""Headless mesh/material quality gates for verified 3D geotechnical runs."""

from math import dist
from typing import Any, Iterable

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import (
    ElementQualityMetric,
    GeotechnicalQualityGateReport,
    MaterialCompatibilityReport,
    MeshQualityGateReport,
    QualityGateIssue,
    SOLID_CELL_TYPES,
    material_mapping_summary,
    solid_mesh_summary,
)
from geoai_simkit.services.geotechnical_readiness import build_geotechnical_readiness_report


def _project(value: Any) -> Any:
    return as_project_context(value).get_project()


def _mesh(value: Any) -> Any:
    return as_project_context(value).current_mesh()


def _sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (float(a[0]) - float(b[0]), float(a[1]) - float(b[1]), float(a[2]) - float(b[2]))


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _tet_volume(points: list[tuple[float, float, float]], cell: tuple[int, ...]) -> float | None:
    if len(cell) < 4:
        return None
    try:
        a, b, c, d = [points[int(idx)] for idx in cell[:4]]
        return abs(_dot(_sub(b, a), _cross(_sub(c, a), _sub(d, a)))) / 6.0
    except Exception:
        return None


def _hex_volume(points: list[tuple[float, float, float]], cell: tuple[int, ...]) -> float | None:
    if len(cell) < 8:
        return None
    try:
        rows = [points[int(idx)] for idx in cell[:8]]
        xs = [p[0] for p in rows]
        ys = [p[1] for p in rows]
        zs = [p[2] for p in rows]
        return abs((max(xs) - min(xs)) * (max(ys) - min(ys)) * (max(zs) - min(zs)))
    except Exception:
        return None


def _aspect_ratio(points: list[tuple[float, float, float]], cell: tuple[int, ...]) -> float | None:
    try:
        rows = [points[int(idx)] for idx in cell]
    except Exception:
        return None
    lengths: list[float] = []
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            value = float(dist(a, b))
            if value > 0.0:
                lengths.append(value)
    if not lengths:
        return None
    return max(lengths) / max(min(lengths), 1.0e-30)


def evaluate_mesh_quality_gate(
    project_or_port: Any,
    *,
    min_volume: float = 1.0e-12,
    max_aspect_ratio: float = 100.0,
    max_metrics: int = 50,
) -> MeshQualityGateReport:
    """Check basic solid-cell quality before a 3D geotechnical solve."""

    mesh = _mesh(project_or_port)
    issues: list[QualityGateIssue] = []
    metrics: list[ElementQualityMetric] = []
    if mesh is None:
        issue = QualityGateIssue("error", "mesh.missing", "No mesh is attached to the project.")
        return MeshQualityGateReport(ok=False, issues=(issue,), metadata={"reason": "missing_mesh"})

    points = [tuple(float(v) for v in row) for row in list(getattr(mesh, "nodes", []) or [])]
    cells = [tuple(int(i) for i in cell) for cell in list(getattr(mesh, "cells", []) or [])]
    cell_types = [str(item).lower() for item in list(getattr(mesh, "cell_types", []) or [])]
    volumes: list[float] = []
    aspects: list[float] = []
    bad: list[int] = []
    solid_count = 0

    for idx, cell in enumerate(cells):
        cell_type = cell_types[idx] if idx < len(cell_types) else "unknown"
        if cell_type not in SOLID_CELL_TYPES:
            continue
        solid_count += 1
        volume = _tet_volume(points, cell) if cell_type.startswith("tet") else _hex_volume(points, cell)
        aspect = _aspect_ratio(points, cell)
        if volume is not None:
            volumes.append(float(volume))
        if aspect is not None:
            aspects.append(float(aspect))
        if volume is None or volume <= min_volume or (aspect is not None and aspect > max_aspect_ratio):
            bad.append(idx)
        if len(metrics) < max_metrics:
            metrics.append(ElementQualityMetric(cell_id=idx, cell_type=cell_type, volume=volume, aspect_ratio=aspect))

    if solid_count <= 0:
        issues.append(QualityGateIssue("error", "mesh.no_solid_cells", "3D analysis requires Tet4/Hex8 solid cells."))
    if bad:
        issues.append(
            QualityGateIssue(
                "error",
                "mesh.bad_solid_cells",
                f"{len(bad)} solid cells failed volume/aspect quality checks.",
                metadata={"bad_cell_ids": bad[:50], "min_volume": min_volume, "max_aspect_ratio": max_aspect_ratio},
            )
        )
    summary = solid_mesh_summary(project_or_port)
    ok = bool(solid_count > 0 and not any(item.blocking for item in issues))
    return MeshQualityGateReport(
        ok=ok,
        checked_cell_count=len(cells),
        solid_cell_count=solid_count,
        min_volume=min(volumes) if volumes else None,
        max_aspect_ratio=max(aspects) if aspects else None,
        bad_cell_ids=tuple(bad),
        issues=tuple(issues),
        metrics=tuple(metrics),
        metadata={"solid_mesh": summary.to_dict(), "min_volume_threshold": min_volume, "max_aspect_ratio_threshold": max_aspect_ratio},
    )


def _all_material_records(project: Any) -> dict[str, Any]:
    library = getattr(project, "material_library", None)
    records: dict[str, Any] = {}
    if library is None:
        return records
    for attr in ("soil_materials", "plate_materials", "beam_materials", "interface_materials"):
        value = getattr(library, attr, None)
        if isinstance(value, dict):
            records.update({str(k): v for k, v in value.items()})
    return records


def _has_any(params: dict[str, Any], names: Iterable[str]) -> bool:
    return any(name in params and params[name] not in {None, ""} for name in names)


def _required_parameter_groups(solver_backend: str) -> tuple[tuple[str, ...], ...]:
    backend = str(solver_backend).lower()
    if "mohr" in backend or "nonlinear" in backend or "staged" in backend:
        return (("E", "E_ref", "E50ref"), ("nu", "nu_ur"), ("cohesion", "c", "c_ref"), ("friction_deg", "phi", "phi_deg"))
    return (("E", "E_ref", "E50ref"), ("nu", "nu_ur"))


def evaluate_material_compatibility(project_or_port: Any, *, solver_backend: str = "solid_linear_static_cpu") -> MaterialCompatibilityReport:
    project = _project(project_or_port)
    mapping = material_mapping_summary(project_or_port)
    records = _all_material_records(project)
    issues: list[QualityGateIssue] = []
    incompatible: list[str] = []
    missing = list(mapping.missing_material_ids)
    required = _required_parameter_groups(solver_backend)
    for material_id in mapping.mesh_material_ids:
        record = records.get(str(material_id))
        if record is None:
            if str(material_id) not in missing:
                missing.append(str(material_id))
            continue
        params = dict(getattr(record, "parameters", {}) or {})
        missing_groups = [group for group in required if not _has_any(params, group)]
        if missing_groups:
            incompatible.append(str(material_id))
            issues.append(
                QualityGateIssue(
                    "error",
                    "material.parameters_incomplete",
                    f"Material {material_id!r} lacks parameters required by {solver_backend}.",
                    target=str(material_id),
                    metadata={"required_parameter_groups": [list(group) for group in missing_groups], "model_type": str(getattr(record, "model_type", ""))},
                )
            )
    if missing:
        issues.append(
            QualityGateIssue(
                "error",
                "material.missing_records",
                "Mesh references material IDs that are absent from the material library.",
                metadata={"missing_material_ids": sorted(set(missing))},
            )
        )
    ok = bool(mapping.ok and not any(item.blocking for item in issues))
    return MaterialCompatibilityReport(
        ok=ok,
        solver_backend=str(solver_backend),
        material_ids=tuple(mapping.mesh_material_ids),
        missing_material_ids=tuple(sorted(set(missing))),
        incompatible_material_ids=tuple(sorted(set(incompatible))),
        issues=tuple(issues),
        metadata={"mapping": mapping.to_dict(), "required_parameter_groups": [list(group) for group in required]},
    )


def build_geotechnical_quality_gate(project_or_port: Any, *, solver_backend: str = "solid_linear_static_cpu") -> GeotechnicalQualityGateReport:
    mesh_quality = evaluate_mesh_quality_gate(project_or_port)
    material = evaluate_material_compatibility(project_or_port, solver_backend=solver_backend)
    readiness = build_geotechnical_readiness_report(project_or_port)
    ok = bool(mesh_quality.ok and material.ok and readiness.get("ready", False))
    return GeotechnicalQualityGateReport(
        ok=ok,
        mesh_quality=mesh_quality,
        material_compatibility=material,
        readiness=readiness,
        metadata={"solver_backend": solver_backend},
    )


__all__ = ["build_geotechnical_quality_gate", "evaluate_material_compatibility", "evaluate_mesh_quality_gate"]
