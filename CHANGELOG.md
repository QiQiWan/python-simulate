# Changelog

## 0.8.73 - Module Optimization Readiness and Complete Modularization Closure

- Added dependency-light module optimization contracts for per-module targets, readiness metrics, optimization steps and actionable plans.
- Added `geoai_simkit.services.module_optimization` to generate module-specific deep optimization plans without importing GUI or implementation internals.
- Added `ModuleOptimizationActionController` and extended `ModuleKernelActionController` so GUI/CLI tooling can select a module and display its isolated optimization plan.
- Embedded optimization readiness in module governance metadata while keeping legacy bridges explicitly contained.
- Added tests for module optimization readiness, service/controller boundaries and serializable optimization plans.


## 0.8.72 - Complete Modularization Boundary Hardening

- Added `contracts.modularity` with module layer, manifest, dependency edge, legacy-boundary and complete-modularization report DTOs.
- Added `services.module_kernel` to build the canonical modular layer topology, module manifests, dependency graph and complete modularization report.
- Added `ModuleKernelActionController` for Qt-free GUI/CLI access to module manifests and modularization health.
- Embedded the complete modularization report into module governance metadata.
- Added 0.8.72 tests for module manifests, dependency edges, explicit legacy isolation and dependency-light modularity boundaries.

## 0.8.71 - Production Meshing Validation

- Added production meshing validation contracts for optional mesher dependency health, STL repair diagnostics, region mesh quality, interface conformity and aggregate validation reports.
- Added headless `services.production_meshing_validation` plus module facade entries for STL repair, production mesh validation, region quality and interface conformity.
- Workflow reports now include an optional typed `mesh_validation` quality artifact for production/STL meshing workflows without changing legacy step ordering.
- Added a Qt-free `MeshingValidationActionController` for GUI validation panels.
- Added 0.8.71 tests covering dependency-light contracts, headless validation services, workflow artifact integration and controller boundaries.

## 0.8.70 - Typed Contract Hardening and Main Window Physical Slimming

- Added typed payload contracts for workflow artifacts, plugin registrations, solver input/output summaries, mesh payloads, material mappings and quality gates.
- Hardened public contract sources by removing exposed `typing.Any` annotations from `geoai_simkit.contracts`.
- Extended workflow manifests with typed payload rows while preserving the legacy manifest v2 contract marker for compatibility.
- Added typed registration payloads to external plugin load records.
- Split the physical GUI entrypoint: `geoai_simkit.app.main_window` is now a thin compatibility wrapper and the legacy implementation lives in `geoai_simkit.app.main_window_impl`.
- Tightened GUI slimming governance to a 4000-line main-window entrypoint budget with zero direct internal imports.
- Added 0.8.69/0.8.70 regression tests for typed contracts, workflow payloads, external plugin registration payloads and GUI physical slimming.

# v0.8.68-external-plugin-entry-points

- Added dependency-light contracts for external plugin entry-point groups, discovered entry points, load records, load issues and load reports.
- Added `geoai_simkit.services.plugin_entry_points` for explicit Python entry-point discovery/loading across mesh generators, solver backends, geology importers, stage compilers, material providers, runtime compilers and postprocessors.
- Added context-registrar, class and factory style plugin loading support while keeping built-in registries deterministic by default.
- Added `PluginEntryPointActionController` for Qt-free GUI plugin status/action panels.
- Extended module governance metadata with external plugin entry-point discovery status.
- Added tests for external mesh/solver entry-point registration and architecture boundary safety.

# v0.8.67-contact-and-interface-solver-v1

- Added dependency-light contact/interface solver contracts: ContactMaterialParameters, InterfaceKinematics, ContactPairState, ContactIterationReport and ContactSolverReport.
- Added `geoai_simkit.solver.contact_core` with Coulomb penalty open/stick/slip evaluation, active-set diagnostics and ResultStore contact field writing.
- Added `contact_interface_cpu` solver backend and registered it in the default solver backend registry.
- Added `geotechnical.contact_report()` facade for module-level contact diagnostics without exposing solver internals.
- Added tests for contact contract serialization, active-set contact reports, backend registry exposure, ResultStore field writing and dependency-boundary cleanliness.
- Verified full test suite: 181 passed, 1 skipped.

# v0.8.66-nonlinear-solver-core-v1

