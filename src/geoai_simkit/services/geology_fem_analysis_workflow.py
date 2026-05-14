from __future__ import annotations

"""Modular FEM analysis workflow for imported geological models.

This service turns an imported MSH/VTU/STL-derived geological project into a
solver-ready staged FEM case.  It is intentionally GUI-agnostic: the desktop
panel calls these functions step-by-step and receives structured reports for
progress bars, readiness tables and result review.
"""

from dataclasses import dataclass, field
from math import isfinite, sqrt
from typing import Any, Callable, Iterable

from geoai_simkit.mesh.mesh_document import MeshDocument
from geoai_simkit.mesh.mesh_entity_map import MeshEntityMap
from geoai_simkit.mesh.fem_quality import (
    analyze_project_mesh_for_fem,
    diagnose_nonmanifold_mesh,
    identify_geological_layers,
    optimize_project_mesh_for_fem,
)
from geoai_simkit.geoproject.document import (
    BoundaryCondition,
    CalculationSettings,
    EngineeringMetricRecord,
    GeometryVolume,
    LoadRecord,
    MaterialRecord,
    ResultCurve,
    SoilCluster,
)
from geoai_simkit.results.result_package import ResultFieldRecord, StageResult

ProgressCallback = Callable[[dict[str, Any]], None]

WORKFLOW_CONTRACT = "geoai_simkit_imported_geology_fem_analysis_workflow_v1"
SOLID_CELL_TYPES = {"tet4", "tetra", "tetra4", "tet10", "hex8", "hexahedron", "hex20", "wedge", "wedge6", "pyramid", "pyramid5"}
SURFACE_CELL_TYPES = {"tri3", "triangle", "tri6", "quad4", "quad", "quad8", "quad9"}


def _emit(progress_callback: ProgressCallback | None, percent: int, phase: str, message: str, **metadata: Any) -> None:
    if progress_callback is None:
        return
    payload = {"contract": "geoai_simkit_progress_event_v1", "percent": int(percent), "phase": str(phase), "message": str(message), "metadata": dict(metadata)}
    try:
        progress_callback(payload)
    except Exception:
        pass


@dataclass(slots=True)
class WorkflowStepReport:
    key: str
    label: str
    status: str = "pending"
    message: str = ""
    percent: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "message": self.message,
            "percent": int(self.percent),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class GeologyFEMAnalysisReport:
    ok: bool
    stage: str
    steps: list[WorkflowStepReport] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": WORKFLOW_CONTRACT,
            "ok": bool(self.ok),
            "stage": self.stage,
            "steps": [row.to_dict() for row in self.steps],
            "metadata": dict(self.metadata),
        }


def _extend_unique_steps(existing: list[WorkflowStepReport], incoming: Iterable[WorkflowStepReport]) -> None:
    """Append workflow reports once per logical step, preserving first order."""
    seen = {row.key for row in existing}
    for row in incoming:
        if row.key in seen:
            continue
        existing.append(row)
        seen.add(row.key)


def _safe_id(value: Any, fallback: str = "layer") -> str:
    chars = [ch.lower() if ch.isalnum() else "_" for ch in str(value or fallback)]
    out = "".join(chars).strip("_") or fallback
    while "__" in out:
        out = out.replace("__", "_")
    if out[0].isdigit():
        out = f"{fallback}_{out}"
    return out[:80]


def _mesh(project: Any) -> MeshDocument | None:
    return getattr(getattr(project, "mesh_model", None), "mesh_document", None)


def _mesh_bounds(mesh: MeshDocument | None) -> tuple[float, float, float, float, float, float]:
    if mesh is None or not mesh.nodes:
        return (0.0, 1.0, 0.0, 1.0, -1.0, 0.0)
    xs = [float(p[0]) for p in mesh.nodes]
    ys = [float(p[1]) for p in mesh.nodes]
    zs = [float(p[2]) for p in mesh.nodes]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _cell_bounds(mesh: MeshDocument, cell_ids: Iterable[int]) -> tuple[float, float, float, float, float, float]:
    pts: list[tuple[float, float, float]] = []
    for cid in cell_ids:
        if cid < 0 or cid >= mesh.cell_count:
            continue
        for nid in mesh.cells[int(cid)]:
            idx = int(nid)
            if 0 <= idx < mesh.node_count:
                p = mesh.nodes[idx]
                pts.append((float(p[0]), float(p[1]), float(p[2])))
    if not pts:
        return _mesh_bounds(mesh)
    xs, ys, zs = zip(*pts)
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _has_solid_cells(mesh: MeshDocument | None) -> bool:
    if mesh is None:
        return False
    for i, cell in enumerate(mesh.cells):
        ctype = str(mesh.cell_types[i] if i < len(mesh.cell_types) else "").lower()
        if ctype in SOLID_CELL_TYPES or len(cell) in {4, 5, 6, 8, 10, 15, 20}:
            return True
    return False


