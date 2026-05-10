from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from geoai_simkit.contracts import MeshRequest, MeshResult, SolveRequest, SolveResult, SolverCapabilities
from geoai_simkit.mesh.mesh_document import MeshDocument


@dataclass
class FakeEntryPoint:
    name: str
    group: str
    value: str
    payload: Any

    @property
    def module(self) -> str:
        return self.value.split(":", 1)[0]

    @property
    def attr(self) -> str:
        return self.value.split(":", 1)[1] if ":" in self.value else ""

    def load(self) -> Any:
        return self.payload


class FakeEntryPoints(list):
    def select(self, *, group: str):
        return FakeEntryPoints([item for item in self if item.group == group])


class ExternalMeshGenerator:
    key = "external_mesh_ep_test"
    label = "External mesh entry-point test"
    supported_mesh_kinds = ("external_mesh_ep_test",)
    capabilities = {
        "features": ["entry_point_test"],
        "supported_inputs": ["project"],
        "supported_outputs": ["mesh_document"],
        "health": {"available": True, "status": "available", "diagnostics": [], "dependencies": []},
    }

    def can_generate(self, request: MeshRequest) -> bool:
        return request.mesh_kind == self.key

    def generate(self, request: MeshRequest) -> MeshResult:
        mesh = MeshDocument(nodes=[(0.0, 0.0, 0.0)], cells=[], cell_types=[])
        return MeshResult(mesh=mesh, mesh_kind=self.key, metadata={"allow_empty": True, "external_plugin": True})


class ExternalSolverBackend:
    key = "external_solver_ep_test"
    capabilities = SolverCapabilities(
        key=key,
        label="External solver entry-point test",
        metadata={
            "plugin_capability": {
                "key": key,
                "label": "External solver entry-point test",
                "category": "solver_backend",
                "version": "1",
                "available": True,
                "features": ["entry_point_test"],
                "devices": ["cpu"],
                "supported_inputs": ["SolveRequest"],
                "supported_outputs": ["SolveResult"],
                "health": {"available": True, "status": "available", "diagnostics": [], "dependencies": []},
                "metadata": {"source": "test"},
            }
        },
    )

    def can_solve(self, request: SolveRequest) -> bool:
        return request.backend_preference == self.key

    def solve(self, request: SolveRequest) -> SolveResult:
        return SolveResult(accepted=True, status="ok", backend_key=self.key, metadata={"external_plugin": True})


def test_external_entry_point_discovery_and_loading(monkeypatch):
    from geoai_simkit.services import plugin_entry_points as service
    from geoai_simkit.mesh.generator_registry import get_default_mesh_generator_registry
    from geoai_simkit.solver.backend_registry import get_default_solver_backend_registry

    fake_eps = FakeEntryPoints(
        [
            FakeEntryPoint(
                name="external_mesh_ep_test",
                group="geoai_simkit.mesh_generators",
                value="fake_package:mesh_plugin",
                payload=ExternalMeshGenerator,
            ),
            FakeEntryPoint(
                name="external_solver_ep_test",
                group="geoai_simkit.solver_backends",
                value="fake_package:solver_plugin",
                payload=lambda: ExternalSolverBackend(),
            ),
        ]
    )
    monkeypatch.setattr(service.importlib_metadata, "entry_points", lambda: fake_eps)

    discovered = service.discover_external_plugin_entry_points()
    assert discovered.ok
    assert discovered.discovered_count == 2
    assert discovered.loaded_count == 0

    report = service.load_external_plugins(replace=True)
    assert report.ok, report.to_dict()
    assert report.loaded_count == 2
    assert "external_mesh_ep_test" in get_default_mesh_generator_registry().keys()
    assert "external_solver_ep_test" in get_default_solver_backend_registry().keys()

    mesh_result = get_default_mesh_generator_registry().get("external_mesh_ep_test").generate(
        MeshRequest(project=object(), mesh_kind="external_mesh_ep_test")
    )
    assert mesh_result.ok
    solve_result = get_default_solver_backend_registry().get("external_solver_ep_test").solve(
        SolveRequest(backend_preference="external_solver_ep_test")
    )
    assert solve_result.accepted


def test_context_registrar_style_entry_point(monkeypatch):
    from geoai_simkit.services import plugin_entry_points as service
    from geoai_simkit.mesh.generator_registry import get_default_mesh_generator_registry

    def register_with_context(context):
        context.register(ExternalMeshGenerator())

    fake_eps = FakeEntryPoints(
        [
            FakeEntryPoint(
                name="external_mesh_registrar_ep_test",
                group="geoai_simkit.mesh_generators",
                value="fake_package:register",
                payload=register_with_context,
            )
        ]
    )
    monkeypatch.setattr(service.importlib_metadata, "entry_points", lambda: fake_eps)

    report = service.load_external_plugins(groups=["mesh_generators"], replace=True)
    assert report.ok, report.to_dict()
    assert report.loaded_count == 1
    assert "external_mesh_ep_test" in get_default_mesh_generator_registry().keys()
