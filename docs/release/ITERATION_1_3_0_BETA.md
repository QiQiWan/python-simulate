# GeoAI SimKit 1.3.0 Beta

## Scope

1.3.0-beta is the first engineering Beta workflow build. It adds a one-click demo center to the six-phase workbench and provides a complete built-in calculation flow:

1. Geology and structure demo project loading
2. Tet4 project mesh and physical-group metadata
3. Phase compilation
4. Global Mohr-Coulomb Newton solve
5. Consolidation coupling
6. Interface open/close/sliding iteration
7. Result viewer payload, VTK export, JSON export and engineering report

## GUI

The PySide fallback phase workbench now exposes a `1.3 Demo` tab with three product actions:

- 一键加载 1.3 Demo
- 运行完整计算流程
- 导出 Demo 审查包

The default launcher still opens the six-phase workbench rather than the old flat geometry editor.

## Headless APIs

- `geoai_simkit.examples.release_1_3_0_workflow.build_release_1_3_0_project()`
- `geoai_simkit.examples.release_1_3_0_workflow.run_release_1_3_0_workflow()`
- `geoai_simkit.services.demo_project_runner.load_demo_project()`
- `geoai_simkit.services.demo_project_runner.run_demo_complete_calculation()`
- `geoai_simkit.services.release_acceptance_130.audit_release_1_3_0()`

## Acceptance

The generated review bundle in `docs/release/release_1_3_0_review_bundle/` passed:

- `status = accepted_1_3_0_beta`
- `blocker_count = 0`
- complete calculation pipeline `ok = true`

Warnings may still be present in headless CI when optional desktop/native dependencies are not installed, especially PySide6, PyVista, and native Gmsh/OCC.

## Boundary

1.3.0-beta is an engineering demo/Beta build. It demonstrates the complete product workflow and is suitable for UI/workflow validation. It is not a certified commercial geotechnical solver. Native meshing, desktop interaction and benchmark tolerances should be validated on the target workstation before production sign-off.