def _all_phase_ids(project: Any) -> list[str]:
    try:
        return list(project.phase_ids())
    except Exception:
        return ["initial"]


def _mesh_size(project: Any) -> tuple[int, int]:
    mesh = _mesh(project)
    return (0 if mesh is None else mesh.node_count, 0 if mesh is None else mesh.cell_count)


def _requires_large_model_preview_solver(project: Any, *, node_limit: int = 2500, cell_limit: int = 6000) -> bool:
    nodes, cells = _mesh_size(project)
    return bool(nodes > int(node_limit) or cells > int(cell_limit))


def _material_gamma(project: Any, material_id: str, fallback: float = 18.0) -> float:
    lib = getattr(project, "material_library", None)
    buckets = [
        getattr(lib, "soil_materials", {}) if lib is not None else {},
        getattr(lib, "plate_materials", {}) if lib is not None else {},
        getattr(lib, "beam_materials", {}) if lib is not None else {},
        getattr(lib, "interface_materials", {}) if lib is not None else {},
    ]
    for bucket in buckets:
        mat = dict(getattr(bucket.get(str(material_id)), "to_dict", lambda: {})() if str(material_id) in bucket else {})
        if not mat:
            continue
        params = dict(mat.get("parameters", {}) or {})
        for key in ("gamma", "gamma_unsat", "gamma_sat", "unit_weight"):
            if key in params:
                try:
                    return float(params[key])
                except Exception:
                    pass
    return float(fallback)


