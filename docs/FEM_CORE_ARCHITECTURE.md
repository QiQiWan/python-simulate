# Core FEM Architecture

The ordinary finite-element workflow is now separated from advanced research tracks.

```text
geometry -> mesh -> material -> element -> assembly -> solver -> result
```

GUI pages follow the same workflow:

```text
Modeling -> Mesh -> Solve -> Results -> Benchmark -> Advanced
```

`Benchmark` verifies the workflow. `Advanced` contains GPU, OCC and UQ capability-gated modules.
