from __future__ import annotations

"""Desktop native runtime verification for OCP/pythonocc/IfcOpenShell.

This module separates *runtime presence* from *native certification*.  A desktop
can have ifcopenshell/OCP installed but still fail exact BRep serialization or
native topology enumeration; the verification report records each gate
independently so acceptance cannot over-claim native capability.
"""

from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any

from geoai_simkit.services.native_brep_serialization import probe_native_brep_capability
from geoai_simkit.services.step_ifc_shape_import import probe_step_ifc_import_capability

NATIVE_RUNTIME_VERIFICATION_CONTRACT = "geoai_simkit_native_runtime_verification_v1"


def _try_import(name: str) -> tuple[bool, str, str]:
    try:
        module = __import__(name, fromlist=["*"])
        version = str(getattr(module, "__version__", ""))
        return True, version, ""
    except Exception as exc:  # pragma: no cover - host dependent
        return False, "", f"{type(exc).__name__}: {exc}"


@dataclass(slots=True)
class NativeRuntimeVerificationReport:
    contract: str = NATIVE_RUNTIME_VERIFICATION_CONTRACT
    ok: bool = False
    status: str = "not_run"
    desktop_runtime_ready: bool = False
    native_brep_certification_possible: bool = False
    exact_step_import_possible: bool = False
    exact_ifc_product_extraction_possible: bool = False
    modules: dict[str, dict[str, Any]] = field(default_factory=dict)
    capability: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "status": self.status,
            "desktop_runtime_ready": bool(self.desktop_runtime_ready),
            "native_brep_certification_possible": bool(self.native_brep_certification_possible),
            "exact_step_import_possible": bool(self.exact_step_import_possible),
            "exact_ifc_product_extraction_possible": bool(self.exact_ifc_product_extraction_possible),
            "modules": self.modules,
            "capability": self.capability,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


def verify_native_desktop_runtime(*, require_native_brep: bool = False, write_json: str | Path | None = None) -> NativeRuntimeVerificationReport:
    module_names = [
        "OCP.TopoDS", "OCP.BRepTools", "OCP.TopExp", "OCP.STEPControl",
        "OCC.Core.TopoDS", "OCC.Core.BRepTools", "OCC.Core.TopExp", "OCC.Core.STEPControl",
        "ifcopenshell", "ifcopenshell.geom", "gmsh", "meshio",
    ]
    modules: dict[str, dict[str, Any]] = {}
    for name in module_names:
        ok, version, error = _try_import(name)
        modules[name] = {"available": ok, "version": version, "error": error}
    brep_cap = probe_native_brep_capability().to_dict()
    step_cap = probe_step_ifc_import_capability().to_dict()
    native_brep_possible = bool(brep_cap.get("native_brep_serialization_possible") and brep_cap.get("native_topology_enumeration_possible"))
    exact_step = bool(step_cap.get("native_step_possible") and native_brep_possible)
    exact_ifc = bool(step_cap.get("ifcopenshell_available"))
    blockers: list[str] = []
    warnings: list[str] = []
    if require_native_brep and not native_brep_possible:
        blockers.append("Native BRep certification was required but TopoDS serialization plus native topology enumeration are not both available.")
    if not exact_ifc:
        warnings.append("IfcOpenShell exact product extraction is unavailable; IFC imports will use surrogate product/bounds extraction when possible.")
    if not exact_step:
        warnings.append("Native STEP TopoDS import/certification is unavailable; STEP imports will use serialized topology references.")
    report = NativeRuntimeVerificationReport(
        ok=not blockers,
        status="native_runtime_verified" if not blockers else "blocked",
        desktop_runtime_ready=bool(modules.get("gmsh", {}).get("available") or modules.get("ifcopenshell", {}).get("available") or modules.get("OCP.TopoDS", {}).get("available") or modules.get("OCC.Core.TopoDS", {}).get("available")),
        native_brep_certification_possible=native_brep_possible,
        exact_step_import_possible=exact_step,
        exact_ifc_product_extraction_possible=exact_ifc,
        modules=modules,
        capability={"native_brep": brep_cap, "step_ifc": step_cap},
        blockers=blockers,
        warnings=warnings,
    )
    if write_json:
        p = Path(write_json); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return report


__all__ = ["NativeRuntimeVerificationReport", "verify_native_desktop_runtime"]
