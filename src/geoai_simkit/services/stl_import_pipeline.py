from __future__ import annotations

"""P3 STL import/repair/volume-mesh pipeline used by the phase workbench.

The GUI can wrap this as a wizard, while tests and scripts can run it headless.
It intentionally coordinates existing production pieces instead of duplicating
STL parsing, repair, or meshing logic.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from geoai_simkit.geometry.stl_loader import STLImportOptions, load_stl_geology


@dataclass(slots=True)
class STLImportWizardOptions:
    name: str | None = None
    unit_scale: float = 1.0
    merge_tolerance: float = 1.0e-9
    material_id: str = "imported_geology"
    role: str = "geology_surface"
    vertical_axis: str = "z"
    flip_normals: bool = False
    center_to_origin: bool = False
    repair: bool = True
    fill_holes: bool = True
    orient_normals: bool = True
    max_hole_edges: int = 64
    generate_volume_mesh: bool = False
    volume_mesh_kind: str = "voxel_hex8_from_stl"
    volume_mesh_options: dict[str, Any] = field(default_factory=dict)
    replace: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "STLImportWizardOptions":
        data = dict(data or {})
        return cls(
            name=None if data.get("name") is None else str(data.get("name")),
            unit_scale=float(data.get("unit_scale", 1.0)),
            merge_tolerance=float(data.get("merge_tolerance", 1.0e-9)),
            material_id=str(data.get("material_id", "imported_geology")),
            role=str(data.get("role", "geology_surface")),
            vertical_axis=str(data.get("vertical_axis", "z")),
            flip_normals=bool(data.get("flip_normals", False)),
            center_to_origin=bool(data.get("center_to_origin", False)),
            repair=bool(data.get("repair", True)),
            fill_holes=bool(data.get("fill_holes", True)),
            orient_normals=bool(data.get("orient_normals", True)),
            max_hole_edges=int(data.get("max_hole_edges", 64)),
            generate_volume_mesh=bool(data.get("generate_volume_mesh", False)),
            volume_mesh_kind=str(data.get("volume_mesh_kind", "voxel_hex8_from_stl")),
            volume_mesh_options=dict(data.get("volume_mesh_options", {}) or {}),
            replace=bool(data.get("replace", False)),
            metadata=dict(data.get("metadata", {}) or {}),
        )

    def to_loader_options(self) -> STLImportOptions:
        return STLImportOptions(
            name=self.name,
            unit_scale=self.unit_scale,
            merge_tolerance=self.merge_tolerance,
            role=self.role,
            material_id=self.material_id,
            vertical_axis=self.vertical_axis,
            flip_normals=self.flip_normals,
            center_to_origin=self.center_to_origin,
            metadata={"source": "stl_import_wizard", **dict(self.metadata)},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit_scale": self.unit_scale,
            "merge_tolerance": self.merge_tolerance,
            "material_id": self.material_id,
            "role": self.role,
            "vertical_axis": self.vertical_axis,
            "flip_normals": self.flip_normals,
            "center_to_origin": self.center_to_origin,
            "repair": self.repair,
            "fill_holes": self.fill_holes,
            "orient_normals": self.orient_normals,
            "max_hole_edges": self.max_hole_edges,
            "generate_volume_mesh": self.generate_volume_mesh,
            "volume_mesh_kind": self.volume_mesh_kind,
            "volume_mesh_options": dict(self.volume_mesh_options),
            "replace": self.replace,
            "metadata": dict(self.metadata),
        }


def classify_stl_status(quality: Any, *, solid_solver_ready: bool = False) -> str:
    if solid_solver_ready:
        return "solid_mesh_ready"
    if not bool(getattr(quality, "is_manifold", False)):
        return "nonmanifold" if int(getattr(quality, "nonmanifold_edge_count", 0) or 0) else "needs_repair"
    if bool(getattr(quality, "is_closed", False)):
        return "closed_surface"
    return "surface_only" if int(getattr(quality, "boundary_edge_count", 0) or 0) == 0 else "needs_repair"


def analyze_stl_file(path: str | Path, options: STLImportWizardOptions | Mapping[str, Any] | None = None) -> dict[str, Any]:
    opts = options if isinstance(options, STLImportWizardOptions) else STLImportWizardOptions.from_mapping(options)
    stl = load_stl_geology(path, opts.to_loader_options())
    status = classify_stl_status(stl.quality)
    return {
        "contract": "stl_import_wizard_analysis_v1",
        "status": status,
        "source_path": str(path),
        "options": opts.to_dict(),
        "summary": stl.to_summary_dict(),
        "quality": stl.quality.to_dict(),
        "recommended_next_step": "generate_volume_mesh" if status == "closed_surface" else "repair_or_import_as_surface",
    }


def build_stl_import_wizard_payload(path: str | Path, options: STLImportWizardOptions | Mapping[str, Any] | None = None) -> dict[str, Any]:
    analysis = analyze_stl_file(path, options)
    quality = dict(analysis.get("quality", {}) or {})
    return {
        "contract": "stl_import_wizard_payload_v1",
        "steps": ["read", "quality", "repair", "semantic", "volume_mesh", "commit"],
        "current_analysis": analysis,
        "quality_rows": [
            {"metric": "triangles", "value": quality.get("triangle_count", 0)},
            {"metric": "vertices", "value": quality.get("vertex_count", 0)},
            {"metric": "closed", "value": quality.get("is_closed", False)},
            {"metric": "manifold", "value": quality.get("is_manifold", False)},
            {"metric": "boundary_edges", "value": quality.get("boundary_edge_count", 0)},
            {"metric": "nonmanifold_edges", "value": quality.get("nonmanifold_edge_count", 0)},
            {"metric": "degenerate_triangles", "value": quality.get("degenerate_triangle_count", 0)},
        ],
        "actions": ["commit_surface", "repair_surface", "generate_voxel_hex8", "generate_gmsh_tet4"],
    }


def run_stl_import_pipeline(project: Any | None, path: str | Path, options: STLImportWizardOptions | Mapping[str, Any] | None = None) -> dict[str, Any]:
    from geoai_simkit.geoproject import GeoProjectDocument
    from geoai_simkit.modules import meshing

    opts = options if isinstance(options, STLImportWizardOptions) else STLImportWizardOptions.from_mapping(options)
    stl = load_stl_geology(path, opts.to_loader_options())
    if project is None or opts.replace:
        project = GeoProjectDocument.from_stl_geology(path, options=opts.to_loader_options(), name=opts.name)
    else:
        project.import_stl_geology(path, options=opts.to_loader_options(), replace=False)
    repair_report: dict[str, Any] | None = None
    if opts.repair:
        repair_report = meshing.optimize_project_complex_stl_surface(
            project,
            tolerance=opts.merge_tolerance,
            fill_holes=opts.fill_holes,
            orient_normals=opts.orient_normals,
            max_hole_edges=opts.max_hole_edges,
            attach=True,
        )
    mesh_result: dict[str, Any] | None = None
    if opts.generate_volume_mesh:
        result = meshing.generate_project_mesh(
            project,
            mesh_kind=opts.volume_mesh_kind,
            attach=True,
            options=dict(opts.volume_mesh_options),
            metadata={"source": "stl_import_pipeline"},
        )
        mesh_result = result.to_dict()
    readiness = meshing.validate_solid_analysis_readiness(project).to_dict()
    solid_ready = bool(readiness.get("ready"))
    current_mesh = meshing.current_project_mesh_summary(project)
    status = classify_stl_status(stl.quality, solid_solver_ready=solid_ready)
    payload = {
        "contract": "stl_import_pipeline_result_v1",
        "ok": True,
        "status": status,
        "source_path": str(path),
        "project": project,
        "surface_summary": stl.to_summary_dict(),
        "geometry": stl.to_summary_dict(),
        "repair_report": repair_report,
        "mesh_result": mesh_result,
        "solid_readiness": readiness,
        "current_mesh_summary": current_mesh,
        "options": opts.to_dict(),
    }
    try:
        project.metadata["stl_import_pipeline"] = {k: v for k, v in payload.items() if k != "project"}
        project.mark_changed(["geometry", "mesh"], action="run_stl_import_pipeline", affected_entities=list(project.geometry_model.volumes))
    except Exception:
        pass
    return payload


__all__ = [
    "STLImportWizardOptions",
    "analyze_stl_file",
    "build_stl_import_wizard_payload",
    "classify_stl_status",
    "run_stl_import_pipeline",
]