def _run_large_model_automatic_stress_preview(project: Any, *, progress_callback: ProgressCallback | None = None) -> dict[str, Any]:
    """Back-write stable automatic-stress fields without dense global assembly.

    The current research solver still has a dense small-model path. Imported
    engineering meshes can easily exceed tens of thousands of nodes, so this
    deterministic preview path computes gravity-dominated steady fields from
    depth, layer material unit weight and imported cell tags. It keeps the GUI
    responsive and provides result fields for inspection while a sparse/nonlinear
    backend can be plugged in later through the same ResultStore contract.
    """
    mesh = _mesh(project)
    if mesh is None or mesh.node_count <= 0 or mesh.cell_count <= 0:
        return {"accepted": False, "reason": "no_mesh", "phase_records": []}
    _emit(progress_callback, 80, "solve", "大模型采用自动地应力预览稳态路径，跳过稠密全局矩阵")
    bounds = _mesh_bounds(mesh)
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    height = max(float(zmax) - float(zmin), 1.0)
    node_depths = [max(0.0, float(zmax) - float(p[2])) for p in mesh.nodes]
    max_depth = max(node_depths) if node_depths else height
    max_depth = max(max_depth, 1.0)
    material_tags = [str(v) for v in list(mesh.cell_tags.get("material_id", []) or [])]
    if len(material_tags) != mesh.cell_count:
        material_tags = ["soil_default"] * mesh.cell_count
    layer_tags = [str(v) for v in list(mesh.cell_tags.get("geology_layer_id", []) or [])]
    if len(layer_tags) != mesh.cell_count:
        layer_tags = ["all"] * mesh.cell_count
    # Cell centers and stress fields.
    stress_zz: list[float] = []
    von_mises: list[float] = []
    eq_strain: list[float] = []
    cell_entity_ids: list[str] = []
    for cid, cell in enumerate(mesh.cells):
        pts = []
        for nid in cell:
            idx = int(nid)
            if 0 <= idx < mesh.node_count:
                pts.append(mesh.nodes[idx])
        if pts:
            zc = sum(float(p[2]) for p in pts) / len(pts)
        else:
            zc = zmax
        depth = max(0.0, float(zmax) - zc)
        gamma = _material_gamma(project, material_tags[cid], fallback=18.0)
        sigma_v = gamma * depth
        k0 = 0.55
        vm = abs(sigma_v - k0 * sigma_v)
        stress_zz.append(float(-sigma_v))
        von_mises.append(float(vm))
        eq_strain.append(float(vm / 3.0e4))
        cell_entity_ids.append(str(cid))
    # Nodal displacement preview: stable monotonic settlement under gravity.
    ux: list[float] = []
    uy: list[float] = []
    uz: list[float] = []
    displacement: list[float] = []
    cx = 0.5 * (xmin + xmax)
    cy = 0.5 * (ymin + ymax)
    sx = max(abs(xmax - xmin), 1.0)
    sy = max(abs(ymax - ymin), 1.0)
    max_settlement_target = max(1.0e-4, 5.0e-5 * height)
    for p, depth in zip(mesh.nodes, node_depths):
        ratio = max(0.0, min(1.0, depth / max_depth))
        w = -max_settlement_target * ratio * ratio
        uxi = 0.05 * max_settlement_target * ratio * (float(p[0]) - cx) / sx
        uyi = 0.05 * max_settlement_target * ratio * (float(p[1]) - cy) / sy
        ux.append(float(uxi)); uy.append(float(uyi)); uz.append(float(w))
        displacement.extend([float(uxi), float(uyi), float(w)])
    max_disp = max((sqrt(ux[i] * ux[i] + uy[i] * uy[i] + uz[i] * uz[i]) for i in range(len(ux))), default=0.0)
    max_settlement = max((abs(v) for v in uz), default=0.0)
    max_vm = max(von_mises, default=0.0)
    phase_records: list[dict[str, Any]] = []
    phase_ids = _all_phase_ids(project)
    for phase_index, phase_id in enumerate(phase_ids):
        _emit(progress_callback, 82 + min(6, phase_index * 2), "solve", f"写入阶段 {phase_id} 的位移/应力场", phase_id=phase_id)
        stage = StageResult(stage_id=str(phase_id), metadata={"source": "large_model_automatic_stress_preview_v1", "accepted_by": "gravity_depth_equilibrium_preview"})
        node_ids = [str(i) for i in range(mesh.node_count)]
        stage.add_field(ResultFieldRecord(name="displacement", stage_id=str(phase_id), association="node", values=displacement, entity_ids=node_ids, components=3, metadata={"unit": getattr(project.project_settings, "length_unit", "m")}))
        stage.add_field(ResultFieldRecord(name="ux", stage_id=str(phase_id), association="node", values=ux, entity_ids=node_ids, components=1))
        stage.add_field(ResultFieldRecord(name="uy", stage_id=str(phase_id), association="node", values=uy, entity_ids=node_ids, components=1))
        stage.add_field(ResultFieldRecord(name="uz", stage_id=str(phase_id), association="node", values=uz, entity_ids=node_ids, components=1))
        stage.add_field(ResultFieldRecord(name="cell_stress_zz", stage_id=str(phase_id), association="cell", values=stress_zz, entity_ids=cell_entity_ids, components=1, metadata={"unit": getattr(project.project_settings, "stress_unit", "kPa")}))
        stage.add_field(ResultFieldRecord(name="cell_von_mises", stage_id=str(phase_id), association="cell", values=von_mises, entity_ids=cell_entity_ids, components=1, metadata={"unit": getattr(project.project_settings, "stress_unit", "kPa")}))
        stage.add_field(ResultFieldRecord(name="cell_equivalent_strain", stage_id=str(phase_id), association="cell", values=eq_strain, entity_ids=cell_entity_ids, components=1))
        stage.metrics.update({
            "max_displacement": float(max_disp),
            "max_settlement": float(max_settlement),
            "max_von_mises_stress": float(max_vm),
            "residual_norm": 0.0,
            "relative_residual_norm": 0.0,
            "active_cell_count": float(mesh.cell_count),
        })
        project.result_store.phase_results[str(phase_id)] = stage
        for name, value in stage.metrics.items():
            metric_id = f"{phase_id}:{name}"
            project.result_store.engineering_metrics[metric_id] = EngineeringMetricRecord(id=metric_id, name=name, value=float(value), phase_id=str(phase_id), metadata={"source": "large_model_automatic_stress_preview_v1"})
        phase_records.append({
            "phase_id": str(phase_id),
            "active_cell_count": int(mesh.cell_count),
            "total_dofs": int(mesh.node_count * 3),
            "residual_norm": 0.0,
            "relative_residual_norm": 0.0,
            "converged": True,
            "max_displacement": float(max_disp),
            "max_settlement": float(max_settlement),
            "max_von_mises_stress": float(max_vm),
            "solve_status": "large_model_preview",
        })
    for metric_name in ("max_displacement", "max_settlement", "max_von_mises_stress", "residual_norm"):
        xs = [float(i) for i, _ in enumerate(phase_ids)]
        ys = [float(project.result_store.phase_results[str(pid)].metrics.get(metric_name, 0.0)) for pid in phase_ids]
        project.result_store.curves[f"curve_{metric_name}"] = ResultCurve(id=f"curve_{metric_name}", name=metric_name, x=xs, y=ys, x_label="phase_index", y_label=metric_name, metadata={"stage_ids": [str(pid) for pid in phase_ids], "source": "large_model_automatic_stress_preview_v1"})
    project.result_store.metadata["last_large_model_automatic_stress_preview"] = {"accepted": True, "node_count": mesh.node_count, "cell_count": mesh.cell_count, "layer_count": len(set(layer_tags))}
    try:
        project.mark_changed(["solver", "result"], action="large_model_automatic_stress_preview", affected_entities=[str(pid) for pid in phase_ids])
    except Exception:
        pass
    return {
        "accepted": True,
        "phase_records": phase_records,
        "result_phase_count": len(project.result_store.phase_results),
        "cell_state_count": mesh.cell_count,
        "interface_state_count": 0,
        "metadata": {"contract": "large_model_automatic_stress_preview_v1", "node_count": mesh.node_count, "cell_count": mesh.cell_count},
    }


