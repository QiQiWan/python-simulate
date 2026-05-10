from __future__ import annotations
from typing import Any, TYPE_CHECKING
from geoai_simkit.app.workspace_aliases import CANONICAL_FEM_PAGES as PAGE_ORDER, FEM_PAGE_TO_LEGACY_SPACE as LEGACY_SPACE_FOR_PAGE, compatibility_alias_rows
from geoai_simkit.fem.api import get_core_fem_api_contracts
from geoai_simkit.app.completion_matrix import build_completion_matrix
if TYPE_CHECKING:
    from geoai_simkit.app.workbench import WorkbenchDocument

PAGE_LABELS = {'modeling':'Modeling','mesh':'Mesh','solve':'Solve','results':'Results','benchmark':'Benchmark','advanced':'Advanced'}

def _action(key: str, label: str, target: str, enabled: bool = True, **meta: Any) -> dict[str, Any]:
    return {'key': key, 'label': label, 'target': target, 'enabled': bool(enabled), 'metadata': dict(meta)}

def _panel(key: str, title: str, rows: list[list[Any]], actions: list[dict[str, Any]] | None = None, **meta: Any) -> dict[str, Any]:
    return {'key': key, 'title': title, 'rows': rows, 'actions': list(actions or []), 'metadata': dict(meta)}

def _operation(key: str, title: str, inputs: list[str], outputs: list[str], status: str = 'ready') -> dict[str, Any]:
    return {'key': key, 'title': title, 'status': status, 'inputs': inputs, 'outputs': outputs}

