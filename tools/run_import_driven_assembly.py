from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geoai_simkit.services.import_driven_model_assembly import run_import_driven_assembly


def _load_structure_specs(path: str | None) -> list[dict]:
    if not path:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("structures", []))
    if isinstance(data, list):
        return [dict(row) for row in data]
    raise ValueError("structure spec JSON must be a list or an object with a 'structures' list")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run import-driven geology/structure boolean/remesh workflow")
    parser.add_argument("geology", nargs="?", help="borehole CSV, geology STL, or other geology source")
    parser.add_argument("--source-type", default=None, help="explicit geology source type, e.g. borehole_csv or stl_geology")
    parser.add_argument("--structures", default=None, help="JSON file containing imported structure bounds/specs")
    parser.add_argument("--output", default="reports/import_driven_assembly_report.json")
    parser.add_argument("--element-size", type=float, default=2.0)
    parser.add_argument("--preserve-original-geology", action="store_true")
    args = parser.parse_args(argv)

    structure_specs = _load_structure_specs(args.structures)
    project, report = run_import_driven_assembly(
        geology_source=args.geology,
        geology_source_type=args.source_type,
        structure_specs=structure_specs,
        options={"element_size": args.element_size, "preserve_original_geology": args.preserve_original_geology, "remesh": True},
        name=Path(args.geology).stem if args.geology else "import-driven-assembly",
    )
    payload = {"ok": report.ok, "report": report.to_dict(), "project_summary": project.to_summary_dict() if hasattr(project, "to_summary_dict") else {"volume_count": len(project.geometry_model.volumes)}}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
