from __future__ import annotations

"""Headless GUI hardening checks for the phase workbench.

The checks in this module intentionally avoid importing Qt or PyVista.  They
validate the contracts that the desktop shell consumes: phase definitions,
ribbon action routes, release showcase payloads and environment readiness.  The
same report can be displayed in the GUI and used by CI on headless runners.
"""

from dataclasses import dataclass, field
from typing import Any
import importlib.util
import os

from geoai_simkit.services.workbench_phase_service import build_workbench_phases, phase_workbench_ui_state


@dataclass(slots=True)
class GuiHardeningFinding:
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
class GuiHardeningReport:
    contract: str = "geoai_simkit_gui_desktop_hardening_v1"
    ok: bool = False
    display_mode: str = "headless"
    phase_count: int = 0
    tool_count: int = 0
    routed_tool_count: int = 0
    optional_runtime: dict[str, bool] = field(default_factory=dict)
    findings: list[GuiHardeningFinding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocker_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "blocker")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.findings if item.severity in {"warning", "risk"})

    def add(self, severity: str, code: str, message: str, recommendation: str = "", **metadata: Any) -> None:
        self.findings.append(GuiHardeningFinding(severity, code, message, recommendation, dict(metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "display_mode": self.display_mode,
            "phase_count": int(self.phase_count),
            "tool_count": int(self.tool_count),
            "routed_tool_count": int(self.routed_tool_count),
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "optional_runtime": dict(self.optional_runtime),
            "findings": [item.to_dict() for item in self.findings],
            "metadata": dict(self.metadata),
        }


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or os.environ.get("QT_QPA_PLATFORM") == "offscreen")


def audit_phase_workbench_desktop_contract(*, expected_phase_count: int = 6) -> GuiHardeningReport:
    """Validate desktop-shell contracts without requiring a GUI display."""

    state = phase_workbench_ui_state()
    phase_specs = list(build_workbench_phases())
    phases = [phase.to_dict() for phase in phase_specs]
    report = GuiHardeningReport(
        phase_count=len(phases),
        display_mode="desktop" if _has_display() else "headless",
        optional_runtime={
            "PySide6": _module_available("PySide6"),
            "pyvista": _module_available("pyvista"),
            "pyvistaqt": _module_available("pyvistaqt"),
        },
        metadata={"state_contract": state.get("contract", ""), "active_phase": state.get("active_phase", "")},
    )
    if len(phases) != int(expected_phase_count):
        report.add("blocker", "gui.phase_count", f"Expected {expected_phase_count} phase(s), found {len(phases)}.", "Regenerate workbench phase definitions.")

    tool_count = 0
    routed = 0
    missing_routes: list[str] = []
    seen_phase_ids: set[str] = set()
    for phase in phases:
        phase_id = str(phase.get("key", phase.get("id", "")))
        if not phase_id:
            report.add("blocker", "gui.phase_id.empty", "A workbench phase has no id.")
        if phase_id in seen_phase_ids:
            report.add("blocker", "gui.phase_id.duplicate", f"Duplicate phase id: {phase_id}.")
        seen_phase_ids.add(phase_id)
        toolbar = dict(phase.get("toolbar", {}) or {})
        for tool in list(toolbar.get("tools", []) or []):
            tool_count += 1
            tool_id = str(tool.get("key", tool.get("id", "")))
            metadata = dict(tool.get("metadata", {}) or {})
            runtime_tool = str(metadata.get("runtime_tool", tool.get("runtime_tool", "")) or "")
            action_id = str(tool.get("command", tool.get("action", tool.get("action_id", ""))) or "")
            if runtime_tool or action_id:
                routed += 1
            else:
                missing_routes.append(tool_id or f"{phase_id}:tool_{tool_count}")
    report.tool_count = tool_count
    report.routed_tool_count = routed
    if missing_routes:
        report.add(
            "blocker",
            "gui.tool_route.missing",
            f"{len(missing_routes)} ribbon tool(s) have no runtime/action route.",
            "Map each phase ribbon tool to a runtime tool or controller action.",
            tools=missing_routes[:20],
        )
    if not report.optional_runtime.get("PySide6", False):
        report.add("warning", "gui.qt.optional_missing", "PySide6 is not installed in this environment.", "Install GUI extras for desktop validation.")
    if not report.optional_runtime.get("pyvista", False):
        report.add("warning", "gui.pyvista.optional_missing", "PyVista is not installed in this environment.", "Install visualization extras for 3D viewport validation.")
    report.ok = report.blocker_count == 0
    return report


__all__ = ["GuiHardeningFinding", "GuiHardeningReport", "audit_phase_workbench_desktop_contract"]