- Added dependency-light nonlinear solver core contracts: LoadIncrement, NewtonIterationReport, ReturnMappingResult, CutbackRecord and NonlinearSolverCoreReport.
- Added geoai_simkit.solver.nonlinear_core with auditable Mohr-Coulomb return mapping, increment control, Newton-style diagnostics, cutback records and material-point state commit.
- Upgraded staged_mohr_coulomb_cpu capability metadata to expose nonlinear_solver_core_v1, return_mapping and cutback support while preserving legacy staged_mohr_coulomb_boundary_v1 result compatibility.
- Integrated nonlinear core reports into staged geotechnical solve metadata and ResultStore stage metadata.
- Added architecture and core tests for nonlinear contract dependency boundaries, return mapping serialization, core path diagnostics and staged backend integration.

# v0.8.66-verified-3d-quality-gates-and-gui-legacy-extraction

- Added Project Port v3 `ProjectEngineeringState` aggregate and typed workflow artifact manifests with lineage while preserving legacy artifact payloads.
- Extracted legacy GUI geometry/solver/post backend imports into `services.legacy_gui_backends`; `app.main_window` is now importable headlessly and has zero direct geometry/solver/post/material legacy imports.
- Added `solver.staging.StageManager` compatibility for GUI validation and presolve checks.
- Added quality-gate contracts/services for Tet4/Hex8 mesh quality, material compatibility and combined geotechnical readiness.
- Added verified deterministic 3D examples for tetra-column and multi-region STL geotechnical workflows.
- Added Qt-free controllers for geometry, export, compute preference, mesher backend and quality-gate status panels.
- Verified full test suite: 166 passed, 1 skipped.

# v0.8.63-gui-main-window-slimming-and-typed-workflow-artifacts

- Added typed workflow artifact DTOs and `ProjectWorkflowReport.artifact_refs` while preserving legacy `report.artifacts[...]` payload access.
- Updated `ProjectWorkflowService` to generate serializable artifact references for mesh, stage, solve and result/postprocessing outputs.
- Added `WorkflowArtifactActionController` for Qt-free GUI artifact tables/status panels.
- Added GUI slimming governance contracts/services/controllers: `GuiSlimmingReport`, `GuiFileSlimmingMetric`, `build_gui_slimming_report()` and `GuiSlimmingActionController`.
- Embedded GUI-slimming status into the module governance report and added tests for controller cleanliness, typed artifact serialization and main-window budget tracking.
- Verified full test suite: 155 passed, 1 skipped.

# v0.8.62-modular-governance-and-geotechnical-facade-boundary

- Added module-boundary governance contracts and a headless governance service that audits dependency direction across contracts, services, modules, mesh, solver and Qt-free controllers.
- Added `geoai_simkit.modules.geotechnical` as a first-class module facade for Project Port v2 geotechnical state, readiness reports and staged geotechnical analysis workflows.
- Registered the geotechnical module in the project module registry and module smoke suite.
- Added `ModuleGovernanceActionController` for GUI status panels without importing Qt/PyVista/solver internals.
- Added tests for governance reports, boundary audits, geotechnical facade routing and controller cleanliness.
- Verified full test suite: 150 passed, 1 skipped.

# v0.8.61-production-geotechnical-solver-boundary-and-gui-slimming

- Added Project Port v2 geotechnical DTOs for solid mesh, material mapping, boundary conditions, loads, interfaces, stage activation and analysis readiness.
- Added `build_geotechnical_readiness_report()` headless service to aggregate strict Project Port summaries, solid readiness, material audit and contact readiness.
- Added `staged_mohr_coulomb_cpu`, a production-boundary nonlinear backend with load-increment control, convergence diagnostics and state-commit metadata around the verified project solid solve and Mohr-Coulomb update path.
- Added Qt-free GUI controllers for material mapping, boundary/load summaries and geotechnical staged workflow actions.
- Added architecture tests protecting the new contract/service/controller boundaries and plugin catalog exposure.
- Verified full test suite: 143 passed, 1 skipped.

# v0.8.60-advanced-3d-geotechnical-pipeline

- Preserved multiple imported STL geological region surfaces during incremental import.
- Added multi-STL closure diagnostics and material mapping audit.
- Added `conformal_tet4_from_stl_regions` mesh-generator plugin with deterministic closed-shell fallback and Gmsh capability/health gating.
- Added automatic Coulomb penalty interface materialization and interface readiness checks.
- Added `nonlinear_mohr_coulomb_cpu` engineering-preview backend with Mohr-Coulomb plasticity result fields.
- Added tests for multi-STL import, conformal Tet4 fallback, material mapping, contact readiness, nonlinear backend, and registry boundaries.

# v0.8.59-project-3d-solid-linear-static-solver

