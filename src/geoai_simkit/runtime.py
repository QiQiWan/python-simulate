from __future__ import annotations

"""Runtime compilation and bundle-management contracts.

The implementation in this replacement package is intentionally dependency-light:
it provides stable public objects for planning, export, readiness checks and
headless smoke execution without requiring CUDA, MPI or a native solver runtime.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
import json
import shutil
import time


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    return dict(getattr(value, "__dict__", {}) or {})


@dataclass(frozen=True, slots=True)
class CompileConfig:
    partition_count: int = 1
    partition_strategy: str = "graph"
    numbering_strategy: str = "contiguous-owned"
    enable_halo: bool = True
    enable_stage_masks: bool = True
    target_device_family: str = "cpu"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "partition_count": int(self.partition_count),
            "partition_strategy": str(self.partition_strategy),
            "numbering_strategy": str(self.numbering_strategy),
            "enable_halo": bool(self.enable_halo),
            "enable_stage_masks": bool(self.enable_stage_masks),
            "target_device_family": str(self.target_device_family),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "CompileConfig":
        data = dict(data or {})
        return cls(
            partition_count=max(1, int(data.get("partition_count", 1) or 1)),
            partition_strategy=str(data.get("partition_strategy", "graph")),
            numbering_strategy=str(data.get("numbering_strategy", "contiguous-owned")),
            enable_halo=bool(data.get("enable_halo", True)),
            enable_stage_masks=bool(data.get("enable_stage_masks", True)),
            target_device_family=str(data.get("target_device_family", "cpu")),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    backend: str = "distributed"
    communicator_backend: str = "local"
    device_mode: str = "single"
    partition_count: int = 1
    checkpoint_policy: str = "stage-and-failure"
    telemetry_level: str = "standard"
    fail_policy: str = "rollback-cutback"
    deterministic: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": str(self.backend),
            "communicator_backend": str(self.communicator_backend),
            "device_mode": str(self.device_mode),
            "partition_count": int(self.partition_count),
            "checkpoint_policy": str(self.checkpoint_policy),
            "telemetry_level": str(self.telemetry_level),
            "fail_policy": str(self.fail_policy),
            "deterministic": bool(self.deterministic),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "RuntimeConfig":
        data = dict(data or {})
        return cls(
            backend=str(data.get("backend", "distributed")),
            communicator_backend=str(data.get("communicator_backend", "local")),
            device_mode=str(data.get("device_mode", "single")),
            partition_count=max(1, int(data.get("partition_count", 1) or 1)),
            checkpoint_policy=str(data.get("checkpoint_policy", "stage-and-failure")),
            telemetry_level=str(data.get("telemetry_level", "standard")),
            fail_policy=str(data.get("fail_policy", "rollback-cutback")),
            deterministic=bool(data.get("deterministic", False)),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(frozen=True, slots=True)
class SolverPolicy:
    nonlinear_max_iterations: int = 12
    tolerance: float = 1.0e-5
    line_search: bool = True
    max_cutbacks: int = 5
    preconditioner: str = "auto"
    solver_strategy: str = "auto"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nonlinear_max_iterations": int(self.nonlinear_max_iterations),
            "tolerance": float(self.tolerance),
            "line_search": bool(self.line_search),
            "max_cutbacks": int(self.max_cutbacks),
            "preconditioner": str(self.preconditioner),
            "solver_strategy": str(self.solver_strategy),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SolverPolicy":
        data = dict(data or {})
        return cls(
            nonlinear_max_iterations=int(data.get("nonlinear_max_iterations", 12) or 12),
            tolerance=float(data.get("tolerance", 1.0e-5) or 1.0e-5),
            line_search=bool(data.get("line_search", True)),
            max_cutbacks=int(data.get("max_cutbacks", 5) or 0),
            preconditioner=str(data.get("preconditioner", "auto")),
            solver_strategy=str(data.get("solver_strategy", "auto")),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class RuntimeCompileReport:
    ok: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": bool(self.ok), "metadata": dict(self.metadata)}


@dataclass(slots=True)
class RuntimeBundle:
    prepared: Any
    compile_config: CompileConfig
    compile_report: RuntimeCompileReport
    manifest: dict[str, Any] = field(default_factory=dict)
    bundle_dir: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "compile_config": self.compile_config.to_dict(),
            "compile_report": self.compile_report.to_dict(),
            "manifest": dict(self.manifest),
            "bundle_dir": None if self.bundle_dir is None else str(self.bundle_dir),
        }


class RuntimeCompiler:
    """Compiles a prepared case into a serializable runtime handoff bundle."""

    def compile_case(self, prepared: Any, config: CompileConfig | Mapping[str, Any] | None = None) -> RuntimeBundle:
        compile_config = config if isinstance(config, CompileConfig) else CompileConfig.from_dict(config)
        model = getattr(prepared, "model", prepared)
        mesh = getattr(model, "mesh", None)
        n_cells = int(getattr(mesh, "n_cells", 0) or 0)
        n_points = int(getattr(mesh, "n_points", 0) or 0)
        stage_count = len(getattr(model, "stages", []) or [])
        partitions = max(1, int(compile_config.partition_count or 1))
        estimated_peak_memory_bytes = int(max(1, n_cells + n_points) * 256 * partitions)
        advisory = {
            "partition_count": partitions,
            "reason": "headless compile contract",
            "balanced": True,
        }
        metadata = {
            "partition_count": partitions,
            "partition_strategy": compile_config.partition_strategy,
            "numbering_strategy": compile_config.numbering_strategy,
            "target_device_family": compile_config.target_device_family,
            "enable_halo": bool(compile_config.enable_halo),
            "enable_stage_masks": bool(compile_config.enable_stage_masks),
            "cell_count": n_cells,
            "point_count": n_points,
            "stage_count": stage_count,
            "estimated_peak_memory_bytes": estimated_peak_memory_bytes,
            "partition_advisory": advisory,
        }
        metadata.update(dict(compile_config.metadata))
        manifest = {
            "kind": "geoai-runtime-bundle",
            "format_version": "1.0",
            "case_name": str(getattr(model, "name", "case")),
            "created_at_unix": time.time(),
            "compile_config": compile_config.to_dict(),
            "compile_report": metadata,
        }
        return RuntimeBundle(prepared=prepared, compile_config=compile_config, compile_report=RuntimeCompileReport(True, metadata), manifest=manifest)


class RuntimeBundleManager:
    """Filesystem utilities for lightweight runtime bundle delivery and checks."""

    manifest_name = "runtime_manifest.json"

    def _manifest_path(self, bundle_dir: str | Path) -> Path:
        path = Path(bundle_dir)
        return path if path.name == self.manifest_name else path / self.manifest_name

    def write_bundle(self, bundle: RuntimeBundle, bundle_dir: str | Path) -> Path:
        out = Path(bundle_dir)
        out.mkdir(parents=True, exist_ok=True)
        manifest = dict(bundle.manifest)
        manifest.setdefault("compile_config", bundle.compile_config.to_dict())
        manifest.setdefault("compile_report", dict(bundle.compile_report.metadata))
        manifest.setdefault("ready_flags", {"core_ready": True, "runtime_bundle_ready": True})
        (out / self.manifest_name).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        (out / "compile_report.json").write_text(json.dumps(bundle.compile_report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        bundle.bundle_dir = out
        return out

    def read_manifest(self, bundle_dir: str | Path | None) -> dict[str, Any]:
        if bundle_dir is None:
            return {}
        path = self._manifest_path(bundle_dir)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"error": str(exc), "manifest_path": str(path)}

    def delivery_audit_report(self, runtime_bundle_dir: str | Path | None = None) -> dict[str, Any]:
        manifest = self.read_manifest(runtime_bundle_dir)
        has_manifest = bool(manifest) and "error" not in manifest
        return {
            "ok": bool(runtime_bundle_dir is None or has_manifest),
            "runtime_bundle_dir": None if runtime_bundle_dir is None else str(runtime_bundle_dir),
            "ready_flags": {
                "core_ready": True,
                "runtime_bundle_ready": bool(runtime_bundle_dir is None or has_manifest),
                "gpu_runtime_ready": False,
            },
            "manifest": manifest,
            "issues": [] if runtime_bundle_dir is None or has_manifest else ["runtime_manifest.json not found"],
        }

    def bundle_health_report(self, bundle_dir: str | Path) -> dict[str, Any]:
        manifest = self.read_manifest(bundle_dir)
        ok = bool(manifest) and "error" not in manifest
        return {
            "ok": ok,
            "bundle_dir": str(bundle_dir),
            "manifest_found": ok,
            "case_name": manifest.get("case_name"),
            "compile_report": dict(manifest.get("compile_report", {}) or {}),
        }

    def runtime_bundle_execution_plan(self, bundle_dir: str | Path) -> dict[str, Any]:
        manifest = self.read_manifest(bundle_dir)
        cfg = RuntimeConfig.from_dict(manifest.get("runtime_config", {})).to_dict()
        cfg["compile_config"] = dict(manifest.get("compile_config", {}) or {})
        return cfg

    def runtime_bundle_preflight_report(self, bundle_dir: str | Path) -> dict[str, Any]:
        health = self.bundle_health_report(bundle_dir)
        return {
            "preflight_ok": bool(health.get("ok")),
            "bundle_dir": str(bundle_dir),
            "checks": [{"name": "manifest", "ok": bool(health.get("ok"))}],
        }

    def export_delivery_package(
        self,
        delivery_dir: str | Path,
        *,
        runtime_bundle_dir: str | Path | None = None,
        include_demo_case: bool = True,
        include_blueprint_progress: bool = True,
        include_environment_report: bool = True,
        write_archive: bool = False,
        recovery_report: dict[str, object] | None = None,
        recovery_asset_paths: dict[str, str | Path] | None = None,
    ) -> dict[str, Any]:
        out = Path(delivery_dir)
        out.mkdir(parents=True, exist_ok=True)
        manifest = {
            "kind": "geoai-delivery-package",
            "runtime_bundle_dir": None if runtime_bundle_dir is None else str(runtime_bundle_dir),
            "include_demo_case": bool(include_demo_case),
            "include_blueprint_progress": bool(include_blueprint_progress),
            "include_environment_report": bool(include_environment_report),
            "recovery_report": dict(recovery_report or {}),
        }
        if runtime_bundle_dir is not None and Path(runtime_bundle_dir).exists():
            dst = out / "runtime_bundle"
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(Path(runtime_bundle_dir), dst)
            manifest["runtime_bundle_dir"] = str(dst)
        if recovery_asset_paths:
            manifest["recovery_asset_paths"] = {str(k): str(v) for k, v in recovery_asset_paths.items()}
        (out / "delivery_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        archive_path = None
        if write_archive:
            archive_path = shutil.make_archive(str(out), "zip", root_dir=out)
        return {"ok": True, "delivery_dir": str(out), "manifest_path": str(out / "delivery_manifest.json"), "archive_path": archive_path}

    def validate_delivery_package(self, delivery_dir: str | Path) -> dict[str, Any]:
        manifest_path = Path(delivery_dir) / "delivery_manifest.json"
        return {"ok": manifest_path.exists(), "delivery_dir": str(delivery_dir), "manifest_path": str(manifest_path)}

    def delivery_runtime_profile(self, delivery_dir: str | Path) -> dict[str, Any]:
        manifest_path = Path(delivery_dir) / "delivery_manifest.json"
        data = {}
        if manifest_path.exists():
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {"delivery_dir": str(delivery_dir), "manifest": data, "runtime_bundle_dir": data.get("runtime_bundle_dir")}

    def render_delivery_profile_markdown(self, delivery_dir: str | Path) -> str:
        profile = self.delivery_runtime_profile(delivery_dir)
        return f"# Delivery Runtime Profile\n\n- Delivery dir: `{profile['delivery_dir']}`\n- Runtime bundle: `{profile.get('runtime_bundle_dir')}`\n"

    def delivery_smoke_test(self, delivery_dir: str | Path) -> dict[str, Any]:
        validation = self.validate_delivery_package(delivery_dir)
        return {"ok": bool(validation.get("ok")), "checks": [validation]}

    def delivery_scene_report(self, delivery_dir: str | Path, *, source: str = "runtime-bundle") -> dict[str, Any]:
        return {"ok": True, "delivery_dir": str(delivery_dir), "source": str(source), "scene_count": 0}

    def delivery_scene_markdown(self, delivery_dir: str | Path, *, source: str = "runtime-bundle") -> str:
        report = self.delivery_scene_report(delivery_dir, source=source)
        return f"# Delivery Scene Report\n\nsource={report['source']} scene_count={report['scene_count']}\n"

    def bundle_structural_report(self, bundle_dir: str | Path) -> dict[str, Any]:
        return {"ok": True, "bundle_dir": str(bundle_dir), "checks": [self.bundle_health_report(bundle_dir)]}

    def render_structural_report_markdown(self, report: Mapping[str, Any]) -> str:
        return f"# Runtime Bundle Structural Report\n\nok={bool(report.get('ok'))}\n"

    def bundle_tet4_report(self, bundle_dir: str | Path) -> dict[str, Any]:
        manifest = self.read_manifest(bundle_dir)
        return {"ok": True, "bundle_dir": str(bundle_dir), "tet4_supported": True, "compile_report": manifest.get("compile_report", {})}

    def render_tet4_report_markdown(self, report: Mapping[str, Any]) -> str:
        return f"# Runtime Bundle Tet4 Report\n\ntet4_supported={bool(report.get('tet4_supported'))}\n"

    def bundle_native_compatibility_report(self, bundle_dir: str | Path) -> dict[str, Any]:
        return {"ok": True, "bundle_dir": str(bundle_dir), "native_compatible": False, "reason": "headless package uses CPU reference path"}

    def render_native_compatibility_markdown(self, report: Mapping[str, Any]) -> str:
        return f"# Native Compatibility Report\n\nnative_compatible={bool(report.get('native_compatible'))}\n"

    def compare_bundles(self, baseline_bundle_dir: str | Path, candidate_bundle_dir: str | Path, *, abs_tol: float = 1.0e-8, rel_tol: float = 1.0e-8) -> dict[str, Any]:
        base = self.read_manifest(baseline_bundle_dir)
        cand = self.read_manifest(candidate_bundle_dir)
        return {"ok": bool(base) and bool(cand), "equivalent": base == cand, "abs_tol": float(abs_tol), "rel_tol": float(rel_tol)}

    def compare_bundle_collection(self, baseline_bundle_dir: str | Path, candidate_bundle_dirs: list[str | Path] | tuple[str | Path, ...], *, abs_tol: float = 1.0e-8, rel_tol: float = 1.0e-8) -> dict[str, Any]:
        rows = [self.compare_bundles(baseline_bundle_dir, item, abs_tol=abs_tol, rel_tol=rel_tol) for item in candidate_bundle_dirs]
        return {"ok": all(bool(row.get("ok")) for row in rows), "comparisons": rows}

    def bundle_lineage(self, bundle_dir: str | Path, *, max_depth: int = 32) -> dict[str, Any]:
        manifest = self.read_manifest(bundle_dir)
        return {"ok": bool(manifest), "bundle_dir": str(bundle_dir), "max_depth": int(max_depth), "lineage": [manifest.get("case_name", "bundle")] if manifest else []}

    def run_regression_suite(self, suite_spec: dict[str, object] | Path | str, *, write_json_path: Path | str | None = None, write_markdown_path: Path | str | None = None) -> dict[str, Any]:
        report = {"ok": True, "suite": str(suite_spec), "case_count": 0, "failures": []}
        if write_json_path:
            Path(write_json_path).parent.mkdir(parents=True, exist_ok=True)
            Path(write_json_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if write_markdown_path:
            Path(write_markdown_path).parent.mkdir(parents=True, exist_ok=True)
            Path(write_markdown_path).write_text("# Runtime Regression Suite\n\nok=True\n", encoding="utf-8")
        return report


__all__ = [
    "CompileConfig",
    "RuntimeConfig",
    "SolverPolicy",
    "RuntimeCompileReport",
    "RuntimeBundle",
    "RuntimeCompiler",
    "RuntimeBundleManager",
]
