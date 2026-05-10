from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal
from geoai_simkit.app.case_service import CaseService, ModelBrowserSummary, StageBrowserRow
from geoai_simkit.app.preprocess_service import PreprocessOverview, PreprocessService
from geoai_simkit.app.results_service import ResultsOverview
from geoai_simkit.app.validation_service import ValidationOverview, ValidationService
from geoai_simkit.app.workspace_aliases import canonical_space
from geoai_simkit.core.model import SimulationModel
from geoai_simkit.pipeline import AnalysisCaseSpec

WorkbenchMode = Literal['geometry','partition','mesh','assign','stage','solve','results']

@dataclass(slots=True)
class WorkbenchDocument:
    case: AnalysisCaseSpec
    model: SimulationModel
    mode: WorkbenchMode
    browser: ModelBrowserSummary
    preprocess: PreprocessOverview | None = None
    results: ResultsOverview | None = None
    validation: ValidationOverview | None = None
    result_db: Any | None = None
    job_plan: Any | None = None
    compile_report: dict[str, Any] | None = None
    telemetry_summary: dict[str, Any] = field(default_factory=dict)
    checkpoint_ids: tuple[str, ...] = ()
    increment_checkpoint_ids: tuple[str, ...] = ()
    failure_checkpoint_ids: tuple[str, ...] = ()
    file_path: str | None = None
    dirty: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)

