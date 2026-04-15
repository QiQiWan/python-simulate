from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import math
import numpy as np

try:
    import pyvista as pv
except ModuleNotFoundError:  # pragma: no cover
    class _DummyDataSet:
        pass
    class _DummyMultiBlock(dict):
        def keys(self):
            return super().keys()
    class _PVStub:
        DataSet = _DummyDataSet
        MultiBlock = _DummyMultiBlock
    pv = _PVStub()

from geoai_simkit.core.model import SimulationModel


@dataclass(slots=True)
class MeshEngineOptions:
    element_family: str = 'auto'
    global_size: float = 2.0
    padding: float = 0.0
    local_refinement: bool = True
    refinement_trigger_count: int = 4
    refinement_ratio: float = 0.65
    only_material_bound_geometry: bool = True
    keep_geometry_copy: bool = True
    max_workers: int = 0


@dataclass(slots=True)
class MeshingTarget:
    block_key: str
    region_name: str
    object_key: str | None = None
    role: str = ''
    material_name: str | None = None
    bbox: tuple[float, float, float, float, float, float] | None = None
    object_density: int = 1
    target_size: float = 2.0
    strategy: str = 'uniform'
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_element_family(value: str | None) -> str:
    text = str(value or 'auto').strip().lower()
    aliases = {
        'voxel_hex8': 'hex8',
        'gmsh_tet': 'tet4',
        'tet': 'tet4',
        'tetra': 'tet4',
        'hex': 'hex8',
        'hexa': 'hex8',
    }
    return aliases.get(text, text if text in {'auto', 'tet4', 'hex8'} else 'auto')


