from __future__ import annotations

"""Dependency preflight checks for the desktop launcher.

The checker is intentionally independent from Qt/PyVista so it can run before
choosing a GUI backend.  It is used by the startup splash dialog, smoke reports,
GUI payloads and release acceptance tests.
"""

from dataclasses import asdict, dataclass
from importlib import import_module
from importlib import metadata
from platform import python_version
from sys import version_info
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class DependencySpec:
    key: str
    label: str
    module: str
    package: str
    group: str
    required: bool = True
    min_version: str | None = None
    purpose: str = ""
    install_hint: str | None = None
    required_attrs: tuple[str, ...] = ()
    required_imports: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    key: str
    label: str
    module: str
    package: str
    group: str
    required: bool
    ok: bool
    installed_version: str | None
    min_version: str | None
    purpose: str
    install_hint: str
    module_file: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DependencyPreflightReport:
    contract: str
    python: dict[str, Any]
    ok: bool
    blocking: bool
    checked_count: int
    required_count: int
    available_required_count: int
    missing_required: list[str]
    missing_optional: list[str]
    checks: list[DependencyCheck]
    install_commands: list[str]
    groups: dict[str, dict[str, Any]]
    next_action: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checks"] = [row.to_dict() for row in self.checks]
        return payload


CORE_DEPENDENCIES: tuple[DependencySpec, ...] = (
    DependencySpec("numpy", "NumPy", "numpy", "numpy", "core", True, "1.24", "numerical arrays", "conda install -c conda-forge numpy scipy  # or: python -m pip install --upgrade --force-reinstall numpy scipy", ("ndarray", "array", "asarray", "zeros")),
    DependencySpec("scipy", "SciPy", "scipy", "scipy", "core", True, "1.10", "sparse solvers and benchmarks", "conda install -c conda-forge scipy  # or: python -m pip install --upgrade scipy", ("sparse", "linalg")),
    DependencySpec("typing_extensions", "typing_extensions", "typing_extensions", "typing_extensions", "core", True, "4.8", "typing compatibility", "python -m pip install --upgrade typing_extensions>=4.8", ("TypedDict",)),
)

GUI_DEPENDENCIES: tuple[DependencySpec, ...] = (
    DependencySpec("pyside6", "PySide6", "PySide6", "PySide6", "desktop_gui", True, "6.5", "six-phase Qt workbench", "conda install -c conda-forge pyside6  # or: python -m pip install --upgrade PySide6>=6.5", required_imports=("PySide6.QtCore", "PySide6.QtWidgets")),
    DependencySpec("qtpy", "QtPy", "qtpy", "QtPy", "desktop_gui", True, "2.4", "Qt abstraction used by PyVistaQt", "conda install -c conda-forge qtpy  # or: python -m pip install QtPy>=2.4"),
    DependencySpec(
        "vtk",
        "VTK",
        "vtk",
        "vtk",
        "three_d_viewport",
        True,
        "9.2",
        "VTK runtime modules required by PyVista. Required before launching the desktop GUI.",
        "conda install -c conda-forge vtk pyvista pyvistaqt  # preferred for conda; do not pip --force-reinstall over conda vtk",
        ("vtkVersion",),
        ("vtkmodules.vtkCommonCore", "vtkmodules.vtkCommonMath", "vtkmodules.vtkCommonDataModel"),
    ),
    DependencySpec(
        "pyvista",
        "PyVista",
        "pyvista",
        "pyvista",
        "three_d_viewport",
        True,
        "0.43",
        "3D visualization and model viewport. Required before launching the desktop GUI.",
        "conda install -c conda-forge vtk pyvista pyvistaqt  # or use a clean pip-only venv",
        ("Plotter", "PolyData", "UnstructuredGrid"),
        ("vtkmodules.vtkCommonMath",),
    ),
    DependencySpec("pyvistaqt", "pyvistaqt", "pyvistaqt", "pyvistaqt", "three_d_viewport", True, "0.11", "Qt integration for PyVista. Required before launching the desktop GUI.", "conda install -c conda-forge pyvistaqt"),
)

MESHING_DEPENDENCIES: tuple[DependencySpec, ...] = (
    DependencySpec("gmsh", "Gmsh", "gmsh", "gmsh", "meshing", True, "4.11", "native OCC/Tet4 production meshing. Required before launching the desktop GUI so meshing tools are always available.", "conda install -c conda-forge gmsh meshio"),
    DependencySpec("meshio", "meshio", "meshio", "meshio", "meshing", True, "5.3", "mesh exchange and physical group import/export. Required before launching the desktop GUI.", "conda install -c conda-forge gmsh meshio"),
)

