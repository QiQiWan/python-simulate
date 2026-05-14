# Iteration 1.4.2d — CadShapeStore / BRep Serialized Shape References

1.4.2d adds a persistent CAD shape layer to bridge GeoProject geometry, 1.4.2c Gmsh/OCC roundtrip artifacts, and future native BRep/STEP/IFC workflows.

## New records

- `CadShapeStore`
- `CadShapeRecord`
- `CadSerializedShapeReference`
- `CadTopologyRecord`
- `CadEntityBinding`
- `CadOperationHistoryRecord`

## Boundary

Headless CI emits deterministic `brep_json` serialized references and marks `native_brep_certified=false`. A future native OCC integration can attach real BRep paths or serialized TopoDS references to the same store.
