from __future__ import annotations

from typing import Iterable, Any

import numpy as np
import pyvista as pv

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.post.stage_mesh import build_stage_dataset

TYPE_COLORS = {
    'IfcWall': '#5c6f82', 'IfcSlab': '#c28743', 'IfcBeam': '#8b6f3a', 'IfcColumn': '#6c7a89', 'IfcBuildingElementProxy': '#c95f5f',
    'soil': '#b9965b', 'wall': '#5c6f82', 'support': '#6b8e23', 'beam': '#8b6f3a', 'column': '#6c7a89', 'slab': '#c28743', 'boundary': '#7b68ee', 'opening': '#e67e22',
}

ACTIVE_COLOR = '#4caf50'
INACTIVE_COLOR = '#b0bec5'
UNASSIGNED_COLOR = '#ff5252'
CONFLICT_COLOR = '#ab47bc'


class PreviewBuilder:
    def add_model(
        self,
        plotter: pv.Plotter,
        model: SimulationModel,
        scalars: str | None = None,
        stage: str | None = None,
        selected_regions: Iterable[str] | None = None,
        selected_blocks: Iterable[str] | None = None,
        displacement_scale: float = 1.0,
        view_mode: str = 'normal',
        stage_activation: dict[str, bool] | None = None,
        unassigned_regions: Iterable[str] | None = None,
        conflict_regions: Iterable[str] | None = None,
        show_edges: bool = False,
        bad_cell_ids: Iterable[int] | None = None,
        visual_options: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        selected_regions = set(selected_regions or [])
        selected_blocks = set(selected_blocks or [])
        unassigned_regions = set(unassigned_regions or [])
        conflict_regions = set(conflict_regions or [])
        bad_cell_ids = np.asarray(list(bad_cell_ids or []), dtype=int)
        visual_options = dict(visual_options or {})
        opacity_default = float(visual_options.get('opacity', 1.0))
        cmap = visual_options.get('cmap') or None
        show_scalar_bar = bool(visual_options.get('show_scalar_bar', True))
        scalar_range = visual_options.get('scalar_range')
        clip_axis = str(visual_options.get('clip_axis', 'none'))
        clip_ratio = float(visual_options.get('clip_ratio', 0.5))
        has_selection = bool(selected_regions or selected_blocks)
        visible_map = {rec.key: bool(getattr(rec, 'visible', True)) for rec in model.object_records}
        pickable_map = {rec.key: bool(getattr(rec, 'pickable', True)) and bool(getattr(rec, 'visible', True)) and (not bool(getattr(rec, 'locked', False))) for rec in model.object_records}
        data = build_stage_dataset(model, stage, displacement_scale=displacement_scale) if stage else model.mesh
        kwargs = {'show_edges': bool(show_edges), 'opacity': opacity_default}
        if cmap:
            kwargs['cmap'] = cmap
        if scalar_range is not None:
            kwargs['clim'] = scalar_range
        kwargs['show_scalar_bar'] = show_scalar_bar
        if scalars:
            kwargs['scalars'] = scalars
        actor_map: dict[str, dict[str, Any]] = {}
        if isinstance(data, pv.MultiBlock):
            for name in data.keys():
                block = data[name]
                if block is None:
                    continue
                meta = self._block_meta(name, block)
                object_key = meta.get('object_key')
                if object_key and not visible_map.get(object_key, True):
                    continue
                highlight = object_key in selected_blocks or str(name) in selected_blocks or meta.get('region_name') in selected_regions
                mesh_kwargs = dict(kwargs)
                active = True if not stage_activation else bool(stage_activation.get(meta.get('region_name') or '', True))
                if scalars is None:
                    if view_mode == 'stage_activity' and stage is not None:
                        mesh_kwargs.setdefault('color', ACTIVE_COLOR if active else INACTIVE_COLOR)
                    elif view_mode == 'validation_regions':
                        region_name = meta.get('region_name') or ''
                        if region_name in conflict_regions:
                            mesh_kwargs.setdefault('color', CONFLICT_COLOR)
                        elif region_name in unassigned_regions:
                            mesh_kwargs.setdefault('color', UNASSIGNED_COLOR)
                        else:
                            mesh_kwargs.setdefault('color', self._block_color(meta))
                    else:
                        mesh_kwargs.setdefault('color', self._block_color(meta))
                if view_mode == 'stage_activity' and stage is not None:
                    mesh_kwargs['opacity'] = 0.98 if active else 0.12
                elif view_mode == 'validation_regions':
                    region_name = meta.get('region_name') or ''
                    if region_name in conflict_regions or region_name in unassigned_regions:
                        mesh_kwargs['opacity'] = 0.98
                        mesh_kwargs['show_edges'] = True
                        mesh_kwargs['edge_color'] = '#212121'
                    elif has_selection:
                        mesh_kwargs['opacity'] = 0.15 if not highlight else 0.98
                    else:
                        mesh_kwargs['opacity'] = 0.32
                elif has_selection:
                    mesh_kwargs['opacity'] = 0.98 if highlight else 0.18
                if highlight:
                    mesh_kwargs['show_edges'] = True
                    mesh_kwargs['edge_color'] = '#ffca28'
                actor_name = f'block:{name}'
                actor = plotter.add_mesh(block, name=actor_name, pickable=pickable_map.get(object_key or '', True), **mesh_kwargs)
                meta['actor'] = actor
                actor_map[actor_name] = meta
        else:
            grid = data
            if clip_axis in {'x', 'y', 'z'}:
                try:
                    bounds = getattr(grid, 'bounds', None)
                    if bounds and len(bounds) == 6:
                        if clip_axis == 'x':
                            lo, hi = bounds[0], bounds[1]; origin = (lo + (hi - lo) * clip_ratio, 0.0, 0.0); normal = (1, 0, 0)
                        elif clip_axis == 'y':
                            lo, hi = bounds[2], bounds[3]; origin = (0.0, lo + (hi - lo) * clip_ratio, 0.0); normal = (0, 1, 0)
                        else:
                            lo, hi = bounds[4], bounds[5]; origin = (0.0, 0.0, lo + (hi - lo) * clip_ratio); normal = (0, 0, 1)
                        grid = grid.clip(normal=normal, origin=origin, invert=False)
                except Exception:
                    pass
            if view_mode == 'mesh_quality':
                qvals = np.zeros(grid.n_cells, dtype=np.int32)
                if bad_cell_ids.size:
                    mask = bad_cell_ids[(bad_cell_ids >= 0) & (bad_cell_ids < grid.n_cells)]
                    qvals[mask] = 1
                grid.cell_data['mesh_quality_state'] = qvals
                actor = plotter.add_mesh(
                    grid,
                    name=model.name,
                    pickable=True,
                    scalars='mesh_quality_state',
                    categories=True,
                    cmap=['#90a4ae', '#ff7043'],
                    show_edges=bool(show_edges),
                    opacity=max(0.65, opacity_default),
                    show_scalar_bar=False,
                )
                actor_map[model.name] = {'region_name': '', 'object_key': '', 'ifc_type': '', 'role': '', 'bounds': getattr(grid, 'bounds', None), 'actor': actor}
                if bad_cell_ids.size:
                    try:
                        sub = grid.extract_cells(bad_cell_ids)
                        plotter.add_mesh(sub, name='bad-cells', color='#ff1744', opacity=0.98, show_edges=True, edge_color='#212121', pickable=False)
                    except Exception:
                        pass
                if selected_regions:
                    self._overlay_selected_regions(plotter, grid, model, selected_regions)
            elif view_mode == 'stage_activity' and stage is not None and stage_activation:
                stage_values = np.ones(grid.n_cells, dtype=np.int32)
                region_names = self._cell_region_names(grid)
                if region_names is not None:
                    stage_values = np.asarray([1 if stage_activation.get(str(name), True) else 0 for name in region_names], dtype=np.int32)
                grid.cell_data['stage_active'] = stage_values
                actor = plotter.add_mesh(
                    grid,
                    name=model.name,
                    pickable=True,
                    scalars='stage_active',
                    categories=True,
                    cmap=[INACTIVE_COLOR, ACTIVE_COLOR],
                    show_edges=False,
                    opacity=0.95,
                )
                actor_map[model.name] = {'region_name': '', 'object_key': '', 'ifc_type': '', 'role': '', 'bounds': getattr(grid, 'bounds', None), 'actor': actor}
                if has_selection and selected_regions:
                    self._overlay_selected_regions(plotter, grid, model, selected_regions)
            elif view_mode == 'validation_regions':
                state_values = np.zeros(grid.n_cells, dtype=np.int32)
                region_names = self._cell_region_names(grid)
                if region_names is not None:
                    for idx, nm in enumerate(region_names):
                        name = str(nm)
                        if name in conflict_regions:
                            state_values[idx] = 2
                        elif name in unassigned_regions:
                            state_values[idx] = 1
                grid.cell_data['validation_state'] = state_values
                actor = plotter.add_mesh(
                    grid,
                    name=model.name,
                    pickable=True,
                    scalars='validation_state',
                    categories=True,
                    cmap=['#90a4ae', UNASSIGNED_COLOR, CONFLICT_COLOR],
                    show_edges=False,
                    opacity=0.95,
                )
                actor_map[model.name] = {'region_name': '', 'object_key': '', 'ifc_type': '', 'role': '', 'bounds': getattr(grid, 'bounds', None), 'actor': actor}
                if selected_regions:
                    self._overlay_selected_regions(plotter, grid, model, selected_regions)
            else:
                actor = plotter.add_mesh(grid, name=model.name, pickable=True, **kwargs)
                actor_map[model.name] = {'region_name': '', 'object_key': '', 'ifc_type': '', 'role': '', 'bounds': getattr(grid, 'bounds', None), 'actor': actor}
                if has_selection and selected_regions:
                    self._overlay_selected_regions(plotter, grid, model, selected_regions)
        plotter.add_axes(); plotter.show_grid()
        return actor_map

    def _overlay_selected_regions(self, plotter: pv.Plotter, grid: pv.DataSet, model: SimulationModel, selected_regions: Iterable[str]) -> None:
        for region in model.region_tags:
            if region.name not in selected_regions:
                continue
            try:
                sub = grid.extract_cells(region.cell_ids)
                plotter.add_mesh(sub, name=f'highlight:{region.name}', color='#ffca28', opacity=0.95, show_edges=True, pickable=False)
            except Exception:
                continue

    def _cell_region_names(self, grid: pv.DataSet):
        if 'region_name' in getattr(grid, 'cell_data', {}):
            arr = grid.cell_data['region_name']
            return [str(x) for x in arr]
        return None

    def _block_meta(self, name: str, block: Any) -> dict[str, Any]:
        def _first(key: str) -> str:
            try:
                fd = getattr(block, 'field_data', {})
                if key in fd and len(fd[key]):
                    return str(fd[key][0])
            except Exception:
                return ''
            return ''
        return {
            'name': str(name),
            'region_name': _first('region_name'),
            'object_key': _first('object_key') or str(name),
            'ifc_type': _first('ifc_type'),
            'role': _first('role') or _first('suggested_role'),
            'visible': _first('visible'),
            'pickable': _first('pickable'),
            'locked': _first('locked'),
            'bounds': getattr(block, 'bounds', None),
        }

    def _block_color(self, meta: dict[str, str]) -> str:
        for key in (meta.get('role'), meta.get('ifc_type')):
            if key and key in TYPE_COLORS:
                return TYPE_COLORS[key]
        if meta.get('region_name', '').lower().startswith('wall'):
            return TYPE_COLORS['wall']
        if meta.get('region_name', '').lower().startswith('soil'):
            return TYPE_COLORS['soil']
        return '#90a4ae'
