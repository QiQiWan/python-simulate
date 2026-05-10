# AGENTS.md

## Project role

You are working on a geotechnical finite element software project.

The project aims to support:

- Geological model import and preprocessing
- GUI-based modeling
- Mesh generation
- Material modeling
- Construction-stage simulation
- Nonlinear finite element solving
- Contact and interface modeling
- Result visualization and benchmark validation

The codebase is expected to evolve toward a modular engineering-grade FEM platform rather than a collection of demos.

---

## Primary engineering goals

When modifying this repository, prioritize the following goals:

1. Keep the system runnable from the repository root.
2. Preserve a clear modular architecture.
3. Avoid large unverified rewrites.
4. Add tests for every meaningful change.
5. Keep GUI, solver, geometry, and data model layers separated.
6. Prefer stable, reproducible dependencies.
7. Keep old compatibility aliases only when they are still needed by existing tests or scripts.
8. Remove obsolete demo-only paths only after replacement paths are tested.
9. Make every new feature verifiable through either a smoke test, unit test, benchmark, or runnable script.

---

## Repository layout

Expected high-level structure:

```text
.
├── AGENTS.md
├── README.md
├── requirements.txt
├── pyproject.toml
├── run_gui.py
├── run_tests.py
├── src/
│   └── geofem/
│       ├── core/
│       │   ├── geometry/
│       │   ├── mesh/
│       │   ├── material/
│       │   ├── element/
│       │   ├── assembly/
│       │   ├── solver/
│       │   └── result/
│       ├── geology/
│       │   ├── importers/
│       │   ├── stl/
│       │   ├── validation/
│       │   └── stratigraphy/
│       ├── contact/
│       ├── stage/
│       ├── gui/
│       ├── benchmark/
│       ├── io/
│       └── utils/
├── tests/
│   ├── smoke/
│   ├── unit/
│   ├── integration/
│   └── benchmark/
├── examples/
├── docs/
├── scripts/
└── assets/
```

If the actual repository structure differs, inspect the repository first and adapt changes to the existing layout instead of forcing this structure blindly.

---

## Environment setup

Use Python 3.10 or newer unless the repository explicitly states another version.

Default setup commands:

```bash
conda activate ifc
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `pyproject.toml` exists and the project is installable, prefer editable installation:

```bash
conda activate ifc
python -m pip install --upgrade pip
pip install -e .
```

If both `requirements.txt` and `pyproject.toml` exist, use:

```bash
conda activate ifc
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

If optional GUI dependencies are separated, install them before running GUI tests.

Example:

```bash
pip install -r requirements-gui.txt
```

If optional GPU dependencies are separated, do not install them unless the task explicitly requires GPU functionality.

---

## Dependency policy

Before adding a new dependency:

1. Check whether the same functionality already exists in the repository.
2. Prefer standard library solutions where reasonable.
3. Prefer stable and widely used packages.
4. Avoid adding heavy dependencies for small utilities.
5. Do not add GPU-only dependencies unless the task explicitly requires them.
6. Do not add dependencies that require complex system-level installation unless documented clearly.

Common acceptable Python dependencies for this project may include:

```text
numpy
scipy
matplotlib
meshio
trimesh
shapely
pyvista
vtk
PySide6
pytest
```

Use caution with:

```text
cupy
numba
torch
jax
gmsh
pythonocc-core
amgx
petsc4py
```

These packages may require platform-specific installation or large binary dependencies.

---

## Running the project

The repository root should provide a simple GUI startup command.

Preferred command:

```bash
python run_gui.py
```

If `run_gui.py` does not exist, create a minimal root-level launcher that imports the actual GUI entry point.

The launcher should:

1. Work from the repository root.
2. Avoid hard-coded absolute paths.
3. Print clear error messages when optional GUI dependencies are missing.
4. Avoid silently swallowing exceptions during startup.

Example behavior:

```text
python run_gui.py
```

Expected result:

- The main GUI starts.
- The default page is usable.
- A demo project can be opened or created.
- Logs are visible in the GUI or terminal.

---

## Testing commands

Run the fastest relevant tests first.

Default smoke test:

```bash
python -m pytest tests/smoke -q
```

Default unit test:

```bash
python -m pytest tests/unit -q
```

Default full test:

```bash
python -m pytest tests -q
```

If a test directory does not exist, create a minimal one when adding new functionality.

For solver or benchmark changes, run:

```bash
python -m pytest tests/benchmark -q
```

