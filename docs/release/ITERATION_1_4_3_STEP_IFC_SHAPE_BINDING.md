# Iteration 1.4.3 — STEP/IFC Solid Topology Import and Native Shape Binding

## Scope

This iteration extends the 1.4.2d `CadShapeStore` so external STEP/IFC solid files can be imported into the GeoProject model and bound to persistent CAD shape references.

The release does **not** claim certified native BRep import unless a target environment provides exact native runtimes and `require_native_brep=True` passes. In dependency-light environments it creates explicit serialized topology references and labels them as non-certified surrogates.

## Added contracts

- `geoai_simkit_step_ifc_import_capability_v1`
- `geoai_simkit_step_ifc_solid_topology_import_v1`
- `geoai_simkit_step_ifc_shape_binding_validation_v1`
- `geoai_simkit_release_1_4_3_step_ifc_shape_binding_acceptance_v1`

## Added services

- `geoai_simkit.services.step_ifc_shape_import`
- `geoai_simkit.services.release_acceptance_143`

## Added command

- `ImportStepIfcSolidTopologyCommand`

## Workflow

```python
from geoai_simkit.examples.release_1_4_3_workflow import run_release_1_4_3_workflow
result = run_release_1_4_3_workflow()
print(result["acceptance"]["status"])
```

## Acceptance status in this build

- Status: `accepted_1_4_3_step_ifc_shape_binding`
- Native BRep certified: `false`
- Import path: serialized STEP/IFC topology binding into `CadShapeStore`

## Next work

- 1.4.4: material/phase binding after boolean/import history
- 1.4.5: exact native TopoDS_Shape serialization and persistent naming verification
