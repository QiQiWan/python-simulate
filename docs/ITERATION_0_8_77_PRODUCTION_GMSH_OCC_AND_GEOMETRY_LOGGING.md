# Iteration 0.8.77 - Production Gmsh/OCC Geometry Kernel and Debug Logging

This iteration strengthens the geometry kernel for real-machine production validation.

## Highlights

- `gmsh_occ_fragment_tet4_from_stl` mesh generator.
- Optional Gmsh/OCC fragment path with meshio conversion when dependencies are installed.
- Explicit fallback report when Gmsh/meshio are unavailable.
- Local bad-cell remeshing for Tet4/Hex8 cells.
- Geometry operation logging controlled by `GEOAI_SIMKIT_GEOMETRY_DEBUG` and `GEOAI_SIMKIT_GEOMETRY_LOG_DIR`.
- Facade/controller entrypoints for production geometry validation.

## Debug logging

Set:

```bash
export GEOAI_SIMKIT_GEOMETRY_DEBUG=1
export GEOAI_SIMKIT_GEOMETRY_LOG_DIR=/path/to/logs
```

The geometry kernel writes JSONL operation records with input summaries, output summaries, elapsed time, diagnostics and debug file paths.

## Validation

```text
249 passed, 1 skipped
```
