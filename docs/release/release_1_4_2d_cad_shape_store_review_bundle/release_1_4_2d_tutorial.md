# GeoAI SimKit 1.4.2d CadShapeStore / BRep Serialized References

This workflow builds a persistent CAD shape store after the 1.4.2c gmsh/OCC roundtrip.
It stores shape records, serialized BRep references, topology records, entity bindings and operation history.
Native BRep references are supported when present; deterministic `brep_json` references are marked as non-certified surrogates.

Acceptance in this run: `True`