- Added `solid_linear_static_cpu`, a project-level 3D solid linear-static CPU backend for Tet4/Hex8 project meshes.
- Preserved `linear_static_cpu` as the benchmark-grade sparse linear-static backend for compatibility.
- Added solid-solve result backwriting for nodal displacement components, nodal reaction force, full 6-component cell stress, full 6-component cell strain, von Mises stress and engineering metrics.
- Added canonical workflow coverage for STL -> Tet4 volume mesh -> project solid solve -> result summary.
- Added architecture tests ensuring the new backend remains in the adapter/registry layer and workflow services stay decoupled from solver internals.

# v0.8.58-stl-to-3d-solid-analysis-pipeline

- Added `SolidAnalysisReadinessReport` / `SolidAnalysisReadinessIssue` contracts for explicit 3D solid FEM gating.
- Marked imported STL geology as `geometry_surface` / `tri3` / `requires_volume_meshing=True` / `solid_solver_ready=False` instead of implying solver-ready volume mesh status.
- Extended Project Mesh summaries with mesh role, dimension, cell families, solid/surface cell counts and volume-meshing requirements.
- Updated phase compilation to exclude surface elements from solid element assembly and expose skipped surface-cell metadata.
- Added `voxel_hex8_from_stl` dependency-light volume meshing and `gmsh_tet4_from_stl` capability-gated Tet4 meshing entrypoints.
- Added STL solid-pipeline tests: surface readiness rejection, tetra STL Tet4 fallback, Hex8 voxel volume generation, and plugin catalog coverage.
- Verified full test suite: 123 passed, 1 skipped.

# v0.8.57-strict-port-interfaces-gui-controller-migration

- Added strict Project Port summary DTOs for geometry, mesh, stages, materials, result stores and compiled phases.
- Updated module facades to prefer Project Port summary helpers before unwrapping legacy `GeoProjectDocument` objects.
- Added Qt-free GUI action controllers for project, mesh, stage, solver and result actions.
- Added `linear_static_cpu`, a second real solver backend backed by the sparse linear-static CPU benchmark kernel.
- Expanded architecture tests for strict port contracts, controller migration and multi-backend solver registry validation.
- Verified full test suite: 118 passed, 1 skipped.

# v0.8.54-p2-p3-p4-modular-boundary-hardening

- Completed P2 by moving remaining business/headless services from `geoai_simkit.app` to `geoai_simkit.services` while preserving app-level compatibility wrappers.
- Completed P3 by adding plugin registries for mesh generators, stage compilers, material model providers, runtime compiler backends and result postprocessors, plus a unified module plugin catalog.
- Completed P4 by adding architecture tests for service wrappers and plugin registry availability, extending the existing dependency-boundary tests.
- Verified full test suite: 96 passed, 1 skipped.

# v0.8.54-modular-contracts-service-boundary

- Added dependency-light `geoai_simkit.contracts` with project, geology, geometry, mesh, stage, solver, runtime and result contracts.
- Added adapters for GeoProjectDocument, current mesh generators and the reference CPU staged solver.
- Added `geoai_simkit.services` and moved JobService/system-readiness/blueprint orchestration behind compatibility shims.
- Added `meshing` and `stage_planning` facades to complete the main module interop chain.
- Added solver backend registry with the default `reference_cpu` backend.
- Added architecture-boundary tests for contracts/services and app-layer import direction.
- Reduced root-directory clutter by relocating duplicate launchers and release-specific docs.
- Verified 92 passing tests and 1 optional skip.

# v0.8.52-runtime-stage-command-hardening

- Fixed staged block activation undo/redo for inherited-active blocks and pre-existing explicit inactive blocks.
- Added runtime public contracts and lightweight bundle/manifest management.
- Added conservative opt-in GPU runtime detection via `GEOAI_ENABLE_GPU_RUNTIME=1`.
- Extended `SolverSettings` to carry sparse, cutback, device, thread-count and nonlinear tolerance settings.
- Added regression coverage for stage activation, runtime bundle contracts, solver settings and JobService planning.
- Verified dependency-light package paths with 86 passing tests and 1 optional skip.

# v0.8.38-gui-startup-result-export-repair

- Restored the public `StageResultRecord` result API expected by GUI/result modules.
- Added `stage_result_records_from_model()` for dependency-light stage metric summaries.
- Added `geoai_simkit.results.stage_package` with `export_stage_result_package()` so staged pit workflows can export a GUI-readable manifest.
- Added the missing `geoai_simkit.app.shell.unified_workbench_window` launcher compatibility module.
- Made `geoai_simkit.results` avoid importing NumPy-heavy core result types at GUI startup unless type checking.
- Verified launcher/result import path with a no-site import smoke.