class WorkbenchService:
    def __init__(self):
        self.case_service = CaseService(); self.preprocess_service = PreprocessService(); self.validation_service = ValidationService()
    def _scene_preview_descriptor(self, model: SimulationModel) -> dict[str, Any]:
        return {'model_name': model.name, 'dataset_kind': 'headless-grid', 'point_count': int(getattr(model.to_unstructured_grid(), 'n_points', 0)) if hasattr(model, 'to_unstructured_grid') else 0, 'cell_count': int(getattr(model.to_unstructured_grid(), 'n_cells', 0)) if hasattr(model, 'to_unstructured_grid') else 0, 'block_count': len(getattr(model, 'region_tags', ()) or ()), 'stage_names': list(model.list_stages()) if hasattr(model, 'list_stages') else [], 'metadata': {'headless_safe': True}}
    def _refresh_workspace_contract(self, document: WorkbenchDocument) -> WorkbenchDocument:
        from geoai_simkit.app.session import build_workbench_session_state
        active_view = str(document.metadata.get('active_view_mode','workflow') or 'workflow')
        active_space = canonical_space(document.metadata.get('active_space'))
        session = build_workbench_session_state(document, active_view=active_view, active_space=active_space).to_dict()
        document.metadata['workspace_session'] = session
        document.metadata['active_space'] = session.get('active_space')
        document.metadata['active_view_mode'] = session.get('active_view')
        document.metadata['primary_navigation'] = list(session.get('navigation', []))
        document.metadata['workspace_views'] = list(session.get('available_views', []))
        document.metadata['modern_workspace_state'] = self.modern_workspace_state(document)
        document.metadata['unified_workbench'] = {'contract':'deferred_unified_workbench_payload_v1', 'active_space': document.metadata.get('active_space'), 'active_view': document.metadata.get('active_view_mode')}
        return document
    def document_from_case(self, case: AnalysisCaseSpec, *, mode: WorkbenchMode='geometry', file_path: str | None = None) -> WorkbenchDocument:
        model = self.case_service.prepare_case(case)
        return self.document_from_model(model, case=case, mode=mode, file_path=file_path)
    def document_from_model(self, model: SimulationModel, *, case: AnalysisCaseSpec, mode: WorkbenchMode='geometry', file_path: str | None = None) -> WorkbenchDocument:
        browser = self.case_service.build_browser_summary(model, case=case)
        preprocess = self.preprocess_service.build_overview(case)
        validation = self.validation_service.build_overview(case)
        doc = WorkbenchDocument(case=case, model=model, mode=mode, browser=browser, preprocess=preprocess, validation=validation, file_path=file_path, metadata={**dict(getattr(model, 'metadata', {}) or {}), 'model_name': model.name, 'has_results': bool(getattr(model,'results',None)), 'scene_preview': self._scene_preview_descriptor(model)})
        # Normalize the GUI data source immediately. From this point onward,
        # object tree, property, material, stage and solver compiler panels read
        # GeoProjectDocument instead of scattered legacy fields.
        try:
            from geoai_simkit.app.geoproject_source import get_geoproject_document, geoproject_summary
            project = get_geoproject_document(doc)
            doc.metadata['geoproject_summary'] = geoproject_summary(project)
        except Exception as exc:
            doc.metadata['geoproject_init_error'] = str(exc)
        return self._refresh_workspace_contract(doc)
    def load_document(self, path: str | Path, *, mode: WorkbenchMode='geometry') -> WorkbenchDocument: return self.document_from_case(self.case_service.load_case(path), mode=mode, file_path=str(path))
    def save_document(self, document: WorkbenchDocument, path: str | Path | None = None) -> Path:
        target = self.case_service.save_case(document.case, path or document.file_path or f'{document.case.name}.json'); document.file_path=str(target); document.dirty=False; return target
    def refresh_document(self, document: WorkbenchDocument, *, preserve_results: bool=False) -> WorkbenchDocument:
        refreshed = self.document_from_case(document.case, mode=document.mode, file_path=document.file_path)
        refreshed.dirty = document.dirty; refreshed.messages = list(document.messages)
        if preserve_results:
            refreshed.results = document.results; refreshed.result_db = document.result_db; refreshed.compile_report = document.compile_report; refreshed.telemetry_summary = dict(document.telemetry_summary); refreshed.checkpoint_ids = tuple(document.checkpoint_ids)
        refreshed.metadata.update({k:v for k,v in document.metadata.items() if k in {'active_space','active_view_mode'}})
        return self._refresh_workspace_contract(refreshed)
    def validate_document(self, document: WorkbenchDocument) -> ValidationOverview:
        document.validation = self.validation_service.build_overview(document.case); self._refresh_workspace_contract(document); return document.validation
    def set_mode(self, document: WorkbenchDocument, mode: WorkbenchMode) -> None: document.mode = mode; self._refresh_workspace_contract(document)
    def set_active_space(self, document: WorkbenchDocument, space: str) -> None: document.metadata['active_space'] = canonical_space(space); self._refresh_workspace_contract(document)
    def set_active_view_mode(self, document: WorkbenchDocument, view_mode: str) -> None: document.metadata['active_view_mode'] = str(view_mode); self._refresh_workspace_contract(document)
    def modern_workspace_state(self, document: WorkbenchDocument) -> dict[str, Any]:
        session = dict(document.metadata.get('workspace_session', {}) or {})
        return self.case_service.modern_workspace_state(document.case, active_space=canonical_space(str(session.get('active_space','modeling'))), active_view=str(session.get('active_view','workflow')), messages=document.messages, document_dirty=document.dirty, file_path=document.file_path, model_metadata=dict(getattr(document.model,'metadata',{}) or {}))
    def command_palette(self, document: WorkbenchDocument) -> dict[str, Any]: return self.case_service.command_palette(document.case, active_space=canonical_space(document.metadata.get('active_space')), active_view=str(document.metadata.get('active_view_mode','workflow')))
    def notification_center(self, document: WorkbenchDocument) -> dict[str, Any]: return self.case_service.notification_center(document.case, messages=document.messages)
    def unified_workbench_payload(self, document: WorkbenchDocument) -> dict[str, object]:
        from geoai_simkit.app.shell.unified_workbench_window import build_unified_workbench_payload
        return build_unified_workbench_payload(document)

# --- GeoProjectDocument-backed visual modeling/workbench methods -----------
# The modern GUI still accepts legacy WorkbenchDocument handles, but all edit
# operations below resolve and mutate GeoProjectDocument as the single source of
# truth. EngineeringDocument is kept only as an import/conversion fallback.
def _geo_project_document(self, document):
    from geoai_simkit.app.geoproject_source import get_geoproject_document
    project = get_geoproject_document(document)
    return project


