from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from geoai_simkit.pipeline.specs import AnalysisCaseSpec


@dataclass(slots=True)
class PreprocessorSnapshot:
    case_name: str
    region_surfaces: list[dict[str, Any]] = field(default_factory=list)
    region_adjacencies: list[dict[str, Any]] = field(default_factory=list)
    boundary_adjacencies: list[dict[str, Any]] = field(default_factory=list)
    interface_candidates: list[dict[str, Any]] = field(default_factory=list)
    node_split_plans: list[dict[str, Any]] = field(default_factory=list)
    interface_element_definitions: list[dict[str, Any]] = field(default_factory=list)
    interface_materialization_requests: dict[str, Any] = field(default_factory=dict)
    stage_interface_activation_plan: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in ('case_name', 'region_surfaces', 'region_adjacencies', 'boundary_adjacencies', 'interface_candidates', 'node_split_plans', 'interface_element_definitions', 'interface_materialization_requests', 'stage_interface_activation_plan', 'metadata')}


@dataclass(slots=True)
class PreprocessorArtifact:
    snapshot: PreprocessorSnapshot
    metadata: dict[str, Any] = field(default_factory=dict)


def _foundation_pit_snapshot(case: AnalysisCaseSpec) -> PreprocessorArtifact | None:
    if str(getattr(case.geometry, 'kind', '')).strip().lower() not in {'foundation_pit_blocks', 'block_foundation_pit', 'pit_blocks'}:
        return None
    from geoai_simkit.geometry.foundation_pit_blocks import build_foundation_pit_blocks

    artifact = build_foundation_pit_blocks(dict(getattr(case.geometry, 'parameters', {}) or {}))
    blocks = list(artifact.get('blocks') or [])
    contacts = list(artifact.get('contact_pairs') or [])
    requests = list(artifact.get('interface_requests') or [])
    snapshot = PreprocessorSnapshot(
        case_name=case.name,
        region_surfaces=[{'region_name': b['name'], 'surface_count': 6, 'role': b.get('role'), 'face_tag_prefix': f"face:{b['name']}:"} for b in blocks],
        region_adjacencies=[{'a': c.get('region_a'), 'b': c.get('region_b'), 'axis': c.get('axis'), 'overlap_area': c.get('overlap_area'), 'contact_mode': c.get('contact_mode')} for c in contacts],
        boundary_adjacencies=[{'region_name': b['name'], 'boundary': 'domain' if b.get('role') != 'excavation' else 'excavation_release'} for b in blocks],
        interface_candidates=[{'master': r.get('master_region'), 'slave': r.get('slave_region'), 'kind': r.get('request_type'), 'mesh_policy': r.get('mesh_policy'), 'stage_policy': r.get('stage_policy')} for r in requests],
        node_split_plans=[r for r in requests if r.get('request_type') == 'node_pair_contact'],
        interface_element_definitions=[r for r in requests if r.get('request_type') in {'node_pair_contact', 'release_boundary'}],
        interface_materialization_requests={'request_rows': requests, 'request_count': len(requests)},
        stage_interface_activation_plan={'stage_rows': list(artifact.get('stage_rows') or []), 'stage_count': int(artifact.get('summary', {}).get('stage_count', 0))},
        metadata={'headless_safe': True, 'source': 'foundation_pit_blocks', **dict(artifact.get('summary') or {})},
    )
    return PreprocessorArtifact(snapshot=snapshot, metadata={'workflow': artifact})


def build_preprocessor_snapshot(case: AnalysisCaseSpec) -> PreprocessorArtifact:
    fp = _foundation_pit_snapshot(case)
    if fp is not None:
        return fp
    region_names = []
    for mat in case.materials:
        region_names.extend([str(x) for x in tuple(getattr(mat, 'region_names', ()) or ())])
    region_names = list(dict.fromkeys(region_names)) or ['soil_mass', 'wall']
    snapshot = PreprocessorSnapshot(
        case_name=case.name,
        region_surfaces=[{'region_name': r, 'surface_count': 1} for r in region_names],
        region_adjacencies=[{'a': region_names[i], 'b': region_names[i + 1]} for i in range(max(0, len(region_names) - 1))],
        boundary_adjacencies=[{'region_name': r, 'boundary': 'domain'} for r in region_names],
        interface_candidates=[{'master': 'wall', 'slave': 'soil_mass', 'kind': 'candidate'}] if 'wall' in region_names else [],
        node_split_plans=[],
        interface_element_definitions=[],
        interface_materialization_requests={'request_rows': []},
        stage_interface_activation_plan={'stage_rows': [{'stage_name': s.name} for s in case.stages]},
        metadata={'headless_safe': True, 'region_count': len(region_names)},
    )
    return PreprocessorArtifact(snapshot=snapshot)


def save_preprocessor_snapshot(artifact: PreprocessorArtifact, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(artifact.snapshot.to_dict(), indent=2, default=str), encoding='utf-8')
    return p
