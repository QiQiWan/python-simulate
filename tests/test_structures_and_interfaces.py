import numpy as np

from geoai_simkit.core.model import InterfaceDefinition, StructuralElementDefinition
from geoai_simkit.solver.hex8_linear import Hex8Submesh
from geoai_simkit.solver.interface_elements import InterfaceElementState, assemble_interface_response
from geoai_simkit.solver.structural_elements import assemble_structural_stiffness, build_structural_dof_map


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


def test_structure_assembly_adds_stiffness_and_rotational_dofs():
    sub = _toy_submesh()
    structures = [
        StructuralElementDefinition(name="strut", kind="truss2", point_ids=(0, 1), parameters={"E": 2.1e11, "A": 1.0e-3, "prestress": 1.0e5}),
        StructuralElementDefinition(name="beam", kind="beam2", point_ids=(2, 3), parameters={"E": 2.1e11, "A": 1.0e-3, "Iy": 1.0e-6, "Iz": 2.0e-6, "J": 1.0e-6}),
        StructuralElementDefinition(name="wall_skin", kind="shellquad4", point_ids=(4, 5, 6, 7), parameters={"E": 3.0e10, "nu": 0.2, "thickness": 0.3}),
    ]
    dof_map = build_structural_dof_map(structures, sub)
    asm = assemble_structural_stiffness(structures, sub, dof_map=dof_map)
    assert asm.count == 3
    assert asm.K.shape[0] == dof_map.total_ndof
    assert dof_map.total_ndof > dof_map.trans_ndof
    assert np.linalg.norm(asm.K) > 0.0
    assert np.linalg.norm(asm.F) > 0.0


def test_interface_assembly_closes_and_generates_contact_force():
    sub = _toy_submesh()
    u = np.zeros((8, 3), dtype=float)
    u[4, 2] = 0.1
    iface = InterfaceDefinition(
        name="pair0",
        kind="node_pair",
        slave_point_ids=(0,),
        master_point_ids=(4,),
        parameters={"normal": (0.0, 0.0, 1.0), "kn": 1.0e6, "ks": 1.0e5, "friction_deg": 20.0},
    )
    asm, states = assemble_interface_response([iface], sub, u, {"pair0": [InterfaceElementState()]})
    assert asm.count == 1
    assert np.linalg.norm(asm.Fint) > 0.0
    assert states["pair0"][0].closed is True
