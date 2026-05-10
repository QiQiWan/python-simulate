from __future__ import annotations

"""Compatibility backend facade for the legacy desktop main window.

The large Qt main window historically imported geometry, meshing, post and
solver implementation modules directly.  This facade centralizes those imports
behind a headless service boundary so architecture checks can keep new GUI code
on the controller/service path while existing GUI workflows remain importable.
"""

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
import os

try:
    from geoai_simkit.geometry.ifc_import import IfcImportOptions, IfcImporter  # type: ignore
    _IFC_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - optional dependency
    IfcImportOptions = None  # type: ignore[assignment]
    IfcImporter = None  # type: ignore[assignment]
    _IFC_IMPORT_ERROR = exc

try:
    from geoai_simkit.geometry.parametric import ParametricPitScene  # type: ignore
except Exception:  # pragma: no cover
    class ParametricPitScene:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            self.parameters = dict(kwargs)

try:
    from geoai_simkit.geometry.mesh_engine import MeshEngine, MeshEngineOptions, normalize_element_family  # type: ignore
except Exception as exc:  # pragma: no cover
    @dataclass(slots=True)
    class MeshEngineOptions:  # type: ignore[no-redef]
        element_family: str = "hex8"
        metadata: dict[str, Any] = field(default_factory=dict)

    class MeshEngine:  # type: ignore[no-redef]
        def __init__(self, options: MeshEngineOptions, progress_callback: Any | None = None) -> None:
            self.options = options
            self.progress_callback = progress_callback

        def mesh_model(self, model: Any) -> Any:
            raise RuntimeError(f"Geometry mesh engine is unavailable: {exc}")

    def normalize_element_family(value: str) -> str:  # type: ignore[no-redef]
        return str(value or "hex8").lower()

try:
    from geoai_simkit.geometry.demo_pit import (  # type: ignore
        build_demo_stages,
        configure_demo_coupling,
        coupling_wizard_summary,
        demo_solver_preset_payload,
        enabled_interface_groups,
        enabled_support_groups,
        enabled_interface_region_overrides,
        explain_interface_policy,
        explain_solver_preset,
        interface_group_options,
        interface_policy_options,
        interface_region_override_options,
        normalize_demo_stage_metadata,
        normalize_solver_preset,
        solver_preset_options,
        summarize_demo_coupling,
        support_group_options,
    )
