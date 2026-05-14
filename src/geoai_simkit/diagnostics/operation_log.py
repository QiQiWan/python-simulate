from __future__ import annotations

"""Low-overhead operation logging for production geometry-kernel validation.

Logging is disabled by default.  Set ``GEOAI_SIMKIT_GEOMETRY_DEBUG=1`` or pass
``enabled=True`` to capture JSONL records.  When debug logging is enabled and
no directory is supplied, records are written to ``./log/geometry_kernel.jsonl``.
The code avoids importing optional meshers and keeps disabled-mode overhead to a
single boolean check.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Mapping

JsonMap = Mapping[str, object]

_TRUE_VALUES = {"1", "true", "yes", "on", "debug"}


def geometry_debug_enabled() -> bool:
    value = os.getenv("GEOAI_SIMKIT_GEOMETRY_DEBUG") or os.getenv("GEOAI_SIMKIT_DEBUG") or ""
    return value.strip().lower() in _TRUE_VALUES




def default_geometry_log_dir(cwd: str | Path | None = None) -> str:
    """Return the default local debug log directory.

    GUI/CLI debug mode intentionally uses a repository/current-working-directory
    ``log`` folder so users can enable diagnostics with a command-line flag only,
    without manually exporting environment variables.
    """

    base = Path(cwd) if cwd is not None else Path.cwd()
    return str((base / "log").resolve())


def configure_geometry_operation_logging(
    *,
    enabled: bool = True,
    debug_dir: str | Path | None = None,
    cwd: str | Path | None = None,
    set_environment: bool = True,
) -> dict[str, object]:
    """Configure geometry-operation logging for the current process.

    This helper is used by GUI launchers and CLI commands.  It keeps logging
    disabled by default, but when users pass ``--debug`` it sets the same process
    environment variables that lower-level geometry kernels already understand.
    """

    resolved_dir = str(Path(debug_dir).resolve()) if debug_dir else default_geometry_log_dir(cwd)
    if enabled:
        Path(resolved_dir).mkdir(parents=True, exist_ok=True)
    if set_environment:
        if enabled:
            os.environ["GEOAI_SIMKIT_GEOMETRY_DEBUG"] = "1"
            os.environ["GEOAI_SIMKIT_DEBUG"] = "1"
            os.environ["GEOAI_SIMKIT_GEOMETRY_LOG_DIR"] = resolved_dir
        else:
            os.environ.pop("GEOAI_SIMKIT_GEOMETRY_DEBUG", None)
            os.environ.pop("GEOAI_SIMKIT_DEBUG", None)
            # Do not remove GEOAI_SIMKIT_GEOMETRY_LOG_DIR when disabling: users may
            # have provided it explicitly for a later manual debug run.
    return {
        "enabled": bool(enabled),
        "debug_dir": resolved_dir,
        "stream_name": "geometry_kernel",
        "log_path": str(Path(resolved_dir) / "geometry_kernel.jsonl"),
        "metadata": {"contract": "geometry_operation_logging_config_v1"},
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class GeometryOperationLogRecord:
    operation: str
    status: str
    started_at: str
    finished_at: str
    elapsed_ms: float
    input_state: JsonMap = field(default_factory=dict)
    output_state: JsonMap = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    error: str = ""
    debug_files: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_ms": float(self.elapsed_ms),
            "input_state": dict(self.input_state),
            "output_state": dict(self.output_state),
            "diagnostics": list(self.diagnostics),
            "error": self.error,
            "debug_files": list(self.debug_files),
            "metadata": {"contract": "geometry_operation_log_record_v1", **dict(self.metadata)},
        }


@dataclass(slots=True)
class GeometryOperationLogger:
    enabled: bool | None = None
    debug_dir: str | None = None
    stream_name: str = "geometry_kernel"

    def __post_init__(self) -> None:
        if self.enabled is None:
            self.enabled = geometry_debug_enabled()
        if self.debug_dir is None:
            self.debug_dir = os.getenv("GEOAI_SIMKIT_GEOMETRY_LOG_DIR") or (default_geometry_log_dir() if bool(self.enabled) else "")

    @property
    def active(self) -> bool:
        return bool(self.enabled)

    def record(
        self,
        operation: str,
        *,
        status: str,
        started_at: str,
        start_counter: float,
        input_state: JsonMap | None = None,
        output_state: JsonMap | None = None,
        diagnostics: tuple[str, ...] = (),
        error: str = "",
        debug_files: tuple[str, ...] = (),
        metadata: JsonMap | None = None,
    ) -> GeometryOperationLogRecord | None:
        if not self.active:
            return None
        finished = _utc_now()
        elapsed_ms = (time.perf_counter() - start_counter) * 1000.0
        record = GeometryOperationLogRecord(
            operation=operation,
            status=status,
            started_at=started_at,
            finished_at=finished,
            elapsed_ms=elapsed_ms,
            input_state=dict(input_state or {}),
            output_state=dict(output_state or {}),
            diagnostics=tuple(str(item) for item in diagnostics),
            error=str(error or ""),
            debug_files=tuple(str(item) for item in debug_files),
            metadata=dict(metadata or {}),
        )
        self._write(record)
        return record

    def _write(self, record: GeometryOperationLogRecord) -> None:
        if not self.debug_dir:
            return
        path = Path(self.debug_dir)
        path.mkdir(parents=True, exist_ok=True)
        log_path = path / f"{self.stream_name}.jsonl"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def log_geometry_operation(
    operation: str,
    *,
    enabled: bool | None = None,
    debug_dir: str | None = None,
    input_state: JsonMap | None = None,
    output_state: JsonMap | None = None,
    status: str = "ok",
    diagnostics: tuple[str, ...] = (),
    error: str = "",
    debug_files: tuple[str, ...] = (),
    metadata: JsonMap | None = None,
    start_counter: float | None = None,
    started_at: str | None = None,
) -> GeometryOperationLogRecord | None:
    logger = GeometryOperationLogger(enabled=enabled, debug_dir=debug_dir)
    return logger.record(
        operation,
        status=status,
        started_at=started_at or _utc_now(),
        start_counter=start_counter if start_counter is not None else time.perf_counter(),
        input_state=input_state,
        output_state=output_state,
        diagnostics=diagnostics,
        error=error,
        debug_files=debug_files,
        metadata=metadata,
    )


def geometry_log_status() -> dict[str, object]:
    enabled = geometry_debug_enabled()
    debug_dir = os.getenv("GEOAI_SIMKIT_GEOMETRY_LOG_DIR") or (default_geometry_log_dir() if enabled else default_geometry_log_dir())
    return {
        "enabled": enabled,
        "debug_dir": debug_dir,
        "log_path": str(Path(debug_dir) / "geometry_kernel.jsonl"),
        "stream_name": "geometry_kernel",
        "metadata": {"contract": "geometry_log_status_v1", "contract_version": "geometry_log_status_v2"},
    }
