from __future__ import annotations

"""Work-plane helpers for reliable mouse-to-world modeling in 3D viewports.

The classes in this module are intentionally independent of Qt and PyVista so
that interactive tools can be tested without a GUI.  GUI adapters can keep a
``WorkPlaneController`` instance and ask it to project a picked/estimated point
onto the current modeling plane before forwarding a ``ToolEvent`` to the
``ViewportToolRuntime``.
"""

from dataclasses import dataclass, field
from math import sqrt
from typing import Any

from geoai_simkit.contracts.viewport import WorkPlane

Vector3 = tuple[float, float, float]


def _dot(a: Vector3, b: Vector3) -> float:
    return float(a[0] * b[0] + a[1] * b[1] + a[2] * b[2])


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return (float(a[0] - b[0]), float(a[1] - b[1]), float(a[2] - b[2]))


def _add(a: Vector3, b: Vector3) -> Vector3:
    return (float(a[0] + b[0]), float(a[1] + b[1]), float(a[2] + b[2]))


def _mul(a: Vector3, s: float) -> Vector3:
    return (float(a[0] * s), float(a[1] * s), float(a[2] * s))


def _norm(a: Vector3) -> float:
    return sqrt(max(_dot(a, a), 0.0))


def _normalize(a: Vector3, fallback: Vector3 = (0.0, 1.0, 0.0)) -> Vector3:
    length = _norm(a)
    if length <= 1.0e-12:
        return fallback
    return (float(a[0] / length), float(a[1] / length), float(a[2] / length))


def project_point_to_plane(point: Vector3, plane: WorkPlane) -> Vector3:
    """Return the orthogonal projection of ``point`` onto ``plane``."""

    origin = tuple(float(v) for v in plane.origin)  # type: ignore[assignment]
    normal = _normalize(tuple(float(v) for v in plane.normal))  # type: ignore[arg-type]
    vec = _sub(tuple(float(v) for v in point), origin)  # type: ignore[arg-type]
    return _sub(tuple(float(v) for v in point), _mul(normal, _dot(vec, normal)))  # type: ignore[arg-type]


def ray_plane_intersection(origin: Vector3, direction: Vector3, plane: WorkPlane) -> Vector3 | None:
    """Intersect a ray and a work plane.

    Returns ``None`` when the ray is almost parallel to the plane.
    """

    ray_origin = tuple(float(v) for v in origin)  # type: ignore[assignment]
    ray_dir = _normalize(tuple(float(v) for v in direction))  # type: ignore[arg-type]
    plane_origin = tuple(float(v) for v in plane.origin)  # type: ignore[assignment]
    normal = _normalize(tuple(float(v) for v in plane.normal))  # type: ignore[arg-type]
    denom = _dot(ray_dir, normal)
    if abs(denom) <= 1.0e-12:
        return None
    t = _dot(_sub(plane_origin, ray_origin), normal) / denom
    return _add(ray_origin, _mul(ray_dir, t))


@dataclass(slots=True)
class WorkPlaneController:
    """Track and apply the active modeling work plane.

    Default plane is XZ, matching the existing geotechnical section-oriented
    creation tools where ``y`` is the out-of-plane direction.
    """

    active: WorkPlane = field(default_factory=WorkPlane)
    mode: str = "xz"
    metadata: dict[str, Any] = field(default_factory=dict)

    def set_named_plane(self, name: str, *, offset: float = 0.0) -> WorkPlane:
        key = str(name).strip().lower()
        if key in {"xz", "section", "front"}:
            self.active = WorkPlane(origin=(0.0, float(offset), 0.0), normal=(0.0, 1.0, 0.0), x_axis=(1.0, 0.0, 0.0), metadata={"name": "xz"})
            self.mode = "xz"
        elif key in {"xy", "plan", "top"}:
            self.active = WorkPlane(origin=(0.0, 0.0, float(offset)), normal=(0.0, 0.0, 1.0), x_axis=(1.0, 0.0, 0.0), metadata={"name": "xy"})
            self.mode = "xy"
        elif key in {"yz", "side"}:
            self.active = WorkPlane(origin=(float(offset), 0.0, 0.0), normal=(1.0, 0.0, 0.0), x_axis=(0.0, 1.0, 0.0), metadata={"name": "yz"})
            self.mode = "yz"
        else:
            raise ValueError(f"Unsupported work plane: {name}")
        return self.active

    def set_from_surface(self, origin: Vector3, normal: Vector3, *, x_axis: Vector3 = (1.0, 0.0, 0.0), name: str = "surface") -> WorkPlane:
        self.active = WorkPlane(origin=tuple(map(float, origin)), normal=_normalize(tuple(map(float, normal))), x_axis=_normalize(tuple(map(float, x_axis)), (1.0, 0.0, 0.0)), metadata={"name": name})
        self.mode = name
        return self.active

    def project(self, point: Vector3) -> Vector3:
        return project_point_to_plane(point, self.active)

    def intersect_ray(self, origin: Vector3, direction: Vector3) -> Vector3 | None:
        return ray_plane_intersection(origin, direction, self.active)

    def to_dict(self) -> dict[str, object]:
        return {"mode": self.mode, "active": self.active.to_dict(), "metadata": {"contract": "work_plane_controller_v1", **dict(self.metadata)}}


__all__ = ["Vector3", "WorkPlaneController", "project_point_to_plane", "ray_plane_intersection"]
