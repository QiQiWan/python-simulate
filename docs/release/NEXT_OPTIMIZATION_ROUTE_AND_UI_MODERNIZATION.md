# Next optimization route and modern UI pass

This note records the post-1.2.4 optimization direction and the UI modernization pass applied to the phase workbench shell.

## Route

| Milestone | Theme | Acceptance |
|---|---|---|
| 1.2.5 | Desktop GUI experience hardening | Six-phase workbench is the only default launcher; phase cards, contextual ribbon and inspection panels are visually consistent. |
| 1.2.6 | Real 3D interactive modeling | Viewport picking, snapping, work planes, previews and CommandStack undo/redo operate as one modeling loop. |
| 1.2.7 | Native Gmsh/OCC loop | Native gmsh/meshio runtime produces physical-group Tet4 meshes and imports the tags back into GeoProjectDocument. |
| 1.2.8 | Solver credibility | Newton residual, tangent check, plastic integration and benchmark acceptance reports are emitted per phase. |
| 1.3.0 | Engineering beta | Foundation pit, slope and pile templates are executable from GUI through report export. |

## UI modernization applied

- Added a headless `modern_phase_workbench_ui_v1` contract.
- Added phase visual tokens: icon, accent color, soft accent, phase purpose and primary output.
- Replaced the PySide-only fallback shell's old toolbar-like phase row with six modern phase cards.
- Added a dark engineering header, status pill, card-style left/center/right panels and a visible roadmap tab.
- Shared the modern stylesheet with the PyVista NextGen workbench so both launch paths use the same visual language.
- Kept the launcher contract unchanged: the legacy flat editor remains disabled by default and only available through `GEOAI_SIMKIT_LEGACY_GUI=1`.

## Remaining UI risks

- The PySide-only shell still uses a placeholder text view instead of the full PyVista 3D viewport when PyVista is unavailable.
- Native desktop verification is still required on Windows/macOS/Linux with PySide6, PyVista, pyvistaqt, gmsh and meshio installed.
- The next high-value UI improvement is a real interaction recording test that launches the desktop app, switches all six phases and records screenshots.
