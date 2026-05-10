from __future__ import annotations

"""Parametric editing and binding migration for engineering modeling features.

The first engineering-tool implementation could create soil splits, excavation
splits and support axes once.  This module upgrades those generated entities to
editable features: the user can select a feature/support, change parameters or
use a drag operation, and the service migrates material, stage activation and
interface review bindings to the regenerated entities.
"""

from dataclasses import dataclass, field
from math import inf
from typing import Any

from geoai_simkit.geometry.entities import BlockEntity, PartitionFeature
from geoai_simkit.geometry.editor import GeometryEditor
from geoai_simkit.geometry.light_block_kernel import LightBlockKernel


def _safe(value: str) -> str:
    out = []
    for ch in str(value):
        out.append(ch if ch.isalnum() else "_")
    return "".join(out).strip("_") or "entity"


def _ensure_unique(mapping: dict[str, Any], wanted: str) -> str:
    if wanted not in mapping:
        return wanted
    base = wanted
    idx = 2
    while f"{base}_{idx:02d}" in mapping:
        idx += 1
    return f"{base}_{idx:02d}"


def _union_bounds(blocks: list[BlockEntity]) -> tuple[float, float, float, float, float, float]:
    if not blocks:
        raise ValueError("Cannot compute bounds for an empty block list.")
    return (
        min(b.bounds[0] for b in blocks),
        max(b.bounds[1] for b in blocks),
        min(b.bounds[2] for b in blocks),
        max(b.bounds[3] for b in blocks),
        min(b.bounds[4] for b in blocks),
        max(b.bounds[5] for b in blocks),
    )


def _centroid_distance(a: BlockEntity, b: BlockEntity) -> float:
    ax, ay, az = a.centroid
    bx, by, bz = b.centroid
    return ((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2) ** 0.5


def _remove_block(document: Any, block_id: str) -> BlockEntity | None:
    block = document.geometry.blocks.pop(block_id, None)
    if block is None:
        return None
    for fid in block.face_ids:
        document.geometry.faces.pop(fid, None)
    return block


def _mark_dirty(document: Any) -> None:
    document.dirty.geometry_dirty = True
    document.dirty.mesh_dirty = True
    document.dirty.solve_dirty = True
    document.dirty.result_stale = True
    document.mesh = None
    document.results = None


@dataclass(slots=True)
class BindingMigrationReport:
    operation: str
    feature_id: str = ""
    removed_entity_ids: list[str] = field(default_factory=list)
    created_entity_ids: list[str] = field(default_factory=list)
    block_id_map: dict[str, list[str]] = field(default_factory=dict)
    material_migrations: dict[str, str | None] = field(default_factory=dict)
    stage_migrations: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    interface_migrations: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "feature_id": self.feature_id,
            "removed_entity_ids": list(self.removed_entity_ids),
            "created_entity_ids": list(self.created_entity_ids),
            "block_id_map": {k: list(v) for k, v in self.block_id_map.items()},
            "material_migrations": dict(self.material_migrations),
            "stage_migrations": {sid: {k: list(v) for k, v in row.items()} for sid, row in self.stage_migrations.items()},
            "interface_migrations": {k: list(v) for k, v in self.interface_migrations.items()},
            "warnings": list(self.warnings),
        }


