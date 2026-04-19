
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from geoai_simkit.pipeline.adjacency import adjacency_summary_rows, compute_region_adjacency, compute_region_boundary_adjacency
from geoai_simkit.pipeline.builder import AnalysisCaseBuilder
from geoai_simkit.pipeline.surfaces import (
    compute_region_boundary_surfaces,
    compute_region_surface_interface_candidates,
    interface_candidate_summary_rows,
    region_surface_summary_rows,
)
from geoai_simkit.pipeline.interface_elements import (
    compute_interface_face_elements,
    interface_element_definition_summary_rows,
    interface_face_element_summary_rows,
    interface_face_group_summary_rows,
)
from geoai_simkit.pipeline.specs import AnalysisCaseSpec, PreparedAnalysisCase
from geoai_simkit.pipeline.topology import analyze_interface_topology, interface_node_split_summary_rows, interface_topology_summary_rows


@dataclass(slots=True)
class PreprocessorSnapshot:
    case_name: str
    geometry_kind: str | None
    region_surfaces: tuple[Any, ...]
    region_adjacencies: tuple[Any, ...]
    boundary_adjacencies: tuple[Any, ...]
    interface_candidates: tuple[Any, ...]
    interface_topology: tuple[Any, ...]
    node_split_plans: tuple[Any, ...]
    interface_face_groups: tuple[Any, ...]
    interface_face_elements: tuple[Any, ...]
    interface_element_definitions: tuple[Any, ...]
    interface_ready: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'case_name': self.case_name,
            'geometry_kind': self.geometry_kind,
            'region_surfaces': region_surface_summary_rows(self.region_surfaces),
            'region_adjacencies': adjacency_summary_rows(self.region_adjacencies),
            'boundary_adjacencies': adjacency_summary_rows(self.boundary_adjacencies),
            'interface_candidates': interface_candidate_summary_rows(self.interface_candidates),
            'interface_topology': interface_topology_summary_rows(self.interface_topology),
            'node_split_plans': interface_node_split_summary_rows(self.node_split_plans),
            'interface_face_groups': interface_face_group_summary_rows(self.interface_face_groups),
            'interface_face_elements': interface_face_element_summary_rows(self.interface_face_elements),
            'interface_element_definitions': interface_element_definition_summary_rows(self.interface_element_definitions),
            'interface_ready': dict(self.interface_ready),
            'notes': list(self.notes),
            'metadata': dict(self.metadata),
        }


@dataclass(slots=True)
class PreprocessorArtifact:
    prepared: PreparedAnalysisCase
    snapshot: PreprocessorSnapshot


def build_preprocessor_snapshot(spec: AnalysisCaseSpec | None = None, *, prepared: PreparedAnalysisCase | None = None) -> PreprocessorArtifact:
    if prepared is None:
        if spec is None:
            raise ValueError('build_preprocessor_snapshot requires spec or prepared.')
        prepared = AnalysisCaseBuilder(spec).build()
    case_name = spec.name if spec is not None else str(prepared.model.name)
    geometry_kind = getattr(spec.geometry, 'kind', None) if spec is not None else str(prepared.model.metadata.get('pipeline.geometry_metadata', {}).get('source') or '') or None
    region_surfaces = compute_region_boundary_surfaces(prepared.model)
    point_adjacencies = compute_region_adjacency(prepared.model, min_shared_points=1)
    boundary_adjacencies = compute_region_boundary_adjacency(prepared.model, min_shared_faces=1)
    interface_candidates = compute_region_surface_interface_candidates(prepared.model, min_shared_faces=1)
    topology = analyze_interface_topology(prepared.model)
    interface_faces = compute_interface_face_elements(prepared.model)
    interface_ready = dict(prepared.model.metadata.get('pipeline.interface_ready') or {})
    metadata = {
        'n_points': int(prepared.report.metadata.get('n_points', 0)),
        'n_cells': int(prepared.report.metadata.get('n_cells', 0)),
        'n_regions': int(len(prepared.model.region_tags)),
        'n_region_surfaces': int(len(region_surfaces)),
        'n_region_adjacencies': int(len(point_adjacencies)),
        'n_boundary_adjacencies': int(len(boundary_adjacencies)),
        'n_interface_candidates': int(len(interface_candidates)),
        'n_interfaces': int(len(prepared.model.interfaces)),
        'n_structures': int(len(prepared.model.structures)),
        'n_boundary_conditions': int(len(prepared.model.boundary_conditions)),
        'n_stages': int(len(prepared.model.stages)),
        'n_material_bindings': int(len(prepared.model.materials)),
        'n_interface_topology_rows': int(len(topology.interfaces)),
        'n_node_split_plans': int(len(topology.split_plans)),
        'n_suggested_duplicate_points': int(topology.metadata.get('n_suggested_duplicate_points', 0)),
        'n_interface_face_groups': int(len(interface_faces.groups)),
        'n_interface_face_elements': int(len(interface_faces.elements)),
        'n_interface_elements': int(len(prepared.model.interface_elements)),
        'interface_face_total_area': float(interface_faces.metadata.get('total_area', 0.0)),
        'interface_ready_applied': bool(interface_ready.get('applied', False)),
        'interface_ready_duplicated_point_count': int(interface_ready.get('duplicated_point_count', 0)),
        'interface_ready_remaining_split_plans': int(interface_ready.get('metadata', {}).get('n_remaining_split_plans', len(topology.split_plans))),
    }
    notes = list(prepared.report.notes)
    notes.append('Preprocessor snapshot includes region surfaces, point/face adjacencies, and interface candidates.')
    if interface_ready:
        notes.append('Interface-ready preprocessing metadata is included in the snapshot.')
    snapshot = PreprocessorSnapshot(
        case_name=case_name,
        geometry_kind=geometry_kind,
        region_surfaces=tuple(region_surfaces),
        region_adjacencies=tuple(point_adjacencies),
        boundary_adjacencies=tuple(boundary_adjacencies),
        interface_candidates=tuple(interface_candidates),
        interface_topology=tuple(topology.interfaces),
        node_split_plans=tuple(topology.split_plans),
        interface_face_groups=tuple(interface_faces.groups),
        interface_face_elements=tuple(interface_faces.elements),
        interface_element_definitions=tuple(prepared.model.interface_elements),
        interface_ready=interface_ready,
        notes=tuple(notes),
        metadata=metadata,
    )
    return PreprocessorArtifact(prepared=prepared, snapshot=snapshot)


def save_preprocessor_snapshot(snapshot: PreprocessorSnapshot, path: str | Path) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot.to_dict()
    suffix = out_path.suffix.lower()
    if suffix in {'.yaml', '.yml'}:
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError('PyYAML is required to write YAML snapshots. Install pyyaml or use .json output.') from exc
        out_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding='utf-8')
        return out_path
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    return out_path
