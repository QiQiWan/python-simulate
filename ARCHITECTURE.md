# Architecture notes for geoai-simkit v4

## Design intent

`geoai-simkit` is organized as a **platform starter** rather than a single-purpose geotechnical code. The key architectural decision is to keep:

- geometry ingestion and conversion,
- simulation model description,
- material plugins,
- solver backends,
- and post-processing / visualization

as separate layers.

This allows the same platform to support excavation, slopes, additive manufacturing, or any other domain-specific workflow with minimal changes to the core.

## Layers

### 1. Geometry layer

Modules:
- `geometry.parametric`
- `geometry.ifc_import`
- `geometry.scene_graph`
- `geometry.voxelize`

Responsibilities:
- build parametric scenes
- import IFC geometry into `pyvista.MultiBlock`
- preserve block-level region and IFC metadata
- convert closed surfaces into volumetric Hex8-friendly grids via voxelization

### 2. Standardized simulation model layer

Modules:
- `core.model`
- `core.types`

Responsibilities:
- hold mesh / stage / materials / boundary conditions / loads / results in a domain-agnostic format
- provide simple helpers for result labels, stage lookup, and region access

### 3. Material plugin layer

Modules:
- `materials.registry`
- `materials.linear_elastic`
- `materials.mohr_coulomb`
- `materials.hss`

Responsibilities:
- register built-in materials
- support external plugin loading using `module:Factory`
- expose enough parameter metadata for current elastic-envelope solving and future constitutive integration

### 4. Solver layer

Modules:
- `solver.warp_backend`
- `solver.hex8_linear`
- `solver.staging`

Responsibilities:
- orchestrate stage execution
- choose the current best available solve path
- today: prefer Hex8 small-strain linear solve, otherwise fall back to graph-relaxation starter path
- tomorrow: host MC/HSS Gauss-point integration and Warp-native kernels

### 5. Post-processing layer

Modules:
- `post.exporters`
- `post.stage_mesh`
- `post.viewer`

Responsibilities:
- software-internal preview via PyVista
- export direct VTK/mesh formats
- reconstruct stage-specific datasets from `X0 + U@stage`
- export ParaView-friendly `.pvd + .vtu` time-series bundles

### 6. Application layer

Modules:
- `app.main_window`
- `cli`

Responsibilities:
- drive common workflows
- visualize geometry and stage results
- expose voxelization and ParaView bundle export without requiring custom scripting

## Why the voxelization layer matters

A major platform limitation in earlier versions was that imported IFC/scene geometry often stayed as surfaces and therefore bypassed the Hex8 solver path.

The voxelization layer reduces this gap by making it possible to:

1. import IFC blocks as surfaces,
2. voxelize them into volumetric cells,
3. preserve region identities,
4. route them into the same solver/data/export pipeline.

This is not a replacement for a full meshing backend, but it is a practical bridge between design geometry and early solver development.

## Why stage-series export matters

The internal model stores stage-tagged result fields such as `U@stage` and `stress@stage`. Earlier exports only wrote the final mesh state.

The new stage export pipeline builds stage-specific datasets by:
- starting from the original coordinates stored in `X0`
- activating only the fields belonging to one stage
- reconstructing the stage geometry
- writing `.vtu` snapshots and a `.pvd` collection

This makes the platform much more useful for staged excavation and future process simulations.

## Current solver honesty

The solver stack is still a **starter**:
- Hex8 small-strain linear path is real and usable for toy / starter cases
- MC and HSS are still represented as elastic envelopes in the current path
- nonlinear constitutive integration, shell/beam elements, interfaces, and contact remain future work

The architecture is intentionally prepared for that next step by keeping geometry, materials, and post-processing already in place.


## v12 增强

- 统一右侧属性检查器（Selection / Actions / Solver）
- IFC 对象右键菜单：设为新 Region、归并到现有 Region、合并 Region、设置对象角色
- Geometry 页面新增对象/Region 编辑区
- Material 页面支持“当前参数 -> 选中区域”的自定义参数赋值
- Stage 页面支持录入初始增量、最大迭代、线搜索和备注
- 预览支持高亮选中对象/Region
