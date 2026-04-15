from __future__ import annotations

import numpy as np

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.core.types import RegionTag
from geoai_simkit.geometry.demo_pit import build_demo_wall_interfaces, configure_demo_coupling, coupling_wizard_summary


class _Cell:
    def __init__(self, point_ids):
        self.point_ids = tuple(int(v) for v in point_ids)


class _Grid:
    def __init__(self, points, cells):
        self.points = np.asarray(points, dtype=float)
        self._cells = [_Cell(ids) for ids in cells]
        self.n_cells = len(self._cells)
        self.celltypes = np.asarray([12] * self.n_cells, dtype=np.int32)

    def cast_to_unstructured_grid(self):
        return self

    def get_cell(self, cid: int):
        return self._cells[int(cid)]


def _make_minimal_model() -> SimulationModel:
    # length=10 => pit_x=5; width=6 => pit_y=3; wall_thickness=1 => outer x plane at -6.
    points = [
        (-5.8, 0.0, -2.0),  # soil_mass point, slightly offset from wall outer plane -> nearest match
        (-6.0, 0.0, -2.0),  # wall point on outer face
    ]
    cells = [
        (0,),
        (1,),
    ]
    model = SimulationModel(name='pit', mesh=_Grid(points, cells))
    model.metadata.update(
        {
            'source': 'parametric_pit',
            'parametric_scene': {
                'length': 10.0,
                'width': 6.0,
                'depth': 4.0,
                'soil_depth': 8.0,
                'wall_thickness': 1.0,
            },
        }
    )
    model.region_tags = [
        RegionTag('soil_mass', np.asarray([0], dtype=np.int64)),
        RegionTag('wall', np.asarray([1], dtype=np.int64)),
    ]
    return model


def test_build_demo_wall_interfaces_falls_back_to_nearest_soil_node() -> None:
    model = _make_minimal_model()
    interfaces = build_demo_wall_interfaces(model)
    assert interfaces
    iface = interfaces[0]
    assert iface.metadata['selection_mode'] == 'nearest_soil_auto'
    assert iface.metadata['nearest_match_count'] >= 1
    assert 'soil_mass' in iface.metadata['matched_regions']
    assert model.metadata['demo_interface_auto_policy'] == 'manual_like_nearest_soil'
    assert 'nearest_soil_auto' in model.metadata['demo_interface_selection_modes']


def test_configure_demo_coupling_records_interface_pairing_diagnostics() -> None:
    model = _make_minimal_model()
    wall_mode = configure_demo_coupling(model, prefer_wall_solver=True, auto_supports=False)
    assert wall_mode == 'auto_interface'
    assert model.metadata['demo_auto_interface_count'] >= 1
    assert model.metadata['demo_interface_nearest_pairs'] >= 1
    assert model.metadata['demo_interface_exact_pairs'] == 0


def test_exact_only_policy_disables_nearest_fallback_for_demo_interfaces() -> None:
    model = _make_minimal_model()
    interfaces = build_demo_wall_interfaces(model, interface_policy='exact_only')
    assert interfaces == []
    assert model.metadata['demo_interface_auto_policy'] == 'exact_only'
    assert model.metadata['demo_interface_selection_modes'] == []


def test_coupling_wizard_summary_exposes_report_rows() -> None:
    model = _make_minimal_model()
    wall_mode = configure_demo_coupling(model, prefer_wall_solver=True, auto_supports=False, interface_policy='nearest_soil_relaxed')
    assert wall_mode == 'auto_interface'
    wizard = coupling_wizard_summary(model)
    assert wizard['interface_policy'] == 'nearest_soil_relaxed'
    assert wizard['interface_count'] >= 1
    assert wizard['nearest_pairs'] >= 1
    rows = wizard['report_rows']
    assert rows and isinstance(rows, list)
    assert any(row.get('selection_mode') == 'nearest_soil_auto' for row in rows)


def test_coupling_wizard_summary_reports_enabled_groups_and_radius() -> None:
    model = _make_minimal_model()
    model.metadata['demo_enabled_interface_groups'] = ['outer']
    model.metadata['demo_enabled_support_groups'] = ['crown_beam']
    model.metadata['demo_interface_nearest_radius_factor'] = 2.25
    configure_demo_coupling(model, prefer_wall_solver=True, auto_supports=False, interface_policy='manual_like_nearest_soil')
    wizard = coupling_wizard_summary(model)
    assert wizard['enabled_interface_groups'] == ['outer']
    assert wizard['enabled_support_groups'] == ['crown_beam']
    assert wizard['nearest_radius_factor'] == 2.25


def test_group_override_prioritizes_requested_soil_region() -> None:
    model = _make_minimal_model()
    model.region_tags.insert(1, RegionTag('soil_excavation_2', np.asarray([0], dtype=np.int64)))
    model.metadata['demo_interface_region_overrides'] = {'outer': 'soil_excavation_2'}
    interfaces = build_demo_wall_interfaces(model)
    assert interfaces
    iface = interfaces[0]
    assert iface.metadata['preferred_region_override'] == 'soil_excavation_2'
    assert 'soil_excavation_2' in iface.metadata['preferred_regions']
    wizard = coupling_wizard_summary(model)
    assert wizard['interface_region_overrides'] == {'outer': 'soil_excavation_2'}
    assert any(row.get('preferred_region_override') == 'soil_excavation_2' for row in wizard['report_rows'])
