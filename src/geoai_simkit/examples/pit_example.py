from __future__ import annotations
from pathlib import Path
from geoai_simkit.pipeline.specs import AnalysisCaseSpec, BoundaryConditionSpec, ExcavationStepSpec, GeometrySource, InterfaceGeneratorSpec, MaterialAssignmentSpec, MeshAssemblySpec, MeshPreparationSpec, StructureGeneratorSpec

DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY = 'pit_rigid_box'

def _default_bcs():
    return (
        BoundaryConditionSpec('fix_bottom','displacement','bottom',(0,1,2),(0.0,0.0,0.0), {'preset_key': DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY}),
        BoundaryConditionSpec('fix_xmin','displacement','xmin',(0,),(0.0,), {'preset_key': DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY}),
        BoundaryConditionSpec('fix_xmax','displacement','xmax',(0,),(0.0,), {'preset_key': DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY}),
        BoundaryConditionSpec('fix_ymin','displacement','ymin',(1,),(0.0,), {'preset_key': DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY}),
        BoundaryConditionSpec('fix_ymax','displacement','ymax',(1,),(0.0,), {'preset_key': DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY}),
    )

def build_demo_case(*, smoke: bool = True) -> AnalysisCaseSpec:
    params = {'length': 24.0, 'width': 12.0, 'depth': 12.0, 'soil_depth': 20.0, 'nx': 3 if smoke else 8, 'ny': 2 if smoke else 6, 'nz': 2 if smoke else 6, 'wall_thickness': 0.6}
    return AnalysisCaseSpec(
        name='pit-demo', geometry=GeometrySource(kind='parametric_pit', parameters=params, metadata={'source':'parametric_pit'}), mesh=MeshAssemblySpec(element_family='auto', merge_points=True, keep_geometry_copy=True),
        material_library=(),
        materials=(MaterialAssignmentSpec(region_names=('soil_mass','soil_excavation_1','soil_excavation_2'), material_name='linear_elastic', parameters={'E':30e6,'nu':0.3,'rho':1800.0}), MaterialAssignmentSpec(region_names=('wall',), material_name='linear_elastic', parameters={'E':32e9,'nu':0.2,'rho':2500.0})),
        boundary_conditions=_default_bcs(),
        structures=(StructureGeneratorSpec(kind='demo_pit_supports'),), interfaces=(InterfaceGeneratorSpec(kind='demo_wall_interfaces', parameters={'interface_policy':'manual_like_nearest_soil'}),),
        mesh_preparation=MeshPreparationSpec(excavation_steps=(ExcavationStepSpec(name='wall_activation', activate_regions=('wall',), metadata={'stage_role':'support-install'}), ExcavationStepSpec(name='excavate_level_1', deactivate_regions=('soil_excavation_1',), metadata={'stage_role':'excavation'}), ExcavationStepSpec(name='excavate_level_2', deactivate_regions=('soil_excavation_2',), metadata={'stage_role':'excavation'}))),
        metadata={'source':'parametric_pit','demo_version':'0.8.36','boundary_preset': DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY, 'smoke_export_default': bool(smoke)},
    )

def build_demo_model():
    from geoai_simkit.pipeline.runner import GeneralFEMSolver
    return GeneralFEMSolver().prepare_case(build_demo_case(smoke=False)).model

def run_demo(out_dir: str | Path = 'exports', **kwargs) -> Path:
    out=Path(out_dir); out.mkdir(parents=True, exist_ok=True); p=out/'pit_demo_headless.txt'; p.write_text('Headless demo prepared.\n', encoding='utf-8'); return p


def build_block_workflow_demo_case(*, dimension: str = '3d', smoke: bool = True):
    from geoai_simkit.examples.block_pit_workflow import build_block_pit_case
    return build_block_pit_case(dimension=dimension, smoke=smoke)
