from geoai_simkit.solver import gpu_runtime
from geoai_simkit.solver.gpu_runtime import GpuDeviceInfo


def test_choose_cuda_device_respects_allowed_aliases(monkeypatch):
    devices = [
        GpuDeviceInfo(alias='cuda:0', name='GPU0', ordinal=0, memory_bytes=8 * 1024**3),
        GpuDeviceInfo(alias='cuda:1', name='GPU1', ordinal=1, memory_bytes=16 * 1024**3),
    ]
    monkeypatch.setattr(gpu_runtime, 'detect_cuda_devices', lambda: devices)
    assert gpu_runtime.choose_cuda_device('auto-best', allowed_aliases=['cuda:0']) == 'cuda:0'
    assert gpu_runtime.choose_cuda_device('auto-round-robin', round_robin_index=3, allowed_aliases=['cuda:1']) == 'cuda:1'


def test_describe_cuda_hardware_marks_selected(monkeypatch):
    devices = [
        GpuDeviceInfo(alias='cuda:0', name='GPU0', ordinal=0, memory_bytes=8 * 1024**3),
        GpuDeviceInfo(alias='cuda:1', name='GPU1', ordinal=1, memory_bytes=16 * 1024**3),
    ]
    monkeypatch.setattr(gpu_runtime, 'detect_cuda_devices', lambda: devices)
    text = gpu_runtime.describe_cuda_hardware(['cuda:1'])
    assert '[selected]' in text
    assert 'cuda:1' in text
