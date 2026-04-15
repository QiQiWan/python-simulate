from __future__ import annotations

from pathlib import Path

from geoai_simkit.app.boundary_presets import DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY, build_boundary_conditions_from_preset
from geoai_simkit.core.model import SimulationModel
from geoai_simkit.geometry.demo_pit import build_demo_stages, configure_demo_coupling
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.post.exporters import ExportManager
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.warp_backend import WarpBackend


def build_demo_model() -> SimulationModel:
    scene = ParametricPitScene(length=24.0, width=12.0, depth=12.0, soil_depth=20.0, nx=8, ny=6, nz=6, wall_thickness=0.6)
    model = SimulationModel(name='pit-demo', mesh=scene.build())
    model.metadata.update({
        'source': 'parametric_pit',
        'demo_version': '0.1.36',
        'boundary_preset': DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY,
        'parametric_scene': {
            'length': scene.length,
            'width': scene.width,
            'depth': scene.depth,
            'soil_depth': scene.soil_depth,
            'nx': scene.nx,
            'ny': scene.ny,
            'nz': scene.nz,
            'wall_thickness': scene.wall_thickness,
        },
    })
    model.ensure_regions()
    soil_regions = [name for name in ('soil_mass', 'soil_excavation_1', 'soil_excavation_2') if model.get_region(name) is not None]
    for region_name in soil_regions:
        model.add_material(region_name, 'mohr_coulomb', E=30e6, nu=0.3, cohesion=15e3, friction_deg=28.0, dilation_deg=0.0, tensile_strength=0.0, rho=1800.0)
    if model.get_region('wall') is not None:
        model.add_material('wall', 'linear_elastic', E=32e9, nu=0.2, rho=2500.0)
    model.metadata['demo_interface_auto_policy'] = 'manual_like_nearest_soil'
    wall_mode = configure_demo_coupling(model, prefer_wall_solver=True, auto_supports=True, interface_policy='manual_like_nearest_soil')
    model.boundary_conditions.extend(build_boundary_conditions_from_preset(DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY))
    model.stages = build_demo_stages(model, wall_active=(wall_mode in {'auto_interface', 'plaxis_like_auto'}))
    return model


def run_demo(out_dir: str | Path = 'exports') -> Path:
    out_dir = Path(out_dir)
    model = build_demo_model()
    solved = WarpBackend().solve(model, SolverSettings(prefer_sparse=True, line_search=True, max_cutbacks=5))
    out = out_dir / 'pit_demo.vtu'
    exporter = ExportManager()
    exporter.export_model(solved, out)
    exporter.export_stage_series(solved, out_dir / 'pit_demo_bundle', stem='pit_demo')
    return out
