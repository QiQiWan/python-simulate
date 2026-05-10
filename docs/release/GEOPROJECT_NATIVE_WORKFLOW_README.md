# GeoProjectDocument-native workflow package

This package contains the v0.8.49 update.  The main workflow is now centered on `GeoProjectDocument` as the single source of truth for visual modeling, command execution, stage editing, material editing, mesh preview, solver compilation and result preview.

Run the smoke validation:

```bash
PYTHONPATH=src python3 -S tools/run_geoproject_native_workflow_smoke.py
```

Key generated artifacts:

```text
reports/geoproject_native_workflow_smoke.json
exports/geoproject_native_workflow_preview.geojson
docs/ITERATION_0_8_49_GEOPROJECT_NATIVE_WORKFLOW.md
```
