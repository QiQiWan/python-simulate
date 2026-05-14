# GeoAI SimKit 1.7.0 - ParaView Geology Visualization and Mesh Optimization

This iteration makes imported VTU/MSH geology meshes render closer to ParaView:
external surface first, categorical geology scalar coloring, boundary wireframe,
feature edges and outline. It also adds geology-layer identification, mesh weight
reduction and non-manifold diagnostics for imported FEM-ready meshes.

Key changes:

- Preserve imported VTU cell data such as `soil_id`, `material_index` and
  `element_id`.
- Preserve Gmsh v2 physical tags as `gmsh_physical`.
- Prefer real geology scalars before elevation fallback.
- Render extracted external surface instead of all internal volume edges.
- Add surface wireframe, outline and feature-edge overlays.
- Add GUI actions: identify geology layers, reduce mesh weight and diagnose
  non-manifold topology.
- Keep mesh reduction conservative: merge duplicate nodes, remove duplicate or
  degenerate cells, remove unused nodes, preserve geology cell tags.

Validated against the provided `model_volume.vtu` and `model_volume.msh`:

- 31,200 nodes
- 27,027 hexahedral cells
- 17 geology groups from `soil_id` or `gmsh_physical`
- 0 non-manifold faces detected by face-use count
- 8,094 exterior boundary faces