def _visual_engineering_document(self, document):
    # Compatibility shim for older callers. New GUI paths should call
    # geo_project_document() and panel builders directly.
    from geoai_simkit.document import engineering_document_from_simulation_model
    cached = document.metadata.get('engineering_document') if isinstance(document.metadata, dict) else None
    if cached is not None:
        return cached
    eng = engineering_document_from_simulation_model(document.model, name=getattr(document.case, 'name', None))
    document.metadata['engineering_document'] = eng
    return eng


def _stage_region_state(self, document, stage_name: str | None = None, region_name: str | None = None):
    project = self.geo_project_document(document)
    phase_id = stage_name or project.phase_manager.active_phase_id or project.phase_manager.initial_phase.id
    snapshot = project.phase_manager.phase_state_snapshots.get(phase_id) or project.refresh_phase_snapshot(phase_id)
    if region_name is not None:
        return str(region_name) in set(snapshot.active_volume_ids)
    return {
        'contract': 'geoproject_phase_region_state_v1',
        'data_source': 'GeoProjectDocument.PhaseManager',
        'phase_id': phase_id,
        'active_volume_ids': list(snapshot.active_volume_ids),
        'inactive_volume_ids': sorted(set(project.geometry_model.volumes) - set(snapshot.active_volume_ids)),
        'active_structure_ids': list(snapshot.active_structure_ids),
        'active_interface_ids': list(snapshot.active_interface_ids),
        'snapshot': snapshot.to_dict(),
    }


def _set_stage_region_state(self, document, stage_name: str, region_name: str, active: bool):
    from geoai_simkit.app.geoproject_source import mark_geoproject_dirty
    project = self.geo_project_document(document)
    snapshot = project.set_phase_volume_activation(stage_name, region_name, active)
    mark_geoproject_dirty(document, project)
    return {'ok': True, 'snapshot': snapshot.to_dict()}


def _set_block_material(self, document, block_id: str, material_name: str):
    from geoai_simkit.app.geoproject_source import mark_geoproject_dirty
    project = self.geo_project_document(document)
    volume = project.set_volume_material(block_id, material_name)
    mark_geoproject_dirty(document, project)
    return {'ok': True, 'volume': volume.to_dict()}


def _set_block_flags(self, document, block_id: str, **flags):
    from geoai_simkit.app.geoproject_source import mark_geoproject_dirty
    project = self.geo_project_document(document)
    volume = project.geometry_model.volumes.get(block_id)
    if volume is None:
        raise KeyError(f'Volume not found: {block_id}')
    volume.metadata.setdefault('gui_flags', {}).update({str(k): v for k, v in flags.items()})
    if 'visible' in flags:
        volume.metadata['visible'] = bool(flags['visible'])
    if 'locked' in flags:
        volume.metadata['locked'] = bool(flags['locked'])
    mark_geoproject_dirty(document, project)
    return volume.to_dict()


def _set_mesh_global_size(self, document, size: float):
    from geoai_simkit.app.geoproject_source import mark_geoproject_dirty
    project = self.geo_project_document(document)
    settings = project.set_mesh_global_size(size)
    mark_geoproject_dirty(document, project)
    return {'mesh_global_size': settings.global_size, 'mesh_dirty': True, 'data_source': 'GeoProjectDocument.MeshModel'}


def _plan_document(self, document, *args, execution_profile: str = 'cpu-robust', device: str = 'cpu', **kwargs):
    project = self.geo_project_document(document)
    project.populate_default_framework_content()
    payload = {
        'contract': 'geoproject_solver_plan_preview_v1',
        'data_source': 'GeoProjectDocument',
        'case_name': document.case.name,
        'phase_count': len(project.phase_ids()),
        'mesh_cell_count': 0 if project.mesh_model.mesh_document is None else project.mesh_model.mesh_document.cell_count,
        'volume_count': len(project.geometry_model.volumes),
        'boundary_condition_count': len(project.solver_model.boundary_conditions),
        'load_count': len(project.solver_model.loads),
        'execution_profile': execution_profile,
        'device': device,
    }
    document.metadata['solver_plan_preview'] = payload
    plan = SimpleNamespace(profile=execution_profile, device=device, thread_count=1, has_cuda=False, note='GeoProject compile preview; nonlinear production solver is capability-gated.')
    document.job_plan = plan
    return plan


