from __future__ import annotations

from geoai_simkit.env_check import DependencyCheck, format_environment_report


def test_environment_report_includes_actions():
    report = format_environment_report([
        DependencyCheck(name='gmsh', installed=False, detail='libGLU.so.1: cannot open shared object file', group='meshing', status='broken', action='Python package is present, but the host is missing libGLU.so.1 / Mesa OpenGL runtime libraries.'),
    ])
    assert '[actions]' in report
    assert 'libGLU.so.1' in report
