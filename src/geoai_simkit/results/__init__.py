from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
import json

if TYPE_CHECKING:
    from geoai_simkit.core.types import ResultField


@dataclass(slots=True)
class ResultDatabase:
    model_name: str
    fields: list[ResultField] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def stage_names(self) -> list[str]:
        names: list[str] = []
        for field in self.fields:
            if field.stage and field.stage not in names:
                names.append(str(field.stage))
        for row in list(self.metadata.get("stage_metrics", []) or []):
            name = str(row.get("stage_name") or row.get("stage") or "")
            if name and name not in names:
                names.append(name)
        return names

    def field_labels(self) -> list[str]:
        labels: list[str] = []
        for field in self.fields:
            label = field.name if field.stage is None else f"{field.name}@{field.stage}"
            if label not in labels:
                labels.append(label)
        return labels

    def stage_metric_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in list(self.metadata.get("stage_metrics", []) or [])]


@dataclass(slots=True)
class StageResultRecord:
    """Compact per-stage result summary used by GUI and package exporters.

    Older GUI modules imported this public symbol directly from
    ``geoai_simkit.results``.  v0.8.37 accidentally removed the export while the
    startup path still expected it.  Keep the record small and dependency-light
    so GUI startup does not pull in heavy result backends.
    """

    stage_name: str
    field_count: int = 0
    max_wall_horizontal_displacement: float | None = None
    max_surface_settlement: float | None = None
    active_block_count: int | None = None
    inactive_block_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stage_name": self.stage_name,
            "field_count": int(self.field_count),
            "max_wall_horizontal_displacement": self.max_wall_horizontal_displacement,
            "max_surface_settlement": self.max_surface_settlement,
            "active_block_count": self.active_block_count,
            "inactive_block_count": self.inactive_block_count,
        }
        payload.update(dict(self.metadata or {}))
        return payload


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def stage_result_records_from_model(model: Any) -> list[StageResultRecord]:
    """Build stage records from a solved model without requiring package files."""
    metadata = getattr(model, "metadata", {}) or {}
    metric_rows = list(metadata.get("stage_result_metrics", []) or metadata.get("foundation_pit.stage_metrics", []) or [])
    fields = list(getattr(model, "results", []) or [])
    records: list[StageResultRecord] = []
    if metric_rows:
        for row in metric_rows:
            stage_name = str(row.get("stage_name") or row.get("stage") or "stage")
            records.append(
                StageResultRecord(
                    stage_name=stage_name,
                    field_count=sum(1 for field in fields if getattr(field, "stage", None) == stage_name),
                    max_wall_horizontal_displacement=_optional_float(
                        row.get("max_wall_horizontal_displacement")
                        or row.get("wall_horizontal_displacement")
                        or row.get("max_wall_dx")
                    ),
                    max_surface_settlement=_optional_float(
                        row.get("max_surface_settlement")
                        or row.get("surface_settlement")
                        or row.get("max_settlement")
                    ),
                    active_block_count=_optional_int(row.get("active_block_count")),
                    inactive_block_count=_optional_int(row.get("inactive_block_count")),
                    metadata=dict(row),
                )
            )
        return records
    stage_names: list[str] = []
    for field in fields:
        stage = getattr(field, "stage", None)
        if stage and stage not in stage_names:
            stage_names.append(str(stage))
    return [
        StageResultRecord(
            stage_name=name,
            field_count=sum(1 for field in fields if getattr(field, "stage", None) == name),
        )
        for name in stage_names
    ]


def build_result_database(model: Any) -> ResultDatabase:
    metadata_obj = getattr(model, "metadata", {}) or {}
    metrics = list(metadata_obj.get("stage_result_metrics", []) or metadata_obj.get("foundation_pit.stage_metrics", []) or [])
    metadata = {
        "stage_asset_count": len(getattr(model, "stages", []) or []),
        "stage_metrics": metrics,
        "stage_linear_system_plans": [],
        "stage_linear_system_diagnostics_count": int(metadata_obj.get("solver.stage_result_metric_count", 0) or 0),
        "linear_system_diagnostics_summary": {"backend": metadata_obj.get("solver.backend", "not_run")},
        "interface_request_count": len(metadata_obj.get("foundation_pit.interface_requests", []) or []),
        "contact_pair_count": len(metadata_obj.get("foundation_pit.contact_pairs", []) or []),
    }
    return ResultDatabase(model_name=str(getattr(model, "name", "model")), fields=list(getattr(model, "results", []) or []), metadata=metadata)


def build_result_database_from_runtime_store(runtime_store: Any) -> ResultDatabase:
    model = getattr(runtime_store, "model", runtime_store)
    return build_result_database(model)


def build_stage_package_gui_payload(package_path: str | Path) -> dict[str, Any]:
    path = Path(package_path)
    manifest = path / "manifest.json" if path.is_dir() else path
    payload: dict[str, Any] = {"available": False, "package_dir": str(path), "manifest_path": str(manifest)}
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        stage_rows = list(data.get("stage_rows") or data.get("stage_metrics") or [])
        field_rows = list(data.get("field_rows") or [])
        payload.update({
            "available": True,
            "case_name": data.get("case_name"),
            "format": data.get("format", "json"),
            "stage_count": len(stage_rows),
            "field_count": len(field_rows),
            "stage_rows": stage_rows,
            "field_rows": field_rows,
        })
    else:
        payload.update({"stage_count": 0, "field_count": 0, "stage_rows": [], "field_rows": []})
    for key in (
        "contact_panel",
        "release_panel",
        "release_load_panel",
        "geostatic_panel",
        "initial_stress_panel",
        "nonlinear_panel",
        "nonlinear_material_residual_panel",
        "solver_balance_panel",
        "solver_acceptance_panel",
        "preview_panel",
        "gui_index",
    ):
        payload.setdefault(key, {})
    return payload


__all__ = [
    "ResultDatabase",
    "StageResultRecord",
    "stage_result_records_from_model",
    "build_result_database",
    "build_result_database_from_runtime_store",
    "build_stage_package_gui_payload",
    "ResultFieldRecord",
    "StageResult",
    "ResultPackage",
    "result_package_from_stage_metrics",
]

try:
    from geoai_simkit.results.result_package import ResultFieldRecord, StageResult, ResultPackage, result_package_from_stage_metrics
except Exception:  # pragma: no cover - keep GUI startup resilient
    ResultFieldRecord = StageResult = ResultPackage = None  # type: ignore
    def result_package_from_stage_metrics(*args, **kwargs):  # type: ignore
        raise RuntimeError("Result package module is unavailable")
