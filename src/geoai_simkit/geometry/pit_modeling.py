from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from geoai_simkit.geometry.sketch_validation import PitOutlineSketchValidator


def _xy(polyline: Iterable[Sequence[Any]]) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for p in list(polyline or []):
        values = list(p)
        if len(values) >= 2:
            pts.append((float(values[0]), float(values[1])))
    return pts


def _bbox_xy(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points] or [0.0]
    ys = [p[1] for p in points] or [0.0]
    return min(xs), max(xs), min(ys), max(ys)


def _offset_outline_bbox(points: list[tuple[float, float]], thickness: float) -> tuple[float, float, float, float]:
    xmin, xmax, ymin, ymax = _bbox_xy(points)
    t = max(0.0, float(thickness or 0.0))
    return xmin - t, xmax + t, ymin - t, ymax + t


@dataclass(slots=True)
class PitModelingPlan:
    pit_outline: tuple[tuple[float, float], ...]
    wall_thickness: float = 0.8
    wall_top: float = 0.0
    wall_bottom: float = -25.0
    excavation_levels: tuple[float, ...] = ()
    support_levels: tuple[float, ...] = ()
    generated_splits: tuple[dict[str, Any], ...] = ()
    generated_blocks: tuple[dict[str, Any], ...] = ()
    generated_named_selections: tuple[dict[str, Any], ...] = ()
    generated_mesh_controls: tuple[dict[str, Any], ...] = ()
    generated_contact_pairs: tuple[dict[str, Any], ...] = ()
    sketch_report: dict[str, Any] = field(default_factory=dict)
    issues: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'contract': 'pit_modeling_plan_v2',
            'pit_outline': [[float(x), float(y)] for x, y in self.pit_outline],
            'wall_thickness': float(self.wall_thickness),
            'wall_top': float(self.wall_top),
            'wall_bottom': float(self.wall_bottom),
            'excavation_levels': [float(v) for v in self.excavation_levels],
            'support_levels': [float(v) for v in self.support_levels],
            'generated_splits': [dict(row) for row in self.generated_splits],
            'generated_blocks': [dict(row) for row in self.generated_blocks],
            'generated_named_selections': [dict(row) for row in self.generated_named_selections],
            'generated_mesh_controls': [dict(row) for row in self.generated_mesh_controls],
            'generated_contact_pairs': [dict(row) for row in self.generated_contact_pairs],
            'sketch_report': dict(self.sketch_report),
            'issues': [dict(row) for row in self.issues],
            'summary': {
                'outline_point_count': len(self.pit_outline),
                'excavation_stage_count': len(self.excavation_levels),
                'support_level_count': len(self.support_levels),
                'split_count': len(self.generated_splits),
                'block_count': len(self.generated_blocks),
                'named_selection_count': len(self.generated_named_selections),
                'mesh_control_count': len(self.generated_mesh_controls),
                'contact_pair_count': len(self.generated_contact_pairs),
                'ready_for_apply': bool(len(self.pit_outline) >= 3 and not any(str(row.get('severity')) == 'error' for row in self.issues)),
            },
            'metadata': dict(self.metadata),
        }


