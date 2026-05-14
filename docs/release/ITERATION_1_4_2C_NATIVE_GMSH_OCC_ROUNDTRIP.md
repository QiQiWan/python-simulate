# Iteration 1.4.2c — Native Gmsh/OCC Boolean + Physical Group Mesh Roundtrip

This iteration promotes the 1.4.2a CAD facade into a roundtrip-oriented Gmsh/OCC integration layer.

## What is implemented

- `geoai_simkit.services.gmsh_occ_boolean_roundtrip`
  - probes `gmsh.model.occ` and `meshio` availability;
  - executes deferred CAD boolean features before meshing;
  - uses native `gmsh.model.occ` when available;
  - creates physical volume groups and imports them back to `MeshDocument.cell_tags`;
  - writes a physical-group manifest and `.msh` artifact when native Gmsh runs;
  - falls back to a deterministic Tet4 contract only when native is not required.

- `ExecuteGmshOccBooleanMeshRoundtripCommand`
  - undoable command wrapper for GUI/workflow usage.

- `release_acceptance_142c`
  - differentiates native-certified acceptance from contract-only acceptance:
    - `accepted_1_4_2c_native_roundtrip`: native Gmsh/OCC executed with no fallback.
    - `accepted_1_4_2c_roundtrip_contract`: deterministic physical-group contract executed because native Gmsh/OCC is unavailable.

- `release_1_4_2c_workflow`
  - loads the foundation pit demo;
  - records a boolean feature;
  - executes boolean + physical-group mesh roundtrip;
  - writes a review bundle.

## Important boundary

In environments without `gmsh`, this build produces an explicit deterministic contract artifact. It does not claim native-certified CAD/OCC execution. To require true native execution, call:

```python
run_release_1_4_2c_workflow(require_native_certified=True)
```

or run the service/command with `require_native=True`.

## Recommended desktop environment

Use conda-forge for native binary packages:

```bash
conda install -c conda-forge numpy scipy pyside6 vtk pyvista pyvistaqt gmsh meshio
python -m pip install -r requirements.txt
```
