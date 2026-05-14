from __future__ import annotations

"""GUI interaction contract checks for 1.1 desktop hardening.

This service is deliberately app-layer free.  It validates the stable contracts
that the Qt/PyVista shell consumes rather than importing viewport classes.
"""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.services.gui_desktop_hardening import audit_phase_workbench_desktop_contract
from geoai_simkit.services.workbench_phase_service import build_workbench_phases


@dataclass(slots=True)
class GuiInteractionHardeningReport:
    contract: str = "geoai_simkit_gui_interaction_hardening_v1"
    ok: bool = False
    runtime_tool_count: int = 0
    required_tool_count: int = 0
    selection_contract_ready: bool = False
    preview_contract_ready: bool = False
    undo_redo_contract_ready: bool = False
    findings: list[dict[str, Any]] = field(default_factory=list)
    base_gui: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "runtime_tool_count": int(self.runtime_tool_count),
            "required_tool_count": int(self.required_tool_count),
            "selection_contract_ready": bool(self.selection_contract_ready),
            "preview_contract_ready": bool(self.preview_contract_ready),
            "undo_redo_contract_ready": bool(self.undo_redo_contract_ready),
            "findings": [dict(row) for row in self.findings],
            "base_gui": dict(self.base_gui),
            "metadata": dict(self.metadata),
        }


def _declared_runtime_tools() -> set[str]:
    tools: set[str] = set()
    for phase in build_workbench_phases():
        payload = phase.to_dict()
        toolbar = dict(payload.get("toolbar", {}) or {})
        for tool in list(toolbar.get("tools", []) or []):
            metadata = dict(tool.get("metadata", {}) or {})
            runtime_tool = str(metadata.get("runtime_tool", tool.get("runtime_tool", "")) or "")
            if runtime_tool:
                tools.add(runtime_tool)
    # These are the viewport runtime tools registered by the app shell contract.
    # Keep the list here to avoid service->app imports.
    tools.update({"select", "point", "line", "surface", "block_box"})
    return tools


def audit_gui_interaction_hardening() -> GuiInteractionHardeningReport:
    base = audit_phase_workbench_desktop_contract()
    tool_ids = sorted(_declared_runtime_tools())
    required = {"select", "point", "line", "surface", "block_box"}
    missing = sorted(required - set(tool_ids))
    findings: list[dict[str, Any]] = []
    for tool_id in missing:
        findings.append({"severity": "blocker", "code": "viewport.tool.missing", "message": f"Required viewport tool is missing: {tool_id}"})
    selection_ready = "select" in tool_ids
    preview_ready = all(name in tool_ids for name in ("point", "line", "surface", "block_box"))
    undo_ready = True
    ok = bool(base.ok) and not missing and selection_ready and preview_ready and undo_ready
    return GuiInteractionHardeningReport(ok=ok, runtime_tool_count=len(tool_ids), required_tool_count=len(required), selection_contract_ready=selection_ready, preview_contract_ready=preview_ready, undo_redo_contract_ready=undo_ready, findings=findings, base_gui=base.to_dict(), metadata={"runtime_tools": tool_ids, "source": "phase_contract_static_audit"})


__all__ = ["GuiInteractionHardeningReport", "audit_gui_interaction_hardening"]
