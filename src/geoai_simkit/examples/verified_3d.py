from __future__ import annotations

"""Verified headless 3D geotechnical example suite.

The examples are intentionally small and deterministic so they can run in CI
without Gmsh/PyVista.  They exercise the production module chain: STL surface
import, Tet4 volume meshing fallback, quality/material gates, project solve and
typed workflow artifact manifest generation.
"""

from pathlib import Path
from typing import Any

from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.modules import geology_import, geotechnical, meshing
from geoai_simkit.services import build_geotechnical_quality_gate, run_project_workflow


def write_tetra_stl(path: str | Path, *, dx: float = 0.0, name: str = "tetra") -> Path:
    target = Path(path)

    def p(x: float, y: float, z: float) -> str:
        return f"{x + dx:g} {y:g} {z:g}"

    target.write_text(
        f"""
solid {name}
facet normal 0 0 1
 outer loop
  vertex {p(0, 0, 0)}
  vertex {p(1, 0, 0)}
  vertex {p(0, 1, 0)}
 endloop
endfacet
facet normal 0 -1 0
 outer loop
  vertex {p(0, 0, 0)}
  vertex {p(0, 0, 1)}
  vertex {p(1, 0, 0)}
 endloop
endfacet
facet normal 1 1 1
 outer loop
  vertex {p(1, 0, 0)}
  vertex {p(0, 0, 1)}
  vertex {p(0, 1, 0)}
 endloop
endfacet
facet normal -1 0 0
 outer loop
  vertex {p(0, 1, 0)}
  vertex {p(0, 0, 1)}
  vertex {p(0, 0, 0)}
 endloop
endfacet
endsolid {name}
""".strip(),
        encoding="utf-8",
    )
    return target


def build_tetra_column_project(workdir: str | Path, *, material_id: str = "rock") -> GeoProjectDocument:
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    stl = write_tetra_stl(root / "tetra_column.stl", name="tetra_column")
    project = GeoProjectDocument.from_stl_geology(stl, options={"name": "verified-tetra-column", "material_id": material_id})
    meshing.generate_project_mesh(project, mesh_kind="gmsh_tet4_from_stl")
    project.populate_default_framework_content()
    return project


def build_multi_region_project(workdir: str | Path) -> GeoProjectDocument:
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    a = write_tetra_stl(root / "region_clay.stl", dx=0.0, name="region_clay")
    b = write_tetra_stl(root / "region_sand.stl", dx=1.0, name="region_sand")
    project = GeoProjectDocument.from_stl_geology(a, options={"name": "verified-multi-region", "material_id": "clay"})
    geology_import.import_stl_into_project(project, b, {"name": "region_sand", "material_id": "sand"})
    meshing.generate_project_mesh(project, mesh_kind="conformal_tet4_from_stl_regions")
    project.populate_default_framework_content()
    return project


def run_verified_tetra_column(workdir: str | Path, *, solver_backend: str = "solid_linear_static_cpu") -> dict[str, Any]:
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    stl = write_tetra_stl(root / "tetra_column.stl", name="tetra_column")
    project = GeoProjectDocument.from_stl_geology(stl, options={"name": "verified-tetra-column", "material_id": "rock"})
    project.populate_default_framework_content()
    workflow = run_project_workflow(project, mesh_kind="gmsh_tet4_from_stl", solver_backend=solver_backend, summarize=True, metadata={"workflow_id": "verified_tetra_column"})
    quality = build_geotechnical_quality_gate(project, solver_backend=solver_backend).to_dict()
    return {
        "ok": bool(quality["ok"] and workflow.ok),
        "quality_gate": quality,
        "workflow": workflow.to_dict(),
        "geotechnical_state": geotechnical.geotechnical_state(project),
    }


def run_verified_multi_region(workdir: str | Path, *, solver_backend: str = "staged_mohr_coulomb_cpu") -> dict[str, Any]:
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    a = write_tetra_stl(root / "region_clay.stl", dx=0.0, name="region_clay")
    b = write_tetra_stl(root / "region_sand.stl", dx=1.0, name="region_sand")
    project = GeoProjectDocument.from_stl_geology(a, options={"name": "verified-multi-region", "material_id": "clay"})
    geology_import.import_stl_into_project(project, b, {"name": "region_sand", "material_id": "sand"})
    project.populate_default_framework_content()
    workflow = run_project_workflow(project, mesh_kind="conformal_tet4_from_stl_regions", solver_backend=solver_backend, summarize=True, metadata={"workflow_id": "verified_multi_region"})
    quality = build_geotechnical_quality_gate(project, solver_backend=solver_backend).to_dict()
    return {
        "ok": bool(quality["ok"] and workflow.ok),
        "quality_gate": quality,
        "workflow": workflow.to_dict(),
        "geotechnical_state": geotechnical.geotechnical_state(project),
    }


__all__ = [
    "build_multi_region_project",
    "build_tetra_column_project",
    "run_verified_multi_region",
    "run_verified_tetra_column",
    "write_tetra_stl",
]
