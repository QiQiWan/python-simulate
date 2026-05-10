from __future__ import annotations

from geoai_simkit.contracts import ContactSolverReport, SolveRequest
from geoai_simkit.examples.verified_3d import build_multi_region_project
from geoai_simkit.modules import fem_solver, geotechnical
from geoai_simkit.solver.backend_registry import get_default_solver_backend_registry
from geoai_simkit.solver.contact_core import ContactRunControl, contact_material_from_record, evaluate_coulomb_contact_pair, interface_kinematics_from_record, run_project_contact_solver


def _prepare_contact_project(tmp_path, *, normal_gap: float = -1.0e-4, slip=(0.01, 0.0)):
    project = build_multi_region_project(tmp_path)
    assert project.structure_model.structural_interfaces
    for row in project.structure_model.structural_interfaces.values():
        row.metadata.setdefault("contact_state", {})["normal_gap"] = normal_gap
        row.metadata.setdefault("contact_state", {})["tangential_slip"] = list(slip)
    return project


def test_coulomb_contact_pair_distinguishes_open_stick_and_slip(tmp_path) -> None:
    project = _prepare_contact_project(tmp_path, normal_gap=-1.0e-4, slip=(0.01, 0.0))
    interface = next(iter(project.structure_model.structural_interfaces.values()))
    material = project.material_library.interface_materials[interface.material_id]
    state = evaluate_coulomb_contact_pair(interface_kinematics_from_record(interface), contact_material_from_record(interface.material_id, material))
    assert state.status in {"stick", "slip"}

    interface.metadata["contact_state"]["normal_gap"] = 1.0e-3
    open_state = evaluate_coulomb_contact_pair(interface_kinematics_from_record(interface), contact_material_from_record(interface.material_id, material))
    assert open_state.status == "open"
    assert open_state.active is False


def test_project_contact_solver_writes_interface_fields(tmp_path) -> None:
    project = _prepare_contact_project(tmp_path)
    report = run_project_contact_solver(project, control=ContactRunControl(max_active_set_iterations=4), write_results=True)

    assert isinstance(report, ContactSolverReport)
    payload = report.to_dict()
    assert payload["algorithm"] == "coulomb_penalty_contact_v1"
    assert payload["metadata"]["contract"] == "contact_interface_solver_v1"
    assert payload["interface_count"] >= 1
    assert payload["active_count"] >= 1

    stage = project.result_store.phase_results["initial"]
    assert "interface_contact_status" in stage.fields
    assert "interface_normal_traction" in stage.fields
    assert stage.metrics["contact_active_interface_count"] >= 1.0


def test_contact_interface_backend_is_registered_and_standard_solve_result(tmp_path) -> None:
    project = _prepare_contact_project(tmp_path)
    registry = get_default_solver_backend_registry()
    backend = registry.get("contact_interface_cpu")
    result = backend.solve(SolveRequest(project=project, backend_preference="contact_interface_cpu", settings={"max_active_set_iterations": 3}))

    assert result.accepted is True
    assert result.backend_key == "contact_interface_cpu"
    assert result.metadata["contract"] == "contact_interface_solver_v1"
    assert result.metadata["contact_report"]["interface_count"] >= 1


def test_contact_backend_can_run_through_fem_solver_facade(tmp_path) -> None:
    project = _prepare_contact_project(tmp_path)
    result = fem_solver.solve_project(project, backend_preference="contact_interface_cpu")

    assert result.ok is True
    assert result.backend_key == "contact_interface_cpu"
    assert project.result_store.phase_results["initial"].fields["interface_shear_traction"].components == 2


def test_geotechnical_contact_report_facade(tmp_path) -> None:
    project = _prepare_contact_project(tmp_path)
    report = geotechnical.contact_report(project)

    assert report["ok"] is True
    assert report["metadata"]["contract"] == "contact_interface_solver_v1"
    assert report["interface_count"] >= 1
