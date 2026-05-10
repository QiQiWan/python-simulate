from __future__ import annotations

"""Complete modularization kernel and manifest builder.

This service consolidates module specs, plugin registries, GUI slimming,
external plugin entry points and import-boundary governance into one headless
report.  It is intentionally service-layer code: GUI panels, CLI tools and tests
can use it without importing solver, mesh, Qt or rendering internals.
"""

from pathlib import Path

from geoai_simkit.contracts.modularity import (
    CompleteModularizationReport,
    LegacyBoundaryMarker,
    ModuleDependencyEdge,
    ModuleInterfaceContract,
    ModuleLayerSpec,
    ModuleManifest,
)
from geoai_simkit.modules.registry import PROJECT_MODULE_SPECS
from geoai_simkit.modules.plugin_catalog import module_plugin_catalog, validate_plugin_catalog
from geoai_simkit.services.gui_slimming import build_gui_slimming_report
from geoai_simkit.services.module_governance import audit_import_boundaries
from geoai_simkit.services.plugin_entry_points import supported_external_plugin_groups

_GEOAI_ROOT = Path(__file__).resolve().parents[1]

_MODULE_CONTRACTS: dict[str, tuple[str, ...]] = {
    "document_model": ("ProjectReadPort", "ProjectWritePort", "ProjectEngineeringState"),
    "geology_import": ("GeologyImporter", "GeologyImportPayload", "GeologySource"),
    "meshing": ("MeshRequest", "MeshResult", "SolidAnalysisReadinessReport", "ProductionMeshingValidationReport"),
    "stage_planning": ("StageCompileRequest", "StageCompileResult"),
    "gui_modeling": ("GuiSlimmingReport", "ProjectWorkflowReport"),
    "fem_solver": ("SolveRequest", "SolveResult", "SolverBackend", "NonlinearSolverCoreReport", "ContactSolverReport"),
    "geotechnical": ("AnalysisReadinessSummary", "GeotechnicalQualityGateReport", "ProjectEngineeringState"),
    "postprocessing": ("ResultRequest", "ResultSummary", "WorkflowArtifactManifest"),
}

_MODULE_PLUGIN_GROUPS: dict[str, tuple[str, ...]] = {
    "geology_import": ("geology_importers",),
    "meshing": ("mesh_generators",),
    "stage_planning": ("stage_compilers",),
    "fem_solver": ("solver_backends",),
    "geotechnical": ("solver_backends", "material_model_providers"),
    "postprocessing": ("postprocessors",),
    "document_model": (),
    "gui_modeling": (),
}

_MODULE_SERVICE_ENTRYPOINTS: dict[str, tuple[str, ...]] = {
    "document_model": ("ProjectLifecycleManager",),
    "geology_import": (),
    "meshing": ("build_production_meshing_validation_report", "evaluate_mesh_quality_gate"),
    "stage_planning": (),
    "gui_modeling": ("build_gui_slimming_report",),
    "fem_solver": ("run_project_workflow",),
    "geotechnical": ("build_geotechnical_readiness_report", "build_geotechnical_quality_gate"),
    "postprocessing": ("ResultsService",),
}


_LAYER_SPECS: tuple[ModuleLayerSpec, ...] = (
    ModuleLayerSpec(
        key="contracts",
        label="Stable contracts",
        order=0,
        allowed_downstream_layers=(),
        description="Dependency-light DTOs and protocols only.",
    ),
    ModuleLayerSpec(
        key="adapters",
        label="Legacy adapters",
        order=1,
        allowed_downstream_layers=("contracts",),
        description="Bridge existing implementation objects to stable contracts.",
    ),
    ModuleLayerSpec(
        key="implementation",
        label="Implementation backends",
        order=2,
        allowed_downstream_layers=("contracts", "adapters"),
        description="Mesh, solver, results and domain implementations selected by registries.",
    ),
    ModuleLayerSpec(
        key="modules",
        label="Module facades",
        order=3,
        allowed_downstream_layers=("contracts", "adapters", "implementation"),
        description="Public business facades and registry-based dispatch.",
    ),
    ModuleLayerSpec(
        key="services",
        label="Headless services",
        order=4,
        allowed_downstream_layers=("contracts", "modules", "adapters"),
        description="Application orchestration without GUI dependencies.",
    ),
    ModuleLayerSpec(
        key="app.controllers",
        label="GUI controllers",
        order=5,
        allowed_downstream_layers=("contracts", "services", "modules"),
        description="Qt-free controller layer for UI actions.",
    ),
    ModuleLayerSpec(
        key="app.shell",
        label="GUI shell",
        order=6,
        allowed_downstream_layers=("app.controllers", "services", "modules"),
        description="Thin UI shell; optional Qt/PyVista imports stay isolated here.",
    ),
)


_LEGACY_BOUNDARIES: tuple[LegacyBoundaryMarker, ...] = (
    LegacyBoundaryMarker(
        key="legacy_qt_main_window_impl",
        path="app/main_window_impl.py",
        owner_module="gui_modeling",
        isolation="imported only by app/main_window.py compatibility shell and GUI launchers",
        replacement_target="app.shell + app.panels + app.controllers",
        metadata={"reason": "physical GUI implementation island", "allowed_to_import_qt": True},
    ),
    LegacyBoundaryMarker(
        key="legacy_gui_backend_bridge",
        path="services/legacy_gui_backends.py",
        owner_module="gui_modeling",
        isolation="single service-layer compatibility bridge for legacy GUI backend symbols",
        replacement_target="typed controllers/services",
        metadata={"reason": "prevents main_window from importing backend internals directly"},
    ),
    LegacyBoundaryMarker(
        key="document_adapter_bridge",
        path="adapters/geoproject_adapter.py",
        owner_module="document_model",
        isolation="Project Port adapter bridge around GeoProjectDocument",
        replacement_target="Project Port v3 DTOs and ProjectContext",
        metadata={"reason": "legacy document compatibility"},
    ),
)


