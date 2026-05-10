from __future__ import annotations

from pathlib import Path

from geoai_simkit.contracts import (
    MeshPayload,
    PluginRegistrationPayload,
    QualityGatePayload,
    SolverInputPayload,
    SolverOutputPayload,
    WorkflowArtifactPayload,
    WorkflowArtifactRef,
    workflow_artifact_manifest_from_refs,
)
from geoai_simkit.contracts.plugins import ExternalPluginLoadRecord


def test_contract_public_sources_do_not_expose_any_annotations() -> None:
    contract_root = Path("src/geoai_simkit/contracts")
    occurrences = []
    for path in contract_root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "Any" in text:
            occurrences.append(path.name)
    assert occurrences == []


def test_typed_payload_contracts_are_serializable() -> None:
    payloads = [
        WorkflowArtifactPayload(artifact_id="wf:mesh:mesh", key="mesh", kind="mesh", producer="meshing"),
        PluginRegistrationPayload(group="geoai_simkit.solver_backends", registry_key="solver_backends", category="solver_backend", plugin_key="x"),
        MeshPayload(mesh_kind="tet4", node_count=4, cell_count=1, cell_families=("tet4",), solid_cell_count=1),
        SolverInputPayload(backend="solid_linear_static_cpu", stage_count=1, active_cell_count=1, material_count=1),
        SolverOutputPayload(backend="solid_linear_static_cpu", accepted=True, stage_count=1, result_field_count=3),
        QualityGatePayload(gate="mesh", ok=True, checked_entity_count=1),
    ]
    for item in payloads:
        data = item.to_dict()
        assert data["metadata"]["contract"].endswith("_v1")


def test_workflow_manifest_exposes_typed_payloads_without_legacy_objects() -> None:
    ref = WorkflowArtifactRef(
        key="solve",
        kind="solve",
        producer="fem_solver",
        payload_type="geoai_simkit.contracts.solver.SolveResult",
        summary={"accepted": True, "backend": "solid_linear_static_cpu"},
    )
    manifest = workflow_artifact_manifest_from_refs((ref,), workflow_id="iter69")
    data = manifest.to_dict()
    assert data["metadata"]["contract"] == "workflow_artifact_manifest_v2"
    assert data["metadata"]["contract_version"] == "workflow_artifact_manifest_v3"
    assert data["typed_payloads"][0]["metadata"]["contract"] == "workflow_artifact_payload_v1"
    assert manifest.typed_payloads()[0].artifact_id == "iter69:solve:solve"


def test_external_plugin_records_have_typed_registration_payload() -> None:
    record = ExternalPluginLoadRecord(
        group="geoai_simkit.mesh_generators",
        entry_point="external_mesh",
        plugin_key="mesh_x",
        registry_key="mesh_generators",
        category="mesh_generator",
    )
    payload = record.to_payload()
    assert payload.plugin_key == "mesh_x"
    assert record.to_dict()["registration_payload"]["metadata"]["contract"] == "plugin_registration_payload_v1"
