from pathlib import Path

from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.pipeline import GeneralFEMSolver, build_execution_plan, build_solver_settings
from geoai_simkit.runtime import RuntimeBundleManager, RuntimeCompiler
from geoai_simkit.solver.gpu_runtime import describe_cuda_hardware, detect_cuda_devices
from geoai_simkit.app.job_service import JobService


def test_runtime_compile_and_bundle_manifest(tmp_path: Path):
    case = build_demo_case(smoke=True)
    solver = GeneralFEMSolver()
    prepared = solver.prepare_case(case)
    plan = build_execution_plan("cpu-debug", tolerance=2.5e-5)
    bundle = RuntimeCompiler().compile_case(prepared, plan.compile_config)
    bundle_dir = RuntimeBundleManager().write_bundle(bundle, tmp_path / "bundle")

    manifest = RuntimeBundleManager().read_manifest(bundle_dir)
    assert manifest["kind"] == "geoai-runtime-bundle"
    assert manifest["compile_report"]["partition_count"] == 1


def test_solver_settings_preserves_plan_policy_and_cpu_gpu_probe_is_conservative():
    settings = build_solver_settings("cpu-debug", tolerance=3.0e-5, max_cutbacks=7)
    assert settings.tolerance == 3.0e-5
    assert settings.max_cutbacks <= 2
    assert settings.device == "cpu"
    assert detect_cuda_devices() == []
    assert describe_cuda_hardware()["available"] is False


def test_job_service_plan_case_uses_runtime_contract():
    summary = JobService().plan_case(build_demo_case(smoke=True), execution_profile="cpu-debug")
    assert summary.profile == "cpu-debug"
    assert summary.metadata["backend_routing"]["resolved_backend"] in {"linear-algebra-bridge", "distributed", "native"}
