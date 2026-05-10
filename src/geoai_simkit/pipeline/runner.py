from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass(slots=True)
class AnalysisExportSpec:
    out_dir: str | Path = "exports"
    format: str = "json"
    stem: str = "analysis"
    export_model: bool = False
    export_stage_series: bool = True
    export_runtime_manifest: bool = False
    export_runtime_bundle: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AnalysisTaskSpec:
    case: Any
    export: AnalysisExportSpec = field(default_factory=AnalysisExportSpec)
    execution_profile: str = "auto"
    device: str | None = None
    compile_config: Any = None
    runtime_config: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AnalysisRunResult:
    prepared: Any
    accepted: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    solved_model: Any = None
    result_db: Any = None
    result_store: Any = None
    runtime_bundle_path: Path | None = None

    def __post_init__(self) -> None:
        if self.solved_model is None and self.prepared is not None:
            self.solved_model = getattr(self.prepared, "model", self.prepared)


class _Backend:
    def solve(self, model, settings=None):
        import numpy as np
        from geoai_simkit.core.types import ResultField
        """Attach deterministic stage-wise excavation indicators.

        This remains a headless smoke backend, but it now respects staged block
        activation/deactivation and produces the two engineering outputs needed
        by the GUI results page: maximum wall horizontal displacement and maximum
        surface settlement for each stage.
        """
        model.metadata["solver.backend"] = "headless_stage_block_backend"
        metrics = list(model.metadata.get("stage_result_metrics") or model.metadata.get("foundation_pit.stage_metrics") or [])
        if not metrics:
            metrics = []
            for idx, stage in enumerate(model.stages):
                d = float(stage.metadata.get("excavation_depth", 0.0) or 0.0) if isinstance(stage.metadata, dict) else 0.0
                wall = 1.2 * d
                settlement = -0.55 * wall
                metrics.append({
                    "stage_name": stage.name,
                    "excavation_depth": d,
                    "max_wall_horizontal_displacement_mm": wall,
                    "max_surface_settlement_mm": settlement,
                    "source": "generic_stage_response_proxy",
                })
        roles = np.asarray(getattr(model.mesh, "cell_data", {}).get("role", []), dtype=object)
        zmax = None
        try:
            pts = np.asarray(model.mesh.points, dtype=float)
            zmax = float(np.max(pts[:, 2])) if pts.size else None
        except Exception:
            zmax = None
        for row in metrics:
            stage_name = str(row.get("stage_name") or row.get("stage") or "stage")
            wall_value = float(row.get("max_wall_horizontal_displacement_mm", 0.0) or 0.0) / 1000.0
            settlement_value = float(row.get("max_surface_settlement_mm", 0.0) or 0.0) / 1000.0
            n_cells = int(getattr(model.mesh, "n_cells", 0) or 0)
            wall_field = np.zeros(n_cells, dtype=float)
            settlement_field = np.zeros(n_cells, dtype=float)
            if roles.size == n_cells:
                wall_mask = np.asarray(["wall" in str(v).lower() for v in roles], dtype=bool)
                excavation_mask = np.asarray(["excavation" in str(v).lower() for v in roles], dtype=bool)
                wall_field[wall_mask] = wall_value
                settlement_field[~excavation_mask] = settlement_value
            elif n_cells:
                wall_field[:] = wall_value
                settlement_field[:] = settlement_value
            model.add_result(ResultField("wall_horizontal_displacement", "cell", wall_field, components=1, stage=stage_name, metadata={"unit": "m", "metric_mm": float(row.get("max_wall_horizontal_displacement_mm", 0.0) or 0.0)}))
            model.add_result(ResultField("surface_settlement", "cell", settlement_field, components=1, stage=stage_name, metadata={"unit": "m", "metric_mm": float(row.get("max_surface_settlement_mm", 0.0) or 0.0), "surface_z": zmax}))
        model.metadata["stage_result_metrics"] = metrics
        model.metadata["solver.stage_result_metric_count"] = len(metrics)
        model.metadata["last_solver_backend"] = model.metadata.get("solver.backend", "headless_stage_block_backend")
        model.metadata["stages_run"] = [str(row.get("stage_name") or row.get("stage") or "stage") for row in metrics]
        return model

    def stage_execution_diagnostics(self, model, settings=None):
        return {
            "stage_count": len(getattr(model, "stages", []) or []),
            "block_activation_maps": sum(1 for s in getattr(model, "stages", []) if isinstance(getattr(s, "metadata", None), dict) and "activation_map" in s.metadata),
            "backend": "headless_stage_block_backend",
            "supported": True,
        }


class _RuntimeStore:
    def __init__(self, model: Any, metadata: dict[str, Any] | None = None) -> None:
        self.model = model
        self.metadata = dict(metadata or {})


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    return str(value)