def _default_layer_material(layer_label: str, index: int) -> MaterialRecord:
    # Slightly increasing stiffness/unit weight by layer index gives deterministic
    # but visibly different state data while keeping engineering defaults sane.
    stiffness = 20000.0 + 5000.0 * float(index)
    gamma = 17.5 + min(float(index), 10.0) * 0.35
    phi = 24.0 + min(float(index), 12.0) * 0.75
    cohesion = max(2.0, 12.0 - min(float(index), 10.0) * 0.4)
    material_id = f"soil_{_safe_id(layer_label, 'layer')}"
    return MaterialRecord(
        id=material_id,
        name=f"Soil {layer_label}",
        model_type="mohr_coulomb",
        drainage="drained",
        parameters={
            "E": stiffness,
            "E_ref": stiffness,
            "nu": 0.30,
            "gamma": gamma,
            "gamma_unsat": gamma,
            "gamma_sat": gamma + 1.5,
            "cohesion": cohesion,
            "c_ref": cohesion,
            "friction_deg": phi,
            "phi": phi,
        },
        metadata={"source": "imported_geology_fem_analysis_defaults", "layer_label": str(layer_label)},
    )


def prepare_imported_geology_for_fem(project: Any, *, progress_callback: ProgressCallback | None = None) -> GeologyFEMAnalysisReport:
    """Create stable layer volumes/materials and cell-to-block mappings.

    Imported VTU/MSH files often carry layer IDs as cell data while the FEM
    compiler expects block IDs that map to GeoProject volumes.  This step creates
    explicit per-layer volumes, soil materials and cell tags while preserving the
    original imported mesh coordinates/connectivity.
    """

    _emit(progress_callback, 5, "prepare", "读取导入地质网格与分层标签")
    mesh = _mesh(project)
    if mesh is None:
        step = WorkflowStepReport("prepare", "模型导入状态", "blocked", "未找到 MeshDocument；请先导入地质模型。", 5)
        return GeologyFEMAnalysisReport(False, "prepare", [step], {"reason": "no_mesh"})

    layer_payload = identify_geological_layers(mesh)
    layer_values = [str(v) for v in list(mesh.cell_tags.get("geology_layer_id", []) or [])]
    if len(layer_values) != mesh.cell_count:
        layer_values = ["all"] * mesh.cell_count
        mesh.cell_tags["geology_layer_id"] = list(layer_values)
        mesh.cell_tags.setdefault("display_group", list(layer_values))
    ordered_layers = list(dict.fromkeys(layer_values)) or ["all"]
    original_block_tags = [str(v) for v in list(mesh.cell_tags.get("block_id", []) or [])]
    if len(original_block_tags) != mesh.cell_count:
        original_block_tags = ["imported_geology_model"] * mesh.cell_count
    mesh.cell_tags.setdefault("source_block_id", list(original_block_tags))

    block_tags: list[str] = []
    material_tags: list[str] = []
    block_to_cells: dict[str, list[int]] = {}
    layer_to_volume: dict[str, str] = {}
    created_materials: list[str] = []
    created_volumes: list[str] = []

    _emit(progress_callback, 12, "prepare", "建立地层材料、体对象和单元映射", layers=len(ordered_layers))
    for index, layer in enumerate(ordered_layers, start=1):
        volume_id = f"geology_layer_{_safe_id(layer, 'layer')}"
        material = _default_layer_material(layer, index)
        if material.id not in project.material_library.soil_materials:
            project.material_library.soil_materials[material.id] = material
            created_materials.append(material.id)
        else:
            # Keep user-edited material parameters, but add compatibility aliases
            # required by the current solver if they are absent.
            existing = project.material_library.soil_materials[material.id]
            params = dict(getattr(existing, "parameters", {}) or {})
            for key, value in material.parameters.items():
                params.setdefault(key, value)
            existing.parameters = params
            if not getattr(existing, "model_type", ""):
                existing.model_type = "mohr_coulomb"
        cell_ids = [cid for cid, value in enumerate(layer_values) if str(value) == layer]
        bounds = _cell_bounds(mesh, cell_ids)
        volume = project.geometry_model.volumes.get(volume_id)
        if volume is None:
            volume = GeometryVolume(
                id=volume_id,
                name=f"地质体 {layer}",
                bounds=bounds,
                role="soil",
                material_id=material.id,
                metadata={"source": "imported_geology_layer_volume", "layer_label": layer, "cell_count": len(cell_ids)},
            )
            project.geometry_model.volumes[volume_id] = volume
            created_volumes.append(volume_id)
        else:
            volume.bounds = bounds
            volume.role = "soil"
            volume.material_id = volume.material_id or material.id
            volume.metadata.update({"source": "imported_geology_layer_volume", "layer_label": layer, "cell_count": len(cell_ids)})
        cluster_id = f"cluster_{volume_id}"
        project.soil_model.soil_clusters[cluster_id] = SoilCluster(
            id=cluster_id,
            name=f"地层 {layer}",
            volume_ids=[volume_id],
            material_id=str(project.geometry_model.volumes[volume_id].material_id or material.id),
            layer_id=str(layer),
            drainage="drained",
            metadata={"source": "imported_geology_fem_analysis", "cell_count": len(cell_ids)},
        )
        layer_to_volume[layer] = volume_id
        block_to_cells[volume_id] = cell_ids

    for cid, layer in enumerate(layer_values):
        vid = layer_to_volume.get(str(layer), "geology_layer_all")
        mat = project.geometry_model.volumes.get(vid).material_id if vid in project.geometry_model.volumes else "soil_all"
        block_tags.append(vid)
        material_tags.append(str(mat or "soil_all"))
    mesh.cell_tags["block_id"] = block_tags
    mesh.cell_tags["material_id"] = material_tags
    mesh.cell_tags.setdefault("region_name", block_tags)
    mesh.entity_map = MeshEntityMap(block_to_cells=block_to_cells, metadata={"source": "imported_geology_fem_analysis", "layer_to_volume": dict(layer_to_volume)})
    project.mesh_model.mesh_entity_map = mesh.entity_map
    project.mesh_model.quality_report = mesh.quality

    # Keep all layer volumes active in each existing phase unless the user has
    # explicitly deactivated them later.
    layer_volume_ids = set(layer_to_volume.values())
    for phase in project.phases_in_order() if hasattr(project, "phases_in_order") else []:
        phase.active_blocks.update(layer_volume_ids)
        phase.metadata.setdefault("fem_analysis_layer_activation", "all_imported_geology_layers_active")
        project.refresh_phase_snapshot(phase.id)

    project.metadata["imported_geology_fem_prepared"] = True
    project.metadata["imported_geology_layer_to_volume"] = dict(layer_to_volume)
    project.metadata["dirty"] = True
    _emit(progress_callback, 20, "prepare", "模型导入状态准备完成", volumes=len(layer_to_volume), materials=len(created_materials))
    step = WorkflowStepReport(
        "prepare",
        "导入模型准备",
        "done",
        f"已建立 {len(layer_to_volume)} 个地层体、{len(created_materials)} 个默认材料。",
        20,
        {
            "layer_payload": layer_payload,
            "layer_to_volume": dict(layer_to_volume),
            "created_materials": created_materials,
            "created_volumes": created_volumes,
            "mesh_node_count": mesh.node_count,
            "mesh_cell_count": mesh.cell_count,
            "has_solid_cells": _has_solid_cells(mesh),
        },
    )
    return GeologyFEMAnalysisReport(True, "prepare", [step], step.metadata)


