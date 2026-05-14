from __future__ import annotations

"""Runtime guard for Qt/VTK OpenGL context stability on Windows desktops.

VTK on Win32 can emit ``wglMakeCurrent failed in MakeCurrent(), error: The
operation completed successfully.(code 0)`` when a render is requested after the
Qt widget is hidden, closing, not exposed yet, or when a remote-desktop/GPU
switch invalidates the WGL context.  The guard is intentionally conservative:
it does not try to recover native VTK state in-place; it prevents repeated
renders while the widget/window is not renderable and records a structured
reason for the GUI diagnostics tab.
"""

from dataclasses import dataclass, field
import os
import sys
from typing import Any

OPENGL_CONTEXT_GUARD_CONTRACT = "geoai_simkit_qt_vtk_opengl_context_guard_v1"


@dataclass(slots=True)
class OpenGLContextGuardState:
    enabled: bool = True
    suspended: bool = False
    render_attempts: int = 0
    skipped_renders: int = 0
    failed_renders: int = 0
    last_reason: str = ""
    last_error: str = ""
    hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": OPENGL_CONTEXT_GUARD_CONTRACT,
            "enabled": bool(self.enabled),
            "suspended": bool(self.suspended),
            "render_attempts": int(self.render_attempts),
            "skipped_renders": int(self.skipped_renders),
            "failed_renders": int(self.failed_renders),
            "last_reason": self.last_reason,
            "last_error": self.last_error,
            "hints": list(self.hints),
        }


@dataclass(frozen=True, slots=True)
class QtVTKOpenGLRuntimePolicy:
    contract: str = OPENGL_CONTEXT_GUARD_CONTRACT
    share_opengl_contexts: bool = True
    double_buffer: bool = True
    depth_buffer_size: int = 24
    stencil_buffer_size: int = 8
    samples: int = 0
    swap_interval: int = 0
    windows_wgl_guard: bool = True
    qt_only_env_flag: str = "GEOAI_SIMKIT_DISABLE_PYVISTA"
    software_opengl_env_flag: str = "GEOAI_SIMKIT_QT_OPENGL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "share_opengl_contexts": self.share_opengl_contexts,
            "double_buffer": self.double_buffer,
            "depth_buffer_size": self.depth_buffer_size,
            "stencil_buffer_size": self.stencil_buffer_size,
            "samples": self.samples,
            "swap_interval": self.swap_interval,
            "windows_wgl_guard": self.windows_wgl_guard,
            "qt_only_env_flag": self.qt_only_env_flag,
            "software_opengl_env_flag": self.software_opengl_env_flag,
            "known_issue": "Win32 VTK wglMakeCurrent can fail when rendering after a Qt/VTK widget is hidden, closing, not exposed, or a remote/GPU context is invalidated.",
            "fallbacks": [
                "Skip renders while widget/window is not visible or not exposed.",
                "Suspend rendering after a VTK/OpenGL context failure instead of repeating the warning.",
                "Set GEOAI_SIMKIT_DISABLE_PYVISTA=1 to launch the Qt-only workbench when the workstation OpenGL stack is unstable.",
                "Set GEOAI_SIMKIT_QT_OPENGL=software before launch on problematic RDP/driver setups.",
            ],
        }


def build_default_qt_vtk_opengl_policy() -> QtVTKOpenGLRuntimePolicy:
    return QtVTKOpenGLRuntimePolicy()