def _run_document(self, document, out_dir: str | Path | None = None, *args, **kwargs):
    from geoai_simkit.app.geoproject_source import mark_geoproject_dirty
    project = self.geo_project_document(document)
    project.populate_default_framework_content()
    compiled = project.compile_phase_models()
    mark_geoproject_dirty(document, project)
    document.dirty = False
    target = Path(out_dir or 'exports_nextgen_gui')
    target.mkdir(parents=True, exist_ok=True)
    out_path = target / f"{document.case.name}_compiled_geoproject.json"
    try:
        project.save_json(out_path)
    except Exception:
        pass
    run = SimpleNamespace(
        accepted=True,
        backend=project.solver_model.runtime_settings.backend,
        data_source='GeoProjectDocument.SolverModel',
        phase_count=len(project.phase_ids()),
        compiled_phase_model_count=len(compiled),
        result_stage_count=len(project.result_store.phase_results),
        out_path=str(out_path),
    )
    document.compile_report = dict(run.__dict__)
    return run


def _add_stage(self, document, stage_name: str, predecessor: str | None = None):
    from geoai_simkit.app.geoproject_source import mark_geoproject_dirty
    project = self.geo_project_document(document)
    stage = project.add_phase(stage_name, name=stage_name, predecessor_id=predecessor)
    mark_geoproject_dirty(document, project)
    return stage.to_dict()


def _clone_stage(self, document, source_stage: str, new_stage: str):
    from geoai_simkit.app.geoproject_source import mark_geoproject_dirty
    project = self.geo_project_document(document)
    cloned = project.add_phase(new_stage, name=new_stage, copy_from=source_stage)
    mark_geoproject_dirty(document, project)
    return cloned.to_dict()


def _remove_stage(self, document, stage_name: str):
    from geoai_simkit.app.geoproject_source import mark_geoproject_dirty
    project = self.geo_project_document(document)
    result = project.remove_phase(stage_name)
    mark_geoproject_dirty(document, project)
    return result


def _set_stage_predecessor(self, document, stage_name: str, predecessor: str | None):
    from geoai_simkit.app.geoproject_source import mark_geoproject_dirty
    project = self.geo_project_document(document)
    stage = project.set_phase_predecessor(stage_name, predecessor)
    mark_geoproject_dirty(document, project)
    return stage.to_dict()


def _import_stl_geology(self, document, path: str | Path, *, unit_scale: float = 1.0, merge_tolerance: float = 1.0e-9, material_id: str = 'imported_geology', role: str = 'geology_surface', replace: bool = True):
    from geoai_simkit.app.geoproject_source import mark_geoproject_dirty, set_geoproject_document
    from geoai_simkit.geometry.stl_loader import STLImportOptions, load_stl_geology
    from geoai_simkit.geoproject import GeoProjectDocument
    from geoai_simkit.pipeline import GeometrySource

    options = STLImportOptions(unit_scale=unit_scale, merge_tolerance=merge_tolerance, material_id=material_id, role=role)
    stl = load_stl_geology(path, options)
    document.case.geometry = GeometrySource(
        kind='stl_geology',
        path=str(path),
        parameters={
            'name': stl.name,
            'unit_scale': float(unit_scale),
            'merge_tolerance': float(merge_tolerance),
            'material_id': material_id,
            'role': role,
        },
        metadata={'source': 'gui_import_stl_geology'},
    )
    document.case.metadata.setdefault('imports', [])
    document.case.metadata['imports'].append({'kind': 'stl_geology', **stl.to_summary_dict()})
    document.model = self.case_service.prepare_case(document.case)
    document.browser = self.case_service.build_browser_summary(document.model, case=document.case)
    document.preprocess = self.preprocess_service.build_overview(document.case)
    document.validation = self.validation_service.build_overview(document.case)
    project = GeoProjectDocument.from_stl_geology(path, options=options, name=document.case.name)
    set_geoproject_document(document, project)
    mark_geoproject_dirty(document, project)
    document.metadata['stl_geology'] = stl.to_summary_dict()
    document.messages.append(f"Imported STL geology model: {stl.name} | vertices={len(stl.vertices)} triangles={len(stl.triangles)} | closed={stl.quality.is_closed}")
    document.dirty = True
    self._refresh_workspace_contract(document)
    return stl.to_summary_dict()


