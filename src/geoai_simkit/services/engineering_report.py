from __future__ import annotations

"""Markdown/JSON engineering report exporter for baseline workflows."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass(slots=True)
class EngineeringReportArtifacts:
    contract: str = "geoai_simkit_engineering_report_artifacts_v1"
    markdown_path: str = ""
    json_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "markdown_path": self.markdown_path,
            "json_path": self.json_path,
            "metadata": dict(self.metadata),
        }


def _solver_records(solver_summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row or {}) for row in list(solver_summary.get("phase_records", []) or [])]


def build_engineering_report_payload(project: Any, *, acceptance: dict[str, Any], solver_summary: dict[str, Any], compiler: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    mesh = getattr(project.mesh_model, "mesh_document", None)
    return {
        "contract": "geoai_simkit_engineering_report_payload_v1",
        "project": {
            "name": getattr(project.project_settings, "name", ""),
            "project_id": getattr(project.project_settings, "project_id", ""),
            "release": getattr(project, "metadata", {}).get("release", getattr(project.project_settings, "metadata", {}).get("release", "")),
            "phase_ids": project.phase_ids() if hasattr(project, "phase_ids") else [],
        },
        "mesh": None if mesh is None else {
            "node_count": int(getattr(mesh, "node_count", 0)),
            "cell_count": int(getattr(mesh, "cell_count", 0)),
            "cell_types": sorted({str(v) for v in list(getattr(mesh, "cell_types", []) or [])}),
            "metadata": dict(getattr(mesh, "metadata", {}) or {}),
            "quality": getattr(getattr(mesh, "quality", None), "to_dict", lambda: {})(),
        },
        "validation": dict(validation),
        "compiler": dict(compiler),
        "solver_summary": dict(solver_summary),
        "acceptance": dict(acceptance),
        "result_metrics": {str(k): row.to_dict() if hasattr(row, "to_dict") else dict(row) for k, row in dict(getattr(project.result_store, "engineering_metrics", {}) or {}).items()},
    }


def render_engineering_report_markdown(payload: dict[str, Any]) -> str:
    project = dict(payload.get("project", {}) or {})
    mesh = dict(payload.get("mesh", {}) or {})
    acceptance = dict(payload.get("acceptance", {}) or {})
    solver = dict(payload.get("solver_summary", {}) or {})
    records = _solver_records(solver)
    lines = [
        f"# {project.get('name', 'GeoAI SimKit Engineering Report')}",
        "",
        "## Release Acceptance",
        f"- Status: `{acceptance.get('status', 'unknown')}`",
        f"- Accepted: `{bool(acceptance.get('accepted', False))}`",
        f"- Blockers: `{int(acceptance.get('blocker_count', 0) or 0)}`",
        "",
        "## Model Scope",
        f"- Phases: `{', '.join(project.get('phase_ids', []) or [])}`",
        f"- Release: `{project.get('release', '')}`",
        "",
        "## Mesh",
        f"- Nodes: `{mesh.get('node_count', 0)}`",
        f"- Cells: `{mesh.get('cell_count', 0)}`",
        f"- Cell types: `{', '.join(mesh.get('cell_types', []) or [])}`",
        f"- Production ready: `{dict(mesh.get('metadata', {}) or {}).get('production_ready', False)}`",
        "",
        "## Solver Phase Records",
        "| Phase | Converged | Relative residual | Max displacement | Max settlement |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in records:
        lines.append(
            f"| {row.get('phase_id', '')} | {bool(row.get('converged', False))} | "
            f"{float(row.get('relative_residual_norm', 0.0) or 0.0):.6g} | "
            f"{float(row.get('max_displacement', 0.0) or 0.0):.6g} | "
            f"{float(row.get('max_settlement', 0.0) or 0.0):.6g} |"
        )
    release_105 = dict(payload.get("release_1_0_5", {}) or {})
    if release_105:
        mesh_route = dict(release_105.get("mesh_route", {}) or {})
        k0 = dict(release_105.get("k0", {}) or {})
        mc = dict(release_105.get("mohr_coulomb", {}) or {})
        gui = dict(release_105.get("gui", {}) or {})
        lines.extend([
            "",
            "## 1.0.5 Hardening",
            f"- GUI contract: `{gui.get('contract', '')}`; blockers `{gui.get('blocker_count', 0)}`",
            f"- Mesh route: `{mesh_route.get('selected_backend', '')}`; requested `{mesh_route.get('requested_backend', '')}`; fallback `{mesh_route.get('fallback_used', False)}`",
            f"- K0 states: `{len(k0.get('states', []) or [])}`",
            f"- Mohr-Coulomb phase count: `{len(mc.get('phase_ids', []) or [])}`",
        ])
    findings = list(acceptance.get("findings", []) or [])
    lines.extend(["", "## Findings"])
    if findings:
        for finding in findings:
            lines.append(f"- **{finding.get('severity', '')}** `{finding.get('code', '')}`: {finding.get('message', '')}")
    else:
        lines.append("- No release blockers or warnings.")
    lines.extend(["", "## Limitations", "- This 1.0 Basic workflow is accepted for the built-in linear-static staged demonstration case. Use validated Gmsh/OCC meshing and calibrated constitutive models before using it for certification-grade design."])
    return "\n".join(lines) + "\n"


def export_engineering_report(output_dir: str | Path, payload: dict[str, Any], *, stem: str = "geoai_1_0_engineering_report") -> EngineeringReportArtifacts:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    md_path = root / f"{stem}.md"
    json_path = root / f"{stem}.json"
    md_path.write_text(render_engineering_report_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return EngineeringReportArtifacts(markdown_path=str(md_path), json_path=str(json_path), metadata={"stem": stem})


__all__ = [
    "EngineeringReportArtifacts",
    "build_engineering_report_payload",
    "render_engineering_report_markdown",
    "export_engineering_report",
]
