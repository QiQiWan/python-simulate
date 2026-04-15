# geoai-simkit v0.1.42

- Fixed geometry-first mesh engine crashes caused by serializing `slots=True` dataclasses with `__dict__`.
- Replaced mesh-engine and UI performance-audit metadata serialization with `dataclasses.asdict(...)`.
- Added safe copy fallbacks for geometry snapshots and per-target temporary blocks, so stub or lightweight dataset implementations do not crash on `copy(deep=True)`.
- Added a remeshing confirmation prompt when the current model is already meshed, to reduce accidental workflow confusion.
- Fixed the geometry-first tetra-to-hex fallback path to import voxel meshing classes correctly.
- Added regression tests for slot-dataclass serialization and safe geometry-first mesh metadata generation.
