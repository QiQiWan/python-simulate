from __future__ import annotations

"""0.9 Alpha end-to-end staged foundation-pit workflow.

The workflow is intentionally deterministic and lightweight enough for CI.  It
creates a PLAXIS-like six-phase model, compiles staged solver inputs, runs the
incremental GeoProject solver, exports review artifacts and audits the result.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from geoai_simkit.commands import (
    AddPhaseCommand,
    AssignGeometrySemanticCommand,
    CommandStack,
    CreateBlockCommand,
    CreateLineCommand,
    CreateSurfaceCommand,
    GeneratePreviewMeshCommand,
    SetPhaseWaterConditionCommand,
)
from geoai_simkit.geoproject import GeoProjectDocument, LoadRecord, MaterialRecord
from geoai_simkit.geoproject.runtime_solver import run_geoproject_incremental_solve
from geoai_simkit.services.model_validation import validate_geoproject_model
from geoai_simkit.services.phase_solver_compiler import compile_phase_solver_inputs
from geoai_simkit.services.system_audit import audit_geoproject_alpha
from geoai_simkit.app.panels.result_viewer import build_result_viewer, export_legacy_vtk, export_result_summary_json


@dataclass(slots=True)
class AlphaWorkflowArtifacts:
    contract: str = "geoai_simkit_alpha_0_9_artifacts_v1"
    project_path: str = ""
    validation_path: str = ""
    compiler_path: str = ""
    solver_summary_path: str = ""
    result_summary_path: str = ""
    audit_path: str = ""
    vtk_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "project_path": self.project_path,
            "validation_path": self.validation_path,
            "compiler_path": self.compiler_path,
            "solver_summary_path": self.solver_summary_path,
            "result_summary_path": self.result_summary_path,
            "audit_path": self.audit_path,
            "vtk_path": self.vtk_path,
            "metadata": dict(self.metadata),
        }


def _ensure_alpha_materials(project: GeoProjectDocument) -> None:
    project.upsert_material(
        "soil",
        MaterialRecord(
            id="alpha_soft_clay",
            name="Alpha soft clay",
            model_type="mohr_coulomb",
            drainage="drained",
            parameters={"gamma_unsat": 18.0, "E_ref": 18000.0, "nu": 0.33, "c_ref": 15.0, "phi": 24.0},
            metadata={"source": "alpha_0_9"},
        ),
    )
    project.upsert_material(
        "soil",
        MaterialRecord(
            id="alpha_dense_sand",
            name="Alpha dense sand",
            model_type="mohr_coulomb",
            drainage="drained",
            parameters={"gamma_unsat": 19.5, "E_ref": 52000.0, "nu": 0.28, "c_ref": 3.0, "phi": 36.0},
            metadata={"source": "alpha_0_9"},
        ),
    )
    project.upsert_material(
        "plate",
        MaterialRecord(
            id="alpha_c30_wall",
            name="C30 diaphragm wall",
            model_type="linear_elastic_plate",
            parameters={"E": 30000000.0, "nu": 0.20, "thickness": 0.8, "gamma": 25.0},
            metadata={"source": "alpha_0_9"},
        ),
    )
    project.upsert_material(
        "beam",
        MaterialRecord(
            id="alpha_steel_strut",
            name="Steel strut",
            model_type="linear_elastic_beam",
            parameters={"E": 200000000.0, "nu": 0.30, "A": 0.16, "I": 0.003},
            metadata={"source": "alpha_0_9"},
        ),
    )
    project.upsert_material(
        "interface",
        MaterialRecord(
            id="alpha_wall_soil_interface",
            name="Wall-soil interface",
            model_type="interface_frictional",
            parameters={"R_inter": 0.70, "kn": 1.0e6, "ks": 4.0e5, "friction_deg": 24.0},
            metadata={"source": "alpha_0_9"},
        ),
    )


def build_alpha_foundation_pit_project(*, name: str = "GeoAI SimKit 0.9 Alpha Foundation Pit") -> GeoProjectDocument:
    """Create a deterministic 3D staged foundation-pit Alpha demo project."""

    project = GeoProjectDocument.create_empty(name=name)
    project.project_settings.metadata.update({"alpha_release": "0.9.0", "workflow": "foundation_pit_staged_demo"})
    _ensure_alpha_materials(project)
    stack = CommandStack()

    # Geology phase: two soil volumes and two staged excavation volumes.  The
    # excavation volumes are initially active and later deactivated to mimic
    # staged excavation in a compact CI-friendly model.
    stack.execute(CreateBlockCommand(bounds=(-18.0, 18.0, -8.0, 8.0, -16.0, -8.0), block_id="soil_lower", name_hint="Lower dense sand", role="soil", material_id="alpha_dense_sand"), project)
    stack.execute(CreateBlockCommand(bounds=(-18.0, 18.0, -8.0, 8.0, -8.0, 0.0), block_id="soil_upper", name_hint="Upper soft clay", role="soil", material_id="alpha_soft_clay"), project)
    stack.execute(CreateBlockCommand(bounds=(-4.0, 4.0, -3.0, 3.0, -4.0, 0.0), block_id="excavation_step_1", name_hint="Excavation step 1", role="excavation", material_id="alpha_soft_clay"), project)
    stack.execute(CreateBlockCommand(bounds=(-4.0, 4.0, -3.0, 3.0, -8.0, -4.0), block_id="excavation_step_2", name_hint="Excavation step 2", role="excavation", material_id="alpha_soft_clay"), project)
    for vid in ("soil_lower", "soil_upper", "excavation_step_1", "excavation_step_2"):
        project.classify_geometry_entity(vid, "soil_volume", material_id=project.geometry_model.volumes[vid].material_id or "alpha_soft_clay")

    # Structure phase: four wall surfaces and two struts.
    wall_specs = {
        "wall_west": ((-4.0, -3.0, 0.0), (-4.0, 3.0, 0.0), (-4.0, 3.0, -10.0), (-4.0, -3.0, -10.0)),
        "wall_east": ((4.0, -3.0, 0.0), (4.0, 3.0, 0.0), (4.0, 3.0, -10.0), (4.0, -3.0, -10.0)),
        "wall_south": ((-4.0, -3.0, 0.0), (4.0, -3.0, 0.0), (4.0, -3.0, -10.0), (-4.0, -3.0, -10.0)),
        "wall_north": ((-4.0, 3.0, 0.0), (4.0, 3.0, 0.0), (4.0, 3.0, -10.0), (-4.0, 3.0, -10.0)),
    }
    for surface_id, coords in wall_specs.items():
        stack.execute(CreateSurfaceCommand(coords=coords, surface_id=surface_id, role="structure_wall", plane="xz"), project)
        stack.execute(AssignGeometrySemanticCommand(surface_id, "wall", material_id="alpha_c30_wall", metadata={"thickness": 0.8}), project)
    stack.execute(CreateLineCommand(start=(-4.0, 0.0, -2.0), end=(4.0, 0.0, -2.0), edge_id="strut_level_1", role="support"), project)
    stack.execute(AssignGeometrySemanticCommand("strut_level_1", "strut", material_id="alpha_steel_strut", metadata={"level": -2.0}), project)
    stack.execute(CreateLineCommand(start=(-4.0, 0.0, -6.0), end=(4.0, 0.0, -6.0), edge_id="strut_level_2", role="support"), project)
    stack.execute(AssignGeometrySemanticCommand("strut_level_2", "strut", material_id="alpha_steel_strut", metadata={"level": -6.0}), project)

    # Phase configuration.
    project.populate_default_framework_content()
    stack.execute(AddPhaseCommand("excavation_1", name_override="Excavate to -4 m", copy_from="initial"), project)
    project.set_phase_volume_activation("excavation_1", "excavation_step_1", False)
    for sid in ("wall_wall_west", "wall_wall_east", "wall_wall_south", "wall_wall_north"):
        project.set_phase_structure_activation("excavation_1", sid, True)
    stack.execute(SetPhaseWaterConditionCommand("excavation_1", water_condition_id="drawdown_1", water_level=-2.0), project)

    stack.execute(AddPhaseCommand("support_1", name_override="Install first strut", copy_from="excavation_1"), project)
    project.set_phase_structure_activation("support_1", "strut_strut_level_1", True)
    stack.execute(SetPhaseWaterConditionCommand("support_1", water_condition_id="drawdown_2", water_level=-4.0), project)

    stack.execute(AddPhaseCommand("excavation_2", name_override="Excavate to -8 m", copy_from="support_1"), project)
    project.set_phase_volume_activation("excavation_2", "excavation_step_2", False)
    project.set_phase_structure_activation("excavation_2", "strut_strut_level_2", False)
    stack.execute(SetPhaseWaterConditionCommand("excavation_2", water_condition_id="drawdown_3", water_level=-6.0), project)

    stack.execute(AddPhaseCommand("support_2", name_override="Install second strut", copy_from="excavation_2"), project)
    project.set_phase_structure_activation("support_2", "strut_strut_level_2", True)
    stack.execute(SetPhaseWaterConditionCommand("support_2", water_condition_id="drawdown_4", water_level=-8.0), project)

    # A surface surcharge should be activated only from support_1 onward.
    project.solver_model.loads["load_surface_surcharge"] = LoadRecord(
        id="load_surface_surcharge",
        name="20 kPa surface surcharge",
        target_ids=list(project.geometry_model.surfaces),
        kind="surface_load",
        components={"qz": -20.0},
        stage_ids=["support_1", "excavation_2", "support_2"],
        metadata={"unit": "kPa", "source": "alpha_0_9"},
    )
    for phase_id in ("initial", "excavation_1"):
        try:
            project.set_phase_load_activation(phase_id, "load_surface_surcharge", False)
        except Exception:
            pass
    for phase_id in ("support_1", "excavation_2", "support_2"):
        project.set_phase_load_activation(phase_id, "load_surface_surcharge", True)

    stack.execute(GeneratePreviewMeshCommand(), project)
    project.populate_default_framework_content()
    for phase_id in project.phase_ids():
        project.refresh_phase_snapshot(phase_id)
    project.compile_phase_models()
    project.metadata["alpha_0_9_build"] = {"status": "model_built", "phase_count": len(project.phase_ids())}
    return project


def run_alpha_foundation_pit_workflow(*, output_dir: str | Path | None = None, run_solver: bool = True) -> dict[str, Any]:
    """Build, validate, compile, solve, export and audit the 0.9 Alpha demo."""

    project = build_alpha_foundation_pit_project()
    validation = validate_geoproject_model(project, require_mesh=True)
    compiler = compile_phase_solver_inputs(project, block_on_errors=False)
    solver_summary = None
    if run_solver:
        solver_summary = run_geoproject_incremental_solve(project, compile_if_needed=False, write_results=True)
    viewer = build_result_viewer(project)
    audit = audit_geoproject_alpha(project)

    artifacts = None
    if output_dir is not None:
        artifacts = export_alpha_workflow_bundle(project, output_dir, validation=validation.to_dict(), compiler=compiler.to_dict(), solver_summary=None if solver_summary is None else solver_summary.to_dict(), viewer=viewer, audit=audit.to_dict())
    return {
        "contract": "geoai_simkit_alpha_0_9_workflow_v1",
        "ok": validation.ok and compiler.ok and bool(project.result_store.phase_results),
        "project": project,
        "validation": validation.to_dict(),
        "compiler": compiler.to_dict(),
        "solver_summary": None if solver_summary is None else solver_summary.to_dict(),
        "viewer": viewer,
        "audit": audit.to_dict(),
        "artifacts": None if artifacts is None else artifacts.to_dict(),
    }


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def export_alpha_workflow_bundle(
    project: GeoProjectDocument,
    output_dir: str | Path,
    *,
    validation: dict[str, Any] | None = None,
    compiler: dict[str, Any] | None = None,
    solver_summary: dict[str, Any] | None = None,
    viewer: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
) -> AlphaWorkflowArtifacts:
    """Export a complete Alpha demo review bundle."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    project_path = project.save_json(root / "alpha_0_9_project.geoproject.json")
    validation_payload = validation or validate_geoproject_model(project, require_mesh=True, require_results=bool(project.result_store.phase_results)).to_dict()
    compiler_payload = compiler or compile_phase_solver_inputs(project, block_on_errors=False).to_dict()
    solver_payload = solver_summary or dict(project.solver_model.metadata.get("last_incremental_solve", {}) or {})
    viewer_payload = viewer or build_result_viewer(project)
    audit_payload = audit or audit_geoproject_alpha(project).to_dict()
    validation_path = _write_json(root / "alpha_0_9_validation.json", validation_payload)
    compiler_path = _write_json(root / "alpha_0_9_compiler.json", compiler_payload)
    solver_path = _write_json(root / "alpha_0_9_solver_summary.json", solver_payload)
    result_path = _write_json(root / "alpha_0_9_result_viewer.json", viewer_payload)
    audit_path = _write_json(root / "alpha_0_9_audit.json", audit_payload)
    vtk = export_legacy_vtk(project, root / "alpha_0_9_results.vtk", phase_id=project.phase_ids()[-1])
    export_result_summary_json(project, root / "alpha_0_9_result_summary_export.json")
    return AlphaWorkflowArtifacts(
        project_path=str(project_path),
        validation_path=validation_path,
        compiler_path=compiler_path,
        solver_summary_path=solver_path,
        result_summary_path=result_path,
        audit_path=audit_path,
        vtk_path=str(vtk["path"]),
        metadata={"phase_count": len(project.phase_ids()), "result_phase_count": len(project.result_store.phase_results)},
    )


__all__ = [
    "AlphaWorkflowArtifacts",
    "build_alpha_foundation_pit_project",
    "run_alpha_foundation_pit_workflow",
    "export_alpha_workflow_bundle",
]
