from __future__ import annotations

import numpy as np

from geoai_simkit.contracts import NonlinearSolverCoreReport, ReturnMappingResult
from geoai_simkit.examples.verified_3d import build_tetra_column_project
from geoai_simkit.materials.mohr_coulomb import MohrCoulomb
from geoai_simkit.modules import fem_solver
from geoai_simkit.solver.nonlinear_core import NonlinearCoreControl, mohr_coulomb_return_mapping, run_mohr_coulomb_core_path


def test_mohr_coulomb_return_mapping_contract_is_serializable() -> None:
    material = MohrCoulomb(E=30_000.0, nu=0.3, cohesion=1.0, friction_deg=25.0, dilation_deg=0.0)
    result = mohr_coulomb_return_mapping(material, np.asarray([0.01, 0.0, -0.01, 0.004, 0.0, 0.0]))

    assert isinstance(result, ReturnMappingResult)
    payload = result.to_dict()
    assert payload["accepted"] is True
    assert payload["algorithm"] == "mohr_coulomb_return_mapping_v1"
    assert len(payload["final_state"]["stress"]) == 6
    assert "plastic_multiplier" in payload["diagnostics"]


def test_nonlinear_core_path_reports_increments_iterations_and_cutbacks() -> None:
    material = MohrCoulomb(E=30_000.0, nu=0.3, cohesion=0.1, friction_deg=20.0, dilation_deg=0.0)
    control = NonlinearCoreControl(load_increments=3, max_iterations=4, tolerance=1.0e-4, max_cutbacks=1)
    report = run_mohr_coulomb_core_path(material, control=control, strain_scale=2.0e-2)

    assert isinstance(report, NonlinearSolverCoreReport)
    assert report.increment_count == 3
    assert report.iteration_count >= 3
    assert report.to_dict()["metadata"]["contract"] == "nonlinear_solver_core_v1"
    assert all(row.accepted for row in report.return_mapping_results)
    assert report.to_dict()["load_increments"][0]["target_load_factor"] > 0.0


def test_staged_backend_embeds_nonlinear_core_report(tmp_path) -> None:
    project = build_tetra_column_project(tmp_path)

    result = fem_solver.solve_project(
        project,
        backend_preference="staged_mohr_coulomb_cpu",
        settings={"load_increments": 2, "max_iterations": 4, "tolerance": 1.0e-4},
    )

    assert result.ok is True
    summary = result.summary.to_dict()
    assert summary["metadata"]["nonlinear_solver_core"] == "nonlinear_solver_core_v1"
    assert summary["nonlinear_core_report"]["contract"] == "nonlinear_solver_core_v1"
    assert summary["nonlinear_core_report"]["last_report"]["algorithm"] == "nonlinear_solver_core_v1"
    stage = project.result_store.phase_results["initial"]
    assert stage.metadata["nonlinear_solver_boundary"]["staged_mohr_coulomb_cpu"]["nonlinear_core_contract"] == "nonlinear_solver_core_v1"
