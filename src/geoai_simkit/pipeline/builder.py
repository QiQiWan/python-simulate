from __future__ import annotations

import json
from typing import Any

import numpy as np

from geoai_simkit.core.model import (
    AnalysisStage,
    BoundaryCondition,
    GeometryObjectRecord,
    InterfaceDefinition,
    MaterialBinding,
    MaterialDefinition,
    SimulationModel,
    StructuralElementDefinition,
)
from geoai_simkit.core.types import RegionTag
from geoai_simkit.geometry.foundation_pit_blocks import compute_stage_response_metrics, workflow_from_grid
from geoai_simkit.pipeline.preprocess import build_stage_sequence_from_excavation, resolve_stage_spec
from geoai_simkit.pipeline.specs import AnalysisCaseSpec, PreparedAnalysisCase, PreparationReport


class AnalysisCaseBuilder:
    """Headless-safe case builder for operation pages and smoke tests.

    v0.8.37 extends the previous deterministic builder with a real foundation-pit
    block workflow: region tags keep block names, cell data keeps block/face
    labels, metadata stores contact/interface requests, and stages carry a full
    activation map for excavation release.
    """

    def __init__(self, spec: AnalysisCaseSpec):
        self.spec = spec

    @staticmethod
    def _cell_value(grid: Any, name: str, index: int, default: Any = "") -> Any:
        data = getattr(grid, "cell_data", {}) or {}
        values = data.get(name)
        if values is None:
            return default
        try:
            return values[index]
        except Exception:
            return default

    @staticmethod
    def _object_bounds_for_cell(grid: Any, cell_ids: np.ndarray) -> tuple[float, float, float, float, float, float] | None:
        points = np.asarray(getattr(grid, "points", []), dtype=float)
        cells = list(getattr(grid, "cells", []) or [])
        ids: list[int] = []
        for cid in list(cell_ids):
            try:
                ids.extend(int(i) for i in cells[int(cid)])
            except Exception:
                continue
        if not ids or points.size == 0:
            return None
        pts = points[np.asarray(sorted(set(ids)), dtype=int)]
        mins = pts.min(axis=0)
        maxs = pts.max(axis=0)
        return (float(mins[0]), float(maxs[0]), float(mins[1]), float(maxs[1]), float(mins[2]), float(maxs[2]))

    @staticmethod
    def _activation_map_for_stage(regions: list[str], stage_rows: list[dict[str, Any]], stage_name: str) -> dict[str, bool]:
        if not stage_rows:
            return {name: True for name in regions}
        active: set[str] = set()
        for row in stage_rows:
            name = str(row.get("name") or "")
            active.update(str(v) for v in list(row.get("activate_blocks") or []) if str(v))
            for block_name in list(row.get("deactivate_blocks") or []):
                active.discard(str(block_name))
            if name == stage_name:
                break
        return {name: name in active for name in regions}

    @staticmethod
    def _stage_rows_from_workflow(workflow: dict[str, Any]) -> list[dict[str, Any]]:
        rows = [dict(row) for row in list(workflow.get("stage_rows") or []) if isinstance(row, dict)]
        return rows

    def build(self) -> PreparedAnalysisCase:
        grid = self.spec.geometry.resolve()
        per_cell_names = [str(x) for x in list(grid.cell_data.get("region_name", []))]
        if not per_cell_names and int(getattr(grid, "n_cells", 0) or 0):
            per_cell_names = [str(self.spec.name)] * int(getattr(grid, "n_cells", 0))
        names = list(dict.fromkeys(per_cell_names))
        workflow = workflow_from_grid(grid)
        stage_rows = self._stage_rows_from_workflow(workflow)
        grouped_cell_ids: dict[str, list[int]] = {name: [] for name in names}
        for i, name in enumerate(per_cell_names):
            grouped_cell_ids.setdefault(str(name), []).append(int(i))
        regions = []
        for n in names:
            ids = np.asarray(grouped_cell_ids.get(n, []), dtype=np.int64)
            first = int(ids[0]) if len(ids) else 0
            regions.append(
                RegionTag(
                    name=n,
                    cell_ids=ids,
                    metadata={
                        "source": "headless_builder",
                        "block_tag": str(self._cell_value(grid, "block_tag", first, n)),
                        "role": str(self._cell_value(grid, "role", first, "")),
                        "material_name": str(self._cell_value(grid, "material_name", first, "")),
                        "bounds": self._object_bounds_for_cell(grid, ids),
                    },
                )
            )
        model_metadata = {
            "geometry_state": "meshed",
            "pipeline.builder": "headless_operation_builder_v3",
            "foundation_pit.workflow": workflow,
        }
        raw_stl_payload = getattr(grid, "field_data", {}).get("stl_geology_json")
        if raw_stl_payload is not None:
            try:
                model_metadata["stl_geology"] = json.loads(raw_stl_payload if isinstance(raw_stl_payload, str) else list(raw_stl_payload)[0])
                model_metadata["geometry_state"] = "surface_mesh"
                model_metadata["pipeline.builder"] = "stl_geology_builder"
            except Exception:
                model_metadata["stl_geology_raw"] = str(raw_stl_payload)
        model = SimulationModel(
            name=self.spec.name,
            mesh=grid,
            region_tags=regions,
            metadata=model_metadata,
        )

        # Material library and explicit assignments.
        for definition in self.spec.material_library:
            if isinstance(definition, MaterialDefinition):
                model.upsert_material_definition(definition)
            else:
                try:
                    model.upsert_material_definition(MaterialDefinition(**dict(definition)))
                except Exception:
                    pass
        assigned_regions: set[str] = set()
        for assignment in self.spec.materials:
            for region_name in tuple(getattr(assignment, "region_names", ()) or ()):  # noqa: B007
                model.materials.append(
                    MaterialBinding(
                        str(region_name),
                        str(getattr(assignment, "material_name", "linear_elastic")),
                        dict(getattr(assignment, "parameters", {}) or {}),
                        dict(getattr(assignment, "metadata", {}) or {}),
                    )
                )
                assigned_regions.add(str(region_name))
        # Auto-bind generated foundation-pit blocks to their cell material names.
        for region in regions:
            mat_name = str(region.metadata.get("material_name") or "")
            if region.name not in assigned_regions and mat_name and mat_name != "void":
                params = {"E": 30.0e6, "nu": 0.30, "rho": 1800.0}
                if "wall" in mat_name or str(region.metadata.get("role")) == "wall":
                    params = {"E": 32.0e9, "nu": 0.20, "rho": 2500.0}
                model.materials.append(MaterialBinding(region.name, "linear_elastic", params, {"library_name": mat_name, "auto_generated": True}))

        # Object/block records for GUI selection and meshing tags.
        for region in regions:
            bbox = region.metadata.get("bounds")
            model.object_records.append(
                GeometryObjectRecord(
                    key=f"object:{region.name}",
                    name=str(region.name),
                    object_type="volume_block",
                    region_name=str(region.name),
                    metadata={
                        "cell_ids": [int(i) for i in region.cell_ids],
                        "selectable": True,
                        "operation_page": "modeling",
                        "block_tag": region.metadata.get("block_tag"),
                        "role": region.metadata.get("role"),
                        "material_name": region.metadata.get("material_name"),
                        "bounds": list(bbox) if bbox is not None else None,
                        "face_tag_prefix": f"face:{region.name}:",
                    },
                )
            )

        # Global boundary conditions.
        for item in tuple(self.spec.boundary_conditions or ()):  # noqa: B007
            model.boundary_conditions.append(
                BoundaryCondition(
                    name=str(getattr(item, "name", "bc")),
                    kind=str(getattr(item, "kind", "displacement")),
                    target=str(getattr(item, "target", "boundary")),
                    components=tuple(getattr(item, "components", (0, 1, 2))),
                    values=tuple(float(v) for v in getattr(item, "values", (0.0, 0.0, 0.0))),
                    metadata=dict(getattr(item, "metadata", {}) or {}),
                )
            )

        # Structures/interfaces: deterministic demo support objects plus generated requests.
        if self.spec.structures:
            model.structures.append(StructuralElementDefinition("strut_level_1", "strut", (0, 1), parameters={"EA": 1.0e9}, active_stages=tuple(s["name"] for s in stage_rows[1:] or [{"name": "wall_activation"}]), metadata={"generated_by": "demo_pit_supports"}))
            if len(stage_rows) > 3:
                model.structures.append(StructuralElementDefinition("strut_level_2", "strut", (2, 3), parameters={"EA": 1.0e9}, active_stages=tuple(s["name"] for s in stage_rows[3:]), metadata={"generated_by": "demo_pit_supports"}))
        interface_requests = [dict(row) for row in list(workflow.get("interface_requests") or [])]
        model.metadata["foundation_pit.interface_requests"] = interface_requests
        model.metadata["foundation_pit.contact_pairs"] = list(workflow.get("contact_pairs") or [])
        model.metadata["foundation_pit.face_tags"] = list(workflow.get("face_tags") or [])
        for idx, request in enumerate(interface_requests, start=1):
            if request.get("request_type") not in {"node_pair_contact", "release_boundary"}:
                continue
            active_stages = tuple(str(s) for s in list(request.get("active_stages") or []) if str(s))
            if not active_stages:
                active_stages = tuple(row["name"] for row in stage_rows[1:])
            model.interfaces.append(
                InterfaceDefinition(
                    name=str(request.get("name") or f"interface_request_{idx:03d}"),
                    kind=str(request.get("request_type") or "face_request"),
                    slave_point_ids=tuple(),
                    master_point_ids=tuple(),
                    parameters={
                        "mesh_policy": request.get("mesh_policy"),
                        "contact_mode": request.get("contact_mode"),
                        "total_overlap_area": request.get("total_overlap_area"),
                    },
                    active_stages=active_stages,
                    metadata={"generated_by": "foundation_pit_block_workflow", "request": request},
                )
            )
        if self.spec.interfaces and not model.interfaces:
            wall_ids = tuple(int(i) for i in range(min(4, grid.n_points)))
            soil_ids = tuple(int(i) for i in range(min(4, grid.n_points), min(8, grid.n_points))) or wall_ids
            model.interfaces.append(InterfaceDefinition("wall_soil_contact", "node_pair", wall_ids, soil_ids, parameters={"kn": 1.0e8, "ks": 5.0e7}, active_stages=("wall_activation",), metadata={"generated_by": "demo_wall_interfaces"}))

        # Stages with full block activation maps.
        if stage_rows:
            stages: list[AnalysisStage] = []
            for row in stage_rows:
                name = str(row.get("name") or "stage")
                amap = self._activation_map_for_stage(names, stage_rows, name)
                stages.append(
                    AnalysisStage(
                        name=name,
                        activate_regions=tuple(str(v) for v in list(row.get("activate_blocks") or [])),
                        deactivate_regions=tuple(str(v) for v in list(row.get("deactivate_blocks") or [])),
                        metadata={
                            "predecessor": row.get("predecessor"),
                            "stage_role": row.get("role"),
                            "excavation_depth": float(row.get("excavation_depth", 0.0) or 0.0),
                            "activation_map": amap,
                            "block_workflow_stage": True,
                        },
                    )
                )
            model.stages = stages
        elif self.spec.stages:
            model.stages = [resolve_stage_spec(model, s) for s in self.spec.stages]
        elif self.spec.mesh_preparation.excavation_steps:
            model.stages = build_stage_sequence_from_excavation(model, self.spec.mesh_preparation.excavation_steps, initial_metadata={"stage_role": "initial"})
        else:
            model.stages = [AnalysisStage("initial", activate_regions=tuple(names), metadata={"stage_role": "initial"})]

        if workflow:
            metrics = compute_stage_response_metrics(workflow)
            model.metadata["foundation_pit.stage_metrics"] = metrics
            model.metadata["stage_result_metrics"] = metrics

        report = PreparationReport(
            merged_points=bool(getattr(self.spec.mesh, "merge_points", True)),
            merged_point_count=0,
            generated_stages=tuple(s.name for s in model.stages),
            generated_interfaces=tuple(i.name for i in model.interfaces),
            notes=("Headless deterministic FEM preparation completed.", "Foundation-pit block workflow attached." if workflow else ("STL geological surface mesh attached." if model.metadata.get("stl_geology") else "Legacy parametric-pit grid attached.")),
            metadata={
                "n_points": grid.n_points,
                "n_cells": grid.n_cells,
                "n_regions": len(regions),
                "n_structures": len(model.structures),
                "n_interfaces": len(model.interfaces),
                "n_interface_elements": len(model.interface_elements),
                "block_count": int(workflow.get("summary", {}).get("block_count", len(regions))) if workflow else len(regions),
                "contact_pair_count": int(workflow.get("summary", {}).get("contact_pair_count", 0)) if workflow else 0,
                "interface_request_count": int(workflow.get("summary", {}).get("interface_request_count", 0)) if workflow else 0,
            },
        )
        model.metadata["pipeline.preparation_report"] = {
            "merged_points": report.merged_points,
            "merged_point_count": report.merged_point_count,
            "generated_stages": list(report.generated_stages),
            "generated_interfaces": list(report.generated_interfaces),
            "notes": list(report.notes),
            **report.metadata,
        }
        return PreparedAnalysisCase(model=model, report=report)
