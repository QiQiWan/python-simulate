# GeoAI SimKit 1.4.0 Beta-2 — Multi-template engineering demo workbench

## Scope

1.4.0 promotes the 1.3.0 single foundation-pit demo into a multi-template Beta-2 demo center.  The GUI and service layer now expose three built-in engineering templates:

1. Three-dimensional staged foundation pit excavation and support.
2. Slope stability under toe disturbance / rainfall-style water condition changes.
3. Pile-soil interaction under installation and service loading stages.

Each template is one-click loadable, can run the complete six-phase calculation pipeline, and exports an auditable review bundle.

## Workflow

The complete calculation pipeline remains phase-driven:

Geology -> Structures -> Mesh -> Staging -> Solve -> Results

For each template the runner creates a project, compiles phase inputs, runs the existing nonlinear/hydro/contact calculation stack, writes result viewer payloads, exports VTK/JSON/Markdown artifacts, and records acceptance status.

## New modules

- `geoai_simkit.services.demo_templates`
- `geoai_simkit.services.release_acceptance_140`
- `geoai_simkit.examples.release_1_4_0_workflow`
- `geoai_simkit.app.panels.release_140_showcase`

## GUI changes

The six-phase PySide fallback workbench now exposes a `1.4 Demo` tab with a template selector and four actions:

- One-click load selected template.
- Run selected template complete calculation.
- Export selected template review bundle.
- Run all 1.4 templates.

The previous preflight dependency gate remains the startup path.

## Acceptance

The 1.4.0 acceptance gate passes only if all required templates are cataloged, loaded, completed, exported, and exposed through the GUI payload.

Generated review bundle: `docs/release/release_1_4_0_review_bundle/`.
