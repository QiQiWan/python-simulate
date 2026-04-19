from __future__ import annotations

import numpy as np

from geoai_simkit.core.model import BoundaryCondition, LoadDefinition
from geoai_simkit.solver.hex8_linear import apply_stage_nodal_loads, select_bc_nodes



def test_select_bc_nodes_maps_global_point_ids_to_local_ids() -> None:
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float)
    local_by_global = {10: 0, 11: 1}
    bc = BoundaryCondition(
        name='fix',
        kind='displacement',
        target='point_ids',
        components=(0,),
        values=(0.0,),
        metadata={'point_ids': (11,), 'point_id_space': 'global'},
    )
    node_ids = select_bc_nodes(points, bc, local_by_global=local_by_global)
    assert node_ids.tolist() == [1]



def test_apply_stage_nodal_loads_maps_global_point_ids_to_local_ids() -> None:
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float)
    local_by_global = {10: 0, 11: 1}
    F = np.zeros(6, dtype=float)
    loads = (
        LoadDefinition(
            name='push',
            kind='point_force',
            target='point_ids',
            values=(5.0, 0.0, 0.0),
            metadata={'point_ids': (11,), 'point_id_space': 'global'},
        ),
    )
    apply_stage_nodal_loads(F, points, loads, local_by_global=local_by_global)
    assert F.tolist() == [0.0, 0.0, 0.0, 5.0, 0.0, 0.0]
