from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.pipeline import AnalysisCaseValidator, StageSpec


def test_validator_flags_missing_and_cyclic_stage_predecessors():
    spec = build_demo_case()
    spec.stages = (
        StageSpec(name='s1', predecessor='missing'),
        StageSpec(name='s2', predecessor='s2'),
    )
    report = AnalysisCaseValidator(spec).validate()
    codes = {issue.code for issue in report.issues}
    assert 'stage_predecessor_missing' in codes
    assert 'stage_predecessor_self' in codes


def test_validator_detects_stage_graph_cycle():
    spec = build_demo_case()
    spec.stages = (
        StageSpec(name='a', predecessor='c'),
        StageSpec(name='b', predecessor='a'),
        StageSpec(name='c', predecessor='b'),
    )
    report = AnalysisCaseValidator(spec).validate()
    codes = {issue.code for issue in report.issues}
    assert 'stage_graph_cycle' in codes
    assert report.ok is False