class PitModelingToolkit:
    """Generate entity-level pit modeling contracts from engineering inputs."""

    def validate_outline_sketch(self, *, points: Iterable[dict[str, Any]], lines: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
        return PitOutlineSketchValidator().validate(points, lines)

    def build_plan(self, parameters: dict[str, Any] | None) -> dict[str, Any]:
        params = dict(parameters or {})
        sketch_report = dict(params.get('sketch_report') or {})
        if not params.get('pit_outline') and not params.get('polyline') and sketch_report.get('polyline'):
            params['pit_outline'] = list(sketch_report.get('polyline', []) or [])
        outline = _xy(params.get('pit_outline') or params.get('polyline') or [])
        issues: list[dict[str, Any]] = []
        issues.extend([dict(row) for row in list(sketch_report.get('issues', []) or []) if isinstance(row, dict)])
        if len(outline) < 3:
            issues.append({'id': 'pit_modeling.outline_too_short', 'severity': 'info', 'message': 'At least three plan points are required to generate a pit modeling plan.'})
            return PitModelingPlan(tuple(outline), sketch_report=sketch_report, issues=tuple(issues)).to_dict()
        wall_thickness = float(params.get('wall_thickness', 0.8) or 0.8)
        wall_top = float(params.get('wall_top', 0.0) or 0.0)
        wall_bottom = float(params.get('wall_bottom', params.get('z_min', -25.0)) or -25.0)
        excavation_levels = tuple(float(v) for v in list(params.get('excavation_levels', []) or []))
        excavation_levels = tuple(sorted(excavation_levels, reverse=True))
        support_levels = tuple(float(v) for v in list(params.get('support_levels', []) or []))
        target_block = str(params.get('target_block') or 'soil_mass')
        name = str(params.get('name') or 'pit_outline_extrusion')
        split = {
            'name': name,
            'target_block': target_block,
            'kind': 'polyline_extrusion',
            'polyline': [[float(x), float(y)] for x, y in outline],
            'z_min': min(wall_bottom, min(excavation_levels or (wall_bottom,))),
            'z_max': max(wall_top, 0.0),
            'role': 'excavation_outline',
            'source': 'pit_modeling_toolkit',
            'requires_remesh': True,
        }
        xmin, xmax, ymin, ymax = _bbox_xy(outline)
        wxmin, wxmax, wymin, wymax = _offset_outline_bbox(outline, wall_thickness)
        blocks: list[dict[str, Any]] = []
        for idx, level in enumerate(excavation_levels, start=1):
            upper = wall_top if idx == 1 else excavation_levels[idx - 2]
            lower = level
            blocks.append({
                'name': f'excavation_stage_{idx:02d}',
                'bounds': [xmin, xmax, ymin, ymax, min(lower, upper), max(lower, upper)],
                'role': 'excavation',
                'material_name': 'void',
                'active_stages': [],
                'mesh_size': params.get('excavation_mesh_size'),
                'metadata': {'stage_index': idx, 'generated_by': 'PitModelingToolkit', 'pit_outline': name},
            })
        wall_block = {
            'name': 'retaining_wall_envelope',
            'bounds': [wxmin, wxmax, wymin, wymax, min(wall_bottom, wall_top), max(wall_bottom, wall_top)],
            'role': 'wall',
            'material_name': str(params.get('wall_material_name') or 'retaining_wall'),
            'active_stages': list(params.get('wall_active_stages', []) or []),
            'mesh_size': params.get('wall_mesh_size'),
            'metadata': {'generated_by': 'PitModelingToolkit', 'semantic': 'wall_envelope_for_occ_partition'},
        }
        if bool(params.get('generate_wall_envelope', True)):
            blocks.append(wall_block)
        selections = [
            {'name': 'pit_outline_faces', 'kind': 'face', 'entity_ids': [f'protected_surface:{split["name"]}'], 'metadata': {'role': 'excavation_boundary', 'source': 'PitModelingToolkit'}},
            {'name': 'retaining_wall_alignment', 'kind': 'face', 'entity_ids': [f'protected_surface:{split["name"]}'], 'metadata': {'role': 'wall_interface', 'wall_thickness': wall_thickness, 'source': 'PitModelingToolkit'}},
            {'name': 'excavation_blocks', 'kind': 'solid', 'entity_ids': [f'solid:{row["name"]}' for row in blocks if str(row.get('role')) == 'excavation'], 'metadata': {'role': 'excavation_sequence'}},
        ]
        mesh_controls = [
            {'target': f'protected_surface:{name}', 'source': 'PitModelingToolkit', 'kind': 'distance_threshold', 'size_min': float(params.get('interface_mesh_size', 0.5) or 0.5), 'size_max': float(params.get('far_mesh_size', 2.0) or 2.0), 'dist_min': 0.0, 'dist_max': float(params.get('interface_refine_distance', 3.0) or 3.0), 'semantic': 'wall_excavation_interface'},
        ]
        contact_pairs = [
            {'name': f'pit_wall_soil_interface:{name}', 'slave_entity': f'protected_surface:{name}', 'master_entity': f'protected_surface:{name}', 'kind': 'face_set_contact', 'mesh_policy': 'nonconforming_contact', 'parameters': {'friction_deg': float(params.get('friction_deg', 25.0) or 25.0), 'kn': float(params.get('kn', 5.0e8) or 5.0e8), 'ks': float(params.get('ks', 1.0e8) or 1.0e8)}, 'source': 'PitModelingToolkit'},
        ]
        return PitModelingPlan(
            pit_outline=tuple(outline),
            wall_thickness=wall_thickness,
            wall_top=wall_top,
            wall_bottom=wall_bottom,
            excavation_levels=excavation_levels,
            support_levels=support_levels,
            generated_splits=(split,),
            generated_blocks=tuple(blocks),
            generated_named_selections=tuple(selections),
            generated_mesh_controls=tuple(mesh_controls),
            generated_contact_pairs=tuple(contact_pairs),
            sketch_report=sketch_report,
            issues=tuple(issues),
            metadata={'target_block': target_block, 'edit_policy': 'edit_source_entity_then_remesh'},
        ).to_dict()


__all__ = ['PitModelingPlan', 'PitModelingToolkit']
