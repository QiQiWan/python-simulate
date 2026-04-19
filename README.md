# geoai-simkit

`geoai-simkit` is a Python starter toolkit for staged geotechnical simulation workflows. It combines parametric scene generation, material assignment, stage management, FEM-style solver paths, export utilities, and an optional Qt/PyVista desktop viewer.

This release is packaged as a **developer-facing beta**: the repository is installable, testable, and buildable as a Python distribution, while advanced constitutive behavior and some commercial FEM features remain intentionally limited.

## What is included

- parametric pit demo model and staged excavation workflow
- editable geometry pipeline and mesh-preparation hooks
- material registry with linear elastic, Mohr–Coulomb, and HSS/HSsmall-style starters
- linear and nonlinear Hex8-oriented solver paths
- structural overlays and interface/contact starter implementations
- VTK/VTU/XDMF/OBJ/PLY/STL export helpers
- optional Qt + PyVista desktop GUI
- root launchers and CLI entrypoint
- pytest test suite and release-oriented project metadata

## Install

### Minimal library install

```bash
python -m pip install .
```

### Editable developer install

```bash
python -m pip install -e .[dev]
```

### Full local workstation install

```bash
python -m pip install -e .[all,dev]
```

### Convenience requirements files

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

## Optional extras

- `.[gui]` installs the Qt/PyVista desktop viewer stack
- `.[ifc]` installs IFC import support
- `.[meshing]` installs mesh import/export and gmsh meshing helpers
- `.[gpu]` installs NVIDIA Warp integration
- `.[all]` installs every optional runtime dependency

## Quick start

Run environment checks:

```bash
python run_checks.py
```

Run the packaged demo from the repository root:

```bash
python run_demo.py --out-dir exports_root
```

Run through the installed CLI:

```bash
geoai-simkit check-env
geoai-simkit demo --out-dir exports
```

Launch the GUI:

```bash
python run_gui.py
# or
geoai-simkit gui
```

## Build distributions

```bash
python -m pip install -e .[dev]
python -m build
python -m twine check dist/*
```

## Test

```bash
pytest -q
```

or

```bash
make test
```

## Project layout

```text
src/geoai_simkit/
├── app/          # GUI, validation, workflow helpers
├── core/         # simulation model and shared types
├── examples/     # packaged demos
├── geometry/     # parametric scenes, IFC, meshing, voxelization
├── materials/    # constitutive-model starters and registry
├── post/         # exporters and post-processing helpers
└── solver/       # linear/nonlinear solver paths and runtime helpers
```

## Current scope and limits

This package is **not** a full commercial nonlinear FEM platform. The current release still has these boundaries:

- `beam2` is a translational engineering approximation, not a full rotational beam element
- `shellquad4` is membrane-only
- contact is node-pair penalty/friction rather than mortar or surface-to-surface contact
- Warp acceleration remains an optional backend, not a fully GPU-native sparse FEM stack
- coupled seepage, consolidation, and production-grade constitutive corner handling are still future work

## Platform notes

- The GUI is optional and needs a desktop-capable Qt/OpenGL environment.
- `gmsh` may require extra system OpenGL libraries on Linux distributions.
- Heavy optional dependencies are intentionally split into extras so the base package stays installable in lighter environments.

## Release workflow

See `RELEASING.md` for the publication checklist and `.github/workflows/` for CI/CD templates.

## Modular general FEM pipeline (v0.3.1)

This iteration adds a generic, modular analysis pipeline on top of the existing solver stack:

- `geoai_simkit.pipeline.GeometrySource`: decouples geometry/mesh input from any particular project example.
- `geoai_simkit.pipeline.MeshAssemblySpec`: isolates meshing/merge-point controls.
- `geoai_simkit.pipeline.MaterialAssignmentSpec`: keeps material binding declarative and region-based.
- `geoai_simkit.pipeline.MeshPreparationSpec`: performs excavation-stage generation and node-pair contact generation at the mesh-preparation step.
- `geoai_simkit.pipeline.GeneralFEMSolver`: prepares a case and dispatches it to the backend solver.

The packaged pit demo now builds through this generic pipeline first, and then applies demo-specific support/interface presets on top.


## Portable analysis cases

The pipeline can now persist and reload portable case files.

Examples:

```bash
geoai-simkit export-demo-case --out pit_demo_case.json
geoai-simkit prepare-case pit_demo_case.json
geoai-simkit run-case pit_demo_case.json --out-dir exports
```

This moves the framework closer to a modern FEM workflow where geometry source,
mesh preparation, material assignment, stage sequencing, and solver execution can
be driven from a case description instead of hard-coded Python entrypoints.

