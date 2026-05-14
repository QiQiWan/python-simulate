# Iteration 1.1.3 Basic

## Scope

1.1.3 deepens the 1.0.5 foundation-pit workflow with four engineering-hardening tracks:

1. staged Mohr-Coulomb nonlinear correction and plastic point result fields;
2. Gmsh/OCC Tet4 project-mesh contract with deterministic Tet4 fallback in headless CI;
3. GUI interaction hardening for viewport tools, previews, selection and undo/redo contract;
4. groundwater / pore pressure / effective stress plus wall-soil contact interface enhancement.

## Boundary

This release is an auditable engineering workflow build.  It is not yet a certified commercial geotechnical solver.  Native Gmsh/OCC is used when available; otherwise a deterministic Tet4 surrogate records the fallback explicitly.
