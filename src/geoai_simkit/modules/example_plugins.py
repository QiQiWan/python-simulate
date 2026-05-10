from __future__ import annotations

"""Dependency-light example plugins used to validate module replaceability.

These are deliberately tiny and deterministic.  They prove that new mesh,
solver and postprocessing plugins can be registered and resolved through the
public registries without touching GUI, services or legacy implementation code.
"""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.contracts import (
    MeshRequest,
    MeshResult,
    PluginCapability,
    PluginHealth,
    ResultRequest,
    ResultSummary,
    SolveRequest,
    SolveResult,
)


@dataclass(slots=True)
class DummyMesh:
    node_count: int = 0
    cell_count: int = 0

    def block_ids(self) -> tuple[str, ...]:
        return ()


class DummyMeshGenerator:
    key = "dummy_mesh"
    label = "Dummy mesh generator"
    supported_mesh_kinds = ("dummy_mesh",)
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="mesh_generator",
        version="1",
        features=("test_double", "headless"),
        supported_inputs=("ProjectReadPort",),
        supported_outputs=("MeshResult",),
        health=PluginHealth(available=True),
    )

    def can_generate(self, request: MeshRequest) -> bool:
        return str(request.mesh_kind) == self.key

    def generate(self, request: MeshRequest) -> MeshResult:
        return MeshResult(
            mesh=DummyMesh(node_count=1, cell_count=1),
            mesh_kind=self.key,
            attached=False,
            metadata={"plugin": self.key, **dict(request.metadata)},
        )


class DummySolverBackend:
    key = "dummy_solver"
    label = "Dummy solver backend"
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="solver_backend",
        version="1",
        features=("test_double", "no_op"),
        devices=("cpu",),
        supported_inputs=("ProjectReadPort",),
        supported_outputs=("SolveResult",),
        health=PluginHealth(available=True),
    )

    def can_solve(self, request: SolveRequest) -> bool:
        return str(request.backend_preference) == self.key

    def solve(self, request: SolveRequest) -> SolveResult:
        return SolveResult(
            accepted=True,
            status="accepted",
            backend_key=self.key,
            solved_model=request.target(),
            metadata={"plugin": self.key, **dict(request.metadata)},
        )


class DummyPostProcessor:
    key = "dummy_postprocessor"
    label = "Dummy postprocessor"
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="postprocessor",
        version="1",
        features=("test_double", "summary"),
        supported_inputs=("object",),
        supported_outputs=("ResultSummary",),
        health=PluginHealth(available=True),
    )

    def summarize(self, request: ResultRequest) -> ResultSummary:
        return ResultSummary(
            stage_count=len(request.stage_ids),
            field_count=len(request.fields),
            accepted=True,
            metadata={"plugin": self.key, **dict(request.metadata)},
        )


__all__ = ["DummyMesh", "DummyMeshGenerator", "DummyPostProcessor", "DummySolverBackend"]
