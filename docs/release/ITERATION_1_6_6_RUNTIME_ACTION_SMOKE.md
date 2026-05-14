# GeoAI SimKit 1.6.6 — Runtime Action Smoke

This iteration continues the 1.6.x GUI stabilization line after the ribbon-startup repair.

## Focus

The main goal is to distinguish between startup success and actual button usability. The canonical PhaseWorkbenchQt now includes a runtime button smoke check in the bottom `交互自检` panel.

## Changes

- Version: `1.6.6-runtime-action-smoke`.
- Launcher diagnostics contract: `geoai_simkit_gui_launcher_info_v6`.
- Geometry interaction contract: `phase_workbench_geometry_interaction_v15`.
- All registered user-facing buttons now receive:
  - `objectName = geoai-action-<action_id>`
  - `geoai_action_id` Qt property
  - `geoai_action_panel` Qt property
  - enabled state forced during registration
  - pointing-hand cursor and strong focus policy where Qt supports it
- The PhaseWorkbenchWindow keeps a live `_gui_action_widgets` map from action id to button widget.
- Added `按钮烟测` in the `交互自检` panel.
- Runtime smoke checks the production action surface without executing destructive actions:
  - import_geology_model
  - import_geology_auto
  - import_structure_model
  - import_structure_auto
  - register_structure_box
  - run_import_driven_assembly
  - run_native_import_assembly
  - assign_material_to_selection
  - refresh_workbench_state
  - refresh_gui_action_audit
  - run_gui_button_smoke

## Validation

Run:

```powershell
python .\start_gui.py --info
python .\tools\check_gui_action_flow.py
python .\start_gui.py --qt-only
```

After the GUI starts, open `交互自检` and click `按钮烟测`. The status pane should report:

```json
{
  "contract": "geoai_simkit_runtime_button_smoke_v1",
  "ok": true
}
```

If the report is ok but file selection still does not appear, use the path field plus `按路径导入`; that path bypasses OS file-dialog focus issues and calls the same import service.
