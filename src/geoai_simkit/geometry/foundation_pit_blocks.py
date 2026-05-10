from __future__ import annotations

"""Dependency-light foundation-pit block workflow.

This module intentionally avoids OCC/Gmsh/PyVista so that the GUI, smoke tests
and command-line demos can build a real staged excavation topology on machines
that only have NumPy installed.  The generated artifact is not a final Boolean
BRep; it is a stable engineering contract: blocks, face tags, contact pairs,
interface requests, mesh cell tags, stage activation and stage metrics.
"""

from dataclasses import dataclass, field
import json
from typing import Any, Iterable


from geoai_simkit.geometry.block_contact import (
    AxisAlignedBlock,
    build_contact_interface_assets,
    contact_assets_to_policy_rows,
    detect_axis_aligned_block_contacts,
)


@dataclass(frozen=True, slots=True)
class PitBlock:
    name: str
    bounds: tuple[float, float, float, float, float, float]
    role: str = "soil"
    material_name: str = "soil"
    active_stages: tuple[str, ...] = ()
    layer_name: str = ""
    stage_index: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def volume(self) -> float:
        xmin, xmax, ymin, ymax, zmin, zmax = self.bounds
        return float(max(xmax - xmin, 0.0) * max(ymax - ymin, 0.0) * max(zmax - zmin, 0.0))

    def to_axis_block(self) -> AxisAlignedBlock:
        meta = dict(self.metadata)
        meta.setdefault("region_name", self.name)
        meta.setdefault("layer_name", self.layer_name)
        if self.stage_index is not None:
            meta.setdefault("stage_index", int(self.stage_index))
        return AxisAlignedBlock(
            name=self.name,
            bounds=self.bounds,
            role=self.role,
            material_name=self.material_name,
            active_stages=self.active_stages,
            metadata=meta,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bounds": [float(v) for v in self.bounds],
            "role": self.role,
            "material_name": self.material_name,
            "active_stages": list(self.active_stages),
            "layer_name": self.layer_name,
            "stage_index": self.stage_index,
            "volume": self.volume,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class PitFaceTag:
    tag: str
    block_name: str
    axis: str
    side: str
    coordinate: float
    area: float
    role: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "block_name": self.block_name,
            "axis": self.axis,
            "side": self.side,
            "coordinate": float(self.coordinate),
            "area": float(self.area),
            "role": self.role,
            "metadata": dict(self.metadata),
        }


def _float_seq(values: Iterable[Any], *, default: tuple[float, ...]) -> tuple[float, ...]:
    out: list[float] = []
    for item in list(values or []):
        try:
            out.append(float(item))
        except Exception:
            continue
    return tuple(out) if out else tuple(default)


def _clean_levels(levels: Iterable[Any], *, top: float, bottom: float) -> tuple[float, ...]:
    vals = [float(top), float(bottom)]
    vals.extend(float(v) for v in list(levels or []))
    vals = [min(max(v, min(top, bottom)), max(top, bottom)) for v in vals]
    vals = sorted(set(round(v, 10) for v in vals), reverse=True)
    if vals[0] != max(top, bottom):
        vals.insert(0, max(top, bottom))
    if vals[-1] != min(top, bottom):
        vals.append(min(top, bottom))
    return tuple(vals)


def _intervals(levels: tuple[float, ...]) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for upper, lower in zip(levels[:-1], levels[1:]):
        if upper > lower:
            pairs.append((float(upper), float(lower)))
    return pairs


def _z_overlap(a_upper: float, a_lower: float, b_upper: float, b_lower: float) -> tuple[float, float] | None:
    upper = min(float(a_upper), float(b_upper))
    lower = max(float(a_lower), float(b_lower))
    if upper <= lower:
        return None
    return upper, lower


def _face_tag(block: PitBlock, axis: str, side: str, coordinate: float, area: float, *, role: str) -> PitFaceTag:
    return PitFaceTag(
        tag=f"face:{block.name}:{axis}{side}",
        block_name=block.name,
        axis=axis,
        side=side,
        coordinate=float(coordinate),
        area=float(area),
        role=role,
        metadata={"block_role": block.role, "layer_name": block.layer_name},
    )