class ParametricEditingService:
    """Edit feature-generated engineering objects while preserving bindings."""

    def __init__(self, document: Any) -> None:
        self.document = document

    def feature_for_block(self, block_id: str) -> str | None:
        block = self.document.geometry.blocks.get(block_id)
        if block is not None:
            fid = block.metadata.get("split_feature_id") or block.metadata.get("feature_id")
            if fid:
                return str(fid)
        for fid, feature in self.document.geometry.partition_features.items():
            if block_id in set(feature.generated_block_ids) or block_id in set(feature.target_block_ids):
                return fid
        return None

    def editable_features(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for fid, feature in self.document.geometry.partition_features.items():
            generated = [bid for bid in feature.generated_block_ids if bid in self.document.geometry.blocks]
            rows.append({
                "id": fid,
                "type": feature.type,
                "parameters": dict(feature.parameters),
                "target_block_ids": list(feature.target_block_ids),
                "generated_block_ids": list(feature.generated_block_ids),
                "existing_generated_block_ids": generated,
                "editable": feature.type in {"horizontal_layer", "excavation_surface"},
                "metadata": dict(feature.metadata),
            })
        return rows

    def _capture_stage_states(self, old_ids: list[str]) -> dict[str, dict[str, set[str]]]:
        old_set = set(old_ids)
        out: dict[str, dict[str, set[str]]] = {}
        for sid, stage in self.document.stages.stages.items():
            out[sid] = {
                "active": set(stage.active_blocks).intersection(old_set),
                "inactive": set(stage.inactive_blocks).intersection(old_set),
            }
        return out

    def _apply_stage_migration(self, block_map: dict[str, list[str]], *, role_filter: dict[str, str] | None = None) -> dict[str, dict[str, list[str]]]:
        report: dict[str, dict[str, list[str]]] = {}
        old_ids = set(block_map.keys())
        for sid, stage in self.document.stages.stages.items():
            active_added: list[str] = []
            inactive_added: list[str] = []
            for old_id, new_ids in block_map.items():
                stage.active_blocks.discard(old_id)
                stage.inactive_blocks.discard(old_id)
                old_role = role_filter.get(old_id) if role_filter else None
                # If the old block was inactive, keep equivalent new blocks inactive.
                # Otherwise add equivalent new blocks to the explicit active set when the
                # stage already manages explicit activation.
                if old_id in stage.metadata.get("inactive_before_parametric_edit", []):
                    for nid in new_ids:
                        stage.inactive_blocks.add(nid)
                        inactive_added.append(nid)
                elif stage.active_blocks or old_id in stage.metadata.get("active_before_parametric_edit", []):
                    for nid in new_ids:
                        stage.active_blocks.add(nid)
                        active_added.append(nid)
                elif old_role == "excavation" and sid == self.document.stages.active_stage_id:
                    for nid in new_ids:
                        stage.inactive_blocks.add(nid)
                        inactive_added.append(nid)
            # Ensure stale ids are gone even when they are not in block_map values.
            stage.active_blocks.difference_update(old_ids)
            stage.inactive_blocks.difference_update(old_ids)
            if active_added or inactive_added:
                report[sid] = {"active_added": sorted(set(active_added)), "inactive_added": sorted(set(inactive_added))}
        return report

    def _store_stage_snapshots(self, old_ids: list[str]) -> None:
        old_set = set(old_ids)
        for stage in self.document.stages.stages.values():
            stage.metadata["active_before_parametric_edit"] = sorted(set(stage.active_blocks).intersection(old_set))
            stage.metadata["inactive_before_parametric_edit"] = sorted(set(stage.inactive_blocks).intersection(old_set))

    def _closest_role_map(self, old_blocks: list[BlockEntity], new_blocks: list[BlockEntity]) -> dict[str, list[str]]:
        mapping: dict[str, list[str]] = {}
        if not new_blocks:
            return {b.id: [] for b in old_blocks}
        for old in old_blocks:
            same_role = [new for new in new_blocks if new.role == old.role]
            candidates = same_role or new_blocks
            nearest = min(candidates, key=lambda item: _centroid_distance(old, item))
            mapping[old.id] = [nearest.id]
        return mapping

    def _migrate_interfaces(self, old_interfaces: dict[str, dict[str, Any]], block_map: dict[str, list[str]], report: BindingMigrationReport) -> None:
        migrated: dict[str, dict[str, Any]] = {}
        for iid, row in old_interfaces.items():
            source = str(row.get("source_block_id") or row.get("region_a") or "")
            target = str(row.get("target_block_id") or row.get("region_b") or "")
            sources = block_map.get(source, [source] if source in self.document.geometry.blocks else [])
            targets = block_map.get(target, [target] if target in self.document.geometry.blocks else [])
            if not sources or not targets:
                report.warnings.append(f"Interface {iid} became stale after editing.")
                continue
            new_ids: list[str] = []
            for si, new_source in enumerate(sources):
                for ti, new_target in enumerate(targets):
                    if new_source == new_target:
                        continue
                    new_iid = iid if si == 0 and ti == 0 and iid not in migrated else f"{iid}:migrated:{si+1}_{ti+1}"
                    new_row = dict(row)
                    new_row.update({
                        "id": new_iid,
                        "source_block_id": new_source,
                        "target_block_id": new_target,
                        "region_a": new_source,
                        "region_b": new_target,
                        "status": row.get("status", "accepted"),
                        "migrated_from": iid,
                    })
                    migrated[new_iid] = new_row
                    new_ids.append(new_iid)
            if new_ids:
                report.interface_migrations[iid] = new_ids
        self.document.interfaces = migrated
        for stage in self.document.stages.stages.values():
            active = set(stage.active_interfaces)
            stage.active_interfaces.clear()
            for old_iid in active:
                for new_iid in report.interface_migrations.get(old_iid, []):
                    stage.active_interfaces.add(new_iid)

    def _finalize(self, report: BindingMigrationReport, old_interfaces: dict[str, dict[str, Any]]) -> BindingMigrationReport:
        self.document.topology = LightBlockKernel().find_adjacent_faces(self.document.geometry)
        self._migrate_interfaces(old_interfaces, report.block_id_map, report)
        _mark_dirty(self.document)
        self.document.metadata.setdefault("binding_migration_reports", []).append(report.to_dict())
        self.document.metadata["last_parametric_edit"] = report.to_dict()
        try:
            from geoai_simkit.geometry.engineering_tools import InterfaceReviewService

            InterfaceReviewService(self.document).rebuild_candidates()
        except Exception as exc:  # pragma: no cover - defensive for optional GUI path
            report.warnings.append(f"Could not rebuild interface candidates: {exc}")
        return report

    def update_horizontal_layer_split(self, feature_id: str, z_level: float) -> dict[str, Any]:
        if feature_id not in self.document.geometry.partition_features:
            raise KeyError(f"Partition feature not found: {feature_id}")
        feature = self.document.geometry.partition_features[feature_id]
        if feature.type != "horizontal_layer":
            raise ValueError(f"Feature is not a horizontal layer split: {feature_id}")
        z = float(z_level)
        generated_ids = [bid for bid in feature.generated_block_ids if bid in self.document.geometry.blocks]
        if not generated_ids:
            generated_ids = [bid for bid, block in self.document.geometry.blocks.items() if block.metadata.get("split_feature_id") == feature_id]
        if not generated_ids:
            raise ValueError(f"Feature has no generated blocks that can be edited: {feature_id}")

        old_blocks = [self.document.geometry.blocks[bid] for bid in generated_ids]
        self._store_stage_snapshots(generated_ids)
        old_interfaces = {iid: dict(row) for iid, row in self.document.interfaces.items()}
        report = BindingMigrationReport(operation="update_horizontal_layer_split", feature_id=feature_id, removed_entity_ids=list(generated_ids))

        groups: dict[str, list[BlockEntity]] = {}
        for block in old_blocks:
            source = str(block.metadata.get("split_from") or block.metadata.get("source_block_id") or (feature.target_block_ids[0] if feature.target_block_ids else block.id))
            groups.setdefault(source, []).append(block)
        editor = GeometryEditor(self.document.geometry)
        new_blocks: list[BlockEntity] = []
        for bid in generated_ids:
            _remove_block(self.document, bid)
        for source, group in groups.items():
            bounds = _union_bounds(group)
            xmin, xmax, ymin, ymax, zmin, zmax = bounds
            if not (zmin < z < zmax):
                report.warnings.append(f"Requested z={z:g} is outside source group {source}; clipped to the group middle.")
                z = (zmin + zmax) * 0.5
            material_id = next((b.material_id for b in group if b.material_id), None)
            layer_id = next((b.layer_id for b in group if b.layer_id), None)
            base = _safe(source)
            below_id = _ensure_unique(self.document.geometry.blocks, f"{base}_below_param_{abs(z):g}".replace(".", "p"))
            upper_id = _ensure_unique(self.document.geometry.blocks, f"{base}_above_param_{abs(z):g}".replace(".", "p"))
            common = {"split_from": source, "split_level": z, "split_feature_id": feature_id, "parametric_editable": True}
            below = editor.create_block((xmin, xmax, ymin, ymax, zmin, z), block_id=below_id, name=f"{source} below z={z:g}", role="soil", material_id=material_id, layer_id=layer_id, metadata={**common, "part": "below"})
            upper = editor.create_block((xmin, xmax, ymin, ymax, z, zmax), block_id=upper_id, name=f"{source} above z={z:g}", role="soil", material_id=material_id, layer_id=layer_id, metadata={**common, "part": "above"})
            new_blocks.extend([below, upper])
            report.material_migrations[below.id] = material_id
            report.material_migrations[upper.id] = material_id
        report.created_entity_ids = [b.id for b in new_blocks]
        report.block_id_map = self._closest_role_map(old_blocks, new_blocks)
        report.stage_migrations = self._apply_stage_migration(report.block_id_map)
        self.document.geometry.partition_features[feature_id] = PartitionFeature(
            id=feature_id,
            type="horizontal_layer",
            parameters={**dict(feature.parameters), "z_level": z, "source": "parametric_update"},
            target_block_ids=tuple(groups.keys()),
            generated_block_ids=tuple(report.created_entity_ids),
            metadata={**dict(feature.metadata), "previous_generated_block_ids": generated_ids, "migration_report": report.to_dict()},
        )
        return self._finalize(report, old_interfaces).to_dict()

    def update_excavation_polygon(self, feature_id: str, vertices: list[tuple[float, float, float]], *, stage_id: str | None = None) -> dict[str, Any]:
        if len(vertices) < 3:
            raise ValueError("Excavation polygon requires at least three vertices.")
        if feature_id not in self.document.geometry.partition_features:
            raise KeyError(f"Partition feature not found: {feature_id}")
        feature = self.document.geometry.partition_features[feature_id]
        if feature.type != "excavation_surface":
            raise ValueError(f"Feature is not an excavation split: {feature_id}")
        generated_ids = [bid for bid in feature.generated_block_ids if bid in self.document.geometry.blocks]
        if not generated_ids:
            generated_ids = [bid for bid, block in self.document.geometry.blocks.items() if block.metadata.get("split_feature_id") == feature_id]
        if not generated_ids:
            raise ValueError(f"Feature has no generated blocks that can be edited: {feature_id}")

        old_blocks = [self.document.geometry.blocks[bid] for bid in generated_ids]
        self._store_stage_snapshots(generated_ids)
        old_interfaces = {iid: dict(row) for iid, row in self.document.interfaces.items()}
        report = BindingMigrationReport(operation="update_excavation_polygon", feature_id=feature_id, removed_entity_ids=list(generated_ids))
        for bid in generated_ids:
            _remove_block(self.document, bid)

        bounds = _union_bounds(old_blocks)
        xmin, xmax, ymin, ymax, zmin, zmax = bounds
        material_id = next((b.material_id for b in old_blocks if b.role == "soil" and b.material_id), next((b.material_id for b in old_blocks if b.material_id), None))
        layer_id = next((b.layer_id for b in old_blocks if b.role == "soil" and b.layer_id), None)
        xs = [float(v[0]) for v in vertices]
        zs = [float(v[2]) for v in vertices]
        ex0, ex1 = max(min(xs), xmin), min(max(xs), xmax)
        ez0, ez1 = max(min(zs), zmin), min(max(zs), zmax)
        if ex1 <= ex0 or ez1 <= ez0:
            raise ValueError("Updated excavation polygon does not overlap the editable source region.")
        editor = GeometryEditor(self.document.geometry)
        base = _safe(feature_id)
        generated: list[BlockEntity] = []
        excavation = editor.create_block((ex0, ex1, ymin, ymax, ez0, ez1), block_id=_ensure_unique(self.document.geometry.blocks, f"excavation_{base}_001"), name=f"Excavation {feature_id}", role="excavation", material_id=None, layer_id=None, metadata={"split_feature_id": feature_id, "polygon_vertices": [list(v) for v in vertices], "parametric_editable": True})
        generated.append(excavation)
        fragments = [
            (xmin, ex0, ymin, ymax, zmin, zmax, "left"),
            (ex1, xmax, ymin, ymax, zmin, zmax, "right"),
            (ex0, ex1, ymin, ymax, zmin, ez0, "below"),
            (ex0, ex1, ymin, ymax, ez1, zmax, "above"),
        ]
        for fx0, fx1, fy0, fy1, fz0, fz1, label in fragments:
            if fx1 - fx0 > 1e-8 and fy1 - fy0 > 1e-8 and fz1 - fz0 > 1e-8:
                block = editor.create_block((fx0, fx1, fy0, fy1, fz0, fz1), block_id=_ensure_unique(self.document.geometry.blocks, f"soil_{base}_{label}"), name=f"Residual soil {label} for {feature_id}", role="soil", material_id=material_id, layer_id=layer_id, metadata={"split_feature_id": feature_id, "part": label, "parametric_editable": True})
                generated.append(block)
        report.created_entity_ids = [b.id for b in generated]
        report.material_migrations = {b.id: b.material_id for b in generated}
        report.block_id_map = self._closest_role_map(old_blocks, generated)
        # Force old excavation blocks to map to the new excavation block so stage release is preserved.
        for old in old_blocks:
            if old.role == "excavation":
                report.block_id_map[old.id] = [excavation.id]
        report.stage_migrations = self._apply_stage_migration(report.block_id_map, role_filter={b.id: b.role for b in old_blocks})
        active_stage = stage_id or self.document.stages.active_stage_id
        if active_stage and active_stage in self.document.stages.stages:
            self.document.stages.deactivate_block(active_stage, excavation.id)
        self.document.geometry.partition_features[feature_id] = PartitionFeature(
            id=feature_id,
            type="excavation_surface",
            parameters={**dict(feature.parameters), "polygon_vertices": [list(v) for v in vertices], "bbox": [ex0, ex1, ymin, ymax, ez0, ez1], "stage_id": active_stage, "source": "parametric_update"},
            target_block_ids=tuple(feature.target_block_ids or ("parametric_excavation_source",)),
            generated_block_ids=tuple(report.created_entity_ids),
            metadata={**dict(feature.metadata), "previous_generated_block_ids": generated_ids, "migration_report": report.to_dict()},
        )
        return self._finalize(report, old_interfaces).to_dict()

    def update_support_parameters(
        self,
        support_id: str,
        *,
        start: tuple[float, float, float] | None = None,
        end: tuple[float, float, float] | None = None,
        support_type: str | None = None,
        material_id: str | None = None,
        stage_id: str | None = None,
    ) -> dict[str, Any]:
        if support_id not in self.document.supports:
            raise KeyError(f"Support not found: {support_id}")
        row = self.document.supports[support_id]
        old_row = dict(row)
        edge_id = str(row.get("axis_edge_id") or "")
        editor = GeometryEditor(self.document.geometry)
        if start is None:
            start = tuple(float(v) for v in row.get("start", (0.0, 0.0, 0.0)))  # type: ignore[assignment]
        if end is None:
            end = tuple(float(v) for v in row.get("end", (0.0, 0.0, 0.0)))  # type: ignore[assignment]
        if edge_id in self.document.geometry.edges and len(self.document.geometry.edges[edge_id].point_ids) >= 2:
            edge = self.document.geometry.edges[edge_id]
            editor.move_point(edge.point_ids[0], *start, snap=True)
            editor.move_point(edge.point_ids[1], *end, snap=True)
        else:
            edge = editor.create_line_from_coords(start, end, edge_id=edge_id or None, role="support_axis", snap=True)
            edge_id = edge.id
            row["axis_edge_id"] = edge_id
            row["point_ids"] = list(edge.point_ids)
        row["start"] = list(start)
        row["end"] = list(end)
        if support_type:
            row["type"] = support_type
        if material_id:
            row["material_id"] = material_id
            if material_id not in self.document.materials:
                from geoai_simkit.document.engineering_document import MaterialLibraryRecord

                self.document.materials[material_id] = MaterialLibraryRecord(id=material_id, name=material_id, model_type="support_placeholder")
        if stage_id:
            for stage in self.document.stages.stages.values():
                stage.active_supports.discard(support_id)
            if stage_id in self.document.stages.stages:
                self.document.stages.stages[stage_id].active_supports.add(support_id)
            row["active_stage_id"] = stage_id
        row["last_parametric_update"] = {"previous": old_row, "current": dict(row)}
        self.document.topology.add_node(support_id, "support", label=support_id, support_type=row.get("type"), axis_edge_id=edge_id)
        self.document.topology.add_node(edge_id, "edge", label=edge_id, role="support_axis")
        self.document.topology.add_edge(support_id, edge_id, "mapped_to")
        _mark_dirty(self.document)
        report = BindingMigrationReport(operation="update_support_parameters", feature_id=support_id, removed_entity_ids=[], created_entity_ids=[support_id], material_migrations={support_id: row.get("material_id")})
        self.document.metadata.setdefault("binding_migration_reports", []).append(report.to_dict())
        self.document.metadata["last_parametric_edit"] = report.to_dict()
        return {"support_id": support_id, "previous": old_row, "current": dict(row), "migration_report": report.to_dict()}

    def contract(self) -> dict[str, Any]:
        return {
            "editable_features": self.editable_features(),
            "supports": [dict(row) for row in self.document.supports.values()],
            "last_parametric_edit": dict(self.document.metadata.get("last_parametric_edit", {}) or {}),
            "migration_report_count": len(self.document.metadata.get("binding_migration_reports", []) or []),
        }


__all__ = ["BindingMigrationReport", "ParametricEditingService"]
