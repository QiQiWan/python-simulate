# Iteration 1.4.2a — CAD Facade Hardening and Acceptance Rename

## Why this iteration exists

The previous 1.4.2 label implied completed Native CAD/OCC integration. The actual implementation was a CAD-kernel facade: it could probe gmsh/OCC availability, execute deferred boolean features through gmsh/OCC when possible, and otherwise use deterministic AABB fallback geometry with synthetic persistent names.

This iteration intentionally renames the release and hardens the acceptance gate so fallback/native state cannot be mistaken for certified native BRep output.

## Release identity

- Version: `1.4.2a-cad-facade`
- Acceptance status: `accepted_1_4_2a_cad_facade`
- Release mode: `cad_facade_hardening`
- Native CAD claimed: `false`
- Native BRep certified: `false`

## Contract changes

- Capability contract: `geoai_simkit_cad_facade_capability_v1`
- Topology contract: `geoai_simkit_cad_facade_topology_index_v1`
- Feature execution contract: `geoai_simkit_cad_facade_feature_execution_v1`
- Acceptance contract: `geoai_simkit_release_1_4_2a_cad_facade_acceptance_v1`
- GUI payload section: `geometry_interaction.cad_facade`

## Acceptance hardening

The acceptance gate now rejects a build if:

1. The version is not `1.4.2a-cad-facade`.
2. The topology index is missing or still uses an outdated native-claim contract.
3. The feature execution report is missing or uses an outdated native-claim contract.
4. `native_backend_used` / `fallback_used` are not explicitly reported.
5. Fallback execution is not labelled as `aabb_fallback` or `mixed`.
6. The report does not explicitly set `native_brep_certified=false`.

## Backend status semantics

- `deterministic_aabb_facade`: no native backend used; deterministic bounds fallback executed.
- `native_passthrough_facade`: gmsh/OCC path was used, but BRep topology is not certified in 1.4.2a.
- `mixed_facade`: both native-like and fallback paths were used.

## Dependency files

- `requirements.txt`: strict desktop runtime stack.
- `requirements-gui.txt`: PySide/PyVista/VTK GUI group.
- `requirements-meshing.txt`: gmsh/meshio group.
- `requirements-cad-facade.txt`: CAD facade group.
- `environment-cad-conda.yml`: recommended conda-forge environment for binary GUI/VTK/gmsh stability.

## Known limitation

This release does not provide true OCC BRep shape persistence, certified OCC history maps, STEP/IFC solid topology import, or native physical group remapping. Those belong to the next native-kernel phase.
