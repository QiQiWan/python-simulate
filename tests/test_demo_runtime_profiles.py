from __future__ import annotations

from geoai_simkit.examples.demo_runtime import build_demo_runtime_plan, build_demo_solver_settings


def test_auto_profile_without_cuda(monkeypatch):
    monkeypatch.setattr('geoai_simkit.examples.demo_runtime.detect_cuda_devices', lambda: [])
    plan = build_demo_runtime_plan('auto')
    assert plan.profile == 'cpu-robust'
    assert plan.device == 'cpu'
    assert plan.metadata['warp_nonlinear_enabled'] is False


def test_gpu_profile_with_cuda(monkeypatch):
    monkeypatch.setattr('geoai_simkit.examples.demo_runtime.detect_cuda_devices', lambda: [object()])
    plan = build_demo_runtime_plan('gpu', device='cuda:0')
    assert plan.profile == 'gpu'
    assert plan.device == 'cuda:0'
    assert plan.metadata['compute_profile'] == 'auto'


def test_demo_solver_settings_uses_plan(monkeypatch):
    monkeypatch.setattr('geoai_simkit.examples.demo_runtime.detect_cuda_devices', lambda: [])
    settings = build_demo_solver_settings('auto')
    assert settings.device == 'cpu'
    assert settings.metadata['demo_execution_profile'] == 'cpu-robust'
