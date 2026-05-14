# GeoAI SimKit 1.4.5 Native Geometry Certification Workflow

Accepted: `True`
Native BRep certified in this run: `False`

This workflow verifies desktop native runtime capability, imports STEP/IFC topology references, expands IFC swept/CSG/BRep representations, builds boolean face lineage, and supports face/edge material/phase assignment.

Native-certified acceptance requires real TopoDS_Shape BRep serialization plus native topology enumeration. In environments without OCP/pythonocc/IfcOpenShell, the workflow remains useful as a contract run and clearly marks native_brep_certified=false.