If the repository contains a benchmark runner, use:

```bash
python scripts/run_solver_benchmarks.py
```

or:

```bash
python run_solver_benchmarks.py
```

depending on the existing repository layout.

---

## Linting and formatting

If the repository already uses formatting tools, follow the existing tools.

Common commands:

```bash
python -m compileall src tests
```

If `ruff` is configured:

```bash
ruff check src tests
```

If `black` is configured:

```bash
black src tests
```

Do not introduce a new formatter unless the repository already uses one or the user explicitly requests it.

---

## Coding style

Use clear, maintainable Python.

Code comments must be written in English.

Prefer:

- Explicit names
- Small functions
- Typed dataclasses for domain models
- Clear separation between data models and GUI logic
- Deterministic tests
- Meaningful exceptions
- Minimal global state

Avoid:

- Hidden side effects
- Large monolithic files
- GUI logic inside solver modules
- Solver logic inside GUI modules
- Silent fallback behavior that hides errors
- Hard-coded absolute paths
- Unverified “production-ready” claims

---

## Architecture rules

Keep these layers separated:

### Geometry layer

Responsible for:

- Points
- Curves
- Surfaces
- Volumes
- Topology
- Block partitioning
- Geometry validation

Should not depend on:

- GUI widgets
- Solver internals
- Rendering-only classes

### Mesh layer

Responsible for:

- Mesh data structures
- Node and element containers
- Mesh quality checks
- Block-to-mesh mapping
- Interface candidate detection

Should not depend on:

- GUI widgets
- High-level project commands

### Material layer

Responsible for:

- Elastic material models
- Mohr-Coulomb material models
- Hardening soil models
- Interface material models
- Material parameter validation
- State variable definitions

Should not depend on:

- GUI widgets
- File importers
- Visualization modules

### Element layer

Responsible for:

- Element interpolation
- Gauss integration
- B-matrix construction
- Element stiffness
- Element residual
- Stress update calls

Should not depend on:

- GUI widgets
- Project document UI state

### Assembly layer

Responsible for:

- Global DOF numbering
- Sparse matrix assembly
- Boundary condition application
- Load vector assembly
- Contact and interface contribution assembly

Should not depend on:

- GUI widgets

### Solver layer

Responsible for:

- Linear solvers
- Nonlinear Newton-Raphson loop
- Load stepping
- Cutback strategy
- Convergence checks
- History transfer between stages

Should not depend on:

- GUI widgets
- Rendering modules

### Result layer

Responsible for:

- Displacement fields
- Stress fields
- Plastic state fields
- Contact status fields
- Result export
- Result interpolation for visualization

Should not depend on:

- Solver internals beyond documented result data structures

### GUI layer

Responsible for:

- User interaction
- View models
- 3D visualization
- Selection tools
- Property panels
- Stage editor
- Logs and warnings

Should call core services through controllers or application services.

Do not place numerical algorithms directly inside GUI event handlers.

---

## Geology and STL import rules

For STL or geological model import functionality, include:

1. File loading
2. Unit handling
3. Coordinate normalization
4. Watertightness check
5. Degenerate triangle check
6. Non-manifold edge check
7. Duplicate vertex cleanup
8. Normal consistency check
9. Mesh simplification or repair when safe
10. Layer or block identification where possible
11. Clear diagnostics when automatic repair is unsafe

Do not silently modify imported geometry without reporting what changed.

Imported geological models should produce a structured object such as:

```text
GeologicalModel
├── surfaces
├── volumes
├── layers
├── faults
├── interfaces
├── metadata
└── diagnostics
```

---

## GUI expectations

The GUI should be organized into major pages such as:

```text
Modeling
Mesh
Materials
Stages
Solve
Results
Benchmark
Advanced
```

The GUI should provide:

- A central 3D viewport
- A project tree or model browser
- A property editor
- A bottom log panel
- Clear warning and error messages
- Selectable geometry objects
- Basic interaction tools
- Result cloud visualization
- Demo project loading

Avoid excessive pop-up inspectors that interrupt modeling.

Prefer dockable or embedded panels.

---

## Solver expectations

For FEM solver work, prioritize correctness before speed.

A credible nonlinear solver path should include:

1. Global residual assembly
2. Global tangent assembly
3. Boundary condition application
4. Newton-Raphson iteration
5. Convergence check using residual and displacement increment
6. Load stepping
7. Cutback on non-convergence
8. Material state commit and rollback
9. Stage-to-stage history transfer
10. Clear solver logs

