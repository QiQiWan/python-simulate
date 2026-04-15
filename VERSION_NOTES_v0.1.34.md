# GeoAI SimKit v0.1.34

## Highlights

- Added PLAXIS-like manual-interface automation for the demo pit: wall-soil interfaces now prefer exact overlapping nodes and automatically fall back to the nearest compatible soil-layer nodes when overlap is missing.
- Stored interface pairing diagnostics in metadata, including matched soil regions, exact/nearest match counts, and maximum wall-soil pairing distance.
- Updated GUI demo messaging and stage diagnostics to explain the automatic nearest-soil interface workflow more clearly.
- Preserved automatic crown beam and staged strut generation from v0.1.33.
