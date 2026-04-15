# GeoAI SimKit v0.1.35

## This release
- Added a demo coupling wizard dialog for the parametric pit example.
- Added configurable wall coupling modes: display-only, auto-interface, and PLAXIS-like auto coupling.
- Added configurable interface matching policies: exact_only, manual_like_nearest_soil, nearest_soil_relaxed.
- Added per-face wall-soil interface diagnostics, including pair counts, unmatched wall points, and max pair distance.
- Added one-click regeneration of demo coupling using the current GUI wall/interface settings.
- Added pre-solve warning when auto-matched interface pair distances become too large.