def _all_box_faces(block: PitBlock) -> list[PitFaceTag]:
    xmin, xmax, ymin, ymax, zmin, zmax = block.bounds
    dx = max(xmax - xmin, 0.0)
    dy = max(ymax - ymin, 0.0)
    dz = max(zmax - zmin, 0.0)
    return [
        _face_tag(block, "x", "min", xmin, dy * dz, role="boundary"),
        _face_tag(block, "x", "max", xmax, dy * dz, role="boundary"),
        _face_tag(block, "y", "min", ymin, dx * dz, role="boundary"),
        _face_tag(block, "y", "max", ymax, dx * dz, role="boundary"),
        _face_tag(block, "z", "min", zmin, dx * dy, role="horizontal_layer_or_bottom"),
        _face_tag(block, "z", "max", zmax, dx * dy, role="horizontal_layer_or_ground"),
    ]


def _stage_names(excavation_levels: tuple[float, ...]) -> tuple[str, ...]:
    return tuple(["initial", "wall_activation"] + [f"excavate_level_{i:02d}" for i in range(1, len(excavation_levels) + 1)])


def build_foundation_pit_blocks(parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a staged 2D/3D foundation-pit block topology artifact.

    Parameters intentionally use simple engineering names so GUI controls can
    bind to them directly.  For 2D mode, the y dimension is collapsed to a thin
    unit-width slice while keeping the same block/contact/tag schema.
    """
    p = dict(parameters or {})
    dimension = str(p.get("dimension", "3d")).strip().lower()
    is_2d = dimension in {"2d", "plane_strain", "plane-strain"}
    pit_length = float(p.get("pit_length", p.get("length", 24.0)) or 24.0)
    pit_width = 1.0 if is_2d else float(p.get("pit_width", p.get("width", 12.0)) or 12.0)
    domain_length = float(p.get("domain_length", max(pit_length * 2.0, pit_length + 20.0)) or max(pit_length * 2.0, pit_length + 20.0))
    domain_width = 1.0 if is_2d else float(p.get("domain_width", max(pit_width * 2.0, pit_width + 16.0)) or max(pit_width * 2.0, pit_width + 16.0))
    final_depth = abs(float(p.get("depth", p.get("final_excavation_depth", 12.0)) or 12.0))
    soil_depth = abs(float(p.get("soil_depth", max(final_depth + 8.0, final_depth * 1.8)) or max(final_depth + 8.0, final_depth * 1.8)))
    wall_thickness = float(p.get("wall_thickness", 0.8) or 0.8)
    wall_bottom = -abs(float(p.get("wall_bottom", max(final_depth + 6.0, soil_depth * 0.85)) or max(final_depth + 6.0, soil_depth * 0.85)))
    excavation_levels = tuple(sorted((v for v in _float_seq(p.get("excavation_levels", ( -final_depth * 0.35, -final_depth * 0.70, -final_depth)), default=(-final_depth * 0.35, -final_depth * 0.70, -final_depth)) if v < 0.0), reverse=True))
    if not excavation_levels or abs(excavation_levels[-1]) < final_depth * 0.95:
        excavation_levels = tuple(list(excavation_levels) + [-final_depth])
    layer_levels = _clean_levels(
        list(p.get("layer_levels", []) or []) + list(excavation_levels),
        top=0.0,
        bottom=-soil_depth,
    )
    stage_names = _stage_names(excavation_levels)
    full_stage_set = tuple(stage_names)
    final_excavation_stage = stage_names[-1]

    px0, px1 = -pit_length / 2.0, pit_length / 2.0
    py0, py1 = -pit_width / 2.0, pit_width / 2.0
    dx0, dx1 = -domain_length / 2.0, domain_length / 2.0
    dy0, dy1 = -domain_width / 2.0, domain_width / 2.0

    blocks: list[PitBlock] = []
    excavation_blocks: list[str] = []
    # Outside soil ring split by horizontal layers.  Blocks are non-overlapping.
    for layer_idx, (upper, lower) in enumerate(_intervals(layer_levels), start=1):
        lname = f"soil_layer_{layer_idx:02d}"
        material = str(p.get(f"material_{lname}", lname))
        # west/east blocks exist in both 2D and 3D.
        side_specs = [
            ("west", (dx0, px0 - wall_thickness, dy0, dy1, lower, upper)),
            ("east", (px1 + wall_thickness, dx1, dy0, dy1, lower, upper)),
        ]
        if not is_2d:
            side_specs.extend([
                ("south", (px0 - wall_thickness, px1 + wall_thickness, dy0, py0 - wall_thickness, lower, upper)),
                ("north", (px0 - wall_thickness, px1 + wall_thickness, py1 + wall_thickness, dy1, lower, upper)),
            ])
        for side, bounds in side_specs:
            if bounds[1] <= bounds[0] or bounds[3] <= bounds[2] or bounds[5] <= bounds[4]:
                continue
            blocks.append(PitBlock(
                name=f"{lname}_{side}",
                bounds=tuple(float(v) for v in bounds),
                role="soil",
                material_name=material,
                active_stages=full_stage_set,
                layer_name=lname,
                metadata={"split_by": "horizontal_soil_layer", "side": side, "dimension": "2d" if is_2d else "3d"},
            ))
        # Central material below final excavation depth remains soil.
        if lower < -final_depth:
            zpair = _z_overlap(upper, lower, -final_depth, -soil_depth)
            if zpair is not None:
                zu, zl = zpair
                blocks.append(PitBlock(
                    name=f"{lname}_below_pit_core",
                    bounds=(px0, px1, py0, py1, zl, zu),
                    role="soil",
                    material_name=material,
                    active_stages=full_stage_set,
                    layer_name=lname,
                    metadata={"split_by": "horizontal_soil_layer", "side": "below_excavation_core", "dimension": "2d" if is_2d else "3d"},
                ))

    # Central excavation column split by excavation planes.  The blocks are real
    # cells/tags in the mesh and are deactivated stage-by-stage by the solver.
    previous = 0.0
    for stage_idx, level in enumerate(excavation_levels, start=1):
        upper, lower = float(previous), float(level)
        if upper <= lower:
            continue
        active_until = tuple(stage_names[: stage_idx + 1])  # initial/wall plus stages before removal.
        name = f"excavation_stage_{stage_idx:02d}"
        blocks.append(PitBlock(
            name=name,
            bounds=(px0, px1, py0, py1, lower, upper),
            role="excavation",
            material_name="void",
            active_stages=active_until,
            layer_name="excavation_column",
            stage_index=stage_idx,
            metadata={"split_by": "excavation_plane", "excavation_level": float(level), "deactivate_at_stage": f"excavate_level_{stage_idx:02d}"},
        ))
        excavation_blocks.append(name)
        previous = level

    # Retaining wall envelope, split into named sides so contacts are explicit.
    wall_sides = [
        ("west", (px0 - wall_thickness, px0, py0, py1, wall_bottom, 0.0)),
        ("east", (px1, px1 + wall_thickness, py0, py1, wall_bottom, 0.0)),
    ]
    if not is_2d:
        wall_sides.extend([
            ("south", (px0 - wall_thickness, px1 + wall_thickness, py0 - wall_thickness, py0, wall_bottom, 0.0)),
            ("north", (px0 - wall_thickness, px1 + wall_thickness, py1, py1 + wall_thickness, wall_bottom, 0.0)),
        ])
    for side, bounds in wall_sides:
        blocks.append(PitBlock(
            name=f"wall_{side}",
            bounds=tuple(float(v) for v in bounds),
            role="wall",
            material_name="retaining_wall",
            active_stages=tuple(stage_names[1:]),
            layer_name="retaining_wall",
            metadata={"split_by": "wall_offset", "side": side, "dimension": "2d" if is_2d else "3d"},
        ))

    face_tags: list[PitFaceTag] = []
    for block in blocks:
        face_tags.extend(_all_box_faces(block))
    contacts = detect_axis_aligned_block_contacts([b.to_axis_block() for b in blocks], tolerance=float(p.get("contact_tolerance", 1.0e-7) or 1.0e-7))
    assets = build_contact_interface_assets(contacts, aggregate_by_region=True)
    interface_requests = contact_assets_to_policy_rows(assets)
    for row in interface_requests:
        policy = str(row.get("mesh_policy") or "").lower()
        if policy == "duplicate_contact_nodes":
            row["request_type"] = "node_pair_contact"
        elif policy == "keep_split_boundary":
            row["request_type"] = "release_boundary"
        elif policy == "merge_or_tie":
            row["request_type"] = "continuity_tie"
        else:
            row.setdefault("request_type", "manual_review")
        row.setdefault("stage_policy", "active_when_both_sides_present")
        if row.get("contact_mode") == "excavation_release_face":
            row["stage_policy"] = "release_when_excavation_block_deactivates"
        elif row.get("contact_mode") == "wall_soil_interface":
            row["stage_policy"] = "activate_after_wall_installation"

    stage_rows: list[dict[str, Any]] = [
        {
            "name": "initial",
            "predecessor": None,
            "activate_blocks": [b.name for b in blocks if b.role == "soil"],
            "deactivate_blocks": [],
            "excavation_depth": 0.0,
            "role": "initial_geostatic",
        },
        {
            "name": "wall_activation",
            "predecessor": "initial",
            "activate_blocks": [b.name for b in blocks if b.role == "wall"],
            "deactivate_blocks": [],
            "excavation_depth": 0.0,
            "role": "support_installation",
        },
    ]
    predecessor = "wall_activation"
    for idx, level in enumerate(excavation_levels, start=1):
        stage_rows.append({
            "name": f"excavate_level_{idx:02d}",
            "predecessor": predecessor,
            "activate_blocks": [],
            "deactivate_blocks": [f"excavation_stage_{idx:02d}"],
            "excavation_depth": abs(float(level)),
            "role": "excavation",
        })
        predecessor = f"excavate_level_{idx:02d}"

    artifact = {
        "contract": "foundation_pit_block_workflow_v1",
        "dimension": "2d" if is_2d else "3d",
        "parameters": {
            "pit_length": pit_length,
            "pit_width": pit_width,
            "domain_length": domain_length,
            "domain_width": domain_width,
            "depth": final_depth,
            "soil_depth": soil_depth,
            "wall_thickness": wall_thickness,
            "wall_bottom": wall_bottom,
            "excavation_levels": list(excavation_levels),
            "layer_levels": list(layer_levels),
        },
        "blocks": [b.to_dict() for b in blocks],
        "face_tags": [f.to_dict() for f in face_tags],
        "contact_pairs": [c.to_dict() for c in contacts],
        "interface_assets": [a.to_dict() for a in assets],
        "interface_requests": interface_requests,
        "stage_rows": stage_rows,
        "summary": {
            "block_count": len(blocks),
            "soil_block_count": sum(1 for b in blocks if b.role == "soil"),
            "excavation_block_count": sum(1 for b in blocks if b.role == "excavation"),
            "wall_block_count": sum(1 for b in blocks if b.role == "wall"),
            "face_tag_count": len(face_tags),
            "contact_pair_count": len(contacts),
            "interface_request_count": len(interface_requests),
            "stage_count": len(stage_rows),
            "excavation_blocks": excavation_blocks,
        },
    }
    return artifact


def build_foundation_pit_grid(parameters: dict[str, Any] | None = None) -> Any:
    """Create one tagged Hex8 cell per block and preserve face/contact metadata."""
    from geoai_simkit.pipeline.specs import SimpleUnstructuredGrid

    artifact = build_foundation_pit_blocks(parameters)
    points: list[tuple[float, float, float]] = []
    cells: list[tuple[int, int, int, int, int, int, int, int]] = []
    region_names: list[str] = []
    roles: list[str] = []
    materials: list[str] = []
    block_tags: list[str] = []
    active_json: list[str] = []
    for block in artifact["blocks"]:
        xmin, xmax, ymin, ymax, zmin, zmax = [float(v) for v in block["bounds"]]
        base = len(points)
        points.extend([
            (xmin, ymin, zmin),
            (xmax, ymin, zmin),
            (xmax, ymax, zmin),
            (xmin, ymax, zmin),
            (xmin, ymin, zmax),
            (xmax, ymin, zmax),
            (xmax, ymax, zmax),
            (xmin, ymax, zmax),
        ])
        cells.append(tuple(range(base, base + 8)))
        region_names.append(str(block["name"]))
        roles.append(str(block.get("role") or "soil"))
        materials.append(str(block.get("material_name") or ""))
        block_tags.append(str(block["name"]))
        active_json.append(json.dumps(list(block.get("active_stages") or [])))
    grid = SimpleUnstructuredGrid(points, cells, region_names=region_names)
    grid.cell_data["block_tag"] = list(block_tags)
    grid.cell_data["role"] = list(roles)
    grid.cell_data["material_name"] = list(materials)
    grid.cell_data["active_stages_json"] = list(active_json)
    grid.field_data["foundation_pit_workflow_json"] = json.dumps(artifact, ensure_ascii=False)
    grid.field_data["face_tags_json"] = json.dumps(artifact["face_tags"], ensure_ascii=False)
    grid.field_data["interface_requests_json"] = json.dumps(artifact["interface_requests"], ensure_ascii=False)
    grid.field_data["stage_rows_json"] = json.dumps(artifact["stage_rows"], ensure_ascii=False)
    grid.field_data["source_kind"] = ["foundation_pit_blocks"]
    return grid


def workflow_from_grid(grid: Any) -> dict[str, Any]:
    raw = getattr(grid, "field_data", {}).get("foundation_pit_workflow_json") if grid is not None else None
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if len(raw) else None
    if raw in (None, ""):
        return {}
    try:
        return json.loads(str(raw))
    except Exception:
        return {}


def compute_stage_response_metrics(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Return deterministic stage engineering indicators for GUI/results smoke.

    This is a response proxy, not a constitutive solver.  It gives the GUI and
    result database a stable stage-wise payload until the nonlinear engine owns
    the complete excavation solve path.
    """
    params = dict(workflow.get("parameters") or {})
    depth = max(float(params.get("depth", 1.0) or 1.0), 1.0)
    wall_bottom = abs(float(params.get("wall_bottom", depth + 4.0) or depth + 4.0))
    stiffness_factor = max(wall_bottom / depth, 1.0)
    rows: list[dict[str, Any]] = []
    for stage in list(workflow.get("stage_rows") or []):
        d = float(stage.get("excavation_depth", 0.0) or 0.0)
        ratio = max(0.0, min(1.2, d / depth))
        wall_mm = 18.0 * (ratio ** 1.45) / (stiffness_factor ** 0.35) if d > 0.0 else 0.0
        settlement_mm = -0.55 * wall_mm * (1.0 + 0.15 * ratio)
        rows.append({
            "stage_name": str(stage.get("name") or "stage"),
            "excavation_depth": d,
            "max_wall_horizontal_displacement_mm": float(wall_mm),
            "max_surface_settlement_mm": float(settlement_mm),
            "active_block_count": len(stage.get("activate_blocks") or []),
            "deactivated_block_count": len(stage.get("deactivate_blocks") or []),
            "role": str(stage.get("role") or ""),
            "source": "foundation_pit_response_proxy",
        })
    return rows


__all__ = [
    "PitBlock",
    "PitFaceTag",
    "build_foundation_pit_blocks",
    "build_foundation_pit_grid",
    "workflow_from_grid",
    "compute_stage_response_metrics",
]
