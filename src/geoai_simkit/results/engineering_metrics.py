from __future__ import annotations

"""Engineering metric extraction and deterministic preview result generation."""

from math import sqrt
from typing import Any

from geoai_simkit.results.result_package import ResultFieldRecord, ResultPackage


def _stage_depth(document: Any, stage_id: str, stage_index: int) -> float:
    stage = document.stages.stages.get(stage_id)
    row = dict(getattr(stage, "metadata", {}) or {}) if stage is not None else {}
    for key in ("excavation_depth", "depth", "target_depth"):
        if key in row:
            try:
                return abs(float(row[key]))
            except Exception:
                pass
    inactive = set(getattr(stage, "inactive_blocks", set()) or set()) if stage is not None else set()
    max_depth = 0.0
    for block_id in inactive:
        block = document.geometry.blocks.get(block_id)
        if block is not None and getattr(block, "role", "") == "excavation":
            max_depth = max(max_depth, abs(float(block.bounds[4])), abs(float(block.bounds[5])))
    if max_depth > 0.0:
        return max_depth
    return float(stage_index) * 2.5


def _active_blocks(document: Any, stage_id: str) -> set[str]:
    all_blocks = tuple(document.geometry.blocks.keys())
    try:
        return set(document.stages.active_blocks_for_stage(all_blocks, stage_id))
    except Exception:
        return set(all_blocks)


def build_preview_result_package(document: Any) -> ResultPackage:
    """Create deterministic stage metrics tied back to engineering blocks.

    This preview backend is monotonic with excavation depth and stage activation.
    It is a GUI/result contract validator, not a production nonlinear FEM solve.
    """

    package = ResultPackage(
        case_name=str(getattr(document, "name", "foundation-pit")),
        metadata={"backend": "deterministic_preview", "contract": "stage_result_package_v1"},
    )
    block_ids = list(document.geometry.blocks.keys())
    wall_ids = [bid for bid, b in document.geometry.blocks.items() if getattr(b, "role", "") == "wall"]
    excavation_ids = [bid for bid, b in document.geometry.blocks.items() if getattr(b, "role", "") == "excavation"]
    max_geom_depth = 1.0
    for bid in excavation_ids or block_ids:
        block = document.geometry.blocks[bid]
        max_geom_depth = max(max_geom_depth, abs(float(block.bounds[4])), abs(float(block.bounds[5])))

    for index, stage_id in enumerate(document.stages.order):
        active = _active_blocks(document, stage_id)
        inactive = set(block_ids) - active
        depth = _stage_depth(document, stage_id, index)
        depth_ratio = min(max(depth / max_geom_depth, 0.0), 1.5)
        excavated_count = len([bid for bid in excavation_ids if bid not in active])
        wall_factor = max(len(wall_ids), 1) ** -0.25
        max_wall_u = 0.0035 * depth * depth * (1.0 + 0.12 * excavated_count) * wall_factor
        max_settlement = 0.55 * max_wall_u + 0.0015 * depth
        max_heave = 0.12 * max_wall_u + 0.0008 * depth
        plastic_ratio = min(0.04 + 0.22 * depth_ratio + 0.01 * excavated_count, 0.65)

        stage_result = package.get_or_create_stage(stage_id)
        stage_result.metrics.update({
            "excavation_depth": float(depth),
            "max_wall_horizontal_displacement": float(max_wall_u),
            "max_surface_settlement": float(max_settlement),
            "max_base_heave": float(max_heave),
            "plastic_zone_ratio": float(plastic_ratio),
            "active_block_count": float(len(active)),
            "inactive_block_count": float(len(inactive)),
        })

        values: list[float] = []
        for bid in block_ids:
            block = document.geometry.blocks[bid]
            cx, cy, cz = block.centroid
            role_scale = 1.35 if block.role == "wall" else 1.0 if block.role == "soil" else 0.35
            active_scale = 1.0 if bid in active else 0.0
            spatial = sqrt(cx * cx + cy * cy + cz * cz) / max_geom_depth
            values.append(float(active_scale * role_scale * max_wall_u * (1.0 + 0.02 * spatial)))
        stage_result.add_field(ResultFieldRecord(
            name="preview_horizontal_displacement",
            stage_id=stage_id,
            association="block",
            values=values,
            entity_ids=block_ids,
            metadata={"unit": "m", "description": "deterministic preview field for GUI validation"},
        ))
    return package


def result_summary(package: ResultPackage | None) -> dict[str, Any]:
    if package is None:
        return {"available": False, "message": "No result package has been generated.", "curves": {}, "stage_results": []}
    metric_names: list[str] = []
    for result in package.stage_results.values():
        for key in result.metrics.keys():
            if key not in metric_names:
                metric_names.append(key)
    curves = {name: [{"stage_id": sid, "value": value} for sid, value in package.metric_curve(name)] for name in metric_names}
    return {
        "available": True,
        "case_name": package.case_name,
        "backend": package.metadata.get("backend", "unknown"),
        "metric_names": metric_names,
        "curves": curves,
        "stage_results": [result.to_dict() for result in package.stage_results.values()],
        "entity_metrics": {k: dict(v) for k, v in package.entity_metrics.items()},
        "metadata": dict(package.metadata),
    }


__all__ = ["build_preview_result_package", "result_summary"]
