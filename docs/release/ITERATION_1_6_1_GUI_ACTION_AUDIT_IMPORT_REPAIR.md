# GeoAI SimKit 1.6.1 — GUI Action Audit and Import Button Repair

This iteration focuses on production GUI interaction reliability for the import-driven geology/structure assembly workflow.

## Main changes

- Added a GUI action audit registry and bottom tab `交互自检`.
- Added direct import buttons for geology CSV, geology STL, geology IFC/STEP, structure STL, and structure IFC/STEP.
- Repaired import button status propagation: every critical import and assembly button now writes status to the status bar, log tab, and the action audit table.
- Added stricter file type validation for direct import buttons.
- Added robust file path handling: direct import buttons open a file dialog when the path field is empty and fail clearly when a path does not exist.
- Made import/cut assembly success independent from later CAD-FEM topology readiness blockers. This prevents successful STL/structure imports from looking like no-op button clicks when no volume mesh or topology identity index exists yet.

## Critical actions

- `import_geology_csv`
- `import_geology_stl`
- `import_geology_ifc_step`
- `import_structure_stl`
- `import_structure_ifc_step`
- `register_structure_box`
- `run_import_driven_assembly`
- `run_native_import_assembly`
- `assign_material_to_selection`

## Validation

- `compileall` passed.
- `tests/gui/test_iter161_gui_action_audit_import_buttons.py`: 4 passed.
- `tests/gui/test_iter159_import_driven_assembly_unified_launch.py`, `test_iter160_native_import_assembly_gui_startup.py`, `test_iter161_gui_action_audit_import_buttons.py`: 14 passed.
- `tests/gui/test_iter158_constraint_visual_launcher.py`: 4 passed.
