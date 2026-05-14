# GeoAI SimKit 1.5.9 — Import-driven assembly and unified non-install launcher

This iteration changes the practical modeling strategy for environments where mouse CAD authoring remains unreliable.  The recommended production path is now:

1. Import geology from borehole CSV, STL surface/solid, or IFC-derived geometry.
2. Import or register retaining/support structures.
3. Spatially align the structure geometry with the geology model.
4. Subtract structure/excavation volumes from overlapping soil volumes.
5. Rebuild CAD-FEM physical groups and mesh entity maps.
6. Regenerate the Tet4 volume mesh and run solver-readiness checks.

The service entry point is `geoai_simkit.services.import_driven_model_assembly`.

## Why this strategy

The earlier mouse CAD workbench contains many interaction contracts, but real desktop startup still depends on Qt/VTK event routing, cell picking, snapping and OpenGL context behavior.  Import-driven preprocessing is more reliable for geotechnical/FEM production because files and bounds are explicit and can be validated headlessly.

## GUI changes

The right dock now includes a `导入拼接` tab.  It supports:

- geology source path selection;
- structure box registration by bounds;
- boolean subtract/remesh execution;
- JSON status output for the last assembly run.

## Launcher change

For non-install use, only the repository-root `start_gui.py` is retained.  The old `run_gui.py` and `src/start_gui.py` compatibility shims have been removed to avoid accidentally launching an older installed package or a stale GUI path.

Use:

```powershell
python .\start_gui.py --info
python .\start_gui.py
```

## CLI

```powershell
python .\tools\run_import_driven_assembly.py .\data\boreholes.csv --structures .\data\structures.json --output .\reports\import_driven_assembly_report.json
```

Structure JSON example:

```json
{
  "structures": [
    {
      "id": "diaphragm_wall_a",
      "kind": "diaphragm_wall",
      "bounds": [2, 4, -1, 11, -12, 0],
      "material_id": "concrete_c30"
    }
  ]
}
```

## Current boolean status

The implemented boolean is an explicit AABB fallback.  It is conservative and deterministic, suitable for headless contract verification and box-like excavation/support workflows.  It does not claim native BRep exactness.  Native OCC/Gmsh fragment/cut integration remains the next certification step.
