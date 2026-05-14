# Iteration 1.4.4 — Native BRep Capability and Face/Edge Material/Phase Binding

## Scope

This release extends the 1.4.3 STEP/IFC shape-binding foundation with:

- Native TopoDS_Shape BRep serialization capability probing.
- Best-effort native STEP import path through OCP/pythonocc when present.
- IFC product exact identity extraction through IfcOpenShell when present.
- CadTopologyBinding records in CadShapeStore.
- Face/edge/solid material and phase binding after STEP/IFC import or boolean/roundtrip history.
- 1.4.4 acceptance gate with separate native-certified and non-native serialized-topology outcomes.

## Certification policy

Native BRep certification is **not** inferred from a package being installed. A shape is marked native-certified only when:

1. A real TopoDS_Shape is obtained from a native runtime.
2. That shape is serialized to an external `.brep` file.
3. Native topology records are enumerated from the shape.
4. The CadShapeRecord has `native_shape_available=true` and `metadata.native_brep_certified=true`.

Fallback or manifest imports remain accepted as topology-binding workflows but are not native-certified.

## New contracts

- `geoai_simkit_native_brep_serialization_capability_v1`
- `geoai_simkit_native_topods_brep_serialization_v1`
- `geoai_simkit_face_edge_material_phase_binding_v1`
- `geoai_simkit_release_1_4_4_topology_binding_acceptance_v1`

## Review bundle

Generated bundle path:

`docs/release/release_1_4_4_topology_binding_review_bundle/`