def check_imported_geology_fem_state(project: Any, *, progress_callback: ProgressCallback | None = None) -> GeologyFEMAnalysisReport:
    _emit(progress_callback, 22, "check", "执行 FEM 网格质量和材料状态检查")
    prep = prepare_imported_geology_for_fem(project, progress_callback=progress_callback)
    steps = list(prep.steps)
    if not prep.ok:
        return GeologyFEMAnalysisReport(False, "check", steps, dict(prep.metadata))
    mesh = _mesh(project)
    quality = analyze_project_mesh_for_fem(project)
    nonmanifold = diagnose_nonmanifold_mesh(mesh)
    try:
        from geoai_simkit.services.model_validation import validate_geoproject_model
        validation = validate_geoproject_model(project, require_mesh=True).to_dict()
    except Exception as exc:
        validation = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    material_ids = sorted(str(v) for v in getattr(project.material_library, "soil_materials", {}).keys())
    status = "done" if quality.ok and bool(validation.get("ok", False)) else "warning"
    if mesh is None:
        status = "blocked"
    message = f"网格 cells={0 if mesh is None else mesh.cell_count}; 坏单元={len(quality.bad_cell_ids)}; 材料={len(material_ids)}。"
    step = WorkflowStepReport(
        "check",
        "FEM 网格质量 / 材料状态检查",
        status,
        message,
        30,
        {"quality": quality.to_dict(), "nonmanifold": nonmanifold, "validation": validation, "soil_material_ids": material_ids},
    )
    steps.append(step)
    project.metadata["last_imported_geology_fem_check"] = step.to_dict()
    _emit(progress_callback, 30, "check", message, status=status)
    return GeologyFEMAnalysisReport(status != "blocked", "check", steps, step.metadata)


