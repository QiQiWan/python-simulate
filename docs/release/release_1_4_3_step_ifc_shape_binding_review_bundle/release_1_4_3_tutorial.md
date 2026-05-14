# GeoAI SimKit 1.4.3 STEP/IFC Solid Topology Import and Native Shape Binding

Accepted: `True`
Native BRep certified in this run: `False`

This release binds STEP/IFC solid references into CadShapeStore. If native runtimes are unavailable, imported solids are stored as explicit serialized topology references and are not reported as native BRep-certified.

Recommended flow:
1. Open the six-phase workbench.
2. Import a STEP or IFC solid file.
3. Inspect CadShapeStore imported shape references and topology records.
4. Build mesh/physical groups after confirming material and phase bindings.