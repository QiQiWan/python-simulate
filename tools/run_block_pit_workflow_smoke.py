#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from geoai_simkit.examples.block_pit_workflow import run_block_pit_workflow


def main() -> int:
    payload = run_block_pit_workflow('reports', dimension='3d', smoke=True)
    summary = dict(payload.get('workflow_summary') or {})
    checks = {
        'accepted': bool(payload.get('accepted')),
        'blocks_created': int(summary.get('block_count', 0) or 0) >= 20,
        'soil_layers_split': int(summary.get('soil_block_count', 0) or 0) > int(summary.get('excavation_block_count', 0) or 0),
        'excavation_blocks_split': int(summary.get('excavation_block_count', 0) or 0) == 3,
        'contact_pairs_detected': int(payload.get('contact_pair_count', 0) or 0) > 0,
        'interface_requests_generated': int(payload.get('interface_request_count', 0) or 0) > 0,
        'stage_metrics_available': len(payload.get('stage_metrics') or []) >= 3,
        'result_fields_available': any(str(x).startswith('surface_settlement@') for x in payload.get('field_labels') or []),
    }
    report = {'ok': all(checks.values()), 'checks': checks, **payload}
    out = Path('reports') / 'block_pit_workflow_smoke.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'ok': report['ok'], 'json_path': str(out), 'checks': checks}, indent=2), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    import os; os._exit(main())
