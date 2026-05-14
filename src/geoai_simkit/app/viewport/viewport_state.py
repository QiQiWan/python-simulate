from __future__ import annotations

"""Viewport scene contract independent from Qt/PyVista implementation."""

from dataclasses import dataclass, field
from typing import Any, Literal

from geoai_simkit.document.selection import SelectionRef, SelectionSet

PrimitiveKind = Literal["block", "face", "mesh_cell", "curve", "point", "edge", "surface", "support", "contact_pair", "partition_feature", "result_contour"]


@dataclass(slots=True)
class ScenePrimitive:
    id: str
    kind: PrimitiveKind
    entity_id: str
    label: str = ""
    bounds: tuple[float, float, float, float, float, float] | None = None
    visible: bool = True
    pickable: bool = True
    style: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "entity_id": self.entity_id,
            "label": self.label or self.entity_id,
            "bounds": list(self.bounds) if self.bounds is not None else None,
            "visible": bool(self.visible),
            "pickable": bool(self.pickable),
            "style": dict(self.style),
            "metadata": dict(self.metadata),
        }


def _cad_topology_records_by_source(project: Any) -> dict[str, dict[str, list[Any]]]:
    store = getattr(project, "cad_shape_store", None)
    records = getattr(store, "topology_records", {}) or {}
    shapes = getattr(store, "shapes", {}) or {}
    out: dict[str, dict[str, list[Any]]] = {}
    for topo in records.values():
        kind = str(getattr(topo, "kind", "") or "")
        if kind not in {"solid", "face", "edge"}:
            continue
        source = str(getattr(topo, "source_entity_id", "") or "")
        if not source:
            shape = shapes.get(str(getattr(topo, "shape_id", "") or ""))
            source_ids = list(getattr(shape, "source_entity_ids", []) or []) if shape is not None else []
            source = str(source_ids[0]) if source_ids else ""
        if not source:
            continue
        out.setdefault(source, {}).setdefault(kind, []).append(topo)
    return out