For Mohr-Coulomb or other plasticity work, avoid claiming strict return mapping unless implemented and tested.

For contact work, avoid claiming production-grade mortar contact unless geometric search, projection, integration, and complementarity handling are implemented and tested.

---

## Benchmark expectations

Every meaningful solver improvement should be linked to at least one benchmark.

Recommended benchmark categories:

```text
1. Linear elastic patch test
2. Single element compression test
3. Mohr-Coulomb triaxial compression test
4. Strip footing settlement test
5. Retaining wall excavation stage test
6. Interface shear test
7. Contact compression/sliding test
8. Mesh refinement convergence test
```

Benchmark output should include:

- Input summary
- Material parameters
- Mesh statistics
- Boundary conditions
- Convergence history
- Runtime
- Key response quantities
- Pass/fail criteria

---

## Result visualization expectations

When adding or modifying result visualization, verify that:

1. The model is visible.
2. The mesh is visible.
3. Displacement scale can be adjusted.
4. Scalar result fields can be selected.
5. Color maps are applied correctly.
6. Deformed and undeformed shapes can be compared.
7. Stage-to-stage comparison is possible.
8. Empty or missing results show a clear message.

Do not return only a raw payload when the user expects visible result clouds.

---

## Project document model

The project should move toward a structured document model similar to:

```text
GeoProjectDocument
├── ProjectSettings
├── SoilModel
├── GeometryModel
├── TopologyGraph
├── StructureModel
├── MaterialLibrary
├── MeshModel
├── StageModel
├── BoundaryConditionModel
├── LoadModel
├── SolverSettings
├── ResultDatabase
└── Diagnostics
```

When adding features, connect them to this document model where appropriate.

Avoid isolated feature code that cannot be saved, loaded, tested, or inspected.

---

## Backward compatibility

Before removing old modules, check:

```bash
grep -R "old_module_name" src tests examples scripts
```

If old imports are still used, either:

1. Update all imports and tests, or
2. Keep a compatibility alias with a deprecation warning.

Do not delete compatibility paths unless tests pass.

---

## File and path handling

Use `pathlib.Path`.

Avoid hard-coded absolute paths.

Prefer repository-relative paths for examples and tests.

When writing generated files, use:

```text
outputs/
artifacts/
build/
tmp/
```

depending on existing repository conventions.

Do not write large generated files into `src/`.

---

## Error handling

Raise clear exceptions for invalid states.

Prefer messages that explain:

1. What failed
2. Why it failed
3. Which file/object/parameter caused it
4. How the user can fix it

Avoid generic messages such as:

```text
Error
Failed
Invalid
Something went wrong
```

Use specific messages such as:

```text
STL import failed: detected 128 non-manifold edges in file model.stl.
```

---

## Logging

Use the repository's existing logging system if available.

If no logging system exists, use Python `logging`.

Solver logs should include:

- Step number
- Iteration number
- Residual norm
- Displacement increment norm
- Cutback status
- Convergence status
- Material update warnings
- Contact status changes

GUI logs should include:

- File import actions
- Mesh generation status
- Solver start and finish
- Errors and warnings
- User-triggered key actions

---

## Testing policy

When changing core code, add or update tests.

Minimum expectations:

### Geometry change

Add tests for:

- Valid geometry
- Invalid geometry
- Edge cases
- Serialization if supported

### Mesh change

Add tests for:

- Node count
- Element count
- Connectivity validity
- Mesh quality metrics

### Material change

Add tests for:

- Parameter validation
- Stress update
- Tangent shape
- State variable update
- Elastic limit behavior

### Solver change

Add tests for:

- Small linear system
- Boundary condition handling
- Residual convergence
- Non-convergence handling
- Stage history transfer if relevant

### GUI change

Add at least one non-interactive smoke test if possible.

If GUI testing is not available, ensure the GUI entry point imports successfully.

---

## Smoke test requirements

At minimum, the project should support:

```bash
python -m pytest tests/smoke -q
```

Recommended smoke tests:

```text
tests/smoke/test_import_core.py
tests/smoke/test_run_gui_import.py
tests/smoke/test_create_demo_project.py
tests/smoke/test_basic_mesh.py
tests/smoke/test_basic_solver.py
```

Smoke tests should be fast and should not require GPU hardware.

---

## GPU policy

GPU functionality should be optional.

CPU tests must pass without GPU dependencies.

When adding GPU code:

