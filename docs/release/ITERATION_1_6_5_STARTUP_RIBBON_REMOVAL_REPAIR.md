# GeoAI SimKit 1.6.5 — Startup Ribbon Removal Repair

This iteration repairs a startup failure introduced while slimming the top toolbar in 1.6.4.

## Fixed

- `PhaseWorkbenchWindow` no longer references the removed contextual ribbon widget during `_set_phase()`.
- `_build_contextual_ribbon()` now creates explicit sentinel attributes (`self.ribbon = None`, `self.ribbon_actions = []`) so any historical code path is safe.
- `_rebuild_ribbon()` is now a startup-safe no-op. Production actions continue through the action dispatcher, right-dock panels, and slim top toolbar.
- `check_gui_action_flow.py` now verifies the historical ribbon is disabled without leaving `self.ribbon.clear()` startup references.

## Why

The previous release removed the toolbar widget but left `_set_phase()` calling `_rebuild_ribbon()`, whose implementation still expected `self.ribbon`. On startup, this caused:

```text
AttributeError: 'PhaseWorkbenchWindow' object has no attribute 'ribbon'
```

The supported workflow remains import-driven assembly: geology/mesh import, structure import or box cutters, boolean/difference, remeshing, readiness checks.