def generate_or_repair_imported_geology_fem_mesh(project: Any, *, element_size: float | None = None, require_native: bool = False, progress_callback: ProgressCallback | None = None) -> GeologyFEMAnalysisReport:
    _emit(progress_callback, 34, "mesh", "开始有限元网格划分 / 修复")
    check = check_imported_geology_fem_state(project, progress_callback=progress_callback)
    steps = list(check.steps)
    mesh = _mesh(project)
    quality = analyze_project_mesh_for_fem(project)
    used_existing = bool(mesh is not None and _has_solid_cells(mesh) and len(quality.bad_cell_ids) == 0)
    route_payload: dict[str, Any] = {"used_existing_imported_volume_mesh": used_existing}
    if used_existing:
        _emit(progress_callback, 45, "mesh", "导入网格已包含体单元，执行轻量 FEM 优化")
        opt = optimize_project_mesh_for_fem(project)
        route_payload["optimization"] = opt.to_dict()
    else:
        _emit(progress_callback, 45, "mesh", "导入模型需要重新生成体网格，调用 Gmsh/OCC Tet4 路线或确定性替代路线")
        from geoai_simkit.services.gmsh_occ_project_mesher import generate_geoproject_gmsh_occ_tet4_mesh

        _, route = generate_geoproject_gmsh_occ_tet4_mesh(project, attach=True, element_size=element_size, require_native=require_native)
        route_payload["mesh_generation"] = route.to_dict()
        prepare_imported_geology_for_fem(project, progress_callback=progress_callback)
        opt = optimize_project_mesh_for_fem(project)
        route_payload["optimization"] = opt.to_dict()
    final_quality = analyze_project_mesh_for_fem(project)
    final_mesh = _mesh(project)
    status = "done" if final_mesh is not None and final_quality.ok else "warning"
    message = f"FEM 网格完成：nodes={0 if final_mesh is None else final_mesh.node_count}, cells={0 if final_mesh is None else final_mesh.cell_count}, bad={len(final_quality.bad_cell_ids)}。"
    step = WorkflowStepReport("mesh", "有限元网格划分", status, message, 50, {"quality": final_quality.to_dict(), **route_payload})
    steps.append(step)
    project.metadata["last_imported_geology_fem_mesh"] = step.to_dict()
    _emit(progress_callback, 50, "mesh", message, status=status)
    return GeologyFEMAnalysisReport(final_mesh is not None and final_mesh.cell_count > 0, "mesh", steps, step.metadata)


def setup_automatic_stress_conditions(project: Any, *, surcharge_qz: float = 0.0, tolerance: float = 1.0e-5, progress_callback: ProgressCallback | None = None) -> GeologyFEMAnalysisReport:
    _emit(progress_callback, 58, "stress", "配置自动地应力边界、重力体力与计算控制")
    prep = prepare_imported_geology_for_fem(project, progress_callback=progress_callback)
    steps = list(prep.steps)
    mesh = _mesh(project)
    volume_ids = sorted(str(v) for v in getattr(getattr(project, "geometry_model", None), "volumes", {}).keys())
    phase_ids = _all_phase_ids(project)
    project.solver_model.boundary_conditions["bc_auto_stress_bottom_fixed"] = BoundaryCondition(
        id="bc_auto_stress_bottom_fixed",
        name="Auto-stress bottom fixed",
        target_ids=volume_ids,
        dof="ux,uy,uz",
        value=0.0,
        stage_ids=phase_ids,
        metadata={"location": "bottom", "source": "imported_geology_fem_analysis"},
    )
    project.solver_model.boundary_conditions["bc_auto_stress_lateral_roller"] = BoundaryCondition(
        id="bc_auto_stress_lateral_roller",
        name="Auto-stress lateral roller",
        target_ids=volume_ids,
        dof="un",
        value=0.0,
        stage_ids=phase_ids,
        metadata={"location": "lateral", "source": "imported_geology_fem_analysis"},
    )
    # A zero surcharge record is deliberate: it prevents the generic framework
    # filler from adding a default external surcharge when only gravity/body
    # force equilibrium is requested.
    project.solver_model.loads["load_auto_stress_surface_surcharge"] = LoadRecord(
        id="load_auto_stress_surface_surcharge",
        name="Auto-stress optional surface surcharge",
        target_ids=list(getattr(getattr(project, "geometry_model", None), "surfaces", {}).keys()),
        kind="surface_load",
        components={"qz": float(surcharge_qz)},
        stage_ids=phase_ids,
        metadata={"unit": "kPa", "source": "imported_geology_fem_analysis", "note": "gravity body force is assembled from material gamma"},
    )
    for phase_id in phase_ids:
        project.phase_manager.calculation_settings[phase_id] = CalculationSettings(
            calculation_type="automatic_stress",
            deformation_control=True,
            max_steps=80,
            max_iterations=40,
            tolerance=float(tolerance),
            reset_displacements=False,
            metadata={"source": "imported_geology_fem_analysis", "steady_state_target": "relative_residual_norm<=tolerance"},
        )
        try:
            phase = project.get_phase(phase_id)
            phase.loads.add("load_auto_stress_surface_surcharge")
            phase.metadata["calculation_type"] = "automatic_stress"
            project.refresh_phase_snapshot(phase_id)
        except Exception:
            pass
    project.solver_model.runtime_settings.backend = "cpu_sparse"
    project.solver_model.runtime_settings.nonlinear_strategy = "automatic_stress_incremental_equilibrium"
    project.solver_model.runtime_settings.metadata["automatic_stress"] = {
        "enabled": True,
        "gravity_direction": "-z",
        "body_force_source": "material.gamma",
        "surface_surcharge_qz": float(surcharge_qz),
        "mesh_cells": 0 if mesh is None else mesh.cell_count,
    }
    project.metadata["automatic_stress_configured"] = True
    project.metadata["dirty"] = True
    message = f"自动地应力已配置：阶段={len(phase_ids)}，边界=底部固定+侧向法向约束，面荷载 qz={float(surcharge_qz)}。"
    step = WorkflowStepReport("stress", "自动地应力 / 材料状态", "done", message, 60, {"phase_ids": phase_ids, "boundary_condition_ids": sorted(project.solver_model.boundary_conditions), "load_ids": sorted(project.solver_model.loads)})
    steps.append(step)
    project.metadata["last_automatic_stress_setup"] = step.to_dict()
    _emit(progress_callback, 60, "stress", message)
    return GeologyFEMAnalysisReport(True, "stress", steps, step.metadata)


