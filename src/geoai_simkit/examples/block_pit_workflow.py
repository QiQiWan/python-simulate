from __future__ import annotations

from pathlib import Path
from typing import Any
import json


DEFAULT_BOUNDARY_PRESET_KEY = "pit_rigid_box"


def _default_bcs():
    from geoai_simkit.pipeline.specs import BoundaryConditionSpec

    return (
        BoundaryConditionSpec("fix_bottom", "displacement", "bottom", (0, 1, 2), (0.0, 0.0, 0.0), {"preset_key": DEFAULT_BOUNDARY_PRESET_KEY}),
        BoundaryConditionSpec("fix_xmin", "displacement", "xmin", (0,), (0.0,), {"preset_key": DEFAULT_BOUNDARY_PRESET_KEY}),
        BoundaryConditionSpec("fix_xmax", "displacement", "xmax", (0,), (0.0,), {"preset_key": DEFAULT_BOUNDARY_PRESET_KEY}),
        BoundaryConditionSpec("fix_ymin", "displacement", "ymin", (1,), (0.0,), {"preset_key": DEFAULT_BOUNDARY_PRESET_KEY}),
        BoundaryConditionSpec("fix_ymax", "displacement", "ymax", (1,), (0.0,), {"preset_key": DEFAULT_BOUNDARY_PRESET_KEY}),
    )


def build_block_pit_case(*, dimension: str = "3d", smoke: bool = True):
    from geoai_simkit.pipeline.specs import AnalysisCaseSpec, GeometrySource, MaterialAssignmentSpec, MeshAssemblySpec, StructureGeneratorSpec

    depth = 9.0 if smoke else 16.0
    params: dict[str, Any] = {
        "dimension": dimension,
        "pit_length": 24.0 if smoke else 42.0,
        "pit_width": 10.0 if smoke else 24.0,
        "domain_length": 46.0 if smoke else 78.0,
        "domain_width": 28.0 if smoke else 56.0,
        "depth": depth,
        "soil_depth": 18.0 if smoke else 32.0,
        "wall_thickness": 0.8,
        "wall_bottom": 14.0 if smoke else 25.0,
        "excavation_levels": (-depth * 0.35, -depth * 0.70, -depth),
        "layer_levels": (0.0, -depth * 0.45, -depth * 0.85, -(18.0 if smoke else 32.0)),
    }
    return AnalysisCaseSpec(
        name=f"block-pit-{dimension}",
        geometry=GeometrySource(kind="foundation_pit_blocks", parameters=params, metadata={"source": "foundation_pit_blocks"}),
        mesh=MeshAssemblySpec(element_family="hex8", merge_points=False, keep_geometry_copy=True, metadata={"preserve_block_tag": True, "preserve_face_tag": True}),
        materials=(MaterialAssignmentSpec(region_names=("retaining_wall",), material_name="linear_elastic", parameters={"E": 32.0e9, "nu": 0.20, "rho": 2500.0}),),
        boundary_conditions=_default_bcs(),
        structures=(StructureGeneratorSpec(kind="pit_struts_from_stage_depths"),),
        metadata={
            "source": "foundation_pit_blocks",
            "demo_version": "0.8.37",
            "workflow_features": [
                "block_creation",
                "horizontal_layer_split",
                "excavation_plane_split",
                "contact_pair_detection",
                "interface_request_generation",
                "mesh_block_face_tags",
                "stage_activation_release",
                "stage_wall_settlement_results",
            ],
        },
    )


def build_block_pit_model(*, dimension: str = "3d", smoke: bool = True):
    from geoai_simkit.pipeline.runner import GeneralFEMSolver

    return GeneralFEMSolver().prepare_case(build_block_pit_case(dimension=dimension, smoke=smoke)).model


def run_block_pit_workflow(out_dir: str | Path = "exports", *, dimension: str = "3d", smoke: bool = True) -> dict[str, Any]:
    from geoai_simkit.pipeline.runner import AnalysisExportSpec, AnalysisTaskSpec, GeneralFEMSolver

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    case = build_block_pit_case(dimension=dimension, smoke=smoke)
    result = GeneralFEMSolver().run(AnalysisTaskSpec(case=case, export=AnalysisExportSpec(out_dir=str(out))))
    model = result.prepared.model
    payload = {
        "case_name": case.name,
        "accepted": bool(result.accepted),
        "preparation_report": dict(model.metadata.get("pipeline.preparation_report", {}) or {}),
        "workflow_summary": dict(model.metadata.get("foundation_pit.workflow", {}).get("summary", {}) or {}),
        "stage_metrics": list(model.metadata.get("stage_result_metrics", []) or []),
        "interface_request_count": len(model.metadata.get("foundation_pit.interface_requests", []) or []),
        "contact_pair_count": len(model.metadata.get("foundation_pit.contact_pairs", []) or []),
        "field_labels": model.list_result_labels(),
    }
    path = out / f"{case.name}_workflow_summary.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    payload["json_path"] = str(path)
    return payload


__all__ = ["build_block_pit_case", "build_block_pit_model", "run_block_pit_workflow"]
