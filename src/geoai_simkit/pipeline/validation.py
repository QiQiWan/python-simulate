from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.pipeline.adjacency import compute_region_adjacency, compute_region_boundary_adjacency
from geoai_simkit.pipeline.builder import AnalysisCaseBuilder
from geoai_simkit.pipeline.surfaces import compute_region_boundary_surfaces, compute_region_surface_interface_candidates
from geoai_simkit.pipeline.interfaces import registered_interface_generators
from geoai_simkit.pipeline.selectors import resolve_region_selector, union_region_names
from geoai_simkit.pipeline.sources import registered_geometry_sources
from geoai_simkit.pipeline.structures import registered_structure_generators
from geoai_simkit.pipeline.specs import AnalysisCaseSpec
from geoai_simkit.pipeline.topology import analyze_interface_topology
from geoai_simkit.pipeline.interface_elements import compute_interface_face_elements


@dataclass(slots=True)
class ValidationIssue:
    level: str
    code: str
    message: str
    hint: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CaseValidationReport:
    ok: bool
    issues: tuple[ValidationIssue, ...]
    summary: dict[str, Any] = field(default_factory=dict)


class AnalysisCaseValidator:
    def __init__(self, spec: AnalysisCaseSpec) -> None:
        self.spec = spec

    def validate(self) -> CaseValidationReport:
        issues: list[ValidationIssue] = []
        if not str(self.spec.name).strip():
            issues.append(ValidationIssue('error', 'case_name', 'Case name is empty.', 'Set AnalysisCaseSpec.name to a stable identifier.'))
        if self.spec.geometry.kind and self.spec.geometry.kind not in registered_geometry_sources():
            choices = ', '.join(registered_geometry_sources()) or '<none>'
            issues.append(ValidationIssue('error', 'geometry_source', f'Unknown geometry source kind: {self.spec.geometry.kind!r}.', f'Register the source or use one of: {choices}.'))
        for structure in self.spec.structures:
            if hasattr(structure, 'kind') and hasattr(structure, 'parameters') and not hasattr(structure, 'point_ids'):
                if structure.kind not in registered_structure_generators():
                    choices = ', '.join(registered_structure_generators()) or '<none>'
                    issues.append(ValidationIssue('error', 'structure_generator', f'Unknown structure generator kind: {structure.kind!r}.', f'Register the generator or use one of: {choices}.'))
        for interface in self.spec.interfaces:
            if hasattr(interface, 'kind') and hasattr(interface, 'parameters') and hasattr(interface, 'metadata') and not hasattr(interface, 'slave_point_ids'):
                if interface.kind not in registered_interface_generators():
                    choices = ', '.join(registered_interface_generators()) or '<none>'
                    issues.append(ValidationIssue('error', 'interface_generator', f'Unknown interface generator kind: {interface.kind!r}.', f'Register the generator or use one of: {choices}.'))
        if not self.spec.material_library:
            issues.append(ValidationIssue('warning', 'material_library', 'No material library entries were provided.', 'Add material definitions so bindings resolve to explicit constitutive models.'))
        try:
            prepared = AnalysisCaseBuilder(self.spec).build()
        except Exception as exc:
            issues.append(ValidationIssue('error', 'prepare_case', f'Case preparation failed: {exc}', 'Inspect geometry source, mesh settings, and assignment selectors.', {'exception_type': type(exc).__name__}))
            return CaseValidationReport(ok=False, issues=tuple(issues), summary={'case_name': self.spec.name})
        model = prepared.model
        region_names = {str(region.name) for region in model.region_tags}
        if not region_names:
            issues.append(ValidationIssue('error', 'regions', 'The prepared model contains no regions.', 'Check geometry import and meshing output.'))
        unassigned = sorted(name for name in region_names if model.material_for_region(name) is None)
        if unassigned:
            issues.append(ValidationIssue('warning', 'materials_unassigned', f'{len(unassigned)} region(s) do not have a material assignment.', 'Add MaterialAssignmentSpec entries or broaden the selector.', {'regions': unassigned}))
        for assignment in self.spec.materials:
            if assignment.selector is not None:
                matched = resolve_region_selector(model, assignment.selector)
                if not matched:
                    issues.append(ValidationIssue('warning', 'material_selector_empty', f'Material selector for {assignment.material_name!r} matched no regions.', 'Adjust selector names/patterns/metadata.', {'material_name': assignment.material_name}))

        for bc in self.spec.boundary_conditions:
            selector = getattr(bc, 'selector', None)
            explicit_names = tuple(getattr(bc, 'region_names', ()) or ())
            if selector is not None or explicit_names:
                matched = union_region_names(model, explicit_names=explicit_names, selector=selector)
                if not matched:
                    issues.append(ValidationIssue('warning', 'boundary_selector_empty', f'Boundary condition {getattr(bc, "name", "<unnamed>")!r} matched no regions.', 'Adjust region_names or selector.'))
        for stage in self.spec.stages:
            for bc in stage.boundary_conditions:
                selector = getattr(bc, 'selector', None)
                explicit_names = tuple(getattr(bc, 'region_names', ()) or ())
                if selector is not None or explicit_names:
                    matched = union_region_names(model, explicit_names=explicit_names, selector=selector)
                    if not matched:
                        issues.append(ValidationIssue('warning', 'stage_boundary_selector_empty', f'Stage {stage.name!r} boundary condition {getattr(bc, "name", "<unnamed>")!r} matched no regions.', 'Adjust region_names or selector.'))
            for load in stage.loads:
                selector = getattr(load, 'selector', None)
                explicit_names = tuple(getattr(load, 'region_names', ()) or ())
                if selector is not None or explicit_names:
                    matched = union_region_names(model, explicit_names=explicit_names, selector=selector)
                    if not matched:
                        issues.append(ValidationIssue('warning', 'stage_load_selector_empty', f'Stage {stage.name!r} load {getattr(load, "name", "<unnamed>")!r} matched no regions.', 'Adjust region_names or selector.'))

        for stage in self.spec.stages:
            activate_hits = resolve_region_selector(model, stage.activate_selector) if stage.activate_selector is not None else ()
            deactivate_hits = resolve_region_selector(model, stage.deactivate_selector) if stage.deactivate_selector is not None else ()
            if stage.activate_selector is not None and not activate_hits:
                issues.append(ValidationIssue('warning', 'stage_activate_selector_empty', f'Stage {stage.name!r} activate selector matched no regions.', 'Adjust the selector or provide explicit activate_regions.'))
            if stage.deactivate_selector is not None and not deactivate_hits:
                issues.append(ValidationIssue('warning', 'stage_deactivate_selector_empty', f'Stage {stage.name!r} deactivate selector matched no regions.', 'Adjust the selector or provide explicit deactivate_regions.'))
        stage_names = [stage.name for stage in self.spec.stages]
        stage_name_set = set(stage_names)
        predecessor_map = {stage.name: stage.predecessor for stage in self.spec.stages}
        for stage in self.spec.stages:
            if stage.predecessor is not None and stage.predecessor not in stage_name_set:
                issues.append(ValidationIssue('error', 'stage_predecessor_missing', f'Stage {stage.name!r} references unknown predecessor {stage.predecessor!r}.', 'Choose an existing predecessor stage or clear the predecessor.'))
            if stage.predecessor == stage.name:
                issues.append(ValidationIssue('error', 'stage_predecessor_self', f'Stage {stage.name!r} cannot reference itself as predecessor.', 'Choose another predecessor or clear the predecessor.'))
        roots = [name for name in stage_names if predecessor_map.get(name) in {None, ''}]
        if stage_names and not roots:
            issues.append(ValidationIssue('warning', 'stage_graph_roots_missing', 'The stage graph has no root stage.', 'Clear the predecessor on at least one stage so the construction sequence has an entry point.'))
        elif len(roots) > 1:
            issues.append(ValidationIssue('info', 'stage_graph_multiple_roots', f'The stage graph currently has {len(roots)} root stages.', 'This is allowed, but make sure the GUI or solver chooses the intended entry sequence.', {'roots': roots}))
        # cycle detection
        visit_state: dict[str, int] = {}
        cycle_nodes: set[str] = set()
        def _visit(name: str) -> None:
            state = visit_state.get(name, 0)
            if state == 1:
                cycle_nodes.add(name)
                return
            if state == 2:
                return
            visit_state[name] = 1
            pred = predecessor_map.get(name)
            if pred in stage_name_set:
                _visit(str(pred))
                if pred in cycle_nodes:
                    cycle_nodes.add(name)
            visit_state[name] = 2
        for name in stage_names:
            _visit(name)
        if cycle_nodes:
            issues.append(ValidationIssue('error', 'stage_graph_cycle', f'The stage graph contains a predecessor cycle involving {sorted(cycle_nodes)!r}.', 'Break the cycle by clearing or changing one of the predecessor links.', {'cycle_nodes': sorted(cycle_nodes)}))
        for pair in self.spec.mesh_preparation.contact_pairs:
            slave_hits = resolve_region_selector(model, pair.slave_selector) if pair.slave_selector is not None else (() if not pair.slave_region else (pair.slave_region,))
            master_hits = resolve_region_selector(model, pair.master_selector) if pair.master_selector is not None else (() if not pair.master_region else (pair.master_region,))
            if not slave_hits:
                issues.append(ValidationIssue('warning', 'contact_slave_empty', f'Contact pair {pair.name!r} matched no slave regions.', 'Adjust slave_region or slave_selector.'))
            if not master_hits:
                issues.append(ValidationIssue('warning', 'contact_master_empty', f'Contact pair {pair.name!r} matched no master regions.', 'Adjust master_region or master_selector.'))
        interface_ready_applied = bool(prepared.report.metadata.get('interface_ready_applied', False))
        if prepared.report.merged_point_count > 0:
            if interface_ready_applied:
                issues.append(ValidationIssue('info', 'intentional_duplicate_points', f'The interface-ready preprocessor intentionally duplicated {prepared.report.metadata.get("interface_ready_duplicated_point_count", 0)} point(s) to separate interface topology.', 'This is expected when interface_node_split_mode=auto.', {'merged_point_count': prepared.report.merged_point_count, 'interface_ready_duplicated_point_count': prepared.report.metadata.get('interface_ready_duplicated_point_count', 0)}))
            else:
                issues.append(ValidationIssue('warning', 'duplicate_points', f'The prepared mesh still has {prepared.report.merged_point_count} coincident points.', 'Investigate mesh source continuity or merge settings.', {'merged_point_count': prepared.report.merged_point_count}))
        if not model.stages:
            issues.append(ValidationIssue('warning', 'stages', 'No analysis stages are defined.', 'Add explicit StageSpec entries or mesh_preparation.excavation_steps.'))

        for structure in model.structures:
            required_points = 4 if structure.kind == 'shellquad4' else 2
            if len(tuple(structure.point_ids)) < required_points:
                issues.append(ValidationIssue('warning', 'structure_topology', f'Structure {structure.name!r} has too few point ids for kind {structure.kind!r}.', 'Check structure generation or explicit point_ids.', {'structure_name': structure.name, 'kind': structure.kind, 'required_points': required_points}))
        if self.spec.structures and not model.structures:
            issues.append(ValidationIssue('warning', 'structures', 'The case requested structures but none were prepared.', 'Inspect structure generators or explicit structure definitions.'))
        if self.spec.interfaces and not model.interfaces:
            issues.append(ValidationIssue('warning', 'interfaces', 'The case requested interfaces but none were prepared.', 'Inspect interface generators or explicit interface definitions.'))
        identical_interface_names = [item.name for item in model.interfaces if any(int(s) == int(m) for s, m in zip(item.slave_point_ids, item.master_point_ids, strict=False))]
        if identical_interface_names:
            issues.append(ValidationIssue('warning', 'interface_identical_pairs', f'{len(identical_interface_names)} interface(s) contain identical slave/master point ids.', 'Prefer adjacency-based generators with avoid_identical_pairs=true or review interface pairing.', {'interfaces': identical_interface_names}))
        adjacency_count = len(compute_region_adjacency(model, min_shared_points=1))
        boundary_adjacency_count = len(compute_region_boundary_adjacency(model, min_shared_faces=1))
        region_surface_count = len(compute_region_boundary_surfaces(model))
        interface_candidate_count = len(compute_region_surface_interface_candidates(model, min_shared_faces=1))
        topology = analyze_interface_topology(model)
        interface_faces = compute_interface_face_elements(model)
        if boundary_adjacency_count > 0 and interface_candidate_count == 0:
            issues.append(ValidationIssue('warning', 'interface_candidates_empty', 'Boundary adjacencies exist but no surface interface candidates were identified.', 'Inspect region partition continuity and boundary surface extraction.'))
        if topology.split_plans:
            issues.append(ValidationIssue('warning', 'interface_node_split_recommended', f'{len(topology.split_plans)} interface(s) would benefit from node splitting before interface assembly.', 'Review preprocess-case/export-preprocess output and duplicate interface-side nodes in the preprocessor stage.', {'interfaces': [item.interface_name for item in topology.split_plans], 'duplicate_side': str(topology.metadata.get('duplicate_side', 'slave'))}))
        if model.interfaces and not interface_faces.elements:
            issues.append(ValidationIssue('warning', 'interface_face_elements_empty', 'Interfaces exist but no face-aware interface topology preview elements were generated.', 'Inspect interface pairing, region ownership, and interface-ready preprocessing.'))
        if model.interfaces and not model.interface_elements:
            issues.append(ValidationIssue('warning', 'interface_elements_empty', 'Interfaces exist but no explicit interface element definitions were materialized.', 'Enable mesh_preparation.interface_element_mode or inspect face-aware interface topology generation.'))
        summary = {
            'case_name': self.spec.name,
            'n_stage_roots': len(roots),
            'stage_roots': roots,
            'n_regions': len(model.region_tags),
            'n_material_bindings': len(model.materials),
            'n_stages': len(model.stages),
            'n_interfaces': len(model.interfaces),
            'n_structures': len(model.structures),
            'n_region_adjacencies': adjacency_count,
            'n_boundary_adjacencies': boundary_adjacency_count,
            'n_region_surfaces': region_surface_count,
            'n_interface_candidates': interface_candidate_count,
            'n_node_split_plans': int(len(topology.split_plans)),
            'n_suggested_duplicate_points': int(topology.metadata.get('n_suggested_duplicate_points', 0)),
            'n_interface_face_groups': int(len(interface_faces.groups)),
            'n_interface_face_elements': int(len(interface_faces.elements)),
            'n_interface_elements': int(len(model.interface_elements)),
            **dict(prepared.report.metadata),
        }
        ok = not any(issue.level == 'error' for issue in issues)
        return CaseValidationReport(ok=ok, issues=tuple(issues), summary=summary)
