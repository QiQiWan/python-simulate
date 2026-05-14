# Iteration 1.4.5 — Native Geometry Certification, IFC Representation Expansion and Face Lineage

## Scope

This iteration extends 1.4.4 topology binding with five certification-oriented layers:

1. Desktop native runtime verification for OCP / pythonocc-core / IfcOpenShell / Gmsh / MeshIO.
2. Complex STEP native BRep certification gates and native topology enumeration paths.
3. IFC swept solid / CSG / BRep representation expansion.
4. Boolean face lineage / split / merge history mapping.
5. GUI-facing direct face/edge material and phase assignment service.

## Native certification policy

A run is native BRep-certified only when a real TopoDS_Shape is serialized to a `.brep` file and native topology records are enumerated from that shape. Surrogate `.json` references and text-scanned IFC/STEP topology are valid contract artifacts, but they never set `native_brep_certified=true`.

## New services

- `native_runtime_verification.py`
- `ifc_representation_expansion.py`
- `boolean_topology_lineage.py`
- extended `topology_material_phase_binding.py`
- `release_acceptance_145.py`

## Workflow

Run:

```bash
PYTHONPATH=src python - <<'PY'
from geoai_simkit.examples.release_1_4_5_workflow import run_release_1_4_5_workflow
result = run_release_1_4_5_workflow()
print(result['ok'])
print(result['acceptance']['status'])
PY
```

Use `require_native_brep=True` to enforce native-certified acceptance on a desktop environment with OCP/pythonocc/IfcOpenShell available.
