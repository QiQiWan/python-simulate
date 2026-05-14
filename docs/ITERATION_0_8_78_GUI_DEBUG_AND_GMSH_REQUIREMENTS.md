# Iteration 0.8.78 — Production Gmsh/Meshio Requirements and GUI Debug Logging

## Goals

- Treat `gmsh` and `meshio` as installed production meshing dependencies when users install `requirements.txt`.
- Add a command-line debug mode for GUI startup.
- Keep debug logging disabled by default.
- When debug is enabled from the command line, write logs to the current working directory under `log/` without requiring users to export environment variables.

## Implemented changes

### Requirements

`requirements.txt` now includes:

```text
gmsh
meshio
```

The optional dependency groups in `pyproject.toml` are preserved for packaging, but the consolidated requirements file now installs the production STL/Tet4 meshing stack by default.

### GUI debug mode

Supported launchers:

```bash
python start_gui.py --debug
python run_gui.py --debug
python -m geoai_simkit gui --debug
geoai-simkit gui --debug
geoai-simkit-gui --debug
```

Default behavior remains unchanged when `--debug` is omitted.

### Logging behavior

When enabled, debug logging uses:

```text
./log/geometry_kernel.jsonl
```

The launcher configures these process variables automatically:

```text
GEOAI_SIMKIT_GEOMETRY_DEBUG=1
GEOAI_SIMKIT_DEBUG=1
GEOAI_SIMKIT_GEOMETRY_LOG_DIR=<current-working-directory>/log
```

No manual environment setup is needed for GUI debugging.

### Backward compatibility

Manual environment-variable configuration is still supported for scripted/headless runs.  Existing calls to `log_geometry_operation(..., enabled=True, debug_dir=...)` continue to work.

## Validation

```text
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -B -m pytest tests -q
253 passed, 1 skipped
```

```text
PYTHONPATH=src python -B -m geoai_simkit --version
geoai-simkit 0.8.78
```

```text
PYTHONPATH=src python -B tools/run_core_fem_smoke.py
Core FEM smoke: 7/7 ok=True
```
