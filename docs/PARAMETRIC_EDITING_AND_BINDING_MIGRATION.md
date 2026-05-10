# Parametric editing and binding migration

Version `0.8.46` upgrades one-shot engineering modeling operations into editable parametric features.

## Editable objects

- Horizontal soil-layer split features.
- Excavation polygon split features.
- Support structures, including wall, strut and anchor axes.

## Editing workflow

1. Create a soil split, excavation polygon, or support structure.
2. Select the generated feature, generated block, or support from the object tree or viewport.
3. Update parameters from the property/edit panel or drag the feature handle in the section viewport.
4. The system regenerates affected geometry and automatically migrates:
   - material assignments,
   - stage activation/inactivation states,
   - support activation stages,
   - accepted contact/interface review bindings where source/target blocks can be mapped.

## New modules

- `geoai_simkit.geometry.parametric_editing`
- `UpdateSoilLayerSplitCommand`
- `UpdateExcavationPolygonCommand`
- `UpdateSupportParametersCommand`

## Smoke test

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python tools/run_parametric_editing_binding_migration_smoke.py
```

The smoke report is written to:

```text
reports/parametric_editing_binding_migration_smoke.json
```
