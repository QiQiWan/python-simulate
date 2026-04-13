from __future__ import annotations

from collections import defaultdict

import numpy as np
import pyvista as pv


def build_point_adjacency(grid: pv.UnstructuredGrid) -> tuple[np.ndarray, np.ndarray]:
    indptr = [0]
    neighbors: list[int] = []
    acc: dict[int, set[int]] = defaultdict(set)
    cells = grid.cells
    offset = 0
    while offset < len(cells):
        n = int(cells[offset])
        pts = cells[offset + 1: offset + 1 + n]
        for i in pts:
            for j in pts:
                if i != j:
                    acc[int(i)].add(int(j))
        offset += n + 1
    for pid in range(grid.n_points):
        neigh = sorted(acc.get(pid, set()))
        neighbors.extend(neigh)
        indptr.append(len(neighbors))
    return np.asarray(indptr, dtype=np.int32), np.asarray(neighbors, dtype=np.int32)
