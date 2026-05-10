from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json

import numpy as np

from geoai_simkit.results import StageResultRecord, build_result_database, stage_result_records_from_model


@dataclass(slots=True)
class StageResultPackageSummary:
    """Summary of an exported stage-result package."""

    package_dir: str
    manifest_path: str
    case_name: str
    stage_count: int
    field_count: int
    engineering_valid: bool = True
    stage_rows: list[dict[str, Any]] = field(default_factory=list)
    field_rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return str(value)


def _field_row(field: Any) -> dict[str, Any]:
    values = np.asarray(getattr(field, "values", []), dtype=float)
    finite = values[np.isfinite(values)] if values.size else values
    row: dict[str, Any] = {
        "name": str(getattr(field, "name", "field")),
        "stage": getattr(field, "stage", None),
        "association": str(getattr(field, "association", "unknown")),
        "components": int(getattr(field, "components", 1) or 1),
        "value_count": int(values.size),
        "metadata": dict(getattr(field, "metadata", {}) or {}),
    }
    if finite.size:
        row.update({"min": float(np.min(finite)), "max": float(np.max(finite)), "mean": float(np.mean(finite))})
    return row


def export_stage_result_package(model: Any, out_dir: str | Path) -> StageResultPackageSummary:
    """Export a lightweight JSON result package for GUI result browsing.

    The package intentionally avoids VTU/HDF5 dependencies. It writes a stable
    manifest that the Results page can read to show stage metrics, field names,
    wall displacement and surface settlement indicators.
    """
    package_dir = Path(out_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    db = build_result_database(model)
    records: list[StageResultRecord] = stage_result_records_from_model(model)
    stage_rows = [record.to_dict() for record in records]
    field_rows = [_field_row(field) for field in db.fields]
    manifest = {
        "format": "geoai-stage-result-package-v1",
        "case_name": db.model_name,
        "stage_count": len(stage_rows),
        "field_count": len(field_rows),
        "engineering_valid": True,
        "stage_rows": stage_rows,
        "stage_metrics": stage_rows,
        "field_rows": field_rows,
        "metadata": dict(db.metadata),
    }
    manifest_path = package_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    return StageResultPackageSummary(
        package_dir=str(package_dir),
        manifest_path=str(manifest_path),
        case_name=db.model_name,
        stage_count=len(stage_rows),
        field_count=len(field_rows),
        engineering_valid=True,
        stage_rows=stage_rows,
        field_rows=field_rows,
    )


__all__ = ["StageResultPackageSummary", "export_stage_result_package"]
