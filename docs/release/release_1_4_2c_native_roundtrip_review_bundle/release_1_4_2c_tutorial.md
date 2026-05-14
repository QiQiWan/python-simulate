# GeoAI SimKit 1.4.2c Native Gmsh/OCC Boolean + Physical Group Mesh Roundtrip

This bundle executes deferred boolean CAD features and then performs a Tet4 mesh roundtrip with physical_volume/material_id tags.
Native-certified mode requires an importable `gmsh.model.occ` runtime. If unavailable, the workflow produces a clearly labelled deterministic contract artifact and is not reported as native-certified.

Native gmsh/OCC available in this run: `False`

Recommended GUI flow:
1. Start the six-phase workbench.
2. Load the foundation pit template.
3. Record Union/Subtract features on selected volumes.
4. Execute Gmsh/OCC roundtrip.
5. Inspect physical groups and mesh tags before solve.