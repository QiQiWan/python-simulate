# P7 Topology Identity and Service Boundary Upgrade

This package advances the desktop CAD workbench architecture from feature-level patches to a shared identity spine.  The new spine connects CAD shape storage, viewport picking, material/phase assignment, operation lineage and future meshing physical groups through one canonical identity model.

## Added contracts

- `ModelEntityIdentity`: engineering entity identity such as a GeoProject volume or imported IFC product.
- `ShapeNodeIdentity`: CAD shape identity, including backend, native availability and source entities.
- `TopologyElementIdentity`: solid/face/edge identity with persistent name, native tag, material, phases and bounds.
- `SelectionStateIdentity`: active viewport/panel selection payload derived from topology identity.
- `OperationLineageIdentity`: operation history between topology keys, including native/derived confidence.

## Boundary policy

- `geoai_simkit.core.topology_identity` is dependency-free and must not import GUI, CAD runtime, meshing or solver modules.
- `geoai_simkit.services.topology_identity_service` is headless and may read `CadShapeStore`, but must not import Qt, PyVista, VTK, OCC, IfcOpenShell, Gmsh or meshio.
- GUI code receives identity keys through metadata; it should not construct native CAD references directly.
- Material/phase panels should consume `topology_id`, `shape_id`, `topology_kind` and `topology_identity_key` from selection metadata.

## Resulting flow

```text
STEP/IFC/OCC import or CAD operation
→ CadShapeStore
→ TopologyIdentityIndex
→ Viewport primitive metadata
→ SelectionController selected_keys
→ Property / material / phase / operation panels
→ Command / service layer
→ Updated CadShapeStore and lineage
```

## Acceptance checks

The new regression suite verifies that:

- entity, shape, topology and lineage records are represented in one index;
- face/edge viewport primitives carry canonical selection keys;
- picking a face/edge produces the same topology identity key used by selection state;
- the index can be built through an undoable command;
- the core and service layers remain headless.
