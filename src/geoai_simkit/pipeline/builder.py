from __future__ import annotations

from dataclasses import asdict

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.geometry.mesh_adapter import to_unstructured_grid
from geoai_simkit.geometry.mesh_engine import MeshEngine, MeshEngineOptions
from geoai_simkit.pipeline.interfaces import resolve_interface_entries
from geoai_simkit.pipeline.preprocess import build_node_pair_contact, build_stage_sequence_from_excavation, resolve_boundary_condition_spec, resolve_stage_spec
from geoai_simkit.pipeline.structures import resolve_structure_entries
from geoai_simkit.pipeline.surfaces import compute_region_boundary_surfaces, compute_region_surface_interface_candidates
from geoai_simkit.pipeline.topology import analyze_interface_topology
from geoai_simkit.pipeline.interface_ready import apply_interface_node_split
from geoai_simkit.pipeline.interface_elements import compute_interface_face_elements, materialize_interface_face_definitions
from geoai_simkit.pipeline.selectors import resolve_region_selector
from geoai_simkit.pipeline.specs import AnalysisCaseSpec, BoundaryConditionSpec, PreparedAnalysisCase, PreparationReport


class AnalysisCaseBuilder:
    def __init__(self, spec: AnalysisCaseSpec) -> None:
        self.spec = spec


    def _apply_global_boundary_conditions(self, model: SimulationModel) -> list[str]:
        notes: list[str] = []
        for bc in self.spec.boundary_conditions:
            resolved = resolve_boundary_condition_spec(model, bc)
            model.add_boundary_condition(resolved)
            if isinstance(bc, BoundaryConditionSpec) and not tuple(resolved.metadata.get('point_ids', ())):
                notes.append(f'Boundary condition {bc.name!r} matched no points.')
        return notes

    def _apply_material_assignments(self, model: SimulationModel) -> list[str]:
        notes: list[str] = []
        for assignment in self.spec.materials:
            target_regions = list(assignment.region_names)
            if assignment.selector is not None:
                target_regions.extend(resolve_region_selector(model, assignment.selector))
            ordered_regions = tuple(dict.fromkeys(str(name) for name in target_regions if str(name)))
            if not ordered_regions:
                notes.append(f'Material assignment {assignment.material_name!r} matched no regions.')
                continue
            for region_name in ordered_regions:
                model.add_material(region_name, assignment.material_name, **dict(assignment.parameters or {}))
                binding = model.material_for_region(region_name)
                if binding is not None:
                    binding.metadata.update(dict(assignment.metadata or {}))
                    if assignment.selector is not None:
                        binding.metadata.setdefault('assigned_via_selector', True)
        return notes


    def _apply_structures(self, model: SimulationModel) -> tuple[list[str], list[str]]:
        resolved, generated_names, notes = resolve_structure_entries(model, self.spec.structures)
        for item in resolved:
            model.add_structure(item)
        return generated_names, notes

    def _apply_interfaces(self, model: SimulationModel) -> tuple[list[str], list[str]]:
        resolved, generated_names, notes = resolve_interface_entries(model, self.spec.interfaces)
        for item in resolved:
            model.add_interface(item)
        return generated_names, notes

    def _expand_contact_pairs(self, model: SimulationModel) -> tuple[list[str], list[str]]:
        generated_interface_names: list[str] = []
        notes: list[str] = []
        for pair in self.spec.mesh_preparation.contact_pairs:
            slave_regions = list(filter(None, [pair.slave_region]))
            master_regions = list(filter(None, [pair.master_region]))
            if pair.slave_selector is not None:
                slave_regions.extend(resolve_region_selector(model, pair.slave_selector))
            if pair.master_selector is not None:
                master_regions.extend(resolve_region_selector(model, pair.master_selector))
            slave_regions = list(dict.fromkeys(slave_regions))
            master_regions = list(dict.fromkeys(master_regions))
            if not slave_regions or not master_regions:
                notes.append(f'Contact pair {pair.name!r} matched no slave/master regions.')
                continue
            for slave_region in slave_regions:
                for master_region in master_regions:
                    if slave_region == master_region:
                        continue
                    interface_name = pair.name if len(slave_regions) == 1 and len(master_regions) == 1 else f'{pair.name}:{slave_region}->{master_region}'
                    interface = build_node_pair_contact(model, slave_region=slave_region, master_region=master_region, active_stages=pair.active_stages, parameters=pair.parameters, name=interface_name, search_radius_factor=pair.search_radius_factor, exact_only=pair.exact_only, metadata=pair.metadata)
                    if interface is not None:
                        model.add_interface(interface)
                        generated_interface_names.append(interface.name)
                    else:
                        notes.append(f'No interface pairs were generated for {slave_region}->{master_region}.')
        return generated_interface_names, notes

    def build(self) -> PreparedAnalysisCase:
        model = SimulationModel(name=self.spec.name, mesh=self.spec.geometry.resolve())
        inferred_state = model.geometry_state()
        model.metadata.update(dict(self.spec.metadata or {}))
        model.metadata.setdefault('pipeline.case_name', self.spec.name)
        model.metadata.setdefault('pipeline.geometry_metadata', dict(self.spec.geometry.metadata or {}))
        model.set_geometry_state(inferred_state)
        for definition in self.spec.material_library:
            model.upsert_material_definition(definition)
        notes: list[str] = []
        opts = MeshEngineOptions(element_family=self.spec.mesh.element_family, global_size=self.spec.mesh.global_size, padding=self.spec.mesh.padding, local_refinement=self.spec.mesh.local_refinement, keep_geometry_copy=self.spec.mesh.keep_geometry_copy, only_material_bound_geometry=self.spec.mesh.only_material_bound_geometry)
        if model.geometry_state() != 'meshed':
            model = MeshEngine(opts).mesh_model(model)
        elif self.spec.mesh.merge_points:
            model.mesh = to_unstructured_grid(model.mesh)
        model.ensure_regions()
        generated_structure_names, structure_notes = self._apply_structures(model)
        notes.extend(structure_notes)
        generated_interface_names, interface_notes = self._apply_interfaces(model)
        notes.extend(interface_notes)
        more_interfaces, contact_notes = self._expand_contact_pairs(model)
        generated_interface_names.extend(more_interfaces)
        notes.extend(contact_notes)
        split_mode = str(getattr(self.spec.mesh_preparation, 'interface_node_split_mode', 'plan') or 'plan').strip().lower()
        split_side = str(getattr(self.spec.mesh_preparation, 'interface_duplicate_side', 'slave') or 'slave').strip().lower()
        interface_ready_report = None
        if split_mode == 'auto':
            interface_ready_report = apply_interface_node_split(model, duplicate_side=split_side)
            if interface_ready_report.applied:
                notes.append(f'Interface-ready preprocessing duplicated {interface_ready_report.duplicated_region_point_count} region-point nodes.')
        notes.extend(self._apply_global_boundary_conditions(model))
        notes.extend(self._apply_material_assignments(model))
        generated_stage_names: list[str] = []
        if self.spec.stages:
            model.stages = [resolve_stage_spec(model, item) for item in self.spec.stages]
            generated_stage_names.extend([item.name for item in model.stages])
        elif self.spec.mesh_preparation.excavation_steps:
            model.stages = build_stage_sequence_from_excavation(model, self.spec.mesh_preparation.excavation_steps, initial_metadata={'stage_role': 'initial', 'source': 'generic_mesh_preparation'})
            generated_stage_names.extend([item.name for item in model.stages])
            notes.append('Stages were auto-generated from excavation sequence metadata.')
        model.metadata['pipeline.generated_stages'] = list(generated_stage_names)
        model.metadata['pipeline.generated_interfaces'] = list(generated_interface_names)
        model.metadata['pipeline.generated_structures'] = list(generated_structure_names)
        model.metadata['pipeline.mesh_spec'] = asdict(self.spec.mesh)
        grid = model.to_unstructured_grid()
        duplicate_count = int(grid.n_points - len({tuple(round(float(v), 9) for v in row) for row in grid.points}))
        region_surfaces = compute_region_boundary_surfaces(model)
        interface_candidates = compute_region_surface_interface_candidates(model, min_shared_faces=1)
        topology = analyze_interface_topology(model)
        interface_ready_meta = dict(model.metadata.get('pipeline.interface_ready') or {})
        interface_faces = compute_interface_face_elements(model)
        interface_element_mode = str(getattr(self.spec.mesh_preparation, 'interface_element_mode', 'explicit') or 'explicit').strip().lower()
        if interface_element_mode not in {'off', 'none'}:
            model.clear_interface_elements()
            for item in materialize_interface_face_definitions(model):
                model.add_interface_element(item)
        else:
            model.clear_interface_elements()
        report = PreparationReport(merged_points=bool(self.spec.mesh.merge_points), merged_point_count=max(0, duplicate_count), generated_stages=tuple(generated_stage_names), generated_interfaces=tuple(generated_interface_names), notes=tuple(notes), metadata={'n_points': int(grid.n_points), 'n_cells': int(grid.n_cells), 'n_regions': int(len(model.region_tags)), 'n_material_bindings': int(len(model.materials)), 'n_boundary_conditions': int(len(model.boundary_conditions)), 'n_structures': int(len(model.structures)), 'n_generated_structures': int(len(generated_structure_names)), 'n_interfaces': int(len(model.interfaces)), 'n_generated_interfaces': int(len(generated_interface_names)), 'n_interface_elements': int(len(model.interface_elements)), 'n_stage_loads': int(sum(len(stage.loads) for stage in model.stages)), 'n_stage_boundary_conditions': int(sum(len(stage.boundary_conditions) for stage in model.stages)), 'n_region_surfaces': int(len(region_surfaces)), 'n_interface_candidates': int(len(interface_candidates)), 'n_node_split_plans': int(len(topology.split_plans)), 'n_suggested_duplicate_points': int(topology.metadata.get('n_suggested_duplicate_points', 0)), 'n_interface_face_groups': int(len(interface_faces.groups)), 'n_interface_face_elements': int(len(interface_faces.elements)), 'interface_face_total_area': float(interface_faces.metadata.get('total_area', 0.0)), 'interface_node_split_mode': split_mode, 'interface_duplicate_side': split_side, 'interface_element_mode': interface_element_mode, 'interface_ready_applied': bool(interface_ready_meta.get('applied', False)), 'interface_ready_duplicated_point_count': int(interface_ready_meta.get('duplicated_point_count', 0)), 'interface_ready_updated_interface_count': int(interface_ready_meta.get('updated_interface_count', 0))})
        model.metadata['pipeline.preparation_report'] = {'merged_points': report.merged_points, 'merged_point_count': report.merged_point_count, 'generated_stages': list(report.generated_stages), 'generated_interfaces': list(report.generated_interfaces), 'notes': list(report.notes), **dict(report.metadata)}
        return PreparedAnalysisCase(model=model, report=report)
