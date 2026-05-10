from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geoai_simkit.geometry.stl_loader import STLImportOptions, load_stl_geology
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.pipeline import AnalysisCaseBuilder, AnalysisCaseSpec, GeometrySource


def main() -> int:
    parser = argparse.ArgumentParser(description="Import and validate an STL geological model.")
    parser.add_argument("stl", help="Path to an ASCII or binary STL file")
    parser.add_argument("--unit-scale", type=float, default=1.0, help="Scale to project length unit; use 0.001 when STL is in mm and project is in m")
    parser.add_argument("--material-id", default="imported_geology")
    parser.add_argument("--name", default=None)
    parser.add_argument("--out", default="reports/stl_geology_import_smoke.json")
    args = parser.parse_args()

    options = STLImportOptions(name=args.name, unit_scale=args.unit_scale, material_id=args.material_id)
    stl = load_stl_geology(args.stl, options)
    case = AnalysisCaseSpec(
        name=stl.name,
        geometry=GeometrySource(kind="stl_geology", path=str(args.stl), parameters={"name": stl.name, "unit_scale": args.unit_scale, "material_id": args.material_id}),
    )
    prepared = AnalysisCaseBuilder(case).build()
    project = GeoProjectDocument.from_stl_geology(args.stl, options=options, name=stl.name)
    compiled = project.compile_phase_models()
    payload = {
        "ok": True,
        "stl": stl.to_summary_dict(),
        "model": {
            "regions": [r.name for r in prepared.model.region_tags],
            "n_points": int(prepared.model.mesh.n_points),
            "n_cells": int(prepared.model.mesh.n_cells),
        },
        "geoproject": project.validate_framework(),
        "compiled_phase_model_count": len(compiled),
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Saved report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
