from __future__ import annotations

from pathlib import Path

from geoai_simkit.app.boundary_presets import DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY, build_boundary_conditions_from_preset
from geoai_simkit.core.model import MaterialDefinition, SimulationModel
from geoai_simkit.examples.demo_runtime import build_demo_solver_settings
from geoai_simkit.geometry.demo_pit import build_demo_stages, configure_demo_coupling
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.pipeline import AnalysisCaseSpec, ExcavationStepSpec, GeneralFEMSolver, GeometrySource, InterfaceGeneratorSpec, MaterialAssignmentSpec, MeshAssemblySpec, MeshPreparationSpec, StructureGeneratorSpec
from geoai_simkit.post.exporters import ExportManager
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.warp_backend import WarpBackend


def build_demo_case() -> AnalysisCaseSpec:
    scene = ParametricPitScene(length=24.0, width=12.0, depth=12.0, soil_depth=20.0, nx=8, ny=6, nz=6, wall_thickness=0.6)
    params = {'length': scene.length, 'width': scene.width, 'depth': scene.depth, 'soil_depth': scene.soil_depth, 'nx': scene.nx, 'ny': scene.ny, 'nz': scene.nz, 'wall_thickness': scene.wall_thickness}
    return AnalysisCaseSpec(
        name='pit-demo',
        geometry=GeometrySource(kind='parametric_pit', parameters=params, metadata={'source': 'parametric_pit'}),
        mesh=MeshAssemblySpec(element_family='auto', merge_points=True, keep_geometry_copy=True),
        material_library=(
            MaterialDefinition(name='soil_mc', model_type='mohr_coulomb', parameters={'E': 30e6, 'nu': 0.3, 'cohesion': 15e3, 'friction_deg': 28.0, 'dilation_deg': 0.0, 'tensile_strength': 0.0, 'rho': 1800.0}),
            MaterialDefinition(name='wall_linear', model_type='linear_elastic', parameters={'E': 32e9, 'nu': 0.2, 'rho': 2500.0}),
        ),
        materials=(
            MaterialAssignmentSpec(region_names=('soil_mass', 'soil_excavation_1', 'soil_excavation_2'), material_name='mohr_coulomb', parameters={'E': 30e6, 'nu': 0.3, 'cohesion': 15e3, 'friction_deg': 28.0, 'dilation_deg': 0.0, 'tensile_strength': 0.0, 'rho': 1800.0}),
            MaterialAssignmentSpec(region_names=('wall',), material_name='linear_elastic', parameters={'E': 32e9, 'nu': 0.2, 'rho': 2500.0}),
        ),
        boundary_conditions=tuple(build_boundary_conditions_from_preset(DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY)),
        structures=(StructureGeneratorSpec(kind='demo_pit_supports'),),
        interfaces=(InterfaceGeneratorSpec(kind='demo_wall_interfaces', parameters={'interface_policy': 'manual_like_nearest_soil'}),),
        mesh_preparation=MeshPreparationSpec(excavation_steps=(
            ExcavationStepSpec(name='wall_activation', deactivate_regions=(), activate_regions=('wall',), metadata={'stage_role': 'support-install'}),
            ExcavationStepSpec(name='excavate_level_1', deactivate_regions=('soil_excavation_1',), metadata={'stage_role': 'excavation'}),
            ExcavationStepSpec(name='excavate_level_2', deactivate_regions=('soil_excavation_2',), metadata={'stage_role': 'excavation'}),
        )),
        metadata={'source': 'parametric_pit', 'demo_version': '0.6.1', 'boundary_preset': DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY, 'parametric_scene': params, 'demo_interface_auto_policy': 'manual_like_nearest_soil'},
    )


def build_demo_model() -> SimulationModel:
    prepared = GeneralFEMSolver(backend=WarpBackend()).prepare_case(build_demo_case())
    model = prepared.model
    model.metadata['pipeline.demo_prepared'] = True
    wall_mode = configure_demo_coupling(model, prefer_wall_solver=True, auto_supports=True, interface_policy='manual_like_nearest_soil')
    model.stages = build_demo_stages(model, wall_active=(wall_mode in {'auto_interface', 'plaxis_like_auto'}))
    return model


def run_demo(out_dir: str | Path = 'exports', *, solver_settings: SolverSettings | None = None, execution_profile: str = 'auto', device: str | None = None) -> Path:
    out_dir = Path(out_dir)
    model = build_demo_model()
    settings = solver_settings or build_demo_solver_settings(execution_profile, device=device)
    solved = WarpBackend().solve(model, settings)
    out = out_dir / 'pit_demo.vtu'
    exporter = ExportManager()
    exporter.export_model(solved, out)
    exporter.export_stage_series(solved, out_dir / 'pit_demo_bundle', stem='pit_demo')
    return out
