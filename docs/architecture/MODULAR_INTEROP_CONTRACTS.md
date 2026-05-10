# Modular Interoperability Contracts

## Rule

Subsystems should exchange dependency-light contract objects instead of importing one another's implementation packages.

## Stable chain

```text
geology_import -> document_model -> meshing -> stage_planning -> fem_solver -> postprocessing
```

## Layers

```text
contracts       DTOs and Protocols only
adapters        current implementation wrappers
modules         stable public module facades
services        headless orchestration used by GUI/CLI/automation
app             GUI and desktop shell only
```

## Direction

```text
app -> services/modules -> contracts -> adapters/implementations
```

Contracts must not import GUI/rendering/GPU/solver implementation packages.
Services must not import PySide6, PyVista, pyvistaqt or Warp directly.
