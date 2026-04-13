from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
from typing import Any

import numpy as np
try:
    import pyvista as pv
except ModuleNotFoundError:  # pragma: no cover
    pv = None

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.core.types import RegionTag


@dataclass(slots=True)
class GmshMesherOptions:
    element_size: float = 2.0
    algorithm3d: int = 1
    optimize: bool = True


class GmshMesher:
    @staticmethod
    def available() -> bool:
        try:
            import meshio  # noqa: F401
            out = subprocess.run(['gmsh', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            return out.returncode == 0
        except Exception:
            return False

    def __init__(self, options: GmshMesherOptions | None = None) -> None:
        self.options = options or GmshMesherOptions()

    def mesh_model(self, model: SimulationModel) -> SimulationModel:
        if pv is None:
            raise RuntimeError('pyvista is required for gmsh meshing')
        try:
            import meshio
        except Exception as exc:
            raise RuntimeError('meshio is required for gmsh meshing') from exc
        data = model.mesh
        items = [(str(k), data[k]) for k in data.keys()] if isinstance(data, pv.MultiBlock) else [(model.name, data)]
        out = pv.MultiBlock()
        region_tags: list[RegionTag] = []
        cell_offset = 0
        warnings: list[str] = []
        for key, block in items:
            if block is None or int(getattr(block, 'n_cells', 0)) == 0:
                continue
            region_name = self._region_name(key, block)
            try:
                grid = self._mesh_block(block, meshio)
            except Exception as exc:
                warnings.append(f'{key}: {exc}')
                continue
            if grid is None or int(grid.n_cells) == 0:
                continue
            grid.cell_data['region_name'] = np.array([region_name] * grid.n_cells)
            grid.field_data['region_name'] = np.array([region_name])
            out[region_name] = grid
            region_tags.append(RegionTag(name=region_name, cell_ids=np.arange(cell_offset, cell_offset + grid.n_cells, dtype=np.int64), metadata={'source': key, 'meshed_by': 'gmsh'}))
            cell_offset += grid.n_cells
        if not out.keys():
            raise RuntimeError('gmsh 未能生成体网格。请确认几何为闭合实体，或改用体素化。')
        model.mesh = out if len(out.keys()) > 1 else next(out[k] for k in out.keys())
        model.region_tags = region_tags
        model.metadata['meshed_by'] = 'gmsh'
        if warnings:
            model.metadata.setdefault('mesh_warnings', []).extend(warnings)
        return model

    def _region_name(self, key: str, block: Any) -> str:
        try:
            fd = getattr(block, 'field_data', {})
            if 'region_name' in fd and len(fd['region_name']):
                return str(fd['region_name'][0])
        except Exception:
            pass
        return key.split('/')[-1] or 'region'

    def _mesh_block(self, block: Any, meshio_mod):
        surf = block.extract_surface().triangulate()
        if surf.n_cells == 0:
            return None
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            stl = td / 'in.stl'
            msh = td / 'out.msh'
            surf.save(stl)
            cmd = ['gmsh', str(stl), '-3', '-format', 'msh4', '-o', str(msh), '-clmax', str(self.options.element_size), '-clmin', str(self.options.element_size), '-algo', str(self.options.algorithm3d)]
            if self.options.optimize:
                cmd.append('-optimize')
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if proc.returncode != 0 or not msh.exists():
                raise RuntimeError((proc.stderr or proc.stdout or 'gmsh failed').strip())
            mesh = meshio_mod.read(msh)
            return self._meshio_to_pyvista(mesh)

    def _meshio_to_pyvista(self, mesh):
        mapping = {'tetra': 10, 'hexahedron': 12, 'wedge': 13, 'pyramid': 14}
        cell_blocks = []
        cell_types = []
        for cb in mesh.cells:
            ctype = getattr(cb, 'type', None)
            data = getattr(cb, 'data', None)
            if ctype not in mapping or data is None or len(data) == 0:
                continue
            arr = np.asarray(data, dtype=np.int64)
            npts = arr.shape[1]
            cell_blocks.append(np.hstack([np.full((arr.shape[0], 1), npts, dtype=np.int64), arr]).ravel())
            cell_types.append(np.full(arr.shape[0], mapping[ctype], dtype=np.uint8))
        if not cell_blocks:
            return None
        return pv.UnstructuredGrid(np.concatenate(cell_blocks), np.concatenate(cell_types), np.asarray(mesh.points[:, :3], dtype=float))
