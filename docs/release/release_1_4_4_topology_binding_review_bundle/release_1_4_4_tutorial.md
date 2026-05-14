# GeoAI SimKit 1.4.4 Topology Material/Phase Binding

Accepted: `True`
Native BRep certified in this run: `False`

This release adds native BRep serialization capability probing, STEP/IFC imported shape binding, and face/edge/solid-level material and phase bindings after import or boolean history.

Acceptance has two levels:
- `accepted_1_4_4_topology_binding`: serialized topology binding is complete; native BRep may be false.
- `accepted_1_4_4_native_brep_topology_binding`: at least one imported shape is native BRep-certified.

Recommended flow:
1. Import STEP/IFC solids.
2. Inspect CadShapeStore shape references and native BRep certification state.
3. Run face/edge/material/phase binding.
4. Continue to Gmsh/OCC physical-group mesh roundtrip and solve.