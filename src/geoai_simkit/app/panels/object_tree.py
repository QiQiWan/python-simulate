from __future__ import annotations

"""Object-tree payloads backed by GeoProjectDocument."""

from typing import Any

from geoai_simkit.app.geoproject_source import get_geoproject_document, geoproject_summary
from geoai_simkit.geoproject import GeoProjectDocument


class ObjectTreeNode:
    """Small tree node without dataclass recursion for robust Python startup."""

    def __init__(
        self,
        id: str,
        label: str,
        type: str,
        entity_id: str | None = None,
        source: str = "geoproject",
        children: list["ObjectTreeNode"] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.label = label
        self.type = type
        self.entity_id = entity_id
        self.source = source
        self.children = list(children or [])
        self.metadata = dict(metadata or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "entity_id": self.entity_id,
            "source": self.source,
            "children": [child.to_dict() for child in self.children],
            "metadata": dict(self.metadata),
        }


def _append_group(root: ObjectTreeNode, group_id: str, label: str, nodes: list[ObjectTreeNode]) -> None:
    root.children.append(ObjectTreeNode(id=group_id, label=f"{label} ({len(nodes)})", type="group", children=nodes))


def _material_nodes(project: GeoProjectDocument) -> list[ObjectTreeNode]:
    rows: list[ObjectTreeNode] = []
    groups = (
        ("soil", project.material_library.soil_materials),
        ("plate", project.material_library.plate_materials),
        ("beam", project.material_library.beam_materials),
        ("interface", project.material_library.interface_materials),
    )
    for category, bucket in groups:
        for mid, record in bucket.items():
            rows.append(ObjectTreeNode(
                id=f"material:{category}:{mid}", label=f"{record.name}  [{category}/{record.model_type}]", type="material",
                entity_id=mid, source="geoproject.material_library", metadata={"category": category, **record.to_dict()},
            ))
    for did, record in project.material_library.drainage_groundwater_properties.items():
        rows.append(ObjectTreeNode(id=f"drainage:{did}", label=f"{record.name}  [groundwater]", type="drainage", entity_id=did, source="geoproject.material_library", metadata=record.to_dict()))
    return rows


def _stage_nodes(project: GeoProjectDocument) -> list[ObjectTreeNode]:
    rows: list[ObjectTreeNode] = []
    for stage in project.phases_in_order():
        sid = stage.id
        snapshot = project.phase_manager.phase_state_snapshots.get(sid)
        rows.append(ObjectTreeNode(
            id=f"phase:{sid}", label=f"{stage.name}{'  *' if sid == project.phase_manager.active_phase_id else ''}", type="stage",
            entity_id=sid, source="geoproject.phase_manager", metadata={"snapshot": None if snapshot is None else snapshot.to_dict(), **stage.to_dict()},
        ))
    return rows


def build_geoproject_object_tree(project: GeoProjectDocument) -> ObjectTreeNode:
    summary = geoproject_summary(project)
    root = ObjectTreeNode(id="project", label=project.project_settings.name, type="project", entity_id=project.project_settings.project_id, metadata=summary)

    settings = ObjectTreeNode(id="project_settings", label="Project settings", type="group", metadata=project.project_settings.to_dict())
    root.children.append(settings)

    soil = ObjectTreeNode(id="soil_model", label="Soil model", type="group", metadata=project.soil_model.to_dict())
    soil.children.append(ObjectTreeNode(id="soil_contour", label="Soil contour", type="soil_contour", entity_id=project.soil_model.soil_contour.id, source="geoproject.soil_model", metadata=project.soil_model.soil_contour.to_dict()))
    _append_group(soil, "boreholes", "Boreholes", [ObjectTreeNode(id=f"borehole:{bid}", label=row.name, type="borehole", entity_id=bid, source="geoproject.soil_model", metadata=row.to_dict()) for bid, row in project.soil_model.boreholes.items()])
    _append_group(soil, "soil_layer_surfaces", "Soil layer surfaces", [ObjectTreeNode(id=f"soil_surface:{sid}", label=row.name, type="soil_layer_surface", entity_id=sid, source="geoproject.soil_model", metadata=row.to_dict()) for sid, row in project.soil_model.soil_layer_surfaces.items()])
    _append_group(soil, "soil_clusters", "Soil clusters", [ObjectTreeNode(id=f"soil_cluster:{cid}", label=f"{row.name}  [{row.material_id}]", type="soil_cluster", entity_id=cid, source="geoproject.soil_model", metadata=row.to_dict()) for cid, row in project.soil_model.soil_clusters.items()])
    _append_group(soil, "water_conditions", "Water conditions", [ObjectTreeNode(id=f"water:{wid}", label=row.name, type="water_condition", entity_id=wid, source="geoproject.soil_model", metadata=row.to_dict()) for wid, row in project.soil_model.water_conditions.items()])
    root.children.append(soil)

    geometry = ObjectTreeNode(id="geometry_model", label="Geometry model", type="group", metadata=project.geometry_model.metadata)
    _append_group(geometry, "geometry_points", "Points", [ObjectTreeNode(id=f"point:{pid}", label=pid, type="point", entity_id=pid, source="geoproject.geometry_model", metadata=point.to_dict()) for pid, point in project.geometry_model.points.items()])
    _append_group(geometry, "geometry_curves", "Curves", [ObjectTreeNode(id=f"curve:{cid}", label=f"{row.name}  [{row.kind}]", type="curve", entity_id=cid, source="geoproject.geometry_model", metadata=row.to_dict()) for cid, row in project.geometry_model.curves.items()])
    _append_group(geometry, "geometry_surfaces", "Surfaces", [ObjectTreeNode(id=f"surface:{sid}", label=f"{row.name}  [{row.kind}]", type="surface", entity_id=sid, source="geoproject.geometry_model", metadata=row.to_dict()) for sid, row in project.geometry_model.surfaces.items()])
    volume_groups: dict[str, list[ObjectTreeNode]] = {"soil": [], "excavation": [], "wall": [], "support": [], "structure": [], "other": []}
    for vid, volume in project.geometry_model.volumes.items():
        key = volume.role if volume.role in volume_groups else "other"
        volume_groups[key].append(ObjectTreeNode(id=f"volume:{vid}", label=f"{volume.name}  [{volume.role}]", type="volume", entity_id=vid, source="geoproject.geometry_model", metadata=volume.to_dict()))
    for key, label in (("soil", "Soil volumes"), ("excavation", "Excavation volumes"), ("wall", "Wall volumes"), ("support", "Support volumes"), ("structure", "Structure volumes"), ("other", "Other volumes")):
        _append_group(geometry, f"volumes_{key}", label, volume_groups[key])
    _append_group(geometry, "parametric_features", "Parametric features", [ObjectTreeNode(id=f"feature:{fid}", label=f"{fid}  [{row.type}]", type="partition_feature", entity_id=fid, source="geoproject.geometry_model", metadata=row.to_dict()) for fid, row in project.geometry_model.parametric_features.items()])
    root.children.append(geometry)

    topology = ObjectTreeNode(id="topology_graph", label="Topology graph", type="group", metadata=project.topology_graph.to_dict())
    rel_groups: dict[str, list[ObjectTreeNode]] = {"owns": [], "adjacent_to": [], "contacts": [], "generated_by": [], "other": []}
    for idx, edge in enumerate(project.topology_graph.edges):
        key = edge.relation if edge.relation in rel_groups else "other"
        rel_groups[key].append(ObjectTreeNode(id=f"topology_edge:{idx:04d}", label=f"{edge.source} --{edge.relation}--> {edge.target}", type="topology_edge", source="geoproject.topology_graph", metadata=edge.to_dict()))
    _append_group(topology, "topology_ownership", "Ownership relations", rel_groups["owns"])
    _append_group(topology, "topology_adjacency", "Adjacency relations", rel_groups["adjacent_to"])
    _append_group(topology, "topology_contacts", "Contact/interface candidates", rel_groups["contacts"])
    _append_group(topology, "topology_generated_by", "Generated-by relations", rel_groups["generated_by"])
    if rel_groups["other"]:
        _append_group(topology, "topology_other", "Other relations", rel_groups["other"])
    root.children.append(topology)

    structures = ObjectTreeNode(id="structure_model", label="Structure model", type="group", metadata=project.structure_model.metadata)
    for group_id, label, bucket, node_type in (
        ("plates", "Plates", project.structure_model.plates, "plate"),
        ("beams", "Beams", project.structure_model.beams, "beam"),
        ("embedded_beams", "Embedded beams", project.structure_model.embedded_beams, "embedded_beam"),
        ("anchors", "Anchors", project.structure_model.anchors, "anchor"),
        ("structural_interfaces", "Structural interfaces", project.structure_model.structural_interfaces, "interface"),
    ):
        _append_group(structures, group_id, label, [ObjectTreeNode(id=f"{node_type}:{sid}", label=row.name, type=node_type, entity_id=sid, source="geoproject.structure_model", metadata=row.to_dict()) for sid, row in bucket.items()])
    root.children.append(structures)

    _append_group(root, "material_library", "Material library", _material_nodes(project))

    mesh = ObjectTreeNode(id="mesh_model", label="Mesh model", type="group", metadata=project.mesh_model.to_dict())
    mesh.children.append(ObjectTreeNode(id="mesh_settings", label=f"Mesh settings  [{project.mesh_model.mesh_settings.element_family}]", type="mesh_settings", source="geoproject.mesh_model", metadata=project.mesh_model.mesh_settings.to_dict()))
    if project.mesh_model.mesh_document is not None:
        mesh.children.append(ObjectTreeNode(id="mesh_document", label=f"Mesh document: {project.mesh_model.mesh_document.cell_count} cells / {project.mesh_model.mesh_document.node_count} nodes", type="mesh", source="geoproject.mesh_model", metadata=project.mesh_model.mesh_document.to_dict()))
    mesh.children.append(ObjectTreeNode(id="mesh_quality", label="Quality report", type="mesh_quality", source="geoproject.mesh_model", metadata=project.mesh_model.quality_report.to_dict()))
    root.children.append(mesh)

    _append_group(root, "phase_manager", "Phase manager", _stage_nodes(project))

    solver = ObjectTreeNode(id="solver_model", label="Solver model", type="group", metadata=project.solver_model.to_dict())
    _append_group(solver, "compiled_phase_models", "Compiled phase models", [ObjectTreeNode(id=f"compiled:{cid}", label=f"{row.phase_id}: {row.active_cell_count} cells", type="compiled_phase_model", entity_id=cid, source="geoproject.solver_model", metadata=row.to_dict()) for cid, row in project.solver_model.compiled_phase_models.items()])
    _append_group(solver, "boundary_conditions", "Boundary conditions", [ObjectTreeNode(id=f"bc:{bid}", label=row.name, type="boundary_condition", entity_id=bid, source="geoproject.solver_model", metadata=row.to_dict()) for bid, row in project.solver_model.boundary_conditions.items()])
    _append_group(solver, "loads", "Loads", [ObjectTreeNode(id=f"load:{lid}", label=row.name, type="load", entity_id=lid, source="geoproject.solver_model", metadata=row.to_dict()) for lid, row in project.solver_model.loads.items()])
    solver.children.append(ObjectTreeNode(id="runtime_settings", label=f"Runtime settings  [{project.solver_model.runtime_settings.backend}]", type="runtime_settings", source="geoproject.solver_model", metadata=project.solver_model.runtime_settings.to_dict()))
    root.children.append(solver)

    results = ObjectTreeNode(id="result_store", label="Result store", type="group", metadata=project.result_store.to_dict())
    _append_group(results, "phase_results", "Phase results", [ObjectTreeNode(id=f"result:{sid}", label=f"{sid} metrics", type="result", entity_id=sid, source="geoproject.result_store", metadata=row.to_dict()) for sid, row in project.result_store.phase_results.items()])
    _append_group(results, "engineering_metrics", "Engineering metrics", [ObjectTreeNode(id=f"metric:{mid}", label=f"{row.name}: {row.value:g} {row.unit}", type="engineering_metric", entity_id=mid, source="geoproject.result_store", metadata=row.to_dict()) for mid, row in project.result_store.engineering_metrics.items()])
    _append_group(results, "curves", "Curves", [ObjectTreeNode(id=f"curve_result:{cid}", label=row.name, type="result_curve", entity_id=cid, source="geoproject.result_store", metadata=row.to_dict()) for cid, row in project.result_store.curves.items()])
    _append_group(results, "sections", "Sections", [ObjectTreeNode(id=f"section:{sid}", label=row.name, type="result_section", entity_id=sid, source="geoproject.result_store", metadata=row.to_dict()) for sid, row in project.result_store.sections.items()])
    _append_group(results, "reports", "Reports", [ObjectTreeNode(id=f"report:{rid}", label=row.title, type="report", entity_id=rid, source="geoproject.result_store", metadata=row.to_dict()) for rid, row in project.result_store.reports.items()])
    root.children.append(results)
    return root



def _compact_group(root: ObjectTreeNode, group_id: str, label: str, nodes: list[ObjectTreeNode]) -> None:
    # Keep the model browser engineering-facing: only show editable physical objects.
    root.children.append(ObjectTreeNode(id=group_id, label=f"{label} ({len(nodes)})", type="group", children=nodes, metadata={"compact": True}))


def _mesh_layer_nodes(project: GeoProjectDocument) -> list[ObjectTreeNode]:
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    if mesh is None:
        return []
    tags = dict(getattr(mesh, "cell_tags", {}) or {})
    scalar = None
    meta = dict(getattr(mesh, "metadata", {}) or {})
    preferred = [
        str(meta.get("preferred_geology_scalar") or ""),
        str(meta.get("active_cell_scalar") or ""),
        "soil_id", "SoilID", "material_id", "stratum_id", "layer_id", "Layer", "gmsh_physical", "geology_layer_id", "display_group",
    ]
    for key in preferred:
        if not key:
            continue
        values = list(tags.get(key, []) or [])
        if values:
            scalar = key
            break
    if scalar is None:
        return [ObjectTreeNode(
            id="imported_geology_model",
            label=f"导入地质模型  [{getattr(mesh, 'cell_count', 0)} cells]",
            type="geology_model",
            entity_id="imported_geology_model",
            source="geoproject.mesh_model",
            metadata={"role": "geology", "mesh_node_count": getattr(mesh, "node_count", 0), "mesh_cell_count": getattr(mesh, "cell_count", 0)},
        )]
    counts: dict[str, int] = {}
    for value in list(tags.get(scalar, []) or []):
        label = str(value)
        counts[label] = counts.get(label, 0) + 1
    layer_props = dict(dict(getattr(mesh, "metadata", {}) or {}).get("layer_properties", {}) or {})
    model_label = str(dict(getattr(mesh, "metadata", {}) or {}).get("display_name") or "导入地质模型")
    rows = [ObjectTreeNode(
        id="imported_geology_model",
        label=f"{model_label}  [{len(counts)} layers]",
        type="geology_model",
        entity_id="imported_geology_model",
        source="geoproject.mesh_model",
        metadata={"role": "geology", "display_scalar": scalar, "mesh_node_count": getattr(mesh, "node_count", 0), "mesh_cell_count": getattr(mesh, "cell_count", 0), "name": model_label},
    )]
    child_nodes: list[ObjectTreeNode] = []
    for label, count in sorted(counts.items(), key=lambda kv: kv[0]):
        props = dict(layer_props.get(str(label), {}) or {})
        display_name = str(props.get("name") or f"地层 {label}")
        material_id = str(props.get("material_id") or (label if scalar in {"material_id", "soil_id", "SoilID"} else ""))
        child_nodes.append(ObjectTreeNode(
            id=f"geology_layer:{label}",
            label=f"{display_name}  [{count} cells]" + (f"  <{material_id}>" if material_id else ""),
            type="geology_layer",
            entity_id=f"geology_layer:{label}",
            source="geoproject.mesh_model.cell_tags",
            metadata={"role": "geology", "display_scalar": scalar, "layer_value": label, "cell_count": count, "name": display_name, "material_id": material_id},
        ))
    rows[0].children.extend(child_nodes)
    return rows


def build_compact_engineering_object_tree(project: GeoProjectDocument) -> ObjectTreeNode:
    """Build a concise engineering object tree for the Qt model browser.

    The full object tree remains available through build_geoproject_object_tree.
    This compact tree intentionally exposes only the physical objects that users
    normally select/edit in the viewport: geology, retaining walls, horizontal
    supports, beams and anchors.
    """
    summary = geoproject_summary(project)
    root = ObjectTreeNode(id="project", label=project.project_settings.name, type="project", entity_id=project.project_settings.project_id, metadata={**summary, "compact": True})

    geology_nodes: list[ObjectTreeNode] = []
    geology_nodes.extend(_mesh_layer_nodes(project))
    has_imported_mesh = bool(getattr(getattr(project, "mesh_model", None), "mesh_document", None) is not None)
    for cid, row in project.soil_model.soil_clusters.items():
        if has_imported_mesh and str(dict(getattr(row, "metadata", {}) or {}).get("source") or "") == "meshio_geology_importer":
            continue
        geology_nodes.append(ObjectTreeNode(id=f"soil_cluster:{cid}", label=f"{row.name}  [{row.material_id}]", type="geology_body", entity_id=cid, source="geoproject.soil_model", metadata={"role": "geology", **row.to_dict()}))
    for vid, volume in project.geometry_model.volumes.items():
        vmeta = dict(getattr(volume, "metadata", {}) or {})
        if has_imported_mesh and str(vmeta.get("source") or "") == "meshio_geology_importer":
            continue
        if str(getattr(volume, "role", "")) in {"soil", "geology", "excavation"}:
            geology_nodes.append(ObjectTreeNode(id=f"volume:{vid}", label=f"{volume.name}  [{volume.role}]", type="geology_body", entity_id=vid, source="geoproject.geometry_model", metadata={"role": "geology", **volume.to_dict()}))
    _compact_group(root, "geology_bodies", "地质体", geology_nodes)

    wall_nodes: list[ObjectTreeNode] = []
    for sid, row in project.structure_model.plates.items():
        data = row.to_dict()
        role = str(data.get("role") or data.get("orientation") or "")
        if role in {"wall", "retaining_wall", "diaphragm_wall", "围护墙", ""}:
            wall_nodes.append(ObjectTreeNode(id=f"plate:{sid}", label=row.name, type="retaining_wall", entity_id=sid, source="geoproject.structure_model", metadata={"role": "retaining_wall", **data}))
    for vid, volume in project.geometry_model.volumes.items():
        if str(getattr(volume, "role", "")) == "wall":
            wall_nodes.append(ObjectTreeNode(id=f"volume:{vid}", label=volume.name, type="retaining_wall", entity_id=vid, source="geoproject.geometry_model", metadata={"role": "retaining_wall", **volume.to_dict()}))
    _compact_group(root, "retaining_walls", "围护墙", wall_nodes)

    support_nodes: list[ObjectTreeNode] = []
    beam_nodes: list[ObjectTreeNode] = []
    for sid, row in project.structure_model.beams.items():
        data = row.to_dict()
        role = str(data.get("role") or data.get("orientation") or "")
        node = ObjectTreeNode(id=f"beam:{sid}", label=row.name, type="horizontal_support" if role in {"support", "horizontal_support", "strut", "支撑"} else "beam", entity_id=sid, source="geoproject.structure_model", metadata={**data})
        (support_nodes if node.type == "horizontal_support" else beam_nodes).append(node)
    for sid, row in project.structure_model.embedded_beams.items():
        beam_nodes.append(ObjectTreeNode(id=f"embedded_beam:{sid}", label=row.name, type="beam", entity_id=sid, source="geoproject.structure_model", metadata={"role": "beam", **row.to_dict()}))
    _compact_group(root, "horizontal_supports", "水平支撑", support_nodes)
    _compact_group(root, "beams", "梁", beam_nodes)

    anchor_nodes = [ObjectTreeNode(id=f"anchor:{sid}", label=row.name, type="anchor", entity_id=sid, source="geoproject.structure_model", metadata={"role": "anchor", **row.to_dict()}) for sid, row in project.structure_model.anchors.items()]
    _compact_group(root, "anchors", "锚杆", anchor_nodes)
    return root

def build_object_tree(document: Any) -> ObjectTreeNode:
    return build_geoproject_object_tree(get_geoproject_document(document))


def object_tree_to_rows(node: ObjectTreeNode, *, depth: int = 0) -> list[dict[str, Any]]:
    row = node.to_dict()
    row["depth"] = depth
    rows = [row]
    for child in node.children:
        rows.extend(object_tree_to_rows(child, depth=depth + 1))
    return rows


__all__ = ["ObjectTreeNode", "build_object_tree", "build_geoproject_object_tree", "build_compact_engineering_object_tree", "object_tree_to_rows"]
