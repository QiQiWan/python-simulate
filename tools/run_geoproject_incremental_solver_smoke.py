from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from tools._no_install_bootstrap import bootstrap
ROOT = bootstrap()

from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.geoproject.runtime_solver import run_geoproject_incremental_solve


def main() -> int:
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="geoproject-incremental-solver-smoke")
    summary = run_geoproject_incremental_solve(project, compile_if_needed=True, write_results=True)
    validation = project.validate_framework()
    compiled = [row.to_dict() for row in project.solver_model.compiled_phase_models.values()]
    missing_runtime_blocks = []
    for row in compiled:
        meta = dict(row.get("metadata", {}) or {})
        if not meta.get("AssemblyBlock"):
            missing_runtime_blocks.append(f"{row.get('id')}:AssemblyBlock")
        if not meta.get("IncrementalSolveBlock"):
            missing_runtime_blocks.append(f"{row.get('id')}:IncrementalSolveBlock")
        state_block = dict(row.get("StateVariableBlock", {}) or {})
        if not state_block.get("cell_states"):
            missing_runtime_blocks.append(f"{row.get('id')}:cell_states")
    first_result = next(iter(project.result_store.phase_results.values())).to_dict() if project.result_store.phase_results else {}
    payload = {
        "accepted": bool(summary.accepted) and not missing_runtime_blocks,
        "summary": summary.to_dict(),
        "validation": validation,
        "missing_runtime_blocks": missing_runtime_blocks,
        "phase_result_count": len(project.result_store.phase_results),
        "curve_count": len(project.result_store.curves),
        "engineering_metric_count": len(project.result_store.engineering_metrics),
        "first_result_fields": [row.get("name") for row in first_result.get("fields", [])],
        "compiled_phase_count": len(project.solver_model.compiled_phase_models),
    }
    out = ROOT / "reports" / "geoproject_incremental_solver_smoke.json"
    preview = ROOT / "exports" / "geoproject_incremental_solver_preview.geojson"
    out.parent.mkdir(parents=True, exist_ok=True)
    preview.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    project.save_json(preview)
    print(json.dumps(payload, indent=2, ensure_ascii=False), flush=True)
    return 0 if payload["accepted"] else 2


if __name__ == "__main__":
    code = main()
    # Some embedded BLAS builds keep worker threads alive in the execution
    # sandbox.  The smoke script writes all outputs before exiting.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
