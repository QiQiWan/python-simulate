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
    use_occ_fragmented: bool = True


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
        # Do not import gmsh here. On hosts without libGLU/OpenCascade runtime,
        # importing the wheel can block or raise before the mesher can fall back.
        try:
            import importlib.util
            return importlib.util.find_spec('gmsh') is not None
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

        occ_warning = None
        if self._should_use_occ_fragmented(model):
            try:
                return self._mesh_occ_fragmented_model(model, meshio)
            except Exception as exc:
                occ_warning = self._format_gmsh_error(exc)
                self._emit(
                    phase='gmsh-occ-fragmented-fallback',
                    value=14,
                    message=f'OCC fragmented volume meshing failed or is unavailable ({occ_warning}); falling back to legacy shell meshing.',
                    severity='warning',
                    log=True,
                )

        data = model.mesh
        items = [(str(k), data[k]) for k in data.keys()] if isinstance(data, pv.MultiBlock) else [(model.name, data)]
        items = [(key, block) for key, block in items if block is not None and int(getattr(block, 'n_cells', 0) or 0) > 0]
        total = len(items)
        out = pv.MultiBlock()
        region_tags: list[RegionTag] = []
        cell_offset = 0
        warnings: list[str] = []
        if occ_warning:
            warnings.append(f'OCC fragmented meshing: {occ_warning}')
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
            grid.field_data['topology_entity_id'] = np.array([f'solid:{region_name}'])
            grid.field_data['topology_kind'] = np.array(['solid'])
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

    def _should_use_occ_fragmented(self, model: SimulationModel) -> bool:
        if not bool(self.options.use_occ_fragmented) or not bool(self.options.use_python_api):
            return False
        occ = dict(model.metadata.get('geometry.occ_partition', {}) or {})
        payload = dict(model.metadata.get('geometry.editable_payload', {}) or {})
        blocks = list(payload.get('block_rows', []) or [])
        strat = dict(payload.get('stratigraphy', model.metadata.get('geometry.stratigraphy', {}) or {}) or {})
        has_occ_split = int(occ.get('executable_tool_count', 0) or 0) > 0
        has_stratigraphy_layers = bool(strat.get('occ_layer_volume_enabled') and list(strat.get('layer_solids', []) or []))
        return bool(blocks) and (has_occ_split or has_stratigraphy_layers) and self._python_api_available()

    def _mesh_occ_fragmented_model(self, model: SimulationModel, meshio_mod: Any) -> SimulationModel:
        from geoai_simkit.geometry.occ_partition import GmshOCCPartitioner

        payload = dict(model.metadata.get('geometry.editable_payload', {}) or {})
        blocks = [dict(row) for row in list(payload.get('block_rows', []) or []) if isinstance(row, dict)]
        split_defs = [dict(row) for row in list(dict(payload.get('partition_plan', {}) or {}).get('split_definitions', []) or []) if isinstance(row, dict)]
        # Older payloads do not keep split_definitions explicitly; rebuild them
        # from user geometry metadata when available, otherwise use OCC tools.
        if not split_defs:
            split_defs = [dict(row) for row in list(payload.get('block_splits', []) or []) if isinstance(row, dict)]
        if not split_defs:
            occ = dict(model.metadata.get('geometry.occ_partition', {}) or {})
            for tool in list(occ.get('tools', []) or []):
                meta = dict(tool.get('metadata', {}) or {})
                row = {
                    'name': tool.get('name'),
                    'target_block': tool.get('target_block'),
                    'kind': tool.get('kind'),
                    'point': tool.get('point'),
                    'normal': tool.get('normal'),
                }
                if tool.get('kind') == 'polyline_extrusion':
                    row.update({'polyline': meta.get('polyline'), 'z_min': meta.get('z_min'), 'z_max': meta.get('z_max')})
                split_defs.append(row)
        protected = [dict(row) for row in list(model.metadata.get('geometry.protected_surface_rows', []) or []) if isinstance(row, dict)]
        if not protected:
            protected = [dict(row) for row in list(dict(payload.get('partition_plan', {}) or {}).get('protected_surfaces', []) or []) if isinstance(row, dict)]
        mesh_size_controls = [dict(row) for row in list(payload.get('mesh_size_controls', []) or []) if isinstance(row, dict)]
        mesh_size_controls.extend([dict(row) for row in list(model.metadata.get('geometry.mesh_size_controls', []) or []) if isinstance(row, dict)])
        stratigraphy_plan = dict(payload.get('stratigraphy', model.metadata.get('geometry.stratigraphy', {}) or {}) or {})
        started_at = time.perf_counter()
        with tempfile.TemporaryDirectory() as td:
            msh = Path(td) / 'occ_fragmented.msh'
            self._emit(phase='gmsh-occ-fragmented-start', value=13, message=f'Launching Gmsh OCC fragmented volume meshing for {len(blocks)} block(s) and {len(split_defs)} split tool(s).', log=True)
            meta = GmshOCCPartitioner(
                characteristic_length=float(self.options.element_size),
                algorithm3d=int(self.options.algorithm3d),
                optimize=bool(self.options.optimize),
            ).mesh_fragmented_model(blocks, split_defs, msh, protected_surfaces=protected, mesh_size_controls=mesh_size_controls, stratigraphy_plan=stratigraphy_plan)
            mesh = meshio_mod.read(msh)
            from geoai_simkit.geometry.face_sets import FaceSetExtractor

            face_sets = FaceSetExtractor().extract_from_meshio(mesh, meta)
            grid, convert_meta = self._meshio_to_pyvista_with_physical(mesh, meta)
        if grid is None or int(getattr(grid, 'n_cells', 0) or 0) == 0:
            raise RuntimeError('OCC fragmented meshing produced an empty volume grid.')
        region_tags = self._region_tags_from_grid(grid, meta)
        from geoai_simkit.geometry.brep_document import build_brep_document_from_occ_meta
        from geoai_simkit.geometry.mesh_quality import MeshQualityEvaluator
        from geoai_simkit.geometry.binding_transfer import BindingTransferManager
        from geoai_simkit.geometry.dirty_state import GeometryDirtyStateManager

        brep_document = build_brep_document_from_occ_meta(meta)
        mesh_quality = MeshQualityEvaluator().evaluate(grid, face_sets=face_sets, brep_document=brep_document)
        binding_transfer = BindingTransferManager().transfer(dict(editable_payload.get("topology_entity_bindings", {}) or {}), editable_payload=editable_payload, brep_document=brep_document, face_sets=face_sets)
        dirty_state = GeometryDirtyStateManager().mark_mesh_current(dict(editable_payload), mesh_options={"element_size": float(self.options.element_size), "backend": "gmsh_occ_fragmented"}, summary=dict(face_sets.get("summary", {}) or {})).get("geometry_dirty_state", {})
        elapsed = time.perf_counter() - started_at
        model.mesh = grid
        model.region_tags = region_tags
        model.metadata['meshed_by'] = 'gmsh_occ_fragmented'
        model.metadata['mesh.occ_fragmented'] = meta
        model.metadata['mesh.occ_fragmented_conversion'] = convert_meta
        model.metadata['mesh.face_sets'] = face_sets
        model.metadata['mesh.quality_report'] = mesh_quality
        model.metadata['geometry.brep_document'] = brep_document
        model.metadata["geometry.binding_transfer_report"] = binding_transfer
        model.metadata["geometry.dirty_state"] = dirty_state
        model.metadata['geometry.face_set_rows'] = list(meta.get('physical_surface_rows', []) or [])
        model.metadata['geometry.solver_face_set_rows'] = list(face_sets.get('face_sets', []) or [])
        editable_payload = dict(model.metadata.get('geometry.editable_payload', {}) or {})
        editable_payload['brep_document'] = brep_document
        editable_payload["binding_transfer_report"] = binding_transfer
        editable_payload["geometry_dirty_state"] = dirty_state
        editable_payload["topology_entity_bindings"] = dict(binding_transfer.get("transferred_bindings", editable_payload.get("topology_entity_bindings", {})) or {})
        editable_payload['solver_face_set_rows'] = list(face_sets.get('face_sets', []) or [])
        editable_payload['mesh_quality_report'] = mesh_quality
        model.metadata['geometry.editable_payload'] = editable_payload
        model.metadata['mesh_summary'] = {
            'method': 'gmsh_occ_fragmented_tet4',
            'backend': 'gmsh.model.occ',
            'object_count': len(blocks),
            'split_tool_count': len(split_defs),
            'stratigraphy_layer_volume_count': int(dict(meta.get('summary', {}) or {}).get('stratigraphy_layer_volume_count', 0) or 0),
            'regions': len(region_tags),
            'cells': int(grid.n_cells),
            'points': int(grid.n_points),
            'elapsed_seconds': elapsed,
            'physical_volume_count': int(dict(meta.get('summary', {}) or {}).get('fragmented_volume_count', 0)),
            'physical_surface_count': int(dict(meta.get('summary', {}) or {}).get('physical_surface_count', 0)),
            'solver_ready_face_set_count': int(dict(face_sets.get('summary', {}) or {}).get('solver_ready_face_set_count', 0)),
            'mesh_quality_ok': bool(dict(mesh_quality.get('summary', {}) or {}).get('quality_ok', False)),
            'mesh_bad_cell_count': int(dict(mesh_quality.get('summary', {}) or {}).get('bad_cell_count', 0)),
            'mesh_size_field_count': int(dict(dict(meta.get('mesh_size_field_plan', {}) or {}).get('summary', {}) or {}).get('field_count', 0)),
            'binding_transfer_invalid_count': int(dict(binding_transfer.get('summary', {}) or {}).get('invalid_binding_count', 0)),
            'geometry_requires_remesh': bool(dirty_state.get('requires_remesh', False)),
        }
        self._emit(phase='gmsh-occ-fragmented-finished', value=88, message=f'OCC fragmented meshing finished: {len(region_tags)} region set(s), {int(grid.n_cells)} cells, {int(grid.n_points)} points.', summary=model.metadata['mesh_summary'], log=True)
        return model

    def _physical_name_maps(self, mesh: Any) -> tuple[dict[int, str], dict[int, str]]:
        volume: dict[int, str] = {}
        surface: dict[int, str] = {}
        field_data = getattr(mesh, 'field_data', {}) or {}
        for name, raw in field_data.items():
            try:
                arr = np.asarray(raw).ravel()
                phys = int(arr[0])
                dim = int(arr[1]) if arr.size > 1 else -1
            except Exception:
                continue
            if dim == 3:
                volume[phys] = str(name)
            elif dim == 2:
                surface[phys] = str(name)
        return volume, surface

    def _cell_data_array(self, mesh: Any, key: str, block_index: int, cell_type: str, n: int, default: int = 0) -> np.ndarray:
        cell_data = getattr(mesh, 'cell_data', {}) or {}
        if isinstance(cell_data, dict) and key in cell_data:
            try:
                return np.asarray(cell_data[key][block_index], dtype=np.int64)
            except Exception:
                pass
        cdict = getattr(mesh, 'cell_data_dict', {}) or {}
        if isinstance(cdict, dict):
            try:
                return np.asarray(cdict.get(key, {}).get(cell_type, np.full(n, default)), dtype=np.int64)
            except Exception:
                pass
        return np.full(n, default, dtype=np.int64)

    def _region_name_from_physical(self, physical_id: int, physical_names: dict[int, str], fallback: str = 'occ_region') -> str:
        name = physical_names.get(int(physical_id), '')
        if name.startswith('region::') and '::occ_volume::' in name:
            return name.split('region::', 1)[1].split('::occ_volume::', 1)[0]
        return fallback

    def _meshio_to_pyvista_with_physical(self, mesh: Any, occ_meta: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        mapping = {'tetra': 10, 'hexahedron': 12, 'wedge': 13, 'pyramid': 14}
        phys_name_by_id, surface_phys_name_by_id = self._physical_name_maps(mesh)
        volume_rows_by_physical = {int(row.get('physical_id')): dict(row) for row in list(occ_meta.get('physical_volume_rows', []) or []) if row.get('physical_id') is not None}
        cell_blocks = []
        cell_types = []
        region_names: list[str] = []
        physical_ids: list[int] = []
        geom_tags: list[int] = []
        source_blocks: list[str] = []
        roles: list[str] = []
        for block_index, cb in enumerate(mesh.cells):
            ctype = getattr(cb, 'type', None)
            data = getattr(cb, 'data', None)
            if ctype not in mapping or data is None or len(data) == 0:
                continue
            arr = np.asarray(data, dtype=np.int64)
            npts = arr.shape[1]
            ncell = arr.shape[0]
            phys = self._cell_data_array(mesh, 'gmsh:physical', block_index, str(ctype), ncell, default=0)
            geom = self._cell_data_array(mesh, 'gmsh:geometrical', block_index, str(ctype), ncell, default=0)
            cell_blocks.append(np.hstack([np.full((ncell, 1), npts, dtype=np.int64), arr]).ravel())
            cell_types.append(np.full(ncell, mapping[ctype], dtype=np.uint8))
            for pid, gid in zip(phys, geom):
                row = volume_rows_by_physical.get(int(pid), {})
                region = str(row.get('region_name') or self._region_name_from_physical(int(pid), phys_name_by_id))
                region_names.append(region)
                physical_ids.append(int(pid))
                geom_tags.append(int(gid))
                source_blocks.append(str(row.get('source_block') or region))
                roles.append(str(row.get('role') or ''))
        if not cell_blocks:
            return None, {'volume_cell_count': 0, 'surface_physical_group_count': len(surface_phys_name_by_id)}
        grid = pv.UnstructuredGrid(np.concatenate(cell_blocks), np.concatenate(cell_types), np.asarray(mesh.points[:, :3], dtype=float))
        grid.cell_data['region_name'] = np.asarray(region_names, dtype='<U128')
        grid.cell_data['gmsh_physical_id'] = np.asarray(physical_ids, dtype=np.int64)
        grid.cell_data['occ_volume_tag'] = np.asarray(geom_tags, dtype=np.int64)
        grid.cell_data['source_block'] = np.asarray(source_blocks, dtype='<U128')
        grid.cell_data['role'] = np.asarray(roles, dtype='<U64')
        grid.field_data['mesh_contract'] = np.array(['occ_fragmented_volume_mesh_v1'])
        grid.field_data['topology_kind'] = np.array(['occ_fragmented_solid_mesh'])
        return grid, {
            'volume_cell_count': int(grid.n_cells),
            'physical_volume_count': len(phys_name_by_id),
            'physical_surface_count': len(surface_phys_name_by_id),
            'surface_physical_names': dict(surface_phys_name_by_id),
        }

    def _region_tags_from_grid(self, grid: Any, occ_meta: dict[str, Any]) -> list[RegionTag]:
        names = [str(v) for v in list(grid.cell_data.get('region_name', []))]
        rows_by_region: dict[str, dict[str, Any]] = {}
        for row in list(occ_meta.get('physical_volume_rows', []) or []):
            region = str(row.get('region_name') or '')
            rows_by_region.setdefault(region, row)
        tags: list[RegionTag] = []
        for region in sorted(set(names)):
            ids = np.asarray([idx for idx, name in enumerate(names) if name == region], dtype=np.int64)
            tags.append(RegionTag(name=region, cell_ids=ids, metadata={'source': 'gmsh_occ_fragmented', 'meshed_by': 'gmsh_occ_fragmented', **dict(rows_by_region.get(region, {}) or {})}))
        return tags

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
        cmd = [exe, str(stl), '-3', '-format', 'msh4', '-o', str(msh), '-clmax', str(self.options.element_size), '-clmin', str(self.options.element_size), '-algo', str(self.options.algorithm3d)]
        if self.options.optimize:
            cmd.append('-optimize')
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0 or not msh.exists():
            raise RuntimeError((proc.stderr or proc.stdout or 'gmsh failed').strip())
        return {'elapsed_seconds': time.perf_counter() - started_at, 'stdout_tail': '\n'.join((proc.stdout or '').splitlines()[-8:]), 'stderr_tail': '\n'.join((proc.stderr or '').splitlines()[-8:]), 'backend': 'gmsh-executable'}

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
        return {'elapsed_seconds': time.perf_counter() - started_at, 'stdout_tail': stdout_tail, 'stderr_tail': '', 'backend': 'gmsh-python'}

    def _meshio_to_pyvista(self, mesh: Any):
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