@dataclass(slots=True)
class ViewportState:
    primitives: dict[str, ScenePrimitive] = field(default_factory=dict)
    selection: SelectionSet = field(default_factory=SelectionSet)
    active_stage_id: str | None = None
    camera: dict[str, Any] = field(default_factory=dict)
    overlays: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def update_from_geoproject_document(self, project: Any, *, stage_id: str | None = None) -> None:
        self.primitives.clear()
        self.active_stage_id = stage_id or getattr(project.phase_manager, "active_phase_id", None)
        snapshot = None
        try:
            snapshot = project.phase_manager.phase_state_snapshots.get(self.active_stage_id) or project.refresh_phase_snapshot(self.active_stage_id)
        except Exception:
            snapshot = None
        active_volumes = set(snapshot.active_volume_ids) if snapshot is not None else set(project.geometry_model.volumes)
        for point_id, point in project.geometry_model.points.items():
            xyz = point.to_tuple()
            self.primitives[f"primitive:point:{point_id}"] = ScenePrimitive(
                id=f"primitive:point:{point_id}",
                kind="point",
                entity_id=point_id,
                label=point_id,
                bounds=(xyz[0], xyz[0], xyz[1], xyz[1], xyz[2], xyz[2]),
                visible=True,
                pickable=True,
                style={"role": "point", "active": True, "opacity": 1.0},
                metadata=point.to_dict(),
            )
        for curve_id, curve in project.geometry_model.curves.items():
            pts = [project.geometry_model.points[pid].to_tuple() for pid in curve.point_ids if pid in project.geometry_model.points]
            bounds = None
            if pts:
                xs, ys, zs = zip(*pts)
                bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
            kind = "support" if curve.kind == "support_axis" else "edge"
            self.primitives[f"primitive:{kind}:{curve_id}"] = ScenePrimitive(
                id=f"primitive:{kind}:{curve_id}",
                kind=kind,
                entity_id=curve_id,
                label=curve.name,
                bounds=bounds,
                visible=True,
                pickable=True,
                style={"role": curve.kind, "active": True, "opacity": 1.0},
                metadata={**curve.to_dict(), "points": [list(p) for p in pts]},
            )
        for surface_id, surface in project.geometry_model.surfaces.items():
            pts = [project.geometry_model.points[pid].to_tuple() for pid in surface.point_ids if pid in project.geometry_model.points]
            bounds = None
            if pts:
                xs, ys, zs = zip(*pts)
                bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
            self.primitives[f"primitive:surface:{surface_id}"] = ScenePrimitive(
                id=f"primitive:surface:{surface_id}",
                kind="surface",
                entity_id=surface_id,
                label=surface.name,
                bounds=bounds,
                visible=True,
                pickable=True,
                style={"role": surface.kind, "active": True, "opacity": 0.35},
                metadata={**surface.to_dict(), "points": [list(p) for p in pts]},
            )
        cad_topology_by_source = _cad_topology_records_by_source(project)
        for volume_id, volume in project.geometry_model.volumes.items():
            is_active = volume_id in active_volumes
            topology_for_volume = cad_topology_by_source.get(volume_id, {})
            face_ids = [str(getattr(t, "id", "")) for t in topology_for_volume.get("face", []) if str(getattr(t, "id", ""))]
            edge_ids = [str(getattr(t, "id", "")) for t in topology_for_volume.get("edge", []) if str(getattr(t, "id", ""))]
            solid_ids = [str(getattr(t, "id", "")) for t in topology_for_volume.get("solid", []) if str(getattr(t, "id", ""))]
            self.primitives[f"primitive:block:{volume_id}"] = ScenePrimitive(
                id=f"primitive:block:{volume_id}",
                kind="block",
                entity_id=volume_id,
                label=volume.name,
                bounds=volume.bounds,
                visible=bool(volume.metadata.get("visible", True)),
                pickable=not bool(volume.metadata.get("locked", False)),
                style={"role": volume.role, "active": is_active, "opacity": 1.0 if is_active else 0.18},
                metadata={
                    **dict(getattr(volume, "metadata", {}) or {}),
                    "name": volume.name,
                    "material_id": volume.material_id,
                    "role": volume.role,
                    "surface_ids": list(volume.surface_ids),
                    "topology_face_ids": face_ids,
                    "topology_edge_ids": edge_ids,
                    "topology_solid_ids": solid_ids,
                    "render_mode": "outline_only" if str(dict(getattr(volume, "metadata", {}) or {}).get("source") or "") == "meshio_geology_importer" else "solid",
                },
            )
        for record in [*project.structure_model.plates.values(), *project.structure_model.beams.values(), *project.structure_model.embedded_beams.values(), *project.structure_model.anchors.values()]:
            curve = project.geometry_model.curves.get(record.geometry_ref)
            pts = [] if curve is None else [project.geometry_model.points[pid].to_tuple() for pid in curve.point_ids if pid in project.geometry_model.points]
            bounds = None
            if pts:
                xs, ys, zs = zip(*pts)
                bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
            self.primitives[f"primitive:support:{record.id}"] = ScenePrimitive(
                id=f"primitive:support:{record.id}",
                kind="support",
                entity_id=record.id,
                label=record.name,
                bounds=bounds,
                visible=True,
                pickable=True,
                style={"role": record.metadata.get("support_type", "structure"), "active": snapshot is None or record.id in snapshot.active_structure_ids, "opacity": 1.0},
                metadata={**record.to_dict(), "points": [list(p) for p in pts]},
            )
        for interface in project.structure_model.structural_interfaces.values():
            a = project.geometry_model.volumes.get(interface.master_ref)
            b = project.geometry_model.volumes.get(interface.slave_ref)
            bounds = None
            if a is not None and b is not None and a.bounds is not None and b.bounds is not None:
                ac = ((a.bounds[0]+a.bounds[1])*0.5, (a.bounds[2]+a.bounds[3])*0.5, (a.bounds[4]+a.bounds[5])*0.5)
                bc = ((b.bounds[0]+b.bounds[1])*0.5, (b.bounds[2]+b.bounds[3])*0.5, (b.bounds[4]+b.bounds[5])*0.5)
                bounds = (min(ac[0], bc[0]), max(ac[0], bc[0]), min(ac[1], bc[1]), max(ac[1], bc[1]), min(ac[2], bc[2]), max(ac[2], bc[2]))
            self.primitives[f"primitive:contact_pair:{interface.id}"] = ScenePrimitive(
                id=f"primitive:contact_pair:{interface.id}",
                kind="contact_pair",
                entity_id=interface.id,
                label=interface.name,
                bounds=bounds,
                visible=True,
                pickable=True,
                style={"role": interface.contact_mode, "active": snapshot is None or interface.id in snapshot.active_interface_ids, "opacity": 0.9},
                metadata=interface.to_dict(),
            )
        for source_id, by_kind in cad_topology_by_source.items():
            for kind in ("face", "edge"):
                for topo in by_kind.get(kind, []):
                    bounds = getattr(topo, "bounds", None)
                    if bounds is None:
                        continue
                    topo_id = str(getattr(topo, "id", ""))
                    primitive_id = f"primitive:cad_topology:{kind}:{topo_id}"
                    self.primitives[primitive_id] = ScenePrimitive(
                        id=primitive_id,
                        kind=kind,
                        entity_id=topo_id,
                        label=str(getattr(topo, "persistent_name", "") or topo_id),
                        bounds=tuple(float(v) for v in bounds),
                        visible=True,
                        pickable=True,
                        style={"role": str(getattr(topo, "orientation", "") or kind), "active": True, "opacity": 0.22 if kind == "face" else 1.0},
                        metadata={
                            **topo.to_dict(),
                            "topology_id": topo_id,
                            "topology_kind": kind,
                            "shape_id": str(getattr(topo, "shape_id", "") or ""),
                            "source_entity_id": source_id,
                            "topology_identity_key": f"topology:{kind}:{getattr(topo, 'shape_id', '')}:{topo_id}",
                            "selection_key": f"topology:{kind}:{getattr(topo, 'shape_id', '')}:{topo_id}",
                        },
                    )
        self.metadata = {"primitive_count": len(self.primitives), "source": "GeoProjectDocument", "cad_topology_pickable": bool(cad_topology_by_source)}

    def update_from_engineering_document(self, document: Any, *, stage_id: str | None = None) -> None:
        if hasattr(document, "geometry_model") and hasattr(document, "phase_manager"):
            self.update_from_geoproject_document(document, stage_id=stage_id)
            return
        self.primitives.clear()
        self.active_stage_id = stage_id or getattr(document.stages, "active_stage_id", None)
        active_blocks = None
        try:
            preview = document.stage_preview(self.active_stage_id)
            active_blocks = set(preview.get("active_blocks", []))
        except Exception:
            active_blocks = None
        for point_id, point in getattr(document.geometry, "points", {}).items():
            xyz = point.to_tuple()
            self.primitives[f"primitive:point:{point_id}"] = ScenePrimitive(
                id=f"primitive:point:{point_id}",
                kind="point",
                entity_id=point_id,
                label=point_id,
                bounds=(xyz[0], xyz[0], xyz[1], xyz[1], xyz[2], xyz[2]),
                visible=True,
                pickable=True,
                style={"role": "point", "active": True, "opacity": 1.0},
                metadata=point.to_dict(),
            )
        for edge_id, edge in getattr(document.geometry, "edges", {}).items():
            pts = [document.geometry.points[pid].to_tuple() for pid in edge.point_ids if pid in document.geometry.points]
            if pts:
                xs, ys, zs = zip(*pts)
                bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
            else:
                bounds = None
            self.primitives[f"primitive:edge:{edge_id}"] = ScenePrimitive(
                id=f"primitive:edge:{edge_id}",
                kind="edge",
                entity_id=edge_id,
                label=edge_id,
                bounds=bounds,
                visible=True,
                pickable=True,
                style={"role": edge.role, "active": True, "opacity": 1.0},
                metadata={**edge.to_dict(), "points": [list(p) for p in pts]},
            )
        for surface_id, surface in getattr(document.geometry, "surfaces", {}).items():
            pts = [document.geometry.points[pid].to_tuple() for pid in surface.point_ids if pid in document.geometry.points]
            if pts:
                xs, ys, zs = zip(*pts)
                bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
            else:
                bounds = None
            self.primitives[f"primitive:surface:{surface_id}"] = ScenePrimitive(
                id=f"primitive:surface:{surface_id}",
                kind="surface",
                entity_id=surface_id,
                label=surface_id,
                bounds=bounds,
                visible=True,
                pickable=True,
                style={"role": surface.role, "active": True, "opacity": 0.35},
                metadata={**surface.to_dict(), "points": [list(p) for p in pts]},
            )

        for support_id, support in getattr(document, "supports", {}).items():
            edge_id = str(support.get("axis_edge_id") or "")
            pts = []
            if edge_id in getattr(document.geometry, "edges", {}):
                edge = document.geometry.edges[edge_id]
                pts = [document.geometry.points[pid].to_tuple() for pid in edge.point_ids if pid in document.geometry.points]
            elif support.get("start") and support.get("end"):
                pts = [tuple(float(v) for v in support["start"]), tuple(float(v) for v in support["end"])]
            if pts:
                xs, ys, zs = zip(*pts)
                bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
            else:
                bounds = None
            self.primitives[f"primitive:support:{support_id}"] = ScenePrimitive(
                id=f"primitive:support:{support_id}",
                kind="support",
                entity_id=support_id,
                label=support_id,
                bounds=bounds,
                visible=str(support.get("status", "active")) != "hidden",
                pickable=True,
                style={"role": str(support.get("type", "support")), "active": True, "opacity": 1.0},
                metadata={**dict(support), "points": [list(p) for p in pts]},
            )
        for block_id, block in document.geometry.blocks.items():
            is_active = True if active_blocks is None else block_id in active_blocks
            self.primitives[f"primitive:block:{block_id}"] = ScenePrimitive(
                id=f"primitive:block:{block_id}",
                kind="block",
                entity_id=block_id,
                label=block.name,
                bounds=block.bounds,
                visible=bool(block.visible),
                pickable=not block.locked,
                style={"role": block.role, "active": is_active, "opacity": 1.0 if is_active else 0.18},
                metadata={"material_id": block.material_id, "layer_id": block.layer_id, "face_ids": list(block.face_ids)},
            )

        # Parametric features are pickable handles in the section editor.  A
        # horizontal-layer feature is displayed as a line, while an excavation
        # feature is displayed as its editable polygon/bounding trace.
        for feature_id, feature in getattr(document.geometry, "partition_features", {}).items():
            if feature.type == "horizontal_layer":
                z = feature.parameters.get("z_level")
                if z is None:
                    levels = feature.parameters.get("z_levels") or []
                    z = levels[1] if len(levels) > 1 else None
                if z is not None:
                    xs = []
                    for bid in feature.generated_block_ids:
                        block = document.geometry.blocks.get(bid)
                        if block is not None:
                            xs.extend([block.bounds[0], block.bounds[1]])
                    if not xs:
                        xs = [-50.0, 50.0]
                    x0, x1 = min(xs), max(xs)
                    zz = float(z)
                    self.primitives[f"primitive:partition_feature:{feature_id}"] = ScenePrimitive(
                        id=f"primitive:partition_feature:{feature_id}",
                        kind="partition_feature",
                        entity_id=feature_id,
                        label=feature_id,
                        bounds=(x0, x1, 0.0, 0.0, zz, zz),
                        visible=True,
                        pickable=True,
                        style={"role": "horizontal_layer", "active": True, "opacity": 1.0},
                        metadata={**feature.to_dict(), "points": [[x0, 0.0, zz], [x1, 0.0, zz]]},
                    )
            elif feature.type == "excavation_surface":
                vertices = feature.parameters.get("polygon_vertices") or []
                if vertices:
                    xs = [float(v[0]) for v in vertices if len(v) >= 3]
                    zs = [float(v[2]) for v in vertices if len(v) >= 3]
                    if xs and zs:
                        self.primitives[f"primitive:partition_feature:{feature_id}"] = ScenePrimitive(
                            id=f"primitive:partition_feature:{feature_id}",
                            kind="partition_feature",
                            entity_id=feature_id,
                            label=feature_id,
                            bounds=(min(xs), max(xs), 0.0, 0.0, min(zs), max(zs)),
                            visible=True,
                            pickable=True,
                            style={"role": "excavation_surface", "active": True, "opacity": 0.9},
                            metadata={**feature.to_dict(), "points": vertices},
                        )

        for row in list(getattr(document, "metadata", {}).get("interface_review_candidates", []) or []):
            if str(row.get("status")) == "rejected":
                continue
            cid = str(row.get("id") or row.get("contact_id") or "")
            if not cid:
                continue
            a = document.geometry.blocks.get(str(row.get("source_block_id", "")))
            b = document.geometry.blocks.get(str(row.get("target_block_id", "")))
            if a is None or b is None:
                continue
            ax, ay, az = a.centroid
            bx, by, bz = b.centroid
            self.primitives[f"primitive:contact_pair:{cid}"] = ScenePrimitive(
                id=f"primitive:contact_pair:{cid}",
                kind="contact_pair",
                entity_id=cid,
                label=cid,
                bounds=(min(ax, bx), max(ax, bx), min(ay, by), max(ay, by), min(az, bz), max(az, bz)),
                visible=True,
                pickable=True,
                style={"role": str(row.get("contact_type", "interface")), "status": str(row.get("status", "candidate")), "opacity": 0.9},
                metadata={**dict(row), "points": [[ax, ay, az], [bx, by, bz]]},
            )
        self.selection = document.selection
        try:
            from geoai_simkit.geometry.engineering_tools import EngineeringSnapService

            snap = EngineeringSnapService(document)
            self.overlays = [*snap.grid_overlays(), *snap.endpoint_overlays()]
        except Exception:
            self.overlays = []
        self.metadata = {"primitive_count": len(self.primitives), "source": "EngineeringDocument"}

    def pick_by_entity_id(self, entity_id: str, entity_type: str = "block") -> SelectionRef | None:
        for primitive in self.primitives.values():
            if primitive.entity_id == entity_id and primitive.kind == entity_type:
                ref = SelectionRef(entity_id=entity_id, entity_type=entity_type, source="geometry", display_name=primitive.label, metadata=dict(primitive.metadata))
                self.selection.set_single(ref)
                return ref
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_stage_id": self.active_stage_id,
            "primitives": [item.to_dict() for item in self.primitives.values()],
            "selection": self.selection.to_dict(),
            "camera": dict(self.camera),
            "overlays": list(self.overlays),
            "metadata": dict(self.metadata),
        }
