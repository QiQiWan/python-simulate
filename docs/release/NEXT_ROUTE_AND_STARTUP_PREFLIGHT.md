# GeoAI SimKit 1.3.x → 1.4.x Optimization Route and Startup Preflight

## Current stabilization focus

The 1.3.0 Beta line now has a one-click foundation pit demo and a complete calculation pipeline. The next priority is not adding more isolated buttons; it is making the workflow dependable for real desktop users and engineering reviewers.

## Added in this build: Startup dependency preflight

The root launcher now performs a dependency preflight before entering the main workbench.

Startup path:

1. `start_gui.py` bootstraps the local `src` path.
2. `geoai_simkit.app.launch.launch_desktop_workbench()` invokes the preflight screen.
3. The preflight checker verifies required runtime packages.
4. If all required dependencies are available, the dialog auto-enters the six-phase workbench.
5. If dependencies are missing, the dialog lists missing packages and installation commands.

Required groups checked before entering the full workbench:

- Core numerical runtime: NumPy, SciPy, typing_extensions
- Desktop GUI: PySide6
- 3D viewport: PyVista, pyvistaqt
- Production meshing exchange: gmsh, meshio

Optional groups are reported but do not block:

- GPU acceleration: warp-lang
- Native OCC/BRep history: pythonocc-core

Developer bypass:

```bash
python start_gui.py --skip-preflight
# or
GEOAI_SIMKIT_SKIP_PREFLIGHT=1 python start_gui.py
```

## Recommended roadmap

### 1.3.1 — Launcher and desktop installation hardening

- Ship dependency preflight as the default entry screen.
- Add a GUI installer checklist for Windows/Linux/macOS.
- Add a `--smoke` preflight-only health report.
- Keep legacy GUI behind `GEOAI_SIMKIT_LEGACY_GUI=1` only.

Acceptance:

- Missing PySide6/PyVista/Gmsh is shown before main-window startup.
- Full dependency pass enters the six-phase workbench automatically.
- Missing dependency prompts include exact pip/conda commands.

### 1.3.2 — Native desktop validation

- Run manual GUI validation with PySide6 + PyVista + Gmsh installed.
- Capture startup screenshots and phase-switch screenshots.
- Verify one-click demo load/run/export from the GUI.

Acceptance:

- GUI opens with six phase cards.
- 1.3 Demo can load, run and export without using the terminal.

### 1.3.3 — Interactive 3D modeling reliability

- Harden pick ray, workplane, snapping and preview overlays.
- Add selection filtering per phase.
- Add input constraints and hover highlighting.

Acceptance:

- User can create and assign points/lines/surfaces/volumes in the 3D viewport.
- Undo/redo works across geometry, semantic assignment and material assignment.

### 1.3.4 — Native Gmsh/OCC production mesh closure

- Replace surrogate Tet4 in fully provisioned environments with native Gmsh/OCC output.
- Round-trip physical groups into `GeoProjectDocument`.
- Add mesh-quality gates that block solve when tags or quality metrics are missing.

Acceptance:

- Native Tet4 mesh exports and imports with material, block and phase tags intact.
- Mesh quality report is included in the release bundle.

### 1.4.0 — Engineering Beta 2

- Add at least three GUI templates: foundation pit, slope, pile-soil interaction.
- Add benchmark acceptance reports for each template.
- Add engineering report templates with screenshots, result fields and limitations.

Acceptance:

- Each template runs from GUI load → mesh → stage compile → solve → results → report export.