class MeshEngine:
    """Geometry-first meshing orchestrator.

    The engine keeps the import step purely geometric and turns meshing into an
    explicit, configurable pipeline step. It inspects geometry objects, region
    names, and material bindings to decide which blocks should be meshed and how
    aggressively they should be refined.
    """

    def __init__(
        self,
        options: MeshEngineOptions | None = None,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.options = options or MeshEngineOptions()
        self.progress_callback = progress_callback
        self.log_callback = log_callback

    def collect_targets(self, model: SimulationModel) -> list[MeshingTarget]:
        data = model.mesh
        if isinstance(data, pv.MultiBlock):
            items = [(str(k), data[k]) for k in data.keys()]
        else:
            items = [(model.name, data)]
        items = [(key, block) for key, block in items if block is not None and int(getattr(block, 'n_cells', 0) or 0) > 0]
        if not items:
            return []

        material_names = {binding.region_name: binding.material_name for binding in model.materials}
        by_region = {rec.region_name: rec for rec in model.object_records if rec.region_name}
        bboxes: list[tuple[str, tuple[float, float, float, float, float, float]]] = []
        for key, block in items:
            bbox = self._safe_bounds(block)
            if bbox is not None:
                bboxes.append((key, bbox))

        targets: list[MeshingTarget] = []
        for key, block in items:
            region_name = self._region_name(key, block)
            rec = by_region.get(region_name) or model.object_record(key)
            material_name = material_names.get(region_name)
            if self.options.only_material_bound_geometry and material_names and material_name is None:
                continue
            role = ''
            if rec is not None:
                role = str(rec.metadata.get('role') or '')
            bbox = self._safe_bounds(block)
            density = self._object_density(key, bbox, bboxes)
            target_size, strategy = self._target_size_for(region_name, role, material_name, density)
            targets.append(
                MeshingTarget(
                    block_key=key,
                    region_name=region_name,
                    object_key=rec.key if rec is not None else None,
                    role=role,
                    material_name=material_name,
                    bbox=bbox,
                    object_density=density,
                    target_size=target_size,
                    strategy=strategy,
                    metadata={
                        'n_source_cells': int(getattr(block, 'n_cells', 0) or 0),
                        'n_source_points': int(getattr(block, 'n_points', 0) or 0),
                    },
                )
            )
        return targets

    def mesh_model(self, model: SimulationModel) -> SimulationModel:
        element_family = normalize_element_family(self.options.element_family)
        targets = self.collect_targets(model)
        if not targets:
            if self.options.only_material_bound_geometry and model.materials:
                raise RuntimeError('No geometry objects are associated with materials, so the mesh engine has nothing to mesh.')
            raise RuntimeError('No geometry objects are available for meshing.')

        source_data = model.mesh
        blocks = source_data if isinstance(source_data, pv.MultiBlock) else None
        meshed_blocks = pv.MultiBlock() if hasattr(pv, 'MultiBlock') else {}
        meshed_regions = []
        warnings: list[str] = []
        total = len(targets)
        geometry_snapshot = self._copy_data(source_data) if self.options.keep_geometry_copy else None
        self._emit('mesh-engine-start', 5, f'Geometry-first meshing started for {total} target(s).', object_count=total, log=True)

        from geoai_simkit.core.types import RegionTag
        cell_offset = 0
        for index, target in enumerate(targets, start=1):
            block = blocks[target.block_key] if blocks is not None else source_data
            phase_prefix = f'[{index}/{total}] {target.region_name}'
            self._emit(
                'mesh-engine-target',
                10 + int(70.0 * max(index - 1, 0) / max(total, 1)),
                f'{phase_prefix}: meshing as {element_family} with target size {target.target_size:g} ({target.strategy}).',
                target=self._target_payload(target),
                log=True,
            )
            temp_model = SimulationModel(name=target.region_name, mesh=self._copy_data(block) or block)
            temp_model.metadata['geometry_state'] = 'geometry'
            temp_model.metadata['source_block'] = target.block_key
            temp_model.materials = [binding for binding in model.materials if binding.region_name == target.region_name]
            try:
                meshed = self._mesh_single_target(temp_model, target, element_family)
            except Exception as exc:
                warnings.append(f'{target.region_name}: {exc}')
                self._emit(
                    'mesh-engine-target-failed',
                    10 + int(70.0 * index / max(total, 1)),
                    f'{phase_prefix}: {exc}',
                    target=self._target_payload(target),
                    severity='warning',
                    log=True,
                )
                continue
            result_grid = meshed.mesh if not isinstance(meshed.mesh, pv.MultiBlock) else next((meshed.mesh[k] for k in meshed.mesh.keys()), None)
            if result_grid is None or int(getattr(result_grid, 'n_cells', 0) or 0) <= 0:
                warnings.append(f'{target.region_name}: meshing returned an empty grid')
                continue
            result_grid.field_data['region_name'] = np.array([target.region_name])
            result_grid.cell_data['region_name'] = np.array([target.region_name] * int(result_grid.n_cells))
            meshed_blocks[target.region_name] = result_grid
            meshed_regions.append(RegionTag(name=target.region_name, cell_ids=np.arange(cell_offset, cell_offset + int(result_grid.n_cells), dtype=np.int64), metadata={'source': target.block_key, 'strategy': target.strategy, 'target_size': target.target_size}))
            cell_offset += int(result_grid.n_cells)
            self._emit(
                'mesh-engine-target-done',
                10 + int(70.0 * index / max(total, 1)),
                f'{phase_prefix}: produced {int(result_grid.n_cells)} cells / {int(result_grid.n_points)} points.',
                target=self._target_payload(target),
                log=True,
            )

        if not getattr(meshed_blocks, 'keys', lambda: [])():
            detail = '\n'.join(warnings[:8]) if warnings else 'Meshing did not produce any volume cells.'
            raise RuntimeError(detail)

        out_model = model
        out_model.mesh = meshed_blocks if len(meshed_blocks.keys()) > 1 else next((meshed_blocks[k] for k in meshed_blocks.keys()), source_data)
        out_model.region_tags = meshed_regions
        out_model.metadata['geometry_state'] = 'meshed'
        out_model.metadata['meshed_by'] = f'geometry_engine::{element_family}'
        out_model.metadata['mesh_engine'] = {
            'element_family': element_family,
            'global_size': float(self.options.global_size),
            'padding': float(self.options.padding),
            'local_refinement': bool(self.options.local_refinement),
            'refinement_ratio': float(self.options.refinement_ratio),
            'refinement_trigger_count': int(self.options.refinement_trigger_count),
            'only_material_bound_geometry': bool(self.options.only_material_bound_geometry),
            'target_count': total,
            'warnings': warnings,
            'targets': [self._target_payload(target) for target in targets],
        }
        if geometry_snapshot is not None:
            out_model.metadata['geometry_snapshot'] = 'available'
            out_model.metadata['_geometry_snapshot_obj'] = geometry_snapshot
        if warnings:
            out_model.metadata.setdefault('mesh_warnings', []).extend(warnings)
        self._emit('mesh-engine-finished', 92, f'Meshing finished with {len(meshed_regions)} region(s).', summary=out_model.metadata['mesh_engine'], log=True)
        return out_model

    def _target_payload(self, target: MeshingTarget) -> dict[str, Any]:
        return asdict(target)

    def _copy_data(self, data: Any) -> Any:
        if data is None or not hasattr(data, 'copy'):
            return None
        try:
            return data.copy(deep=True)
        except TypeError:
            try:
                return data.copy()
            except Exception:
                return None
        except Exception:
            return None

    def _mesh_single_target(self, model: SimulationModel, target: MeshingTarget, element_family: str) -> SimulationModel:
        if element_family == 'hex8':
            from geoai_simkit.geometry.voxelize import VoxelMesher, VoxelizeOptions
            return VoxelMesher(
                VoxelizeOptions(
                    cell_size=float(target.target_size),
                    padding=float(self.options.padding),
                    worker_count=max(1, int(self.options.max_workers or 0)),
                ),
                progress_callback=self._forward_nested,
                log_callback=self.log_callback,
            ).voxelize_model(model)
        try:
            from geoai_simkit.geometry.gmsh_mesher import GmshMesher, GmshMesherOptions
            return GmshMesher(
                GmshMesherOptions(element_size=float(target.target_size)),
                progress_callback=self._forward_nested,
                log_callback=self.log_callback,
            ).mesh_model(model)
        except Exception:
            if element_family == 'tet4':
                raise
            from geoai_simkit.geometry.voxelize import VoxelMesher, VoxelizeOptions
            self._emit('mesh-engine-fallback', None, f'{target.region_name}: tetra meshing failed, falling back to hex8 voxelization.', target=self._target_payload(target), severity='warning', log=True)
            return VoxelMesher(
                VoxelizeOptions(
                    cell_size=float(target.target_size),
                    padding=float(self.options.padding),
                    worker_count=max(1, int(self.options.max_workers or 0)),
                ),
                progress_callback=self._forward_nested,
                log_callback=self.log_callback,
            ).voxelize_model(model)

    def _forward_nested(self, payload: dict[str, Any]) -> None:
        if isinstance(payload, dict):
            self._emit(payload.get('phase', 'mesh-engine-nested'), payload.get('value'), str(payload.get('message', '') or '').strip(), **payload)

    def _region_name(self, key: str, block: Any) -> str:
        try:
            fd = getattr(block, 'field_data', {})
            if 'region_name' in fd and len(fd['region_name']):
                return str(fd['region_name'][0])
        except Exception:
            pass
        return key.split('/')[-1] or key

    def _safe_bounds(self, block: Any) -> tuple[float, float, float, float, float, float] | None:
        try:
            bounds = getattr(block, 'bounds', None)
            if bounds is None or len(bounds) != 6:
                return None
            return tuple(float(v) for v in bounds)
        except Exception:
            return None

    def _object_density(self, key: str, bbox, all_boxes: list[tuple[str, tuple[float, float, float, float, float, float]]]) -> int:
        if bbox is None:
            return 1
        count = 0
        ax0, ax1, ay0, ay1, az0, az1 = bbox
        for other_key, other_bbox in all_boxes:
            if other_key == key:
                count += 1
                continue
            bx0, bx1, by0, by1, bz0, bz1 = other_bbox
            if not (ax1 < bx0 or ax0 > bx1 or ay1 < by0 or ay0 > by1 or az1 < bz0 or az0 > bz1):
                count += 1
        return max(1, count)

    def _target_size_for(self, region_name: str, role: str, material_name: str | None, density: int) -> tuple[float, str]:
        size = max(0.05, float(self.options.global_size))
        strategy = 'uniform'
        if not self.options.local_refinement:
            return size, strategy
        refine = False
        if density >= max(2, int(self.options.refinement_trigger_count)):
            refine = True
            strategy = f'local-density x{density}'
        if role in {'wall', 'beam', 'column', 'support', 'slab'}:
            refine = True
            strategy = f'role-sensitive:{role}'
        if material_name and material_name.lower() in {'hss', 'hs_small', 'mohr_coulomb'}:
            refine = True
            strategy = f'material-sensitive:{material_name}'
        if 'excavation' in region_name.lower():
            refine = True
            strategy = 'excavation-local'
        if refine:
            size = max(0.05, size * float(self.options.refinement_ratio))
        return size, strategy

    def _emit(self, phase: str, value: Any, message: str, **payload: Any) -> None:
        data = dict(payload)
        data['phase'] = phase
        if value is not None:
            try:
                data['value'] = int(value)
            except Exception:
                pass
        data['message'] = message
        if self.progress_callback is not None:
            try:
                self.progress_callback(data)
            except Exception:
                pass
        if message and payload.get('log') and self.log_callback is not None:
            try:
                self.log_callback(message)
            except Exception:
                pass
