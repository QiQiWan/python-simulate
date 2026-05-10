from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass(slots=True)
class ProjectLifecycleManager:
    """Autosave/recovery helper for the GUI shell.

    It stores source-entity level case snapshots only.  Mesh and result arrays are
    deliberately not treated as editable state; they are regenerated or reloaded
    from result packages.
    """

    app_name: str = "geoai_simkit"

    def build_autosave_manifest(self, case_payload: dict[str, Any], *, root_dir: str | Path | None = None, retention: int = 10) -> dict[str, Any]:
        autosave_id = f"autosave_{_now_id()}"
        root = Path(root_dir) if root_dir is not None else Path(".geoai_autosave")
        return {
            "contract": "project_autosave_manifest_v1",
            "autosave_id": autosave_id,
            "root_dir": str(root),
            "retention": int(retention),
            "editable_state_only": True,
            "mesh_editable": False,
            "case_name": str(case_payload.get("name") or case_payload.get("case_name") or "Untitled"),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "payload_keys": sorted(str(k) for k in case_payload.keys()),
        }

    def write_autosave(self, case_payload: dict[str, Any], *, root_dir: str | Path | None = None, retention: int = 10) -> dict[str, Any]:
        manifest = self.build_autosave_manifest(case_payload, root_dir=root_dir, retention=retention)
        root = Path(str(manifest["root_dir"]))
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{manifest['autosave_id']}.json"
        data = {"manifest": manifest, "case": case_payload}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        entries = sorted(root.glob("autosave_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in entries[int(retention):]:
            try:
                old.unlink()
            except OSError:
                pass
        manifest["path"] = str(path)
        manifest["retained_count"] = min(len(entries), int(retention))
        return manifest

    def recovery_index(self, *, root_dir: str | Path | None = None) -> dict[str, Any]:
        root = Path(root_dir) if root_dir is not None else Path(".geoai_autosave")
        rows: list[dict[str, Any]] = []
        if root.exists():
            for path in sorted(root.glob("autosave_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    manifest = dict(data.get("manifest", {}) or {})
                except Exception:
                    manifest = {"autosave_id": path.stem, "error": "Could not read autosave file."}
                manifest["path"] = str(path)
                rows.append(manifest)
        return {"contract": "project_recovery_index_v1", "root_dir": str(root), "recovery_available": bool(rows), "rows": rows}
