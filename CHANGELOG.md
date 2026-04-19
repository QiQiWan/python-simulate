# Changelog

## 0.4.3

- Added face-aware interface topology preview generation via `pipeline.interface_elements`.
- Added CLI command `interface-elements-case` to inspect explicit interface face preview elements.
- Extended preprocessor snapshots with `interface_face_groups` and `interface_face_elements`.
- Fixed interface-ready node splitting so only the declared interface side region is duplicated, avoiding orphan opposite-side points.
- Extended preparation and validation summaries with interface face topology metrics.


## 0.3.7

- Added region adjacency analysis utilities and the `adjacency-case` CLI command.
- Added `adjacent_region_contact_pairs` interface generator for selector- and adjacency-driven contact setup.
- Updated demo wall interface pairing to avoid identical slave/master node pairs.
- Extended validation with adjacency counts and interface pairing diagnostics.

## 0.3.6

- Added interface generator registry to the case-driven pipeline (`contact_pair`, `selector_contact_pairs`, `demo_wall_interfaces`).
- Portable case files now preserve interface generator entries during JSON/YAML round-trip.
- Demo case now declares wall interfaces directly through the pipeline instead of relying only on post-preparation coupling helpers.
- Validator now reports unknown interface generators and missing prepared interfaces.
- Preparation reports now expose `n_interfaces` and `n_generated_interfaces`.

# Changelog

## 0.3.3 - 2026-04-16

### Added

- selector-driven `BoundaryConditionSpec` and `LoadSpec` for declarative case files
- region-to-point resolution utilities for boundary/load preprocessing
- solver support for `point_id_space='global'` so staged submeshes can consume global point IDs safely
- targeted regression tests for selector-driven boundary/load resolution and point-ID mapping

### Changed

- case preparation now resolves global boundary conditions after meshing/region discovery
- stage preparation now expands boundary/load selector specs into concrete solver-ready definitions
- `inspect-case` and validation summaries now expose boundary/load counts alongside region and stage counts
- portable case JSON/YAML round-trips now preserve selector-based boundary conditions and stage loads


## 0.2.0 - 2026-04-16

### Added

- release-oriented package metadata in `pyproject.toml`
- optional dependency extras for GUI, IFC, meshing, GPU, and full installs
- `requirements-dev.txt`, `MANIFEST.in`, `setup.py` shim, `.gitignore`, and release documentation
- GitHub Actions templates for CI and PyPI/TestPyPI publishing
- `--version` support and explicit subcommand handling in the CLI

### Changed

- simplified package `__init__` so importing `geoai_simkit` no longer monkey-patches third-party libraries at runtime
- moved the PyVista/pytest compatibility patch into test configuration instead of package import side effects
- improved user-facing error messages when optional dependencies are missing
- refreshed README to match publishable repository structure and installation modes

### Removed

- cached bytecode, smoke-output artifacts, and internal repair notes from the release package
