from geoai_simkit.solver.compute_preferences import BackendComputePreferences


def test_compute_preferences_emit_selected_gpu_metadata():
    prefs = BackendComputePreferences(device='auto-best', selected_gpu_aliases=('cuda:0', 'cuda:1'))
    meta = prefs.to_metadata(cuda_available=True)
    assert meta['allowed_gpu_devices'] == ['cuda:0', 'cuda:1']
    summary = prefs.summary(cpu_total=8, cuda_available=True)
    assert 'selected_gpus=2' in summary