def modular_layer_specs() -> tuple[ModuleLayerSpec, ...]:
    """Return the canonical layer topology for the fully modular system."""

    return _LAYER_SPECS


def legacy_boundary_markers() -> tuple[LegacyBoundaryMarker, ...]:
    """Return explicitly contained legacy islands."""

    return _LEGACY_BOUNDARIES


def module_manifests() -> tuple[ModuleManifest, ...]:
    """Build stable manifests for all public project modules."""

    manifests: list[ModuleManifest] = []
    for spec in PROJECT_MODULE_SPECS:
        interface = ModuleInterfaceContract(
            module_key=spec.key,
            entrypoints=tuple(spec.public_entrypoints),
            contracts=_MODULE_CONTRACTS.get(spec.key, ()),
            plugin_groups=_MODULE_PLUGIN_GROUPS.get(spec.key, ()),
            service_entrypoints=_MODULE_SERVICE_ENTRYPOINTS.get(spec.key, ()),
            metadata={"contract": "module_interface_contract_v1"},
        )
        manifests.append(
            ModuleManifest(
                key=spec.key,
                label=spec.label,
                responsibility=spec.responsibility,
                layer="modules",
                owned_namespaces=tuple(spec.owned_namespaces),
                depends_on=tuple(spec.depends_on),
                interface=interface,
                status="stable" if spec.key != "gui_modeling" else "legacy_shell_isolated",
                legacy_boundary=(spec.key == "gui_modeling"),
                metadata={
                    "contract": "module_manifest_v1",
                    "boundary_notes": list(spec.boundary_notes),
                },
            )
        )
    return tuple(manifests)


def module_dependency_edges() -> tuple[ModuleDependencyEdge, ...]:
    """Return declared module dependency DAG edges."""

    known = {spec.key for spec in PROJECT_MODULE_SPECS}
    edges: list[ModuleDependencyEdge] = []
    for spec in PROJECT_MODULE_SPECS:
        for target in spec.depends_on:
            edges.append(
                ModuleDependencyEdge(
                    source=spec.key,
                    target=target,
                    kind="declared_module_dependency",
                    allowed=target in known and target != spec.key,
                    reason="declared in PROJECT_MODULE_SPECS" if target in known else "unknown target module",
                )
            )
    return tuple(edges)


def build_complete_modularization_report(*, include_external_plugins: bool = False) -> CompleteModularizationReport:
    """Build a system-level modularization closure report.

    The report is intentionally strict about boundary/governance state while
    treating legacy implementations as acceptable only when they are explicitly
    marked and isolated behind known bridges.
    """

    catalog = module_plugin_catalog(include_external=include_external_plugins)
    validation = validate_plugin_catalog(catalog)
    boundary = audit_import_boundaries()
    gui = build_gui_slimming_report()
    manifests = module_manifests()
    edges = module_dependency_edges()
    legacy = legacy_boundary_markers()
    external_groups = tuple(group.group for group in supported_external_plugin_groups())
    registry_counts = {key: len(rows) for key, rows in catalog.items()}

    issues: list[str] = []
    warnings: list[str] = []

    if not validation.get("ok"):
        issues.append("plugin_catalog_validation_failed")
    if not boundary.ok:
        issues.append("import_boundary_violations_present")
    if not gui.ok:
        issues.append("gui_slimming_budget_failed")
    if not manifests:
        issues.append("no_module_manifests")
    for manifest in manifests:
        if not manifest.owned_namespaces:
            issues.append(f"module_missing_owned_namespaces:{manifest.key}")
        if not manifest.interface or not manifest.interface.entrypoints:
            issues.append(f"module_missing_public_entrypoints:{manifest.key}")
    for edge in edges:
        if not edge.allowed:
            issues.append(f"invalid_module_dependency:{edge.source}->{edge.target}")
    for marker in legacy:
        if not (_GEOAI_ROOT / marker.path).exists():
            warnings.append(f"legacy_boundary_path_missing:{marker.path}")
    if len(external_groups) < 7:
        warnings.append("external_plugin_group_count_lower_than_expected")

    return CompleteModularizationReport(
        ok=not issues,
        version="complete_modularization_v2",
        layers=modular_layer_specs(),
        modules=manifests,
        dependency_edges=edges,
        legacy_boundaries=legacy,
        plugin_registry_counts=registry_counts,
        external_plugin_groups=external_groups,
        issue_count=len(issues),
        issues=tuple(issues),
        warnings=tuple(warnings),
        metadata={
            "contract": "complete_modularization_report_v1",
            "contract_version": "complete_modularization_report_v2",
            "module_count": len(manifests),
            "edge_count": len(edges),
            "legacy_boundary_count": len(legacy),
            "boundary_audit": boundary.to_dict(),
            "plugin_validation": validation,
            "gui_slimming": gui.to_dict(),
            "architecture_status": "fully_modular_with_contained_legacy_bridges",
            "optimization_status": "module_deep_optimization_ready",
            "optimization_target_count": len(manifests),
            "optimization_service": "geoai_simkit.services.module_optimization",
        },
    )


__all__ = [
    "build_complete_modularization_report",
    "legacy_boundary_markers",
    "modular_layer_specs",
    "module_dependency_edges",
    "module_manifests",
]
