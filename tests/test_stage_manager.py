from geoai_simkit.core.model import AnalysisStage, SimulationModel
from geoai_simkit.solver.staging import StageManager


class DummyMesh:
    def cast_to_unstructured_grid(self):
        return self


def test_stage_manager_default_and_activation() -> None:
    model = SimulationModel(name="x", mesh=DummyMesh())
    model.add_material("soil", "linear_elastic", E=1.0, nu=0.2)
    model.add_stage(AnalysisStage(name="s1", activate_regions=("wall",)))
    model.add_stage(AnalysisStage(name="s2", deactivate_regions=("soil",)))
    contexts = StageManager(model).iter_stages()
    assert contexts[0].stage.name == "s1"
    assert "wall" in contexts[0].active_regions
    assert "soil" in contexts[0].active_regions
    assert "soil" not in contexts[1].active_regions
