# GeoAI SimKit 1.6.0 — Native Import Assembly + GUI Startup Repair

This iteration changes the recommended CAD/FEM preprocessing strategy from mouse-first authoring to import-first assembly.

## Main changes

- Adds `geoai_simkit.services.native_import_assembly`.
- Supports geology sources from borehole CSV, STL, IFC/STEP topology import, and explicit box bounds.
- Supports support/retaining structure sources from IFC, STEP, STL, or explicit bounds.
- Adds transform controls for imported sources: translate, scale, rotate Z, and transform origin.
- Runs structure/soil overlap subtraction and remeshing through the import-driven assembly pipeline.
- Keeps native/fallback provenance explicit: native import and native boolean availability are reported separately.
- Adds `tools/run_native_import_assembly.py` for headless workflow execution.
- Repairs the GUI startup path by adding a Qt-only workbench fallback when PyVista/VTK/OpenGL cannot create a render window.
- Restores the missing `导入拼接` panel builder, which could prevent `start_gui.py` from opening the main window.
- Keeps the single repository-root non-install entrypoint: `python .\start_gui.py`.

## Recommended launch commands

```powershell
python .\start_gui.py --info
python .\start_gui.py
```

If the 3D OpenGL viewport still fails on Windows/RDP/driver-limited machines:

```powershell
python .\start_gui.py --qt-only
```

The Qt-only workbench keeps import assembly, material assignment, meshing, readiness, benchmark and reporting panels available while disabling PyVista/VTK rendering.

## Native import assembly CLI

```powershell
python .\tools\run_native_import_assembly.py --geology .\data\geology_sources.json --structures .\data\structure_sources.json --output .\reports\native_import_assembly_report.json
```

Source JSON example:

```json
[
  {"id": "soil", "role": "geology", "source_type": "box_bounds", "bounds": [0, 10, 0, 10, -10, 0]},
  {"id": "geology_ifc", "role": "geology", "path": "geology.ifc"}
]
```

Structure JSON example:

```json
[
  {"id": "wall_a", "role": "structure", "path": "retaining_wall.ifc", "kind": "diaphragm_wall", "material_id": "concrete_c30"},
  {"id": "excavation", "role": "structure", "source_type": "box_bounds", "kind": "excavation", "bounds": [2, 8, 2, 8, -8, 0]}
]
```