def _mesh_document_to_simple_grid(mesh):
    import numpy as np
    from geoai_simkit.pipeline.specs import SimpleUnstructuredGrid

    block_ids = [str(v) for v in list(mesh.cell_tags.get('block_id', []) or [])]
    region_names = block_ids if block_ids else [f'cell_{i}' for i in range(mesh.cell_count)]
    grid = SimpleUnstructuredGrid(points=mesh.nodes, cells=mesh.cells, celltypes=mesh.cell_types, region_names=region_names)
    for key, values in (mesh.cell_tags or {}).items():
        grid.cell_data[str(key)] = np.asarray(list(values), dtype=object)
    grid.field_data['source_kind'] = ['geoproject_mesh_document']
    grid.field_data['mesher'] = [str(mesh.metadata.get('mesher', ''))]
    return grid


def _sync_geoproject_mesh_to_workbench_model(self, document, project):
    import numpy as np
    from geoai_simkit.core.model import AnalysisStage, GeometryObjectRecord, MaterialBinding, MaterialDefinition
    from geoai_simkit.core.types import RegionTag

    mesh = project.mesh_model.mesh_document
    if mesh is None:
        return None
    document.model.mesh = _mesh_document_to_simple_grid(mesh)
    grouped: dict[str, list[int]] = {}
    block_ids = [str(v) for v in list(mesh.cell_tags.get('block_id', []) or [])]
    for cell_id, block_id in enumerate(block_ids):
        grouped.setdefault(block_id, []).append(cell_id)
    regions = []
    materials = []
    object_records = []
    material_library = []
    for block_id, cell_ids in grouped.items():
        volume = project.geometry_model.volumes.get(block_id)
        material_id = str(getattr(volume, 'material_id', '') or '')
        regions.append(RegionTag(
            name=block_id,
            cell_ids=np.asarray(cell_ids, dtype=np.int64),
            metadata={
                'source': 'GeoProjectDocument.MeshModel',
                'role': str(getattr(volume, 'role', '') or ''),
                'material_name': material_id,
                'bounds': list(getattr(volume, 'bounds', []) or []),
                'layer_id': dict(getattr(volume, 'metadata', {}) or {}).get('layer_id'),
            },
        ))
        mat = project.material_library.soil_materials.get(material_id)
        materials.append(MaterialBinding(
            region_name=block_id,
            material_name=material_id or 'unassigned',
            parameters=dict(getattr(mat, 'parameters', {}) or {}),
            metadata={'source': 'GeoProjectDocument.MaterialLibrary', 'model_type': getattr(mat, 'model_type', '') if mat is not None else ''},
        ))
        if mat is not None:
            material_library.append(MaterialDefinition(name=mat.id, model_type=mat.model_type, parameters=dict(mat.parameters), metadata=dict(mat.metadata)))
        object_records.append(GeometryObjectRecord(
            key=f'object:{block_id}',
            name=block_id,
            object_type='volume_block',
            region_name=block_id,
            metadata={
                'source': 'GeoProjectDocument.MeshModel',
                'cell_ids': list(cell_ids),
                'role': str(getattr(volume, 'role', '') or ''),
                'material_name': material_id,
                'bounds': list(getattr(volume, 'bounds', []) or []),
            },
        ))
    document.model.region_tags = regions
    document.model.materials = materials
    document.model.material_library = material_library
    document.model.object_records = object_records
    document.model.stages = [AnalysisStage(name=phase_id, metadata={'source': 'GeoProjectDocument.PhaseManager'}) for phase_id in project.phase_ids()]
    document.model.metadata.update({
        'geometry_state': 'meshed',
        'geoproject_mesh': mesh.to_dict(),
        'geoproject_mesh_summary': {
            'node_count': mesh.node_count,
            'cell_count': mesh.cell_count,
            'mesher': mesh.metadata.get('mesher'),
        },
    })
    document.browser = self.case_service.build_browser_summary(document.model, case=None)
    document.metadata['scene_preview'] = self._scene_preview_descriptor(document.model)
    document.metadata['geoproject_mesh_summary'] = document.model.metadata['geoproject_mesh_summary']
    return mesh


