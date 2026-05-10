from __future__ import annotations

"""Minimal PyVista preview builder used by the desktop workbench."""

from typing import Any

import numpy as np


class PreviewBuilder:
    """Render lightweight SimpleUnstructuredGrid/PyVista-like meshes.

    The class avoids importing PyVista until the GUI has already requested it.
    This keeps CLI and smoke tests headless-safe while restoring a real viewport
    path for imported STL geological surfaces.
    """

    @staticmethod
    def _region_names(mesh: Any) -> list[str]:
        values = (getattr(mesh, "cell_data", {}) or {}).get("region_name", [])
        return [str(v) for v in list(values)]

    @staticmethod
    def _to_dataset(mesh: Any):
        import pyvista as pv

        if hasattr(mesh, "cast_to_unstructured_grid") and type(mesh).__module__.startswith("pyvista"):
            return mesh
        points = np.asarray(getattr(mesh, "points", []), dtype=float).reshape((-1, 3))
        cells = [tuple(int(i) for i in cell) for cell in list(getattr(mesh, "cells", []) or [])]
        if len(points) == 0:
            return pv.PolyData()
        if not cells:
            return pv.PolyData(points)
        sizes = {len(c) for c in cells}
        if sizes == {3}:
            faces = np.asarray([[3, *c] for c in cells], dtype=np.int64).ravel()
            poly = pv.PolyData(points, faces)
            for key, values in (getattr(mesh, "cell_data", {}) or {}).items():
                try:
                    if len(values) == len(cells):
                        poly.cell_data[str(key)] = np.asarray(values)
                except Exception:
                    pass
            return poly
        if sizes == {8}:
            flat = np.asarray([[8, *c] for c in cells], dtype=np.int64).ravel()
            celltypes = np.full((len(cells),), 12, dtype=np.uint8)  # VTK_HEXAHEDRON
            grid = pv.UnstructuredGrid(flat, celltypes, points)
            for key, values in (getattr(mesh, "cell_data", {}) or {}).items():
                try:
                    if len(values) == len(cells):
                        grid.cell_data[str(key)] = np.asarray(values)
                except Exception:
                    pass
            return grid
        # Mixed preview fallback: render all vertices and triangle cells only.
        tri_cells = [c for c in cells if len(c) == 3]
        if tri_cells:
            faces = np.asarray([[3, *c] for c in tri_cells], dtype=np.int64).ravel()
            return pv.PolyData(points, faces)
        return pv.PolyData(points)

    def add_model(
        self,
        plotter: Any,
        model: Any,
        *,
        stage: str | None = None,
        selected_regions: list[str] | None = None,
        selected_blocks: list[str] | None = None,
        view_mode: str = "normal",
        stage_activation: dict[str, bool] | None = None,
        unassigned_regions: list[str] | None = None,
        conflict_regions: list[str] | None = None,
        show_edges: bool = True,
        visual_options: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, object]]:
        opts = dict(visual_options or {})
        mesh = getattr(model, "mesh", None)
        dataset = self._to_dataset(mesh)
        opacity = float(opts.get("opacity", 0.95))
        actor = plotter.add_mesh(dataset, show_edges=show_edges, opacity=opacity, name="model-preview")
        actor_map: dict[str, dict[str, object]] = {}
        for region in list(getattr(model, "region_tags", []) or []):
            actor_map[str(getattr(region, "name", "region"))] = {"actor": actor, "selected": str(getattr(region, "name", "")) in set(selected_regions or [])}
        if not actor_map:
            actor_map["model"] = {"actor": actor, "selected": False}
        return actor_map


__all__ = ["PreviewBuilder"]