except Exception:  # pragma: no cover
    def _empty_list(*_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    def _empty_dict(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}

    def _identity(value: Any = None, *_args: Any, **_kwargs: Any) -> Any:
        return value

    build_demo_stages = _empty_list
    configure_demo_coupling = _empty_dict
    coupling_wizard_summary = lambda *_a, **_k: ""
    demo_solver_preset_payload = _empty_dict
    enabled_interface_groups = _empty_list
    enabled_support_groups = _empty_list
    enabled_interface_region_overrides = _empty_list
    explain_interface_policy = lambda *_a, **_k: ""
    explain_solver_preset = lambda *_a, **_k: ""
    interface_group_options = _empty_list
    interface_policy_options = _empty_list
    interface_region_override_options = _empty_list
    normalize_demo_stage_metadata = _identity
    normalize_solver_preset = _identity
    solver_preset_options = _empty_list
    summarize_demo_coupling = _empty_dict
    support_group_options = _empty_list

try:
    from geoai_simkit.geometry.voxelize import VoxelMesher, VoxelizeOptions  # type: ignore
    _VOXEL_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    VoxelMesher = None  # type: ignore[assignment]
    VoxelizeOptions = None  # type: ignore[assignment]
    _VOXEL_IMPORT_ERROR = exc

try:
    from geoai_simkit.geometry.gmsh_mesher import GmshMesher, GmshMesherOptions  # type: ignore
    _GMSH_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    GmshMesher = None  # type: ignore[assignment]
    GmshMesherOptions = None  # type: ignore[assignment]
    _GMSH_IMPORT_ERROR = exc

try:
    from geoai_simkit.materials import registry  # type: ignore
except Exception:  # pragma: no cover
    class _EmptyRegistry:
        def available(self) -> list[str]:
            return []

    registry = _EmptyRegistry()  # type: ignore[assignment]

try:
    from geoai_simkit.post.viewer import PreviewBuilder  # type: ignore
except Exception:  # pragma: no cover
    class PreviewBuilder:  # type: ignore[no-redef]
        def add_model(self, *_args: Any, **_kwargs: Any) -> dict[str, dict[str, object]]:
            return {}


class ExportManager:
    """Small legacy export facade used when the historical exporter is absent."""

    def export(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"ok": False, "status": "export_manager_placeholder", "message": "No exporter backend is installed."}


class QtPyVistaViewportEventBinder:
    """No-op event binder fallback; real GUI integrations can replace it later."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def bind(self) -> None:
        return None

    def detach(self) -> None:
        return None


from geoai_simkit.solver.base import SolverResult, SolverSettings
from geoai_simkit.solver.gpu_runtime import describe_cuda_hardware as _describe_cuda_hardware, detect_cuda_devices as _detect_cuda_devices


def default_thread_count() -> int:
    total = max(1, int(os.cpu_count() or 1))
    return max(1, total - 1)


@dataclass(slots=True)
class BackendComputePreferences:
    backend: str = "reference_cpu"
    profile: str = "cpu-safe"
    device: str = "cpu"
    thread_count: int = 0
    require_warp: bool = False
    warp_hex8_enabled: bool = True
    warp_nonlinear_enabled: bool = True
    warp_full_gpu_linear_solve: bool = False
    warp_gpu_global_assembly: bool = False
    warp_interface_enabled: bool = True
    warp_structural_enabled: bool = True
    warp_unified_block_merge: bool = True
    stage_state_sync: bool = True
    ordering: str = "auto"
    preconditioner: str = "auto"
    solver_strategy: str = "auto"
    warp_preconditioner: str = "diag"
    iterative_tolerance: float = 1.0e-10
    iterative_maxiter: int = 2000
    block_size: int = 3
    allowed_gpu_devices: list[str] = field(default_factory=list)

    def resolved_device(self, cuda_available: bool = False) -> str:
        value = str(self.device or "cpu")
        if value in {"auto-best", "auto-round-robin"}:
            return "cuda:0" if cuda_available else "cpu"
        if value.startswith("cuda") and not cuda_available:
            return "cpu"
        return value

    def resolved_thread_count(self, cpu_total: int | None = None) -> int:
        if int(self.thread_count or 0) > 0:
            return int(self.thread_count)
        total = max(1, int(cpu_total or os.cpu_count() or 1))
        return max(1, total - 1)

    def to_metadata(self, *, cuda_available: bool = False) -> dict[str, Any]:
        return {
            "compute_profile": self.profile,
            "backend": self.backend,
            "device": self.resolved_device(cuda_available),
            "thread_count": self.resolved_thread_count(None),
            "require_warp": bool(self.require_warp),
            "ordering": self.ordering,
            "preconditioner": self.preconditioner,
            "solver_strategy": self.solver_strategy,
            "allowed_gpu_devices": list(self.allowed_gpu_devices),
        }

    def summary(self, *, cpu_total: int | None = None, cuda_available: bool = False) -> str:
        return (
            f"profile={self.profile}, backend={self.backend}, "
            f"device={self.resolved_device(cuda_available)}, "
            f"threads={self.resolved_thread_count(cpu_total)}"
        )


def recommended_compute_preferences(profile: str = "cpu-safe", *, cuda_available: bool = False, cpu_total: int | None = None) -> BackendComputePreferences:
    total = max(1, int(cpu_total or os.cpu_count() or 1))
    if profile == "gpu-throughput" and cuda_available:
        return BackendComputePreferences(backend="warp", profile=profile, device="auto-best", thread_count=max(1, total - 1), require_warp=True)
    if profile == "cpu-throughput":
        return BackendComputePreferences(backend="reference_cpu", profile=profile, device="cpu", thread_count=max(1, total))
    return BackendComputePreferences(backend="reference_cpu", profile=profile or "cpu-safe", device="cpu", thread_count=max(1, total - 1))


def detect_cuda_devices() -> list[Any]:
    devices: list[Any] = []
    for idx, item in enumerate(_detect_cuda_devices() or []):
        if isinstance(item, dict):
            alias = str(item.get("alias") or item.get("name") or f"cuda:{idx}")
            devices.append(SimpleNamespace(alias=alias, name=str(item.get("name", alias)), memory_total=int(item.get("memory_total", 0) or 0)))
        else:
            alias = str(getattr(item, "alias", getattr(item, "name", f"cuda:{idx}")))
            devices.append(SimpleNamespace(alias=alias, name=str(getattr(item, "name", alias)), memory_total=int(getattr(item, "memory_total", 0) or 0)))
    return devices


def describe_cuda_hardware() -> str:
    info = _describe_cuda_hardware()
    if isinstance(info, dict):
        return f"CUDA enabled={info.get('enabled')} available={info.get('available')} devices={info.get('device_count', 0)}"
    return str(info)


class WarpBackend:
    """Compatibility solver backend used by the legacy GUI worker.

    It intentionally delegates no heavy GPU work.  The modular solver backends
    are available through ``modules.fem_solver`` and workflow services; this
    shim keeps the old GUI import path alive until the main window is fully
    slimmed down.
    """

    def solve(self, model: Any, settings: SolverSettings, progress_callback: Any | None = None, cancel_check: Any | None = None) -> SolverResult:
        if callable(progress_callback):
            progress_callback({"phase": "compat", "value": 100, "message": "Compatibility GUI solver path completed."})
        if callable(cancel_check) and cancel_check():
            return SolverResult(converged=False, status="cancelled", iterations=0, metadata={"backend": "gui_compat"})
        return SolverResult(converged=True, status="compatibility_result", iterations=0, metadata={"backend": "gui_compat", "settings": settings.metadata})


__all__ = [
    "BackendComputePreferences",
    "ExportManager",
    "GmshMesher",
    "GmshMesherOptions",
    "IfcImportOptions",
    "IfcImporter",
    "MeshEngine",
    "MeshEngineOptions",
    "ParametricPitScene",
    "PreviewBuilder",
    "QtPyVistaViewportEventBinder",
    "SolverSettings",
    "VoxelMesher",
    "VoxelizeOptions",
    "WarpBackend",
    "_GMSH_IMPORT_ERROR",
    "_IFC_IMPORT_ERROR",
    "_VOXEL_IMPORT_ERROR",
    "build_demo_stages",
    "configure_demo_coupling",
    "coupling_wizard_summary",
    "default_thread_count",
    "demo_solver_preset_payload",
    "describe_cuda_hardware",
    "detect_cuda_devices",
    "enabled_interface_groups",
    "enabled_interface_region_overrides",
    "enabled_support_groups",
    "explain_interface_policy",
    "explain_solver_preset",
    "interface_group_options",
    "interface_policy_options",
    "interface_region_override_options",
    "normalize_demo_stage_metadata",
    "normalize_element_family",
    "normalize_solver_preset",
    "recommended_compute_preferences",
    "registry",
    "solver_preset_options",
    "summarize_demo_coupling",
    "support_group_options",
]