def _import_borehole_csv_geology(self, document, path: str | Path, *, unit_scale: float = 1.0, top_bottom_mode: str = 'depth', xy_padding: float | None = None):
    from geoai_simkit.app.geoproject_source import mark_geoproject_dirty, set_geoproject_document
    from geoai_simkit.modules import geology_import

    options: dict[str, Any] = {'unit_scale': float(unit_scale), 'top_bottom_mode': str(top_bottom_mode or 'depth')}
    if xy_padding is not None:
        options['xy_padding'] = float(xy_padding)
    result = geology_import.import_geology(path, source_type='borehole_csv', options=options)
    project = result.project
    set_geoproject_document(document, project)
    mark_geoproject_dirty(document, project)
    document.metadata['borehole_csv_import'] = result.to_dict()
    document.metadata['geology_import_summary'] = dict(result.metadata)
    document.messages.append(
        f"Imported borehole CSV: {Path(path).name} | boreholes={result.metadata.get('borehole_count', 0)} layers={result.metadata.get('soil_cluster_count', 0)}"
    )
    document.dirty = True
    self._refresh_workspace_contract(document)
    return result.to_dict()


def _generate_layered_volume_mesh(self, document, *, nx: int = 8, ny: int = 8):
    from geoai_simkit.app.geoproject_source import mark_geoproject_dirty
    from geoai_simkit.commands import CommandStack, GenerateLayeredVolumeMeshCommand

    project = self.geo_project_document(document)
    stack = document.metadata.get('command_stack') if isinstance(document.metadata, dict) else None
    if not isinstance(stack, CommandStack):
        stack = CommandStack()
        document.metadata['command_stack'] = stack
    command = GenerateLayeredVolumeMeshCommand(nx=nx, ny=ny, interpolate_missing=True)
    result = stack.execute(command, project)
    if result.ok:
        self.sync_geoproject_mesh_to_workbench_model(document, project)
        mark_geoproject_dirty(document, project)
        document.messages.append(result.message)
        document.metadata['layered_volume_mesh'] = result.to_dict()
        document.metadata['layered_mesh_preview'] = self.layered_mesh_preview_payload(document)
        document.dirty = True
        self._refresh_workspace_contract(document)
    return result


def _hex8_thickness_values(nodes, cell) -> list[float]:
    if len(cell) < 8:
        return []
    values: list[float] = []
    for bottom_idx, top_idx in ((0, 4), (1, 5), (2, 6), (3, 7)):
        try:
            bottom = nodes[int(cell[bottom_idx])]
            top = nodes[int(cell[top_idx])]
            values.append(abs(float(top[2]) - float(bottom[2])))
        except Exception:
            continue
    return values


def _cell_bbox_volume(nodes, cell) -> float:
    try:
        pts = [nodes[int(idx)] for idx in cell]
    except Exception:
        return 0.0
    if not pts:
        return 0.0
    xs = [float(point[0]) for point in pts]
    ys = [float(point[1]) for point in pts]
    zs = [float(point[2]) for point in pts]
    return max(max(xs) - min(xs), 0.0) * max(max(ys) - min(ys), 0.0) * max(max(zs) - min(zs), 0.0)


