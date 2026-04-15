from geoai_simkit.core.model import AnalysisStage, SimulationModel
from geoai_simkit.solver.staging import StageManager


class DummyMesh:
    def cast_to_unstructured_grid(self):
        return self


def test_stage_manager_honors_activation_map_metadata() -> None:
    model = SimulationModel(name='x', mesh=DummyMesh())
    model.add_material('soil', 'linear_elastic', E=1.0, nu=0.2)
    model.add_material('wall', 'linear_elastic', E=1.0, nu=0.2)
    model.add_stage(AnalysisStage(name='initial', metadata={'activation_map': {'soil': True, 'wall': True}}))
    model.add_stage(AnalysisStage(name='excavate', metadata={'activation_map': {'soil': False, 'wall': True}}))
    contexts = StageManager(model).iter_stages()
    assert contexts[0].active_regions == {'soil', 'wall'}
    assert contexts[1].active_regions == {'wall'}
