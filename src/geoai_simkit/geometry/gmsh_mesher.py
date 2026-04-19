from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import os
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable

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
    gmsh_executable: str | None = None
    use_python_api: bool = True


class GmshMesher:
    @staticmethod
    def find_gmsh_executable(explicit: str | None = None) -> str | None:
        candidates: list[str] = []
        if explicit:
            candidates.append(explicit)
        env_value = os.environ.get('GMSH_EXE') or os.environ.get('GMSH_PATH')
        if env_value:
            candidates.append(env_value)
        for name in ('gmsh', 'gmsh.exe'):
            found = shutil.which(name)
            if found:
                candidates.append(found)
        for candidate in candidates:
            if not candidate:
                continue
            try:
                proc = subprocess.run([candidate, '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                if proc.returncode == 0:
                    return candidate
            except Exception:
                continue
        return None

    @staticmethod
    def _python_api_available() -> bool:
        try:
            import gmsh  # noqa: F401
            return True
        except Exception:
            return False

    @classmethod
    def available(cls) -> bool:
        try:
            import meshio  # noqa: F401
        except Exception:
            return False
        return cls._python_api_available() or cls.find_gmsh_executable() is not None

    def __init__(
        self,
        options: GmshMesherOptions | None = None,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.options = options or GmshMesherOptions()
        self.progress_callback = progress_callback
        self.log_callback = log_callback

    def mesh_model(self, model: SimulationModel) -> SimulationModel:
        if pv is None:
            raise RuntimeError('pyvista is required for gmsh meshing')
        try:
            import meshio
        except Exception as exc:
            raise RuntimeError('meshio is required for gmsh meshing') from exc
        if not self.available():
            raise RuntimeError('Neither the gmsh Python package nor a gmsh executable on PATH is available.')

        data = model.mesh
        items = [(str(k), data[k]) for k in data.keys()] if isinstance(data, pv.MultiBlock) else [(model.name, data)]
        items = [(key, block) for key, block in items if block is not None and int(getattr(block, 'n_cells', 0) or 0) > 0]
        total = len(items)
        out = pv.MultiBlock()
        region_tags: list[RegionTag] = []
        cell_offset = 0
        warnings: list[str] = []
        started_at = time.perf_counter()

        backend = 'gmsh-python' if (self.options.use_python_api and self._python_api_available()) else (self.find_gmsh_executable(self.options.gmsh_executable) or 'gmsh')
        self._emit(phase='gmsh-start', value=12, message=f'Launching local gmsh mesher for {total} object(s) using {backend}.', object_count=total, log=True)
        for index, (key, block) in enumerate(items, start=1):
            region_name = self._region_name(key, block)
            try:
                self._emit(
                    phase='gmsh-object-start',
                    value=15 + int(60.0 * max(0, index - 1) / max(1, total)),
                    message=(
                        f'Gmsh meshing {key} ({index}/{total}) with target size={self.options.element_size:g}; '
                        f'source cells={int(getattr(block, "n_cells", 0) or 0)}'
                    ),
                    object_name=key,
                    object_index=index,
                    object_count=total,
                    log=True,
                )
                grid, stats = self._mesh_block(block, meshio)
            except Exception as exc:
                reason = self._format_gmsh_error(exc)
                warnings.append(f'{key}: {reason}')
                self._emit(
                    phase='gmsh-object-failed',
                    value=15 + int(60.0 * index / max(1, total)),
                    message=f'{key}: {reason}',
                    object_name=key,
                    object_index=index,
                    object_count=total,
                    severity='warning',
                    hint='Check whether the object is a closed solid; otherwise switch to voxel_hex8.',
                    log=True,
                )
                continue
            if grid is None or int(grid.n_cells) == 0:
                warnings.append(f'{key}: gmsh returned an empty volume mesh.')
                continue
            grid.cell_data['region_name'] = np.array([region_name] * grid.n_cells)
            grid.field_data['region_name'] = np.array([region_name])
            out[region_name] = grid
            region_tags.append(RegionTag(name=region_name, cell_ids=np.arange(cell_offset, cell_offset + grid.n_cells, dtype=np.int64), metadata={'source': key, 'meshed_by': 'gmsh'}))
            cell_offset += grid.n_cells
            self._emit(
                phase='gmsh-object-complete',
                value=15 + int(60.0 * index / max(1, total)),
                message=(
                    f'Gmsh completed {key} ({index}/{total}) -> {int(grid.n_cells)} cells, '
                    f'{int(grid.n_points)} points, elapsed {float(stats.get("elapsed_seconds", 0.0)):.2f}s'
                ),
                object_name=key,
                object_index=index,
                object_count=total,
                stats=stats,
                log=True,
            )

        if not out.keys():
            detail = '\n'.join(warnings[:6]) if warnings else 'No object produced a valid volume mesh.'
            raise RuntimeError('gmsh 未能生成体网格。请确认几何为闭合实体，或改用体素化。\n' + detail)

        elapsed = time.perf_counter() - started_at
        model.mesh = out if len(out.keys()) > 1 else next(out[k] for k in out.keys())
        model.region_tags = region_tags
        model.metadata['meshed_by'] = 'gmsh'
        model.metadata['mesh_summary'] = {
            'method': 'gmsh_tet',
            'object_count': total,
            'warning_count': len(warnings),
            'elapsed_seconds': elapsed,
            'regions': len(region_tags),
            'cells': int(sum(int(getattr(out[k], 'n_cells', 0) or 0) for k in out.keys())),
            'points': int(sum(int(getattr(out[k], 'n_points', 0) or 0) for k in out.keys())),
            'backend': backend,
        }
        if warnings:
            model.metadata.setdefault('mesh_warnings', []).extend(warnings)
        self._emit(
            phase='gmsh-finished',
            value=88,
            message=(
                f'Gmsh meshing finished: {model.metadata["mesh_summary"]["regions"]} region(s), '
                f'{model.metadata["mesh_summary"]["cells"]} cells, elapsed {elapsed:.2f}s.'
            ),
            summary=model.metadata['mesh_summary'],
            log=True,
        )
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
        surf = block.extract_surface(algorithm='dataset_surface').triangulate()
        if surf.n_cells == 0:
            return None, {'elapsed_seconds': 0.0}
        started_at = time.perf_counter()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            stl = td / 'in.stl'
            msh = td / 'out.msh'
            surf.save(stl)
            stats = self._mesh_with_python_api(stl, msh) if (self.options.use_python_api and self._python_api_available()) else self._mesh_with_executable(stl, msh)
            mesh = meshio_mod.read(msh)
            grid = self._meshio_to_pyvista(mesh)
            stats.setdefault('elapsed_seconds', time.perf_counter() - started_at)
            return grid, stats

    def _mesh_with_executable(self, stl: Path, msh: Path) -> dict[str, Any]:
        exe = self.find_gmsh_executable(self.options.gmsh_executable)
        if exe is None:
            raise FileNotFoundError('gmsh executable was not found on PATH.')
        started_at = time.perf_counter()
        cmd = [
            exe,
            str(stl),
            '-3',
            '-format',
            'msh4',
            '-o',
            str(msh),
            '-clmax',
            str(self.options.element_size),
            '-clmin',
            str(self.options.element_size),
            '-algo',
            str(self.options.algorithm3d),
        ]
        if self.options.optimize:
            cmd.append('-optimize')
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0 or not msh.exists():
            raise RuntimeError((proc.stderr or proc.stdout or 'gmsh failed').strip())
        return {
            'elapsed_seconds': time.perf_counter() - started_at,
            'stdout_tail': '\n'.join((proc.stdout or '').splitlines()[-8:]),
            'stderr_tail': '\n'.join((proc.stderr or '').splitlines()[-8:]),
            'backend': 'gmsh-executable',
        }

    def _mesh_with_python_api(self, stl: Path, msh: Path) -> dict[str, Any]:
        import gmsh

        started_at = time.perf_counter()
        stdout_tail = ''
        gmsh.initialize()
        try:
            gmsh.model.add('geoai_volume')
            gmsh.option.setNumber('General.Terminal', 0)
            gmsh.option.setNumber('Mesh.CharacteristicLengthMin', float(self.options.element_size))
            gmsh.option.setNumber('Mesh.CharacteristicLengthMax', float(self.options.element_size))
            gmsh.option.setNumber('Mesh.Algorithm3D', int(self.options.algorithm3d))
            gmsh.merge(str(stl))
            gmsh.model.mesh.classifySurfaces(math.radians(40.0), True, True, math.pi)
            gmsh.model.mesh.createGeometry()
            surfaces = gmsh.model.getEntities(2)
            if not surfaces:
                raise RuntimeError('gmsh python API could not recover any surfaces from the shell.')
            loop = gmsh.model.geo.addSurfaceLoop([tag for _, tag in surfaces])
            gmsh.model.geo.addVolume([loop])
            gmsh.model.geo.synchronize()
            gmsh.model.mesh.generate(3)
            if self.options.optimize:
                try:
                    gmsh.model.mesh.optimize('Netgen')
                except Exception:
                    pass
            gmsh.write(str(msh))
            try:
                stdout_tail = '\n'.join(gmsh.logger.get()[-8:])
            except Exception:
                stdout_tail = ''
        finally:
            try:
                gmsh.finalize()
            except Exception:
                pass
        if not msh.exists():
            raise RuntimeError('gmsh python API did not produce an output mesh file.')
        return {
            'elapsed_seconds': time.perf_counter() - started_at,
            'stdout_tail': stdout_tail,
            'stderr_tail': '',
            'backend': 'gmsh-python',
        }

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

    def _format_gmsh_error(self, exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        lower = text.lower()
        if 'meshio is required' in lower:
            return 'meshio is not installed, so gmsh output cannot be converted. Install requirements.txt dependencies.'
        if 'libglu.so.1' in lower:
            return 'gmsh Python package is installed, but the host is missing libGLU.so.1 / Mesa OpenGL runtime libraries.'
        if 'not found' in lower or 'no such file' in lower or 'winerror 2' in lower:
            return 'gmsh executable was not found on PATH, and the gmsh Python package is unavailable.'
        if 'self intersect' in lower or 'non manifold' in lower:
            return 'The surface appears self-intersecting or non-manifold; gmsh cannot build a valid 3D volume from it.'
        if 'unable to recover' in lower or 'surface mesh' in lower:
            return 'gmsh failed while recovering the volume from the imported shell; the object is likely open or has damaged facets.'
        return text

    def _emit(self, **payload: Any) -> None:
        if self.progress_callback is not None:
            try:
                self.progress_callback(payload)
            except Exception:
                pass
        text = str(payload.get('message') or '').strip()
        if text and payload.get('log') and self.log_callback is not None:
            try:
                self.log_callback(text)
            except Exception:
                pass