def build_fem_workflow_pages(document: 'WorkbenchDocument') -> dict[str, dict[str, Any]]:
    from geoai_simkit.app.geoproject_source import get_geoproject_document, geoproject_summary
    from geoai_simkit.app.panels.material_editor import build_geoproject_material_editor
    from geoai_simkit.app.panels.stage_editor import build_geoproject_stage_editor
    from geoai_simkit.app.panels.solver_compiler import build_geoproject_solver_compiler

    project = get_geoproject_document(document)
    summary = geoproject_summary(project)
    validation = document.validation
    results = document.results
    completion = build_completion_matrix()
    contracts = get_core_fem_api_contracts()
    contract_by_key = {c['key']: c for c in contracts}
    counts = dict(summary.get('counts', {}) or {})
    material_editor = build_geoproject_material_editor(project)
    stage_editor = build_geoproject_stage_editor(project)
    solver_compiler = build_geoproject_solver_compiler(project)
    common = {'page_contract': 'fem_operation_page_v4_geoproject', 'case_name': document.case.name, 'data_source': 'GeoProjectDocument'}

    modeling = {
        **common, 'key': 'modeling', 'label': 'Modeling', 'legacy_space_alias': 'project',
        'headline': 'Modeling operation page',
        'summary': 'Create and edit the complete GeoProjectDocument: soil, geometry, topology, structures, materials and stages.',
        'panels': [
            _panel('soil_model','Soil model', [['Soil contour', project.soil_model.soil_contour.name], ['Boreholes', counts.get('boreholes', 0)], ['Layer surfaces', len(project.soil_model.soil_layer_surfaces)], ['Soil clusters', counts.get('soil_clusters', 0)], ['Water conditions', len(project.soil_model.water_conditions)]], [_action('edit_boreholes','Edit boreholes','geoproject.soil.boreholes'), _action('edit_water','Edit water conditions','geoproject.soil.water')]),
            _panel('geometry_model','Geometry model', [['Points', counts.get('points', 0)], ['Curves', counts.get('curves', 0)], ['Surfaces', counts.get('surfaces', 0)], ['Volumes', counts.get('volumes', 0)], ['Parametric features', len(project.geometry_model.parametric_features)]], [_action('create_volume','Create/split volume','geoproject.geometry.volume'), _action('review_topology','Review topology','geoproject.topology.review')]),
            _panel('structure_model','Structure model', [['Plates', counts.get('plates', 0)], ['Beams', counts.get('beams', 0)], ['Embedded beams', len(project.structure_model.embedded_beams)], ['Anchors', counts.get('anchors', 0)], ['Structural interfaces', len(project.structure_model.structural_interfaces)]], [_action('add_wall_plate','Add wall/plate','geoproject.structure.plate'), _action('add_support','Add support beam/anchor','geoproject.structure.support')]),
            _panel('material_stage_editor','Material and stage editors', [['Material records', counts.get('materials', 0)], ['Assignments', len(material_editor['assignments'])], ['Phases', len(stage_editor['phases'])], ['Active phase', project.phase_manager.active_phase_id]], [_action('assign_material','Assign material','geoproject.material.assign'), _action('add_phase','Add phase','geoproject.phase.add')]),
        ],
        'operations': [_operation('edit_geoproject_document','Edit project document',['user operation'],['GeoProjectDocument diff']), _operation('rebuild_topology','Rebuild topology relations',['geometry/soil/structure'],['ownership','adjacency','contact','generated-by'])],
        'api': [contract_by_key['geometry'], contract_by_key['material']],
        'material_editor': material_editor,
        'stage_editor': stage_editor,
    }

    mesh_doc = project.mesh_model.mesh_document
    mesh = {
        **common, 'key':'mesh','label':'Mesh','legacy_space_alias':'model',
        'headline': 'Mesh operation page', 'summary': 'Generate and audit GeoProjectDocument.MeshModel with entity maps and quality reports.',
        'panels': [
            _panel('mesh_settings','Mesh settings', [['Element family', project.mesh_model.mesh_settings.element_family], ['Global size', project.mesh_model.mesh_settings.global_size], ['Preserve interfaces', project.mesh_model.mesh_settings.preserve_interfaces], ['Conformal blocks', project.mesh_model.mesh_settings.conformal_blocks]], [_action('set_global_size','Set global size','geoproject.mesh.global_size')]),
            _panel('mesh_document','Mesh document', [['Nodes', 0 if mesh_doc is None else mesh_doc.node_count], ['Cells', 0 if mesh_doc is None else mesh_doc.cell_count], ['Mapped volumes', len(project.mesh_model.mesh_entity_map.block_to_cells)], ['Quality report', bool(project.mesh_model.quality_report)]], [_action('generate_mesh','Generate mesh','geoproject.mesh.generate'), _action('quality_gate','Run quality gate','geoproject.mesh.quality')]),
            _panel('contact_interface_preview','Contact/interface preview', [['Contact candidates', counts.get('contact_candidates', 0)], ['Structural interfaces', len(project.structure_model.structural_interfaces)], ['Interface materials', len(project.material_library.interface_materials)]], [_action('materialize_interfaces','Materialize interfaces','geoproject.interface.materialize')]),
        ],
        'operations': [_operation('mesh_volumes','Mesh document volumes',['GeometryModel.Volumes','MeshSettings'],['MeshDocument','MeshEntityMap']), _operation('detect_contacts','Detect block contacts',['TopologyGraph'],['contact/interface candidates'])],
        'api': [contract_by_key['mesh'], contract_by_key['assembly']],
    }

    solve = {
        **common, 'key':'solve','label':'Solve','legacy_space_alias':'solve','headline':'Solve operation page',
        'summary':'Compile GeoProjectDocument.PhaseManager snapshots into SolverModel.CompiledPhaseModels.',
        'panels': [
            _panel('pre_solve_gate','Pre-solve gate', [['Framework validation', summary.get('ok')], ['Missing snapshots', len(solver_compiler['compile_readiness']['missing_snapshots'])], ['Boundary conditions', len(project.solver_model.boundary_conditions)], ['Loads', len(project.solver_model.loads)]], [_action('validate','Validate GeoProjectDocument','geoproject.validate'), _action('compile','Compile phase models','geoproject.solver.compile')]),
            _panel('runtime_settings','Runtime settings', [['Backend', project.solver_model.runtime_settings.backend], ['Nonlinear strategy', project.solver_model.runtime_settings.nonlinear_strategy], ['Linear solver', project.solver_model.runtime_settings.linear_solver], ['GPU', project.solver_model.runtime_settings.use_gpu], ['Precision', project.solver_model.runtime_settings.precision]], [_action('edit_runtime','Edit runtime settings','geoproject.solver.runtime')]),
            _panel('compiled_models','Compiled phase models', [['Compiled phases', len(project.solver_model.compiled_phase_models)], ['Phase inputs', len(solver_compiler['phase_inputs'])], ['Mesh cells', solver_compiler['compile_readiness']['mesh_cell_count']]], [_action('run_solver','Run solver','geoproject.solver.run', summary.get('ok', False))]),
        ],
        'operations': [_operation('compile_phase_snapshots','Compile phase snapshots',['PhaseStateSnapshots','BoundaryConditions','Loads'],['CompiledPhaseModels']), _operation('launch_runtime','Launch runtime',['CompiledPhaseModels','RuntimeSettings'],['ResultStore'])],
        'api': [contract_by_key['assembly'], contract_by_key['solver']],
        'solver_compiler': solver_compiler,
    }

    result_page = {
        **common, 'key':'results','label':'Results','legacy_space_alias':'results','headline':'Results operation page',
        'summary':'Browse ResultStore phase results, engineering metrics, curves, sections and reports.',
        'panels': [_panel('result_store','Result store', [['Phase results', counts.get('phase_results', 0)], ['Engineering metrics', counts.get('engineering_metrics', 0)], ['Curves', len(project.result_store.curves)], ['Sections', len(project.result_store.sections)], ['Reports', len(project.result_store.reports)], ['Legacy overview loaded', results is not None]], [_action('compare_stage','Compare stages','geoproject.results.compare'), _action('export','Export reports','geoproject.results.export')])],
        'operations': [_operation('load_result_store','Load/refresh ResultStore',['solver output'],['PhaseResults','EngineeringMetrics','Curves']), _operation('stage_wall_settlement_metrics','Show wall displacement and settlement by phase',['EngineeringMetrics'],['control metrics']), _operation('export_figures','Export figures/tables',['Curves','Sections'],['image/table artifacts'])],
        'api': [contract_by_key['result']],
    }

    benchmark = {
        **common, 'key':'benchmark','label':'Benchmark','legacy_space_alias':'diagnostics','headline':'Benchmark operation page',
        'summary':'Run smoke tests and regenerate the completion matrix from artifacts.',
        'panels': [
            _panel('benchmark_runner','Benchmark runner', [['Benchmark source', completion.get('benchmark_results',{}).get('source','not_run')], ['Benchmark passed', f"{completion.get('benchmark_results',{}).get('passed_count',0)}/{completion.get('benchmark_results',{}).get('benchmark_count',0)}"]], [_action('run_benchmarks','Run solver benchmarks','benchmark.run_solver_benchmarks')]),
            _panel('geoproject_smoke','GeoProjectDocument smoke', [['Data source', 'GeoProjectDocument'], ['Framework ok', summary.get('ok')], ['Compiled phases', counts.get('compiled_phase_models', 0)]], [_action('run_geoproject_smoke','Run GeoProjectDocument smoke','benchmark.run_geoproject_gui_smoke')]),
        ],
        'operations': [_operation('core_smoke','Run module numerical smoke',['core modules'],['core_fem_smoke_results.json']), _operation('geoproject_gui_smoke','Run GUI datasource smoke',['GeoProjectDocument'],['geoproject_gui_datasource_smoke.json'])],
        'api': list(completion.get('core_fem', [])),
    }

    advanced = {
        **common, 'key':'advanced','label':'Advanced','legacy_space_alias':'delivery','headline':'Advanced operation page',
        'summary':'Capability-gated GPU/OCC/UQ functions and compatibility aliases.',
        'panels': [_panel('advanced_capabilities','Advanced capabilities', [[r.get('key'), r.get('status')] for r in completion.get('advanced', [])]), _panel('compatibility_aliases','Compatibility aliases', [[r['legacy_space'], '→', r['canonical_space']] for r in compatibility_alias_rows()])],
        'operations': [_operation('probe_gpu','Probe GPU native runtime',['runtime environment'],['capability report'], 'capability_gated'), _operation('occ_persistent_naming','OCC persistent naming bridge',['BRep topology'],['naming history'], 'capability_gated')],
        'api': list(completion.get('advanced', [])),
    }
    return {'modeling': modeling, 'mesh': mesh, 'solve': solve, 'results': result_page, 'benchmark': benchmark, 'advanced': advanced}
