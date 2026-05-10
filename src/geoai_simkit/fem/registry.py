from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal

Status = Literal["usable_core", "benchmark_grade", "research_scaffold", "capability_probe", "planned"]
Layer = Literal["core_fem", "advanced", "research"]


@dataclass(frozen=True, slots=True)
class FEMModuleStatus:
    key: str
    title: str
    layer: Layer
    status: Status
    namespace: str
    purpose: str
    evidence: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


CORE_FEM_MODULES: tuple[FEMModuleStatus, ...] = (
    FEMModuleStatus(
        key="geometry",
        title="Geometry and topology",
        layer="core_fem",
        status="benchmark_grade",
        namespace="geoai_simkit.geometry",
        purpose="Block, region, support and topology data used by the modelling workflow.",
        evidence=("geometry package", "demo foundation-pit case", "scene payloads"),
        limitations=("CAD editing and OCC native naming are still advanced/research capabilities.",),
    ),
    FEMModuleStatus(
        key="mesh",
        title="Mesh generation and quality gate",
        layer="core_fem",
        status="benchmark_grade",
        namespace="geoai_simkit.geometry.mesh_engine / geoai_simkit.geometry.mesh_quality",
        purpose="Generate/check Tet4/Hex8-style meshes and block invalid meshes before strict solve.",
        evidence=("mesh quality gate", "bad-mesh strict rejection benchmark"),
        limitations=("Complex BRep meshing still depends on optional meshing/OCC stack.",),
    ),
    FEMModuleStatus(
        key="material",
        title="Material models",
        layer="core_fem",
        status="benchmark_grade",
        namespace="geoai_simkit.materials",
        purpose="Elastic, Mohr-Coulomb and HSS/HSsmall research material updates.",
        evidence=("MC material path benchmark", "HSS state benchmark"),
        limitations=("HSS/HSsmall is benchmark-grade, not PLAXIS-equivalent certified.",),
    ),
    FEMModuleStatus(
        key="element",
        title="Element formulations",
        layer="core_fem",
        status="benchmark_grade",
        namespace="geoai_simkit.solver.hex8_global / tet4_linear / structural",
        purpose="Tet4, Hex8, truss, beam and shell-style element benchmarks.",
        evidence=("Tet4 patch", "Hex8 patch", "shell benchmark book scaffold"),
        limitations=("Shell benchmark book still needs official reference datasets for certification-grade comparison.",),
    ),
    FEMModuleStatus(
        key="assembly",
        title="Global assembly and constraints",
        layer="core_fem",
        status="benchmark_grade",
        namespace="geoai_simkit.solver.linsys / sparse_nonlinear",
        purpose="Assemble sparse systems, apply constraints, and route preconditioned solves.",
        evidence=("CSR assembly benchmark", "Krylov/preconditioner chain"),
        limitations=("Large engineering models need more real-data validation.",),
    ),
    FEMModuleStatus(
        key="solver",
        title="Linear and nonlinear solve",
        layer="core_fem",
        status="benchmark_grade",
        namespace="geoai_simkit.solver",
        purpose="Reference nonlinear and Newton/Krylov solver paths with strict fallback metadata.",
        evidence=("Hex8 nonlinear benchmark", "Newton-Krylov benchmark", "result acceptance gate"),
        limitations=("GPU-resident execution is an advanced layer and truth-gated separately.",),
    ),
    FEMModuleStatus(
        key="result",
        title="Results and acceptance",
        layer="core_fem",
        status="usable_core",
        namespace="geoai_simkit.results",
        purpose="Export result packages, acceptance fragments and benchmark metadata.",
        evidence=("stage_package", "results.acceptance", "benchmark_report"),
        limitations=("Engineering certification still requires project-specific validation.",),
    ),
)


def core_fem_matrix() -> list[dict[str, object]]:
    return [m.to_dict() for m in CORE_FEM_MODULES]


def core_fem_navigation_cards() -> list[dict[str, object]]:
    return [
        {"key": "modeling", "label": "Modeling", "module": "geometry", "status": "benchmark_grade", "space": "project", "summary": "Create and inspect project geometry, blocks and stage objects."},
        {"key": "mesh", "label": "Mesh", "module": "mesh", "status": "benchmark_grade", "space": "model", "summary": "Generate/check meshes and surface/block tags."},
        {"key": "solve", "label": "Solve", "module": "solver", "status": "benchmark_grade", "space": "solve", "summary": "Run validation, assembly and solver routes."},
        {"key": "results", "label": "Results", "module": "result", "status": "usable_core", "space": "results", "summary": "Review results, acceptance and export packages."},
        {"key": "benchmark", "label": "Benchmark", "module": "verification", "status": "benchmark_grade", "space": "diagnostics", "summary": "Run numerical benchmark and traceability checks."},
        {"key": "advanced", "label": "Advanced modules", "module": "advanced", "status": "capability_probe", "space": "delivery", "summary": "GPU, OCC and UQ tracks with explicit capability status."},
    ]