CAD_DEPENDENCIES: tuple[DependencySpec, ...] = (
    DependencySpec("ocp", "OCP / cadquery-ocp", "OCP", "cadquery-ocp", "native_cad", True, "7.7", "TopoDS_Shape BRep serialization and native topology enumeration", "conda install -c conda-forge ocp  # or: python -m pip install cadquery-ocp>=7.7", required_imports=("OCP.TopoDS", "OCP.BRepTools", "OCP.TopExp", "OCP.STEPControl")),
    DependencySpec("ifcopenshell", "IfcOpenShell", "ifcopenshell", "ifcopenshell", "native_cad", True, "0.8", "IFC product exact solid extraction and representation expansion", "conda install -c conda-forge ifcopenshell  # or: python -m pip install ifcopenshell>=0.8", required_imports=("ifcopenshell.geom",)),
)

REPORTING_DEPENDENCIES: tuple[DependencySpec, ...] = (
    DependencySpec("matplotlib", "Matplotlib", "matplotlib", "matplotlib", "reporting", True, "3.7", "plots and engineering report artifacts", "python -m pip install matplotlib>=3.7"),
    DependencySpec("pillow", "Pillow", "PIL", "pillow", "reporting", True, "10", "image handling for reports and screenshots", "python -m pip install pillow>=10"),
    DependencySpec("pooch", "Pooch", "pooch", "pooch", "reporting", True, "1.8", "dataset/cache utility used by visualization dependencies", "python -m pip install pooch>=1.8"),
    DependencySpec("scooby", "Scooby", "scooby", "scooby", "reporting", True, "0.10", "dependency diagnostics used by PyVista", "python -m pip install scooby>=0.10"),
    DependencySpec("packaging", "Packaging", "packaging", "packaging", "runtime", True, "23", "version parsing and compatibility checks", "python -m pip install packaging>=23"),
    DependencySpec("requests", "Requests", "requests", "requests", "runtime", True, "2.31", "report/export helper dependency", "python -m pip install requests>=2.31"),
    DependencySpec("rich", "Rich", "rich", "rich", "runtime", True, "13", "CLI/report formatting", "python -m pip install rich>=13"),
    DependencySpec("pytest", "pytest", "pytest", "pytest", "verification", True, "8", "runtime smoke and desktop verification tests", "python -m pip install pytest>=8"),
)

OPTIONAL_DEPENDENCIES: tuple[DependencySpec, ...] = (
    DependencySpec("warp", "warp-lang", "warp", "warp-lang", "optional_acceleration", False, None, "CUDA/GPU experimental runtime", "python -m pip install warp-lang"),
)

DEFAULT_DEPENDENCIES: tuple[DependencySpec, ...] = CORE_DEPENDENCIES + GUI_DEPENDENCIES + MESHING_DEPENDENCIES + CAD_DEPENDENCIES + REPORTING_DEPENDENCIES + OPTIONAL_DEPENDENCIES