def _layered_mesh_preview_payload(self, document):
    project = self.geo_project_document(document)
    mesh = project.mesh_model.mesh_document
    settings_meta = dict(project.mesh_model.mesh_settings.metadata or {})
    interpolation_meta = dict(project.metadata.get('layer_surface_interpolation', {}) or {})
    command_meta = dict((document.metadata.get('layered_volume_mesh', {}) or {}).get('metadata', {}) or {}) if isinstance(document.metadata, dict) else {}
    needs_remesh = bool(settings_meta.get('requires_volume_meshing', mesh is None)) or mesh is None
    if mesh is not None and str(mesh.metadata.get('mesher', '')) != 'layered_surface_mesher':
        needs_remesh = True
    warnings: list[str] = []
    for item in list(interpolation_meta.get('warnings', []) or []):
        if str(item) not in warnings:
            warnings.append(str(item))
    if mesh is not None:
        for item in list(getattr(mesh.quality, 'warnings', []) or []):
            if str(item) not in warnings:
                warnings.append(str(item))
    for item in list(command_meta.get('warnings', []) or []):
        if str(item) not in warnings:
            warnings.append(str(item))
    if mesh is None:
        warnings.append('No layered mesh has been generated yet.')

    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    if mesh is not None:
        layers = [str(v) for v in list(mesh.cell_tags.get('layer_id', []) or [])]
        blocks = [str(v) for v in list(mesh.cell_tags.get('block_id', []) or [])]
        materials = [str(v) for v in list(mesh.cell_tags.get('material_id', []) or [])]
        for cell_id in range(mesh.cell_count):
            block_id = blocks[cell_id] if cell_id < len(blocks) else ''
            volume = project.geometry_model.volumes.get(block_id)
            layer_id = layers[cell_id] if cell_id < len(layers) else str((dict(getattr(volume, 'metadata', {}) or {}).get('layer_id') or block_id.removeprefix('volume_')))
            material_id = materials[cell_id] if cell_id < len(materials) else str(getattr(volume, 'material_id', '') or '')
            row = rows_by_key.setdefault(
                (layer_id, block_id),
                {
                    'layer_id': layer_id,
                    'block_id': block_id,
                    'cell_count': 0,
                    'material_id': material_id,
                    'needs_remesh': needs_remesh,
                    'warnings': [],
                    'min_thickness': None,
                    'max_thickness_ratio': None,
                    'degenerate_cell_count': 0,
                    '_thickness_values': [],
                },
            )
            row['cell_count'] += 1
            thickness_values = _hex8_thickness_values(mesh.nodes, mesh.cells[cell_id])
            row['_thickness_values'].extend(thickness_values)
            if min(thickness_values or [0.0]) <= 1.0e-9 or _cell_bbox_volume(mesh.nodes, mesh.cells[cell_id]) <= 1.0e-12:
                row['degenerate_cell_count'] += 1
            if material_id and material_id not in str(row.get('material_id', '')).split('|'):
                row['material_id'] = '|'.join([v for v in [str(row.get('material_id', '')), material_id] if v])
    else:
        for volume_id, volume in project.geometry_model.volumes.items():
            meta = dict(getattr(volume, 'metadata', {}) or {})
            if meta.get('source') != 'borehole_csv':
                continue
            layer_id = str(meta.get('layer_id') or str(volume_id).removeprefix('volume_'))
            rows_by_key[(layer_id, str(volume_id))] = {
                'layer_id': layer_id,
                'block_id': str(volume_id),
                'cell_count': 0,
                'material_id': str(getattr(volume, 'material_id', '') or ''),
                'needs_remesh': True,
                'warnings': ['Layer volume has no generated mesh cells.'],
                'min_thickness': None,
                'max_thickness_ratio': None,
                'degenerate_cell_count': 0,
            }
    rows = sorted(rows_by_key.values(), key=lambda item: (str(item.get('layer_id', '')), str(item.get('block_id', ''))))
    global_thickness_values: list[float] = []
    global_degenerate_count = 0
    for row in rows:
        thickness_values = [float(value) for value in list(row.pop('_thickness_values', []) or [])]
        positive = [value for value in thickness_values if value > 1.0e-9]
        if thickness_values:
            row['min_thickness'] = min(thickness_values)
            row['max_thickness_ratio'] = (max(thickness_values) / min(positive)) if positive else None
            global_thickness_values.extend(thickness_values)
        if int(row.get('degenerate_cell_count', 0) or 0) > 0:
            row['warnings'] = [*list(row.get('warnings', []) or []), f"{row['degenerate_cell_count']} degenerate cells detected."]
        global_degenerate_count += int(row.get('degenerate_cell_count', 0) or 0)
    material_tags = sorted({str(row.get('material_id', '')) for row in rows if str(row.get('material_id', ''))})
    global_positive = [value for value in global_thickness_values if value > 1.0e-9]
    payload = {
        'contract': 'layered_mesh_preview_panel_v1',
        'available': mesh is not None,
        'needs_remesh': bool(needs_remesh),
        'mesher': '' if mesh is None else str(mesh.metadata.get('mesher', '')),
        'node_count': 0 if mesh is None else mesh.node_count,
        'cell_count': 0 if mesh is None else mesh.cell_count,
        'layer_count': len(rows),
        'material_tags': material_tags,
        'min_thickness': min(global_thickness_values) if global_thickness_values else None,
        'max_thickness_ratio': (max(global_thickness_values) / min(global_positive)) if global_positive else None,
        'degenerate_cell_count': global_degenerate_count,
        'interpolation_warning_count': len(list(interpolation_meta.get('warnings', []) or [])),
        'quality_warning_count': 0 if mesh is None else len(getattr(mesh.quality, 'warnings', []) or []),
        'warnings': warnings,
        'layers': rows,
    }
    if isinstance(document.metadata, dict):
        document.metadata['layered_mesh_preview'] = payload
    return payload


