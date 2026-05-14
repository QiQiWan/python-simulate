from __future__ import annotations

"""Release 1.3.0 beta acceptance audit.

1.3.0 is the first engineering-beta workflow: it must expose a one-click demo,
run the complete calculation chain and export the review/report bundle from the
six-phase workbench.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geoai_simkit.services.release_acceptance_124 import audit_release_1_2_4


@dataclass(slots=True)
class Release130Finding:
    severity: str
    code: str
    message: str
    recommendation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "recommendation": self.recommendation,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class Release130AcceptanceReport:
    contract: str = "geoai_simkit_release_1_3_0_acceptance_v1"
    status: str = "unknown"
    accepted: bool = False
    findings: list[Release130Finding] = field(default_factory=list)
    release_1_2_4: dict[str, Any] = field(default_factory=dict)
    demo: dict[str, Any] = field(default_factory=dict)
    pipeline: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    gui_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocker_count(self) -> int:
        return sum(1 for row in self.findings if row.severity == "blocker")

    @property
    def warning_count(self) -> int:
        return sum(1 for row in self.findings if row.severity in {"warning", "risk"})

    def add(self, severity: str, code: str, message: str, recommendation: str = "", **metadata: Any) -> None:
        self.findings.append(Release130Finding(str(severity), str(code), str(message), str(recommendation), dict(metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "status": self.status,
            "accepted": bool(self.accepted),
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "findings": [row.to_dict() for row in self.findings],
            "release_1_2_4": dict(self.release_1_2_4),
            "demo": dict(self.demo),
            "pipeline": dict(self.pipeline),
            "artifacts": dict(self.artifacts),
            "gui_payload": dict(self.gui_payload),
            "metadata": dict(self.metadata),
        }


def _payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    if isinstance(value, dict):
        return dict(value)
    return {"value": value}


def _path_exists(value: Any) -> bool:
    if value in {None, ""}:
        return False
    try:
        return Path(str(value)).exists()
    except Exception:
        return False


def audit_release_1_3_0(
    project: Any,
    *,
    pipeline: Any | None = None,
    artifacts: Any | None = None,
    gui_payload: Any | None = None,
    tutorial_path: str | Path | None = None,
) -> Release130AcceptanceReport:
    newton = dict(getattr(project.solver_model, "metadata", {}).get("last_global_mohr_coulomb_newton_solve", {}) or {})
    base = audit_release_1_2_4(project, newton_summary=newton, tutorial_path=tutorial_path)
    pipeline_payload = dict(getattr(project, "metadata", {}).get("release_1_3_0_pipeline", {}) or {}) if pipeline is None else _payload(pipeline)
    artifacts_payload = dict(getattr(project, "metadata", {}).get("release_1_3_0_artifacts", {}) or {}) if artifacts is None else _payload(artifacts)
    gui_payload_dict = dict(getattr(project, "metadata", {}).get("release_1_3_0_gui_payload", {}) or {}) if gui_payload is None else _payload(gui_payload)
    demo_payload = dict(getattr(project, "metadata", {}).get("release_1_3_0_demo", {}) or {})
    report = Release130AcceptanceReport(
        release_1_2_4=base.to_dict(),
        demo=demo_payload,
        pipeline=pipeline_payload,
        artifacts=artifacts_payload,
        gui_payload=gui_payload_dict,
        metadata={"release": getattr(project, "metadata", {}).get("release", "")},
    )
    for finding in base.findings:
        severity = finding.severity
        if finding.code in {"gmsh_native_exchange.fallback", "1_1_3.mesh.gmsh_occ_project_fallback", "1_1_3.1_0_5.mesh.route.fallback_used"}:
            severity = "warning"
        report.add(severity, f"1_2_4.{finding.code}", finding.message, finding.recommendation, **finding.metadata)
    if not base.accepted:
        report.add("blocker", "base_1_2_4.not_accepted", "Underlying 1.2.4 acceptance did not pass.")
    if demo_payload.get("demo_id") != "foundation_pit_3d_beta":
        report.add("blocker", "demo.id_missing", "1.3.0 beta demo metadata is missing or unexpected.")
    if not demo_payload.get("one_click_load", False):
        report.add("blocker", "demo.one_click_load_missing", "Demo is not marked as one-click loadable in metadata.")
    if not demo_payload.get("complete_calculation", False):
        report.add("blocker", "demo.complete_calculation_missing", "Demo is not marked as complete-calculation capable.")
    if not pipeline_payload:
        report.add("blocker", "pipeline.missing", "Complete demo calculation pipeline report is missing.")
    elif not pipeline_payload.get("ok", False):
        blocked_steps = [row for row in list(pipeline_payload.get("steps", []) or []) if row.get("status") != "done"]
        report.add("blocker", "pipeline.not_ok", "Complete demo calculation pipeline did not finish all steps.", blocked_steps=blocked_steps)
    else:
        step_keys = {str(row.get("key")) for row in list(pipeline_payload.get("steps", []) or [])}
        expected = {"load_demo", "geology_structure", "mesh", "compile", "solve", "hydro_contact", "results_export"}
        missing = sorted(expected - step_keys)
        if missing:
            report.add("blocker", "pipeline.missing_steps", "Complete demo calculation pipeline is missing required steps.", missing=missing)
    required_artifacts = [
        "project_path",
        "validation_path",
        "compiler_path",
        "global_newton_path",
        "acceptance_path",
        "result_viewer_path",
        "vtk_path",
        "report_markdown_path",
        "report_json_path",
        "tutorial_path",
        "demo_run_path",
    ]
    missing_artifacts = [key for key in required_artifacts if not _path_exists(artifacts_payload.get(key))]
    if missing_artifacts:
        report.add("blocker", "artifacts.missing", "One-click demo did not export all required artifacts.", missing=missing_artifacts)
    if gui_payload_dict:
        actions = set(gui_payload_dict.get("demo_center", {}).get("actions", []) or gui_payload_dict.get("actions", []) or [])
        for action in {"load_demo_project", "run_complete_calculation", "export_demo_bundle"}:
            if action not in actions:
                report.add("blocker", f"gui.action.{action}.missing", f"GUI one-click demo action `{action}` is missing.")
    else:
        report.add("warning", "gui_payload.missing", "1.3.0 GUI payload was not supplied to acceptance.")
    if tutorial_path is not None and not Path(tutorial_path).exists():
        report.add("warning", "docs.tutorial_missing", "1.3.0 tutorial artifact was requested but not found.")
    report.accepted = report.blocker_count == 0
    report.status = "accepted_1_3_0_beta" if report.accepted else "blocked_1_3_0_beta"
    return report


__all__ = ["Release130Finding", "Release130AcceptanceReport", "audit_release_1_3_0"]
