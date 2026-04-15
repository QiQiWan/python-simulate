from geoai_simkit.solver.compute_preferences import BackendComputePreferences, recommended_compute_preferences


def test_recommended_gpu_profile_enables_gpu_path_when_cuda_available():
    prefs = recommended_compute_preferences('gpu-fullpath', cuda_available=True, cpu_total=16)
    meta = prefs.to_metadata(cuda_available=True)
    assert prefs.device == 'auto-best'
    assert meta['require_warp'] is True
    assert meta['warp_full_gpu_linear_solve'] is True
    assert meta['warp_gpu_global_assembly'] is True


def test_cpu_safe_profile_disables_gpu_specific_paths():
    prefs = recommended_compute_preferences('cpu-safe', cuda_available=False, cpu_total=12)
    meta = prefs.to_metadata(cuda_available=False)
    assert prefs.resolved_device(False) == 'cpu'
    assert meta['require_warp'] is False
    assert meta['warp_hex8_enabled'] is False
    assert meta['preconditioner'] == 'block-jacobi'


def test_preferences_summary_mentions_threads_and_device():
    prefs = BackendComputePreferences(device='auto-best', thread_count=0, preconditioner='auto', ordering='auto')
    summary = prefs.summary(cpu_total=8, cuda_available=True)
    assert 'device=cuda:0' in summary
    assert 'cpu_threads=7' in summary
