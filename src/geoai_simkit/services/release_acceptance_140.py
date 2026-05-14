from __future__ import annotations

"""Release 1.4.0 Beta-2 acceptance gates.

1.4.0 is accepted only when the built-in engineering template catalog exposes
all required demos and every selected template can be loaded, run through the
complete calculation pipeline and export its review bundle.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geoai_simkit.services.demo_templates import TEMPLATE_SPECS


@dataclass(slots=True)
class Release140Finding:
    severity: str
    code: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "code": self.code, "message": self.message, "metadata": dict(self.metadata)}


@dataclass(slots=True)
class Release140AcceptanceReport:
    contract: str = "geoai_simkit_release_1_4_0_acceptance_v1"
    status: str = "pending"
    accepted: bool = False
    template_count: int = 0
    completed_template_count: int = 0
    exported_template_count: int = 0
    required_demo_ids: list[str] = field(default_factory=list)
    completed_demo_ids: list[str] = field(default_factory=list)
    findings: list[Release140Finding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocker_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "blocker")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    def add(self, severity: str, code: str, message: str, **metadata: Any) -> None:
        self.findings.append(Release140Finding(severity=severity, code=code, message=message, metadata=metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "status": self.status,
            "accepted": bool(self.accepted),
            "template_count": int(self.template_count),
            "completed_template_count": int(self.completed_template_count),
            "exported_template_count": int(self.exported_template_count),
            "required_demo_ids": list(self.required_demo_ids),
            "completed_demo_ids": list(self.completed_demo_ids),
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "findings": [f.to_dict() for f in self.findings],
            "metadata": dict(self.metadata),
        }


def _exists(path: Any) -> bool:
    try:
        return bool(path) and Path(str(path)).exists()
    except Exception:
        return False


def audit_release_1_4_0(
    *,
    catalog: dict[str, Any] | None = None,
    template_results: dict[str, Any] | None = None,
    aggregate_artifacts: dict[str, Any] | None = None,
    gui_payload: dict[str, Any] | None = None,
) -> Release140AcceptanceReport:
    required = list(TEMPLATE_SPECS.keys())
    results = dict(template_results or {})
    catalog = dict(catalog or {})
    aggregate_artifacts = dict(aggregate_artifacts or {})
    gui_payload = dict(gui_payload or {})
    report = Release140AcceptanceReport(template_count=len(required), required_demo_ids=required, metadata={"release": "1.4.2a-cad-facade"})

    if catalog.get("contract") not in {"geoai_simkit_engineering_template_catalog_v1", "geoai_simkit_demo_catalog_v1"}:
        report.add("blocker", "catalog.contract_missing", "1.4.0 engineering template catalog is missing or invalid.")
    catalog_ids = {str(row.get("demo_id")) for row in list(catalog.get("templates", catalog.get("demos", [])) or [])}
    missing_from_catalog = sorted(set(required) - catalog_ids)
    if missing_from_catalog:
        report.add("blocker", "catalog.templates_missing", "Engineering template catalog is missing required demos.", missing=missing_from_catalog)
    if catalog.get("template_count", len(catalog_ids)) < len(required):
        report.add("blocker", "catalog.template_count", "Engineering template catalog does not expose all required templates.", template_count=catalog.get("template_count"))

    completed: list[str] = []
    exported: list[str] = []
    for demo_id in required:
        result = dict(results.get(demo_id, {}) or {})
        if not result:
            report.add("blocker", f"template.{demo_id}.missing", f"Template `{demo_id}` was not run.")
            continue
        if not result.get("ok", False):
            report.add("blocker", f"template.{demo_id}.not_ok", f"Template `{demo_id}` complete calculation did not pass.", status=result.get("status"))
            continue
        pipeline = dict(result.get("pipeline", {}) or {})
        if not pipeline.get("ok", False):
            report.add("blocker", f"template.{demo_id}.pipeline", f"Template `{demo_id}` pipeline is not complete.", pipeline=pipeline)
        else:
            completed.append(demo_id)
        acceptance = dict(result.get("acceptance", {}) or {})
        if not acceptance.get("accepted", False):
            report.add("blocker", f"template.{demo_id}.acceptance", f"Template `{demo_id}` acceptance gate did not pass.", acceptance=acceptance)
        artifacts = dict(result.get("artifacts", {}) or {})
        required_artifact_keys = ["project_path", "acceptance_path", "demo_run_path", "vtk_path", "report_markdown_path", "report_json_path", "tutorial_path"]
        missing_artifacts = [key for key in required_artifact_keys if not _exists(artifacts.get(key))]
        if missing_artifacts:
            report.add("blocker", f"template.{demo_id}.artifacts", f"Template `{demo_id}` did not export all required artifacts.", missing=missing_artifacts)
        else:
            exported.append(demo_id)
    report.completed_template_count = len(set(completed))
    report.exported_template_count = len(set(exported))
    report.completed_demo_ids = sorted(set(completed))

    if report.completed_template_count != len(required):
        report.add("blocker", "templates.not_all_completed", "Not all engineering templates completed the calculation workflow.", completed=report.completed_demo_ids)
    if report.exported_template_count != len(required):
        report.add("blocker", "templates.not_all_exported", "Not all engineering templates exported review bundles.", exported=exported)

    if aggregate_artifacts:
        for key in ("catalog_path", "acceptance_path", "summary_path", "tutorial_path"):
            if not _exists(aggregate_artifacts.get(key)):
                report.add("blocker", f"aggregate.{key}.missing", f"Aggregate 1.4.0 artifact `{key}` is missing.")
    else:
        report.add("warning", "aggregate.artifacts_missing", "Aggregate 1.4.0 artifacts were not supplied to acceptance.")

    if gui_payload:
        actions = set(gui_payload.get("demo_center", {}).get("actions", []) or gui_payload.get("actions", []) or [])
        for action in {"load_demo_project", "run_complete_calculation", "export_demo_bundle", "run_all_templates"}:
            if action not in actions:
                report.add("blocker", f"gui.action.{action}.missing", f"GUI action `{action}` is missing from the 1.4.0 demo center.")
        exposed_ids = {str(row.get("demo_id")) for row in list(gui_payload.get("demo_center", {}).get("templates", []) or [])}
        if exposed_ids and set(required) - exposed_ids:
            report.add("blocker", "gui.templates_missing", "GUI demo center does not expose all required templates.", missing=sorted(set(required) - exposed_ids))
    else:
        report.add("warning", "gui.payload_missing", "1.4.0 GUI payload was not supplied to acceptance.")

    report.accepted = report.blocker_count == 0
    report.status = "accepted_1_4_0_beta2" if report.accepted else "blocked_1_4_0_beta2"
    return report


__all__ = ["Release140Finding", "Release140AcceptanceReport", "audit_release_1_4_0"]
