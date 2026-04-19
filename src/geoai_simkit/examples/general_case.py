from __future__ import annotations

from geoai_simkit.app.boundary_presets import DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY, build_boundary_conditions_from_preset
from geoai_simkit.core.model import MaterialDefinition
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.pipeline import AnalysisCaseSpec, ExcavationStepSpec, GeneralFEMSolver, GeometrySource, InterfaceGeneratorSpec, MaterialAssignmentSpec, MeshAssemblySpec, MeshPreparationSpec, StructureGeneratorSpec
from geoai_simkit.solver.base import SolverSettings


def build_general_excavation_case() -> AnalysisCaseSpec:
    scene = ParametricPitScene(length=24.0, width=12.0, depth=12.0, soil_depth=20.0, nx=8, ny=6, nz=6, wall_thickness=0.6)
    params = {'length': scene.length, 'width': scene.width, 'depth': scene.depth, 'soil_depth': scene.soil_depth, 'nx': scene.nx, 'ny': scene.ny, 'nz': scene.nz, 'wall_thickness': scene.wall_thickness}
    return AnalysisCaseSpec(
        name='general-excavation-case',
        geometry=GeometrySource(kind='parametric_pit', parameters=params, metadata={'source': 'parametric_pit'}),
        mesh=MeshAssemblySpec(element_family='auto', merge_points=True),
        material_library=(
            MaterialDefinition(name='soil_mc', model_type='mohr_coulomb', parameters={'E': 30e6, 'nu': 0.3, 'cohesion': 15e3, 'friction_deg': 28.0, 'rho': 1800.0}),
            MaterialDefinition(name='wall_linear', model_type='linear_elastic', parameters={'E': 32e9, 'nu': 0.2, 'rho': 2500.0}),
        ),
        materials=(
            MaterialAssignmentSpec(region_names=('soil_mass', 'soil_excavation_1', 'soil_excavation_2'), material_name='mohr_coulomb', parameters={'E': 30e6, 'nu': 0.3, 'cohesion': 15e3, 'friction_deg': 28.0, 'rho': 1800.0}),
            MaterialAssignmentSpec(region_names=('wall',), material_name='linear_elastic', parameters={'E': 32e9, 'nu': 0.2, 'rho': 2500.0}),
        ),
        boundary_conditions=tuple(build_boundary_conditions_from_preset(DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY)),
        structures=(StructureGeneratorSpec(kind='demo_pit_supports'),),
        mesh_preparation=MeshPreparationSpec(excavation_steps=(ExcavationStepSpec(name='wall_activation', deactivate_regions=(), activate_regions=('wall',), metadata={'stage_role': 'support-install'}), ExcavationStepSpec(name='excavate_level_1', deactivate_regions=('soil_excavation_1',), metadata={'stage_role': 'excavation'}), ExcavationStepSpec(name='excavate_level_2', deactivate_regions=('soil_excavation_2',), metadata={'stage_role': 'excavation'}))),
        metadata={'parametric_scene': params},
    )


def solve_general_excavation_case(settings: SolverSettings | None = None):
    return GeneralFEMSolver().solve_case(build_general_excavation_case(), settings or SolverSettings())
