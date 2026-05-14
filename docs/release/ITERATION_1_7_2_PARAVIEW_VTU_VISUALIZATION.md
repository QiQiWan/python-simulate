# Iteration 1.7.2 - ParaView-style VTU visualization repair

## Problem
The imported VTU geology model did not match the visual effect users see in ParaView. The main gaps were:

- soil/material/layer scalar arrays were not selected broadly enough, especially when VTU files used names such as `SoilID`, `Layer`, `Material`, `Physical`, or point-data scalars;
- numeric soil IDs could be rendered as a continuous heat map instead of categorical layer colors;
- the external mesh grid on the four lateral directions was not drawn, because only feature edges and the bounding outline were shown;
- higher-order VTU cells such as Tet10, Hex20, Quad8/Quad9 and Triangle6 were not mapped to the correct VTK cell types.

## Changes
- Preserved VTU `CellData Scalars` and `PointData Scalars` metadata in the ASCII fallback reader.
- Added broader geology scalar detection for `soil`, `stratum`, `layer`, `lithology`, `formation`, `material`, `physical`, `gmsh`, `domain`, `region`, `zone`, and related names.
- Projected point scalar data to cell categories when ParaView-style layer labels are stored on points.
- Forced imported geology rendering through categorical scalar indices with labels, so different soil layers get discrete colors.
- Added external surface grid-line actor and four lateral side contour actors: `xmin`, `xmax`, `ymin`, `ymax`.
- Kept the surface actor free of coincident wireframe to avoid visual flower-shadow artifacts.
- Added high-order VTU cell type mapping: Tet10, Hex20, Wedge15, Pyramid13, Triangle6, Quad8, Quad9.

## Validation
- Added `tests/gui/test_vtu_paraview_style_visualization.py`.
- Verified targeted tests:
  - `tests/test_borehole_csv_importer.py`
  - `tests/test_stl_geology_loader.py`
  - `tests/gui/test_vtu_paraview_style_visualization.py`