1. Provide a CPU fallback.
2. Guard imports carefully.
3. Detect device availability.
4. Add clear messages when GPU dependencies are missing.
5. Do not make GUI startup depend on GPU availability.
6. Do not make basic tests require CUDA.

Example pattern:

```python
try:
    import cupy as cp
except ImportError:
    cp = None
```

Then handle `cp is None` explicitly.

---

## Documentation expectations

Update documentation when behavior changes.

Useful documentation files:

```text
docs/architecture.md
docs/setup.md
docs/gui_usage.md
docs/solver_design.md
docs/benchmark.md
docs/stl_import.md
docs/troubleshooting.md
```

For new modules, include:

1. Purpose
2. Public API
3. Example usage
4. Known limitations
5. Test command

---

## Commit and change policy

Make focused changes.

Avoid mixing unrelated tasks.

For large tasks, prefer incremental implementation:

1. Add data model
2. Add core logic
3. Add tests
4. Add GUI binding
5. Add documentation
6. Add benchmark or example

Do not claim a feature is complete unless it is runnable and tested.

---

## Done definition

A task is considered done only when:

1. The code imports successfully.
2. Relevant tests pass.
3. The changed feature has a runnable path.
4. Failure cases produce clear messages.
5. New dependencies are documented.
6. The root-level run command still works.
7. The change does not break existing examples.
8. Documentation or comments are updated where needed.

For GUI tasks, done also means:

1. The page or control is reachable from the main window.
2. The user can see meaningful feedback.
3. Errors appear in the log panel or terminal.
4. The feature does not rely on hidden manual steps.

For solver tasks, done also means:

1. Convergence history is available.
2. Solver settings are explicit.
3. Material state is committed only after convergence.
4. Non-convergence is handled safely.
5. A small benchmark or smoke test verifies the path.

---

## Troubleshooting commands

Use these commands when diagnosing dependency or import problems:

```bash
python --version
python -m pip --version
python -m pip list
python -m compileall src tests
python -m pytest tests/smoke -q
```

Use this command to check uncommitted files:

```bash
git status
```

Use this command to search for obsolete names:

```bash
grep -R "production\|commercial\|fully_resident\|old_solver" src tests examples scripts
```

On Windows PowerShell, use:

```powershell
Select-String -Path "src\*", "tests\*", "examples\*", "scripts\*" -Pattern "production|commercial|fully_resident|old_solver" -Recurse
```

---

## Codex configuration note

If Codex reports:

```text
[features].codex_hooks is deprecated. Use [features].hooks instead.
```

Update Codex config from:

```toml
[features]
codex_hooks = true
```

to:

```toml
[features]
hooks = true
```

This belongs in Codex `config.toml`, not in this `AGENTS.md` file.

Common config locations:

```text
~/.codex/config.toml
.codex/config.toml
```

---

## Instructions for Codex

When starting a task:

1. Read this file.
2. Inspect the repository structure.
3. Identify the smallest safe implementation path.
4. Run the most relevant tests before and after changes when possible.
5. Prefer real runnable implementation over placeholder code.
6. Report clearly what was changed, what was tested, and what remains incomplete.

When the user asks to “continue iteration” or “push the system forward”:

1. Do not only edit documentation.
2. Prefer implementing one or more concrete missing capabilities.
3. Add or update tests.
4. Keep the root launcher usable.
5. Summarize progress by module.

When the user asks for a downloadable code package:

1. Ensure generated files are included.
2. Exclude cache folders such as `__pycache__`, `.pytest_cache`, `.venv`, and build artifacts unless needed.
3. Provide a clear root-level startup script.
4. Include a short usage note.

---

## Non-goals

Do not turn the repository into a purely theoretical prototype.

Do not replace tested simple code with complex untested abstractions.

Do not claim support for advanced features unless they are implemented, wired, and tested.

Examples of claims that require strong evidence:

- Production-grade nonlinear FEM solver
- Strict Mohr-Coulomb return mapping
- Fully resident GPU nonlinear contact solver
- Mortar contact with large sliding
- Consistent tangent for multi-surface plasticity
- Complete HSS small-strain hardening model
- Robust geological Boolean modeling
- Commercial-grade GUI modeling workflow

If such features are only partially implemented, describe them as partial, experimental, or scaffolded.

---

## Preferred response style for code work

When reporting work, use this structure:

```text
Changed:
- ...

Tested:
- ...

Known limitations:
- ...

Next recommended step:
- ...
```

Keep reports honest and specific.