def _object_tree_payload(self, document):
    from geoai_simkit.app.panels import build_object_tree, object_tree_to_rows
    tree = build_object_tree(document)
    return {'tree': tree.to_dict(), 'rows': object_tree_to_rows(tree)}


def _property_panel_payload(self, document, selection=None):
    from geoai_simkit.app.panels import build_property_payload
    return build_property_payload(document, selection)


def _stage_editor_payload(self, document):
    from geoai_simkit.app.panels.stage_editor import build_stage_editor
    return build_stage_editor(document)


def _material_editor_payload(self, document):
    from geoai_simkit.app.panels.material_editor import build_material_editor
    return build_material_editor(document)


def _solver_compiler_payload(self, document, *, compile_now: bool = False):
    from geoai_simkit.app.panels.solver_compiler import build_solver_compiler
    return build_solver_compiler(document, compile_now=compile_now)


WorkbenchService.geo_project_document = _geo_project_document
WorkbenchService.engineering_document = _visual_engineering_document
WorkbenchService.stage_region_state = _stage_region_state
WorkbenchService.set_stage_region_state = _set_stage_region_state
WorkbenchService.set_block_material = _set_block_material
WorkbenchService.set_block_flags = _set_block_flags
WorkbenchService.set_mesh_global_size = _set_mesh_global_size
WorkbenchService.plan_document = _plan_document
WorkbenchService.run_document = _run_document
WorkbenchService.add_stage = _add_stage
WorkbenchService.clone_stage = _clone_stage
WorkbenchService.remove_stage = _remove_stage
WorkbenchService.set_stage_predecessor = _set_stage_predecessor
WorkbenchService.import_stl_geology = _import_stl_geology
WorkbenchService.import_borehole_csv_geology = _import_borehole_csv_geology
WorkbenchService.generate_layered_volume_mesh = _generate_layered_volume_mesh
WorkbenchService.layered_mesh_preview_payload = _layered_mesh_preview_payload
WorkbenchService.sync_geoproject_mesh_to_workbench_model = _sync_geoproject_mesh_to_workbench_model
WorkbenchService.object_tree_payload = _object_tree_payload
WorkbenchService.property_panel_payload = _property_panel_payload
WorkbenchService.stage_editor_payload = _stage_editor_payload
WorkbenchService.material_editor_payload = _material_editor_payload
WorkbenchService.solver_compiler_payload = _solver_compiler_payload


def _save_geoproject_document(self, document, path=None):
    project = self.geo_project_document(document)
    target = path or document.file_path or f'{document.case.name}.geoproject.json'
    saved = project.save_json(target)
    document.file_path = str(saved)
    document.dirty = False
    return saved


WorkbenchService.save_geoproject_document = _save_geoproject_document