def _parse_version_tuple(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    parts: list[int] = []
    for chunk in str(value).replace("-", ".").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if digits == "":
            break
        parts.append(int(digits))
    return tuple(parts)


def _version_satisfies(installed: str | None, minimum: str | None) -> bool:
    if not minimum:
        return True
    if not installed:
        return False
    return _parse_version_tuple(installed) >= _parse_version_tuple(minimum)


def _package_version(package: str, module: Any | None = None) -> str | None:
    try:
        return metadata.version(package)
    except Exception:
        value = getattr(module, "__version__", None) if module is not None else None
        return str(value) if value else None


def _validate_required_attrs(module: Any, attrs: tuple[str, ...]) -> str | None:
    """Return a human-readable error when an imported module is only a stub or broken install."""

    missing = [name for name in attrs if not hasattr(module, name)]
    if not missing:
        return None
    location = getattr(module, "__file__", None) or "<unknown>"
    return (
        f"Imported module is missing required API attribute(s): {', '.join(missing)}. "
        f"This usually means the package is corrupted, partially installed, or shadowed by a local file. "
        f"Imported from: {location}"
    )


def _validate_required_imports(imports: tuple[str, ...]) -> str | None:
    failed: list[str] = []
    for name in imports:
        try:
            import_module(name)
        except Exception as exc:
            failed.append(f"{name} ({type(exc).__name__}: {exc})")
    if not failed:
        return None
    return (
        "Required runtime submodule import failed: " + "; ".join(failed) + ". "
        "This usually means the dependency wheel is incomplete, incompatible with this Python/platform, "
        "or was partially installed. Reinstall the package shown in the install hint."
    )


def check_dependency(spec: DependencySpec) -> DependencyCheck:
    module_file: str | None = None
    try:
        module = import_module(spec.module)
        module_file = str(getattr(module, "__file__", "") or "") or None
        installed_version = _package_version(spec.package, module)
        version_ok = _version_satisfies(installed_version, spec.min_version)
        attr_error = _validate_required_attrs(module, spec.required_attrs)
        import_error = _validate_required_imports(spec.required_imports)
        ok = bool(version_ok and attr_error is None and import_error is None)
        if not version_ok:
            error = f"Installed version {installed_version!r} is lower than required {spec.min_version!r}."
        else:
            error = attr_error or import_error
    except Exception as exc:
        installed_version = None
        ok = False
        error = f"{type(exc).__name__}: {exc}"
    return DependencyCheck(
        key=spec.key,
        label=spec.label,
        module=spec.module,
        package=spec.package,
        group=spec.group,
        required=bool(spec.required),
        ok=bool(ok),
        installed_version=installed_version,
        min_version=spec.min_version,
        purpose=spec.purpose,
        install_hint=spec.install_hint or f"python -m pip install {spec.package}",
        module_file=module_file,
        error=error,
    )


def build_dependency_preflight_report(specs: Iterable[DependencySpec] | None = None) -> DependencyPreflightReport:
    checks = [check_dependency(spec) for spec in (tuple(specs) if specs is not None else DEFAULT_DEPENDENCIES)]
    missing_required = [row.key for row in checks if row.required and not row.ok]
    missing_optional = [row.key for row in checks if not row.required and not row.ok]
    install_commands: list[str] = []
    seen_commands: set[str] = set()
    for row in checks:
        if not row.ok and row.install_hint not in seen_commands:
            seen_commands.add(row.install_hint)
            install_commands.append(row.install_hint)
    groups: dict[str, dict[str, Any]] = {}
    for row in checks:
        group = groups.setdefault(row.group, {"ok": True, "required": False, "checks": [], "missing": []})
        group["required"] = bool(group["required"] or row.required)
        group["checks"].append(row.key)
        if not row.ok:
            group["ok"] = False
            group["missing"].append(row.key)
    required_count = sum(1 for row in checks if row.required)
    available_required_count = sum(1 for row in checks if row.required and row.ok)
    ok = not missing_required
    return DependencyPreflightReport(
        contract="geoai_simkit_dependency_preflight_v1",
        python={
            "version": python_version(),
            "ok": version_info >= (3, 10),
            "minimum": "3.10",
        },
        ok=bool(ok),
        blocking=bool(not ok),
        checked_count=len(checks),
        required_count=required_count,
        available_required_count=available_required_count,
        missing_required=missing_required,
        missing_optional=missing_optional,
        checks=checks,
        install_commands=install_commands,
        groups=groups,
        next_action="enter_main_workbench" if ok else "show_missing_dependency_prompt",
    )


def render_dependency_preflight_text(report: DependencyPreflightReport | dict[str, Any] | None = None) -> str:
    if report is None:
        report = build_dependency_preflight_report()
    payload = report.to_dict() if isinstance(report, DependencyPreflightReport) else report
    lines = ["GeoAI SimKit 启动依赖检查", ""]
    lines.append(f"Python: {payload['python']['version']} (minimum {payload['python']['minimum']})")
    lines.append(f"Required: {payload['available_required_count']}/{payload['required_count']} available")
    lines.append(f"Status: {'PASS' if payload['ok'] else 'BLOCKED'}")
    lines.append("")
    for row in payload["checks"]:
        mark = "OK" if row["ok"] else ("BROKEN" if row.get("installed_version") else "MISSING")
        required = "required" if row["required"] else "optional"
        version = row.get("installed_version") or "not installed"
        lines.append(f"[{mark}] {row['label']} ({required}) - {version} - {row['purpose']}")
        if not row.get("ok") and row.get("error"):
            lines.append(f"    reason: {row['error']}")
        if row.get("module_file"):
            lines.append(f"    module: {row['module_file']}")
    if payload.get("install_commands"):
        lines.append("")
        lines.append("Install suggestions:")
        for command in payload["install_commands"]:
            lines.append(f"  {command}")
    return "\n".join(lines)


def is_pyvista_stack_ready() -> tuple[bool, str | None]:
    """Return whether the PyVista/VTK stack is safe to use for the 3D viewport.

    A plain ``import pyvista`` is not enough on conda/pip mixed environments: VTK
    may import but miss compiled submodules such as ``vtkCommonMath``. The GUI
    launcher uses this helper for diagnostics only; startup preflight still
    blocks the main workbench until the complete required stack is healthy.
    """

    required = (
        "vtk",
        "vtkmodules.vtkCommonCore",
        "vtkmodules.vtkCommonMath",
        "vtkmodules.vtkCommonDataModel",
        "pyvista",
        "pyvistaqt",
    )
    for name in required:
        try:
            import_module(name)
        except Exception as exc:
            return False, f"{name}: {type(exc).__name__}: {exc}"
    return True, None


__all__ = [
    "DependencySpec",
    "DependencyCheck",
    "DependencyPreflightReport",
    "build_dependency_preflight_report",
    "check_dependency",
    "render_dependency_preflight_text",
    "is_pyvista_stack_ready",
]
