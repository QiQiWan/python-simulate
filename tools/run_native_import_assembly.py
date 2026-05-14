from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geoai_simkit.services.native_import_assembly import run_native_import_assembly


def _load_sources(path: str | None, default_role: str) -> list[dict]:
    if not path:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("sources", data.get("structures", data.get("geology", data))) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("source JSON must be a list or an object containing sources/geology/structures")
    out = []
    for row in rows:
        item = dict(row or {})
        item.setdefault("role", default_role)
        out.append(item)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run GeoAI SimKit native/fallback-aware import assembly workflow")
    parser.add_argument("--geology", default=None, help="JSON list of geology sources")
    parser.add_argument("--structures", default=None, help="JSON list of structure sources/cutters")
    parser.add_argument("--output", default="reports/native_import_assembly_report.json")
    parser.add_argument("--element-size", type=float, default=2.0)
    parser.add_argument("--require-native-import", action="store_true")
    parser.add_argument("--require-native-boolean", action="store_true")
    parser.add_argument("--preserve-original-geology", action="store_true")
    args = parser.parse_args(argv)

    geology = _load_sources(args.geology, "geology")
    structures = _load_sources(args.structures, "structure")
    project, report = run_native_import_assembly(
        geology_sources=geology,
        structure_sources=structures,
        options={
            "element_size": args.element_size,
            "require_native_import": args.require_native_import,
            "require_native_boolean": args.require_native_boolean,
            "preserve_original_geology": args.preserve_original_geology,
            "remesh": True,
        },
        output_dir=Path(args.output).parent / "native_import_refs",
    )
    payload = {
        "ok": report.ok,
        "report": report.to_dict(),
        "project_summary": project.to_summary_dict() if hasattr(project, "to_summary_dict") else {"volume_count": len(project.geometry_model.volumes)},
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