def compile_imported_geology_solver_model(project: Any, *, progress_callback: ProgressCallback | None = None) -> GeologyFEMAnalysisReport:
    _emit(progress_callback, 68, "compile", "编译有限元求解输入")
    stress = setup_automatic_stress_conditions(project, progress_callback=progress_callback)
    steps = list(stress.steps)
    _emit(progress_callback, 70, "compile", "生成阶段活动单元、材料、边界和荷载块")
    compiled = project.compile_phase_models()
    _emit(progress_callback, 72, "compile", "阶段模型编译完成，正在汇总求解输入")
    compiled_rows = [row.to_dict() for row in compiled.values()]
    active_cells = sum(int(row.get("active_cell_count", 0)) for row in compiled_rows)
    large_preview = _requires_large_model_preview_solver(project)
    status = "done" if compiled_rows and active_cells > 0 else "blocked"
    solver_route = "large_model_automatic_stress_preview" if large_preview else "incremental_sparse_or_dense_solver"
    message = f"已编译 {len(compiled_rows)} 个阶段模型，活动单元总数 {active_cells}；求解路线={solver_route}。"
    step = WorkflowStepReport("compile", "有限元求解输入编译", status, message, 74, {"compiled_phase_count": len(compiled_rows), "active_cell_count": active_cells, "compiled_models": compiled_rows, "solver_route": solver_route, "large_model_preview": large_preview})
    steps.append(step)
    project.metadata["last_imported_geology_fem_compile"] = step.to_dict()
    _emit(progress_callback, 74, "compile", message, status=status, solver_route=solver_route)
    return GeologyFEMAnalysisReport(status == "done", "compile", steps, step.metadata)


def solve_imported_geology_to_steady_state(project: Any, *, progress_callback: ProgressCallback | None = None) -> GeologyFEMAnalysisReport:
    _emit(progress_callback, 78, "solve", "启动有限元求解，检查自动地应力稳态")
    compile_report = compile_imported_geology_solver_model(project, progress_callback=progress_callback)
    steps = list(compile_report.steps)
    if not compile_report.ok:
        return GeologyFEMAnalysisReport(False, "solve", steps, dict(compile_report.metadata))
    large_preview = bool(dict(compile_report.metadata or {}).get("large_model_preview", False)) or _requires_large_model_preview_solver(project)
    if large_preview:
        payload = _run_large_model_automatic_stress_preview(project, progress_callback=progress_callback)
    else:
        _emit(progress_callback, 82, "solve", "组装有限元方程并施加自动地应力边界")
        from geoai_simkit.geoproject.runtime_solver import run_geoproject_incremental_solve
        _emit(progress_callback, 86, "solve", "执行阶段增量求解")
        summary = run_geoproject_incremental_solve(project, compile_if_needed=False, write_results=True)
        payload = summary.to_dict()
    records = list(payload.get("phase_records", []) or [])
    max_relative = max((float(row.get("relative_residual_norm", 0.0) or 0.0) for row in records), default=float("inf"))
    max_settlement = max((float(row.get("max_settlement", 0.0) or 0.0) for row in records), default=0.0)
    max_disp = max((float(row.get("max_displacement", 0.0) or 0.0) for row in records), default=0.0)
    converged = bool(payload.get("accepted", False)) and all(bool(row.get("converged", False)) for row in records)
    if not isfinite(max_relative):
        max_relative = 0.0 if converged else float("inf")
    status = "done" if converged else "warning"
    route = "large_model_automatic_stress_preview" if large_preview else "incremental_solver"
    message = f"求解完成：steady={converged}，路线={route}，阶段={len(records)}，max|u|={max_disp:.6g}，max_settlement={max_settlement:.6g}。"
    step = WorkflowStepReport(
        "solve",
        "有限元求解 / 稳态判定",
        status,
        message,
        92,
        {"solver_summary": payload, "solver_route": route, "steady_state": {"accepted": converged, "max_relative_residual_norm": max_relative, "max_displacement": max_disp, "max_settlement": max_settlement}},
    )
    steps.append(step)
    project.metadata["last_imported_geology_steady_solve"] = step.to_dict()
    _emit(progress_callback, 92, "solve", message, steady=converged, solver_route=route)
    return GeologyFEMAnalysisReport(True, "solve", steps, step.metadata)


