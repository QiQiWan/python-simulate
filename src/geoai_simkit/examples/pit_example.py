from __future__ import annotations

from pathlib import Path

from geoai_simkit.core.model import AnalysisStage, BoundaryCondition, LoadDefinition, SimulationModel
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.post.exporters import ExportManager
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.warp_backend import WarpBackend


def build_demo_model() -> SimulationModel:
    scene = ParametricPitScene(length=24.0, width=12.0, depth=12.0, soil_depth=20.0, nx=8, ny=6, nz=6, wall_thickness=0.6)
    model = SimulationModel(name="pit-demo", mesh=scene.build())
    model.ensure_regions()
    model.add_material("soil", "mohr_coulomb", E=30e6, nu=0.3, cohesion=15e3, friction_deg=28.0, rho=1800.0)
    model.add_material("wall", "linear_elastic", E=32e9, nu=0.2, rho=2500.0)
    model.add_boundary_condition(BoundaryCondition(name="fix_bottom", kind="displacement", target="bottom", components=(0, 1, 2), values=(0.0, 0.0, 0.0)))
    model.add_stage(AnalysisStage(name="initial", steps=1))
    model.add_stage(AnalysisStage(name="excavate_level_1", deactivate_regions=(), steps=1))
    model.add_stage(AnalysisStage(name="excavate_level_2", steps=1, loads=(LoadDefinition(name="crest_load", kind="point_force", target="all", values=(0.0, 0.0, -1000.0)),)))
    return model


def run_demo(out_dir: str | Path = "exports") -> Path:
    out_dir = Path(out_dir)
    model = build_demo_model()
    solved = WarpBackend().solve(model, SolverSettings(prefer_sparse=True, line_search=True, max_cutbacks=5))
    out = out_dir / "pit_demo.vtu"
    exporter = ExportManager()
    exporter.export_model(solved, out)
    exporter.export_stage_series(solved, out_dir / "pit_demo_bundle", stem="pit_demo")
    return out
