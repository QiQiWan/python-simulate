from __future__ import annotations

import numpy as np


def test_hex8_sparse_linear_patch_benchmark():
    from geoai_simkit.fem.linear_static import run_hex8_linear_patch_benchmark

    result = run_hex8_linear_patch_benchmark()

    assert result["passed"] is True
    assert result["contract"] == "sparse_linear_static_v1"
    assert result["max_strain_error"] < 1.0e-12
    assert result["max_stress_error"] < 1.0e-5


def test_sparse_linear_static_solves_free_dofs_with_small_residual():
    from geoai_simkit.fem.linear_static import LinearElasticMaterial, solve_sparse_linear_static
    from geoai_simkit.mesh.mesh_document import MeshDocument

    mesh = MeshDocument(
        nodes=[
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ],
        cells=[(0, 1, 2, 3)],
        cell_types=["tet4"],
        cell_tags={"material_id": ["soil"]},
    )
    fixed = {3 * node + axis: 0.0 for node in (0, 2, 3) for axis in range(3)}
    fixed[3 * 1 + 1] = 0.0
    fixed[3 * 1 + 2] = 0.0
    load = {3 * 1 + 0: 1.0}

    result = solve_sparse_linear_static(
        mesh,
        materials={"soil": LinearElasticMaterial(E=1000.0, nu=0.25)},
        fixed_dofs=fixed,
        nodal_loads=load,
        tolerance=1.0e-10,
    )

    assert result.converged is True
    assert result.free_dof_count == 1
    assert result.relative_residual_norm < 1.0e-10
    assert np.isfinite(result.displacement).all()
    assert len(result.element_recovery) == 1
    assert result.element_recovery[0].stress.shape == (6,)
