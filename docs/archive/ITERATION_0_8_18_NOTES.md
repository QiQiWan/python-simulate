# GeoAI SimKit v0.8.18 / iter76

This iteration hardens the PLAXIS-like GUI modeling workflow around real entity editing and remeshing.

## Highlights

- Added a defensive Qt/PyVista viewport event binder (`post/qt_viewport_events.py`) that routes mesh picking, hover tracking, rectangle selection availability, context menus, and drag release transforms into the existing controller methods.
- Added an OpenCascade native persistent naming bridge (`geometry/occ_native_naming.py`). When `pythonocc-core` is available it prepares TNaming/TDF label handles; otherwise it explicitly reports fallback to the v4 semantic geometry fingerprint scheme rather than pretending native TNaming is available.
- Added source-entity realization for retaining-wall panels, strut rows, ground anchors, wall-soil interfaces, named selections, and installation stages (`geometry/support_realization.py`). Component parameters now become editable source entities and mark mesh/results stale.
- Added stratigraphy robustness analysis (`geometry/stratigraphy_robustness.py`) for surface crossing, pinch-out, thin lens layers, missing surfaces, and triangle/grid mismatch before OCC boolean operations.
- Added GUI binding-transfer review queues and decision application (`geometry/binding_review.py`) so users can accept, reject, or manually map inherited bindings after geometry changes/remeshing.
- Added `_version.py` with `__version__ = 0.8.18` to restore package metadata completeness.

## Principle kept

Users edit source entities/BRep/sketches/components. Meshes remain generated artifacts and must be regenerated after entity changes.
