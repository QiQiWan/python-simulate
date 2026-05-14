from __future__ import annotations

"""K0/self-weight initial stress preparation for 1.0.5 workflows."""

from dataclasses import dataclass, field
from math import radians, sin
from typing import Any

from geoai_simkit.geoproject.document import EngineeringMetricRecord
from geoai_simkit.results.result_package import ResultFieldRecord, StageResult


@dataclass(slots=True)
class K0InitialStressReport:
    contract: str = "geoai_simkit_k0_initial_stress_v1"
    ok: bool = False
    phase_id: str = "initial"
    cell_count: int = 0
    stress_state_count: int = 0
    max_vertical_stress: float = 0.0
    default_k0: float = 0.5
    findings: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "phase_id": self.phase_id,
            "cell_count": int(self.cell_count),
            "stress_state_count": int(self.stress_state_count),
            "max_vertical_stress": float(self.max_vertical_stress),
            "default_k0": float(self.default_k0),
            "findings": [dict(row) for row in self.findings],
            "metadata": dict(self.metadata),
        }


def _material_index(project: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    library = getattr(project, "material_library", None)
    for bucket_name in ("soil_materials", "plate_materials", "beam_materials", "interface_materials"):
        out.update(dict(getattr(library, bucket_name, {}) or {}))
    return out


def _unit_weight(material: Any, fallback: float) -> float:
    params = dict(getattr(material, "parameters", {}) or {})
    meta = dict(getattr(material, "metadata", {}) or {})
    original = dict(meta.get("release_1_0_original_unit_weights", {}) or {})
    for key in ("gamma_unsat", "gamma", "gamma_sat", "unit_weight"):
        if key in params and float(params[key]) > 0.0:
            return float(params[key])
        if key in original and float(original[key]) > 0.0:
            return float(original[key])
    return float(fallback)


def _k0(material: Any, default: float) -> float:
    params = dict(getattr(material, "parameters", {}) or {})
    if "K0" in params:
        return max(0.05, min(2.0, float(params["K0"])))
    phi = params.get("phi", params.get("friction_angle", None))
    if phi is None:
        return float(default)
    return max(0.05, min(2.0, 1.0 - sin(radians(float(phi)))))


def _cell_centroid(nodes: list[tuple[float, float, float]], conn: tuple[int, ...] | list[int]) -> tuple[float, float, float]:
    pts = [nodes[int(i)] for i in conn]
    n = max(1, len(pts))
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n)


def apply_k0_initial_stress(
    project: Any,
    *,
    phase_id: str = "initial",
    ground_level: float = 0.0,
    default_unit_weight: float = 18.0,
    default_k0: float = 0.5,
    compression_negative: bool = True,
    write_result_field: bool = True,
) -> K0InitialStressReport:
    """Compute a simple K0 stress field for active soil cells and store it.

    The implementation is intentionally conservative and deterministic: it uses
    mesh cell centroids, material unit weights and Jaky's K0 estimate when a
    friction angle is available.  The field is written to solver metadata and,
    optionally, the initial stage result as a six-component cell stress field.
    """

    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    report = K0InitialStressReport(phase_id=phase_id, default_k0=float(default_k0))
    if mesh is None or int(getattr(mesh, "cell_count", 0) or 0) == 0:
        report.findings.append({"severity": "blocker", "code": "k0.mesh.missing", "message": "No solid mesh is attached."})
        return report
    nodes = [tuple(float(v) for v in row) for row in list(mesh.nodes or [])]
    materials = _material_index(project)
    material_tags = list(dict(getattr(mesh, "cell_tags", {}) or {}).get("material_id", []) or [])
    block_tags = list(dict(getattr(mesh, "cell_tags", {}) or {}).get("block_id", []) or [])
    values: list[float] = []
    entity_ids: list[str] = []
    rows: list[dict[str, Any]] = []
    max_sv = 0.0
    sign = -1.0 if compression_negative else 1.0
    for cid, conn in enumerate(list(mesh.cells or [])):
        centroid = _cell_centroid(nodes, conn)
        material_id = str(material_tags[cid]) if cid < len(material_tags) else ""
        material = materials.get(material_id)
        gamma = _unit_weight(material, default_unit_weight) if material is not None else float(default_unit_weight)
        k0 = _k0(material, default_k0) if material is not None else float(default_k0)
        depth = max(0.0, float(ground_level) - float(centroid[2]))
        sv = gamma * depth
        sh = k0 * sv
        stress = [sign * sh, sign * sh, sign * sv, 0.0, 0.0, 0.0]
        values.extend(stress)
        entity_ids.append(str(cid))
        max_sv = max(max_sv, float(abs(sv)))
        rows.append(
            {
                "cell_id": int(cid),
                "block_id": str(block_tags[cid]) if cid < len(block_tags) else "",
                "material_id": material_id,
                "centroid": [float(v) for v in centroid],
                "depth": float(depth),
                "unit_weight": float(gamma),
                "k0": float(k0),
                "stress": [float(v) for v in stress],
            }
        )
    payload = {
        "contract": "geoai_simkit_k0_initial_stress_payload_v1",
        "phase_id": phase_id,
        "ground_level": float(ground_level),
        "compression_negative": bool(compression_negative),
        "states": rows,
    }
    project.solver_model.metadata["k0_initial_stress"] = payload
    project.metadata["k0_initial_stress"] = {"phase_id": phase_id, "stress_state_count": len(rows), "max_vertical_stress": max_sv}
    if write_result_field:
        stage = project.result_store.phase_results.get(phase_id) or StageResult(stage_id=phase_id)
        stage.add_field(
            ResultFieldRecord(
                name="k0_initial_stress",
                stage_id=phase_id,
                association="cell",
                values=values,
                entity_ids=entity_ids,
                components=6,
                metadata={"unit": getattr(project.project_settings, "stress_unit", "kPa"), "components": ["sxx", "syy", "szz", "txy", "tyz", "txz"], "source": "apply_k0_initial_stress"},
            )
        )
        stage.metrics["k0_max_vertical_stress"] = float(max_sv)
        stage.metadata["k0_initialized"] = True
        project.result_store.phase_results[phase_id] = stage
        mid = f"{phase_id}:k0_max_vertical_stress"
        project.result_store.engineering_metrics[mid] = EngineeringMetricRecord(id=mid, name="k0_max_vertical_stress", value=float(max_sv), unit=getattr(project.project_settings, "stress_unit", "kPa"), phase_id=phase_id, metadata={"source": "apply_k0_initial_stress"})
    report.ok = bool(rows)
    report.cell_count = int(getattr(mesh, "cell_count", len(rows)) or len(rows))
    report.stress_state_count = len(rows)
    report.max_vertical_stress = float(max_sv)
    report.metadata = {"ground_level": float(ground_level), "compression_negative": bool(compression_negative)}
    return report


__all__ = ["K0InitialStressReport", "apply_k0_initial_stress"]