def apply_qt_vtk_opengl_policy(QtCore: Any, QtGui: Any, QtWidgets: Any, policy: QtVTKOpenGLRuntimePolicy | None = None) -> dict[str, Any]:
    """Apply Qt OpenGL attributes before creating QApplication.

    The function is best-effort and import-safe.  It returns a diagnostic dict
    so tests and the GUI payload can verify which settings were applied.
    """

    policy = policy or build_default_qt_vtk_opengl_policy()
    applied: list[str] = []
    warnings: list[str] = []

    try:
        attr = getattr(QtCore.Qt.ApplicationAttribute, "AA_ShareOpenGLContexts", None)
        if attr is None:
            attr = getattr(QtCore.Qt, "AA_ShareOpenGLContexts", None)
        if attr is not None and policy.share_opengl_contexts:
            QtWidgets.QApplication.setAttribute(attr, True)
            applied.append("AA_ShareOpenGLContexts")
    except Exception as exc:  # pragma: no cover - depends on Qt build
        warnings.append(f"AA_ShareOpenGLContexts not applied: {type(exc).__name__}: {exc}")

    # Allow an explicit software OpenGL request for RDP/driver setups.  Do not
    # force it by default because native CAD viewports should use hardware GL on
    # healthy workstations.
    requested_opengl = os.environ.get(policy.software_opengl_env_flag, "").strip().lower()
    if requested_opengl in {"software", "desktop", "angle"}:
        attr_name = {
            "software": "AA_UseSoftwareOpenGL",
            "desktop": "AA_UseDesktopOpenGL",
            "angle": "AA_UseOpenGLES",
        }[requested_opengl]
        try:
            attr = getattr(QtCore.Qt.ApplicationAttribute, attr_name, None) or getattr(QtCore.Qt, attr_name, None)
            if attr is not None:
                QtWidgets.QApplication.setAttribute(attr, True)
                applied.append(attr_name)
        except Exception as exc:  # pragma: no cover
            warnings.append(f"{attr_name} not applied: {type(exc).__name__}: {exc}")

    try:
        fmt = QtGui.QSurfaceFormat()
        fmt.setDepthBufferSize(int(policy.depth_buffer_size))
        fmt.setStencilBufferSize(int(policy.stencil_buffer_size))
        fmt.setSamples(int(policy.samples))
        fmt.setSwapInterval(int(policy.swap_interval))
        try:
            fmt.setSwapBehavior(QtGui.QSurfaceFormat.SwapBehavior.DoubleBuffer if policy.double_buffer else QtGui.QSurfaceFormat.SwapBehavior.SingleBuffer)
        except Exception:
            pass
        QtGui.QSurfaceFormat.setDefaultFormat(fmt)
        applied.append("QSurfaceFormat.default")
    except Exception as exc:  # pragma: no cover
        warnings.append(f"QSurfaceFormat not applied: {type(exc).__name__}: {exc}")

    return {
        "contract": policy.contract,
        "platform": sys.platform,
        "applied": applied,
        "warnings": warnings,
        "policy": policy.to_dict(),
    }


def widget_exposure_state(widget: Any) -> dict[str, Any]:
    """Return conservative renderability state for a Qt widget-like object."""

    result: dict[str, Any] = {
        "visible": None,
        "hidden": None,
        "enabled": None,
        "closing": False,
        "window_exposed": None,
        "renderable": True,
        "reason": "renderable",
    }
    checks: list[tuple[str, str, bool]] = [
        ("isVisible", "visible", True),
        ("isHidden", "hidden", False),
        ("isEnabled", "enabled", True),
    ]
    for method, key, expected in checks:
        fn = getattr(widget, method, None)
        if fn is None:
            continue
        try:
            value = bool(fn())
            result[key] = value
            if value != expected:
                result["renderable"] = False
                result["reason"] = f"widget_{key}_{value}"
        except Exception:
            pass
    try:
        closing = bool(getattr(widget, "_closed", False)) or bool(getattr(widget, "_closing", False)) or bool(getattr(widget, "_geoai_closing", False))
        result["closing"] = closing
        if closing:
            result["renderable"] = False
            result["reason"] = "widget_closing"
    except Exception:
        pass
    try:
        window_handle = getattr(widget, "windowHandle", lambda: None)()
        if window_handle is not None:
            exposed = bool(window_handle.isExposed())
            result["window_exposed"] = exposed
            if not exposed:
                result["renderable"] = False
                result["reason"] = "window_not_exposed"
    except Exception:
        pass
    return result


__all__ = [
    "OPENGL_CONTEXT_GUARD_CONTRACT",
    "OpenGLContextGuardState",
    "QtVTKOpenGLRuntimePolicy",
    "apply_qt_vtk_opengl_policy",
    "build_default_qt_vtk_opengl_policy",
    "widget_exposure_state",
]