# Changelog

## v0.8.37 - block pit stage workflow

- Added a dependency-light foundation-pit block workflow that creates 2D/3D pit blocks, horizontal soil-layer splits, excavation-stage blocks, retaining-wall side blocks, face tags, contact pairs and interface requests.
- Added tagged Hex8 smoke mesh generation that preserves `block_tag`, `role`, `material_name`, `active_stages_json`, `face_tags_json`, `interface_requests_json` and stage rows.
- Extended the headless case builder to attach block activation maps, generated interface definitions, contact metadata and stage response metrics.
- Extended the headless solver route to emit stage-wise wall horizontal displacement and surface settlement result fields.
- Added a minimal results package and result acceptance helper so GUI/result services can display stage metrics without requiring a heavy runtime package.
- Added a foundation-pit preprocessor snapshot that exposes contact/interface/stage activation rows to GUI pages.
- Added `tools/run_block_pit_workflow_smoke.py` and workflow regression tests for the complete block-to-results chain.


- Promoted GUI workflow to six canonical operation pages: Modeling, Mesh, Solve, Results, Benchmark, and Advanced.
- Retired `project/model/diagnostics/delivery` as internal spaces and kept them as compatibility aliases.
- Replaced dependency-light core FEM smoke with deterministic numerical checks for geometry, mesh, material, element, assembly, solver, and result.
- Linked `run_solver_benchmarks.py`, core smoke JSON, and completion matrix generation.
- Cleaned old test vocabulary around production/commercial/fully_resident naming.

# v0.8.35-core-fem-hardening

- Added six independent GUI workflow page payloads: Modeling, Mesh, Solve, Results, Benchmark and Advanced.
- Added dependency-light core FEM API contracts for geometry, mesh, material, element, assembly, solver and result.
- Added smoke checks for every core FEM facade under `geoai_simkit.fem`.
- Added `tools/run_core_fem_smoke.py` to generate `reports/core_fem_smoke_results.json` and `docs/COMPLETION_MATRIX.generated.md`.
- Updated completion matrix generation so core FEM status can be driven by real smoke-test results.
- Kept GPU/OCC/UQ as advanced capability-gated tracks rather than core FEM promises.

# v0.8.34-core-fem-cleanup

- Added `geoai_simkit.fem` as the stable core FEM facade: geometry, mesh, material, element, assembly, solver and result.
- Added `geoai_simkit.advanced` for GPU/OCC/UQ capability-gated modules.
- Added completion matrix and status-driven wording policy documents.
- Reorganized GUI-facing homepage cards into Modeling, Mesh, Solve, Results, Benchmark and Advanced modules.
- Added benchmark report display-name/status normalization so CPU fallbacks, OCC fallbacks and research scaffolds are not over-claimed.
- Preserved old implementation modules for compatibility while clarifying their layer/status.

# Changelog

## 0.8.33-scope-cleanup-kernel-contract

- Added `docs/FEM_SCOPE_AND_ROADMAP.md` to separate general FEM responsibilities from GPU/OCC/UQ research tracks.
- Added truthful GPU Krylov kernel-completeness benchmark for CG/GMRES coverage metadata.
- Added strict GPU-resident coupled engineering-model benchmark that does not relabel CPU reference as GPU execution.
- Added shell NAFEMS/MacNeal reference traceability scaffold requiring official JSON references for certification-grade comparison.
- Added OCC Boolean TNaming/BRepTools end-to-end verification gate with explicit native-vs-fallback status.
- Added `tests/solver/test_iter93_scope_cleanup_kernel_contract.py`.


## v0.8.32-production-verification

- Added production-oriented GPU resident CG/GMRES verification with global preconditioner metadata.
- Added coupled Hex8/contact/material-state resident GPU workflow benchmark.
- Added full lightweight NAFEMS/MacNeal shell benchmark book and convergence proof summary.
- Added OCC TNaming/BRepTools boolean-history binding with curved-surface healing and mortar contact gate.
- Added batch triaxial database Bayesian inversion, posterior confidence intervals, and parameter correlation reports.
- Preserved simplified root layout and single `requirements.txt`.

## v0.8.31-gpu-krylov-gui-repair

- Added GUI fallback startup repair.
- Added first resident Krylov and Bayesian UQ benchmark contracts.
