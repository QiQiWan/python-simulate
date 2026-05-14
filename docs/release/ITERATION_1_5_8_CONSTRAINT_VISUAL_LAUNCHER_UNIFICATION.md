# GeoAI SimKit 1.5.8 — Constraint Visual Feedback and Launcher Unification

This iteration strengthens the structure-modeling viewport feedback and removes ambiguity between GUI launch scripts.

## Constraint visualization enhancements

The persistent constraint lock now exposes visible feedback that is independent from the transient cursor preview:

- locked edge highlight for `edge_aligned` constraints;
- locked normal arrow for `normal_aligned` constraints;
- continuous placement trail for point, line, surface and block creation tools;
- explicit unlock feedback at the previous lock anchor or lock edge midpoint.

The controller contract is upgraded to `viewport_snap_controller_v4`. `ConstraintLockState.to_dict()` now includes `trail` and `visualization` fields. The PyVista adapter renders these fields as persistent overlay actors, while creation tools write the updated lock state into command metadata after each successful geometry creation.

## Launcher unification

`start_gui.py` is now the canonical repository-root launcher. `run_gui.py` and `src/start_gui.py` are compatibility shims that call the same `geoai_simkit.app.launcher_entry.main()` function.

Use:

```powershell
python .\start_gui.py --info
```

to verify the exact package file being launched. If `package_file` points to `site-packages`, the user is launching an installed old package instead of the edited checkout.

`run_gui.py` is retained only to avoid breaking old shortcuts. New docs and support instructions should use `start_gui.py`.

## Validation

Targeted tests:

```powershell
$env:PYTHONPATH="src"
python -m pytest -q tests/gui/test_iter153_structure_mouse_material_workflow.py tests/gui/test_iter154_viewport_workplane_hover_creation.py tests/gui/test_iter155_snap_crosshair_surface_menu.py tests/gui/test_iter156_engineering_snap_constraints.py tests/gui/test_iter157_constraint_lock_toolbar.py tests/gui/test_iter158_constraint_visual_launcher.py
```
