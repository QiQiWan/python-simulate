# Iteration 1.6.3 — GUI action dispatch and file dialog repair

This iteration repairs a critical usability failure reported on Windows: import buttons wrote a click log but did not surface a file browser or perform the import.

## Diagnosis

The 1.6.2 import buttons still relied on synchronous modal file-dialog execution for the file selection step. In Windows sessions that mix PySide6 with VTK/PyVista OpenGL, a modal `QFileDialog.exec()` can be hidden behind the render window or placed outside the visible desktop. The GUI then appears unresponsive because the action has already logged `started` and is blocked inside the invisible modal dialog.

## Fix

The import pipeline now uses non-modal action dispatch:

1. Direct import buttons open a retained, non-modal `QFileDialog`.
2. The dialog object is stored on `PhaseWorkbenchWindow._active_file_dialogs` so PySide cannot destroy it immediately.
3. Selection is handled through `fileSelected`, then the chosen path is written to the line edit and passed to the import service via `path_override`.
4. The modal `dialog.exec()` path was removed from the import actions.
5. The status bar, log, import panel, and interaction-audit table now report: opening chooser, selected path, cancelled, or import failure.

## Covered direct import actions

- `import_geology_csv`
- `import_geology_stl`
- `import_geology_ifc_step`
- `import_structure_stl`
- `import_structure_ifc_step`

Auto import buttons now also open a file chooser when the path field is empty, while still allowing manual path paste followed by auto import.

## Verification

Run:

```powershell
python .\start_gui.py --info
python .\tools\check_gui_action_flow.py
python .\start_gui.py --qt-only
```

Expected `check_gui_action_flow.py` result:

```json
{
  "ok": true,
  "async_file_dialog_retained": true,
  "non_modal_file_dialog": true,
  "modal_dialog_exec_removed_for_imports": true,
  "direct_import_buttons_are_async": true
}
```
