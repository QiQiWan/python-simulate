from __future__ import annotations

import numpy as np
import pytest

sp = pytest.importorskip('scipy.sparse')

from geoai_simkit.core.model import InterfaceDefinition, StructuralElementDefinition
from geoai_simkit.solver.hex8_linear import Hex8Submesh
from geoai_simkit.solver.interface_elements import InterfaceElementState, assemble_interface_block_response, assemble_interface_response
from geoai_simkit.solver.structural_elements import assemble_structural_hybrid_response, assemble_structural_stiffness, build_structural_dof_map
from geoai_simkit.solver.warp_hex8 import block_values_to_csr, build_node_block_sparse_pattern


def _toy_submesh() -> Hex8Submesh:
    pts = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 1.0],
        [0.0, 1.0, 1.0],
    ], dtype=float)
    elems = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    gids = np.arange(8, dtype=np.int64)
    return Hex8Submesh(global_point_ids=gids, points=pts, elements=elems, full_cell_ids=np.array([0], dtype=np.int64), local_by_global={int(i): int(i) for i in gids})


def test_interface_block_response_matches_dense_response() -> None:
    sub = _toy_submesh()
    u = np.zeros((8, 3), dtype=float)
    u[4, 2] = 0.05
    iface = InterfaceDefinition(
        name='pair0',
        kind='node_pair',
        slave_point_ids=(0,),
        master_point_ids=(4,),
        parameters={'normal': (0.0, 0.0, 1.0), 'kn': 1.0e6, 'ks': 1.0e5, 'friction_deg': 20.0},
    )
    dense_asm, dense_states = assemble_interface_response([iface], sub, u, {'pair0': [InterfaceElementState()]})
    pattern = build_node_block_sparse_pattern([sub.elements.astype(np.int32), np.array([[0, 4]], dtype=np.int32)], n_nodes=sub.points.shape[0])
    blk_asm, blk_states = assemble_interface_block_response([iface], sub, u, {'pair0': [InterfaceElementState()]}, pattern=pattern)
    K_blk = block_values_to_csr(pattern, blk_asm.block_values, ndof=sub.points.shape[0] * 3)
    assert np.allclose(blk_asm.Fint, dense_asm.Fint)
    assert np.allclose(K_blk.toarray(), dense_asm.K)
    assert blk_states['pair0'][0].closed == dense_states['pair0'][0].closed


def test_structural_hybrid_response_reproduces_translational_blocks() -> None:
    sub = _toy_submesh()
    structures = [
        StructuralElementDefinition(name='strut', kind='truss2', point_ids=(0, 1), parameters={'E': 2.1e11, 'A': 1.0e-3, 'prestress': 1.0e5}),
        StructuralElementDefinition(name='beam', kind='beam2', point_ids=(2, 3), parameters={'E': 2.1e11, 'A': 1.0e-3, 'Iy': 1.0e-6, 'Iz': 2.0e-6, 'J': 1.0e-6}),
    ]
    dof_map = build_structural_dof_map(structures, sub)
    dense = assemble_structural_stiffness(structures, sub, dof_map=dof_map)
    pattern = build_node_block_sparse_pattern([sub.elements.astype(np.int32), np.array([[0, 1], [2, 3]], dtype=np.int32)], n_nodes=sub.points.shape[0])
    hybrid = assemble_structural_hybrid_response(structures, sub, dof_map=dof_map, pattern=pattern)
    K_trans = block_values_to_csr(pattern, hybrid.trans_block_values, ndof=dof_map.trans_ndof)
    dense_tt = dense.K[:dof_map.trans_ndof, :dof_map.trans_ndof]
    tail = hybrid.tail_K.toarray() if hasattr(hybrid.tail_K, 'toarray') else np.asarray(hybrid.tail_K, dtype=float)
    combined = np.zeros_like(dense.K)
    combined[:dof_map.trans_ndof, :dof_map.trans_ndof] = K_trans.toarray()
    combined += tail
    assert np.allclose(combined, dense.K)
    assert np.allclose(hybrid.F, dense.F)