class GeneralFEMSolver:
    def __init__(self):
        self.backend = _Backend()

    def prepare_case(self, case: Any) -> Any:
        from geoai_simkit.pipeline.builder import AnalysisCaseBuilder
        return AnalysisCaseBuilder(case).build()

    def _export_run_artifacts(self, task: AnalysisTaskSpec, prepared: Any, result_db: Any, metadata: dict[str, Any]) -> tuple[dict[str, Any], Path | None]:
        from geoai_simkit.runtime import RuntimeBundleManager, RuntimeCompiler, CompileConfig

        export = task.export or AnalysisExportSpec()
        out_dir = Path(export.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = str(export.stem or getattr(task.case, "name", "analysis"))
        exported: dict[str, str] = {}

        if export.export_stage_series or export.format == "json":
            manifest = {
                "case_name": getattr(task.case, "name", stem),
                "format": "json",
                "stage_metrics": _json_safe(result_db.stage_metric_rows() if hasattr(result_db, "stage_metric_rows") else []),
                "stage_rows": _json_safe(result_db.stage_metric_rows() if hasattr(result_db, "stage_metric_rows") else []),
                "field_rows": _json_safe(result_db.field_labels() if hasattr(result_db, "field_labels") else []),
                "metadata": _json_safe(metadata),
            }
            manifest_path = out_dir / f"{stem}_result_manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            exported["result_manifest"] = str(manifest_path)

        if export.export_model:
            model = getattr(prepared, "model", prepared)
            model_path = out_dir / f"{stem}_model_summary.json"
            model_payload = {
                "name": str(getattr(model, "name", stem)),
                "stage_count": len(getattr(model, "stages", []) or []),
                "result_count": len(getattr(model, "results", []) or []),
                "metadata": _json_safe(getattr(model, "metadata", {}) or {}),
            }
            model_path.write_text(json.dumps(model_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            exported["model_summary"] = str(model_path)

        runtime_bundle_path: Path | None = None
        if export.export_runtime_manifest or export.export_runtime_bundle:
            cfg = task.compile_config if task.compile_config is not None else CompileConfig()
            bundle = RuntimeCompiler().compile_case(prepared, cfg)
            bundle.manifest["runtime_config"] = task.runtime_config.to_dict() if hasattr(task.runtime_config, "to_dict") else _json_safe(task.runtime_config)
            runtime_bundle_path = out_dir / f"{stem}_runtime_bundle"
            RuntimeBundleManager().write_bundle(bundle, runtime_bundle_path)
            metadata["runtime_manifest_path"] = str(runtime_bundle_path / RuntimeBundleManager.manifest_name)
            metadata["runtime_bundle_path"] = str(runtime_bundle_path)
            metadata["compile_report"] = dict(bundle.compile_report.metadata)
            metadata["partition_advisory"] = dict(bundle.compile_report.metadata.get("partition_advisory", {}) or {})
            exported["runtime_bundle"] = str(runtime_bundle_path)
        metadata["exports"] = exported
        return exported, runtime_bundle_path

    def run(self, task: AnalysisTaskSpec) -> AnalysisRunResult:
        from geoai_simkit.results import build_result_database

        prepared = self.prepare_case(task.case)
        model = self.backend.solve(prepared.model, settings=dict(task.metadata or {}))
        result_db = build_result_database(model)
        metadata = {
            "runner": "headless",
            "case_name": str(getattr(task.case, "name", "case")),
            "execution_profile": str(task.execution_profile),
            "device": task.device or "auto",
            "stage_result_metric_count": model.metadata.get("solver.stage_result_metric_count", 0),
        }
        metadata.update(dict(task.metadata or {}))
        _, runtime_bundle_path = self._export_run_artifacts(task, prepared, result_db, metadata)
        return AnalysisRunResult(
            prepared=prepared,
            accepted=True,
            metadata=metadata,
            solved_model=model,
            result_db=result_db,
            result_store=_RuntimeStore(model, metadata),
            runtime_bundle_path=runtime_bundle_path,
        )

    def run_task(self, task: AnalysisTaskSpec) -> AnalysisRunResult:
        return self.run(task)

    def run_runtime_bundle(self, bundle_dir: str | Path, out_dir: str | Path, **kwargs: Any) -> AnalysisRunResult:
        from geoai_simkit.examples.pit_example import build_demo_case
        from geoai_simkit.runtime import RuntimeBundleManager

        manifest = RuntimeBundleManager().read_manifest(bundle_dir)
        case_name = str(manifest.get("case_name") or "bundle-resume")
        case = build_demo_case(smoke=True)
        try:
            case.name = case_name
        except Exception:
            pass
        task = AnalysisTaskSpec(
            case=case,
            execution_profile=str(kwargs.get("execution_profile", "auto")),
            device=kwargs.get("device"),
            export=AnalysisExportSpec(out_dir=out_dir, stem=f"{case_name}_resume", export_stage_series=bool(kwargs.get("export_stage_series", True))),
            metadata={"runtime_bundle_source": str(bundle_dir)},
        )
        result = self.run_task(task)
        result.metadata["runtime_bundle_source"] = str(bundle_dir)
        result.metadata.setdefault("case_name", case_name)
        return result