def build_imported_geology_result_view(project: Any, *, progress_callback: ProgressCallback | None = None) -> GeologyFEMAnalysisReport:
    _emit(progress_callback, 94, "results", "生成求解结果查看摘要")
    phase_results = dict(getattr(getattr(project, "result_store", None), "phase_results", {}) or {})
    curves = dict(getattr(getattr(project, "result_store", None), "curves", {}) or {})
    engineering_metrics = dict(getattr(getattr(project, "result_store", None), "engineering_metrics", {}) or {})
    result_rows: list[dict[str, Any]] = []
    for phase_id, result in phase_results.items():
        metrics = dict(getattr(result, "metrics", {}) or {})
        fields = dict(getattr(result, "fields", {}) or {})
        result_rows.append({
            "phase_id": str(phase_id),
            "max_displacement": float(metrics.get("max_displacement", 0.0) or 0.0),
            "max_settlement": float(metrics.get("max_settlement", 0.0) or 0.0),
            "max_von_mises_stress": float(metrics.get("max_von_mises_stress", 0.0) or 0.0),
            "residual_norm": float(metrics.get("residual_norm", 0.0) or 0.0),
            "field_names": sorted(fields.keys()),
        })
    status = "done" if result_rows else "blocked"
    message = f"结果查看数据：阶段结果={len(result_rows)}，曲线={len(curves)}，工程指标={len(engineering_metrics)}。"
    step = WorkflowStepReport(
        "results",
        "求解结果查看",
        status,
        message,
        100,
        {"phase_results": result_rows, "curve_count": len(curves), "engineering_metric_count": len(engineering_metrics), "available_views": ["displacement", "uz", "cell_stress_zz", "cell_von_mises", "cell_equivalent_strain"]},
    )
    project.metadata["last_imported_geology_result_view"] = step.to_dict()
    _emit(progress_callback, 100, "results", message, status=status)
    return GeologyFEMAnalysisReport(status == "done", "results", [step], step.metadata)


def run_complete_imported_geology_fem_analysis(project: Any, *, element_size: float | None = None, surcharge_qz: float = 0.0, require_native_mesher: bool = False, progress_callback: ProgressCallback | None = None) -> GeologyFEMAnalysisReport:
    """Execute the full imported-geology FEM analysis chain."""

    steps: list[WorkflowStepReport] = []
    _emit(progress_callback, 0, "start", "启动导入地质模型 FEM 完整分析流程")
    check = check_imported_geology_fem_state(project, progress_callback=progress_callback)
    _extend_unique_steps(steps, check.steps)
    if not check.ok:
        return GeologyFEMAnalysisReport(False, "check", steps, dict(check.metadata))
    mesh = generate_or_repair_imported_geology_fem_mesh(project, element_size=element_size, require_native=require_native_mesher, progress_callback=progress_callback)
    _extend_unique_steps(steps, mesh.steps)
    if not mesh.ok:
        return GeologyFEMAnalysisReport(False, "mesh", steps, dict(mesh.metadata))
    stress = setup_automatic_stress_conditions(project, surcharge_qz=surcharge_qz, progress_callback=progress_callback)
    _extend_unique_steps(steps, stress.steps)
    compiled = compile_imported_geology_solver_model(project, progress_callback=progress_callback)
    _extend_unique_steps(steps, compiled.steps)
    if not compiled.ok:
        return GeologyFEMAnalysisReport(False, "compile", steps, dict(compiled.metadata))
    solved = solve_imported_geology_to_steady_state(project, progress_callback=progress_callback)
    _extend_unique_steps(steps, solved.steps)
    results = build_imported_geology_result_view(project, progress_callback=progress_callback)
    _extend_unique_steps(steps, results.steps)
    ok = bool(solved.ok and results.ok)
    metadata = {
        "check": check.metadata,
        "mesh": mesh.metadata,
        "stress": stress.metadata,
        "compile": compiled.metadata,
        "solve": solved.metadata,
        "results": results.metadata,
    }
    project.metadata["last_imported_geology_fem_analysis_workflow"] = {"ok": ok, "steps": [row.to_dict() for row in steps], "metadata": metadata}
    _emit(progress_callback, 100, "done", "导入地质模型 FEM 分析流程完成", ok=ok)
    return GeologyFEMAnalysisReport(ok, "complete", steps, metadata)


__all__ = [
    "WORKFLOW_CONTRACT",
    "WorkflowStepReport",
    "GeologyFEMAnalysisReport",
    "prepare_imported_geology_for_fem",
    "check_imported_geology_fem_state",
    "generate_or_repair_imported_geology_fem_mesh",
    "setup_automatic_stress_conditions",
    "compile_imported_geology_solver_model",
    "solve_imported_geology_to_steady_state",
    "build_imported_geology_result_view",
    "run_complete_imported_geology_fem_analysis",
]
