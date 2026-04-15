# geoai-simkit v10

`geoai-simkit` is a **graphics-first simulation platform starter** for geotechnical and related engineering problems. It is designed around four ideas:

- **geometry is editable/importable** (parametric scenes or IFC)
- **materials are pluggable** (linear elastic, Mohr–Coulomb, HSS/HSsmall-style)
- **solvers are replaceable** (current Warp-oriented backend with linear and nonlinear Hex8 paths)
- **post-processing is native** (in-app preview + ParaView/VTK/mesh export)

The package already contains:

- parametric pit example
- IFC import hooks
- voxelization for solver-friendly Hex8 grids
- stage-based analysis model
- Hex8 linear path
- Hex8 nonlinear path with material-state carry-over
- structural overlays (`truss2`, translational `beam2`, membrane-style `shellquad4`)
- node-pair interface contact/friction starter
- Qt/PyVista preview
- VTK / VTU / VTM / XDMF / OBJ / PLY / STL export
- ParaView stage bundle export (`.pvd` + per-stage `.vtu`)

It is still **not a full commercial-grade nonlinear FEM product**. The main remaining gaps are:

- fuller industrial shell quality / element stabilization beyond the current starter implementation
- mortar / surface-to-surface contact
- more rigorous Mohr–Coulomb corner/apex return mapping
- fuller HSsmall memory and cyclic rules
- more advanced sparse/global large-scale assembly beyond the current SciPy-backed starter path
- coupled seepage / effective stress / consolidation workflows


## What is new in v12

This revision focuses on **GPU residency, multi-GPU selection, and UI/runtime modernization**:

- added **resident GPU upload caches** for Warp Hex8 and nonlinear continuum paths to reduce repeated host→device uploads
- solver progress now reports **gpu-data-upload** and **gpu-data-ready** phases, including cache hits and upload timing
- results page can now **detect all CUDA GPUs**, highlight-select a GPU pool, and pass the selected pool to backend scheduling
- compute preferences now support **allowed GPU device pools** in addition to single-device and round-robin selection
- improved default GPU throughput tuning with less aggressive line-search retries and fewer synchronization-heavy checks
- GUI styling was refreshed and key solver buttons now use standard icons

## What is new in v11

This revision focuses on **Warp/CUDA element-level acceleration and solver configurability**:

- added an optional **Warp Hex8 element kernel path** for linear Hex8 stiffness/body-force evaluation
- keeps **CPU sparse global assembly** as a stable fallback, so environments without Warp still work
- stores element-assembly details under `model.metadata["linear_element_assembly"]`
- added configurable Warp knobs through `SolverSettings.metadata`
- added documentation for recommended CUDA / thread / fallback settings

## What is new in v10

This revision focuses on **desktop usability and interaction design**:

- solver now runs in a **background Qt worker thread**, so the GUI no longer blocks during long solves
- added **stage/iteration progress bars** and live progress messages
- left control area is now a **workflow stepper** instead of a button stack
- added **region/material assignment editor** with direct binding to selected regions
- added **stage/boundary editor** for step-by-step setup
- added **validation panel**, **task table**, and **convergence history table**
- results page now separates **stage** and **field** selection
- root-directory launchers remain available (`run_demo.py`, `run_gui.py`, `run_checks.py`)

## What is new in v9

This revision focuses on **solver robustness and root-directory usability**:

- added a sparse-capable linear algebra helper with SciPy fallback
- nonlinear Hex8 path now supports backtracking line search and load cutbacks
- nonlinear convergence history is stored in `model.metadata["solver_history"]`
- root install now includes `scipy` and adds `requirements-solver.txt`
- environment checks now report SciPy availability

Earlier usability improvements remain in place:

- added root-level launchers:
  - `run_demo.py`
  - `run_gui.py`
  - `run_checks.py`
- added `python -m geoai_simkit ...` support through `__main__.py`
- added environment diagnostics via `geoai-simkit check-env`
- added split requirement files for base / UI / IFC / Warp / dev
- added a root `Makefile` for common tasks
- updated docs so you can run from the project root without first packaging/installing the wheel
- changed CLI imports to **lazy imports**, so `check-env` works even when GUI or solver extras are not installed

## How to run from the project root

Assuming you are in the repository root.

### Option A: run directly from root without installing the package

This is the fastest way to start.

```bash
python run_checks.py
python run_demo.py
python run_gui.py
```

These scripts automatically add `src/` to `PYTHONPATH`.

### Option B: use the module entrypoint from root

```bash
PYTHONPATH=src python -m geoai_simkit check-env
PYTHONPATH=src python -m geoai_simkit demo --out-dir exports_root
PYTHONPATH=src python -m geoai_simkit gui
```

### Option C: install editable and use the CLI

```bash
python -m pip install -e .
geoai-simkit check-env
geoai-simkit demo --out-dir exports_root
geoai-simkit gui
```

## Recommended dependency setup

### Minimal headless usage

```bash
python -m pip install -r requirements.txt
```

### Add GUI

```bash
python -m pip install -r requirements-ui.txt
```

### Add IFC import

```bash
python -m pip install -r requirements-ifc.txt
```

### Add Warp backend dependency

```bash
python -m pip install -r requirements-warp.txt
```

### Add test/dev tools

```bash
python -m pip install -r requirements-dev.txt
```

Or use the convenience targets:

```bash
make install
make install-ui
make install-ifc
make install-warp
make install-dev
make install-solver
```

## Typical root-directory workflow

```bash
python run_checks.py
python run_demo.py
```

This generates outputs under `exports_root/`.

Then open ParaView with the bundle, for example:

- `exports_root/pit_demo_bundle/pit_demo.pvd`

To launch the local viewer:

```bash
python run_gui.py
```

## In-app workflow

1. Create a parametric model or import IFC.
2. Check the left-side workflow stepper and validation list.
3. Voxelize / prepare a Hex8-friendly solver mesh if needed.
4. Select regions and assign materials in the material page.
5. Configure stages and boundary conditions in the stage page.
6. Run the solver in the background and track progress in the progress bars / task table.
7. Inspect stages and result fields in-app, then export to VTK/ParaView if needed.

## Current solver behavior

The current backend chooses among these paths:

- **nonlinear-hex8** if nonlinear materials, structures, or interfaces are present
- **linear-hex8** if the model is a Hex8-friendly volumetric mesh without nonlinear extras
- **graph-relaxation fallback** for arbitrary imported meshes not yet suitable for Hex8 solving

## Important notes for development

- `beam2` is currently a **translational engineering approximation**, not a full rotational beam element.
- `shellquad4` is currently **membrane-only**.
- contact is currently **node-pair penalty/friction**, not mortar contact.
- the Warp backend is still a **platform starter** and not yet a full Warp-native sparse FEM assembly stack.

## Handy commands

### Run checks

```bash
python run_checks.py
```

### Run the packaged demo

```bash
python run_demo.py
```

### Run tests

```bash
PYTHONPATH=src pytest -q
```

or

```bash
make test
```

### Launch the GUI

```bash
python run_gui.py
```

## Main modules

- `geoai_simkit.geometry.ifc_import` – IFC import via IfcOpenShell iterator
- `geoai_simkit.geometry.voxelize` – surface-to-volume voxelization helper
- `geoai_simkit.materials.registry` – pluggable material model registry
- `geoai_simkit.solver.warp_backend` – platform backend with linear/nonlinear Hex8 paths
- `geoai_simkit.solver.hex8_nonlinear` – nonlinear Hex8 path with state carry-over
- `geoai_simkit.solver.structural_elements` – structural overlays
- `geoai_simkit.solver.interface_elements` – contact/interface starter
- `geoai_simkit.post.exporters` – direct export + ParaView bundle export
- `geoai_simkit.app.main_window` – Qt + PyVista preview app


## v12 增强

- 统一右侧属性检查器（Selection / Actions / Solver）
- IFC 对象右键菜单：设为新 Region、归并到现有 Region、合并 Region、设置对象角色
- Geometry 页面新增对象/Region 编辑区
- Material 页面支持“当前参数 -> 选中区域”的自定义参数赋值
- Stage 页面支持录入初始增量、最大迭代、线搜索和备注
- 预览支持高亮选中对象/Region


## 额外网格划分依赖

```bash
python -m pip install -r requirements-meshing.txt
```

若本机安装了 `gmsh` 可执行程序，并安装了 `meshio`，即可在 GUI 的“网格划分流程”中选择 `gmsh_tet`。若不可用，软件会提示并可回退到体素化。

---

# Consolidated project notes


## Architecture

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


## Continue Optimization Notes

# 本轮继续优化内容

## 1. Block sparse pattern 构建加速
- `build_node_block_sparse_pattern()` 从 Python 三重/四重循环改成 NumPy 向量化构建。
- 现在通过连接关系批量生成 `(row_node, col_node)` 键，再用 `np.unique(..., return_inverse=True)` 一次性生成：
  - `rows`
  - `cols`
  - `diag_block_slots`
  - `elem_block_slots`
- 对大网格、interface / structure / continuum 统一建图时，这一块会明显更快。

## 2. Block sparse matvec 加速
- `block_values_matvec()` 改成向量化实现：
  - 原来逐 block Python 循环
  - 现在使用 `einsum + add.at` 完成节点块乘加
- 这对非线性迭代里频繁计算内力/残差更有帮助。

## 3. CSR 物化索引缓存
- `block_values_to_csr()` 现在缓存每个 `block_size` 下展开后的 `(rr, cc)` 索引。
- 避免每次 materialize 都重复构造 COO 行列索引。

## 4. Pattern lookup 缓存
- `pattern_slot_lookup()` 现在挂到 `BlockSparsePattern` 上缓存。
- interface / structure 混合装配时，减少重复构造 node-pair -> slot 映射。

## 5. Warp 设备侧 pattern 数组缓存
- 新增 `get_pattern_device_arrays()`：
  - `rows_wp`
  - `cols_wp`
  - `diag_slots_wp`
- 现在 GPU block sparse 求解不会每次都重新 `wp.from_numpy(...)` 上传相同 pattern。

## 6. 修复 GPU block sparse solve 的隐性污染问题
- 之前 `_try_warp_block_sparse_solve()` 会直接在 `matrix.values_device` 上叠加：
  - regularization
  - Dirichlet penalty
- 如果同一个矩阵对象被多次求解，会导致设备端值被反复污染。
- 现在新增 `clone_warp_block_values()`，求解前先复制 scratch values，再在 scratch 上做修正。
- 这是一个**性能+正确性**同时相关的关键修复。

## 7. Warp 向量类型兼容性增强
- `warp_hex8.py`
- `warp_nonlinear.py`

优先使用：
- `wp.vec6f / wp.vec6`
- `wp.vec8f / wp.vec8`

只有在不存在时才退回动态 vector factory。
这样对不同 Warp 版本更稳，也能降低模块编译期不兼容的概率。

## 验证
- 全量测试：`37 passed, 3 skipped`


## Gpu Continuum Downsink Analysis

# GPU Continuum Downsink Analysis

## This round

### 1) Global assembly no longer depends on CPU COO concatenation for the Warp path

Previous path:
- Warp kernel computed per-element `Ke/fe`
- Host copied all element matrices back
- CPU built `scipy.sparse.coo_matrix(...)`

Current path:
- Precompute a stable node-block sparsity pattern once (`8x8` node-pair blocks per hex element, `3x3` DOF blocks per node pair)
- Warp kernel still computes element-level `Ke/fe`
- A second Warp kernel performs **atomic accumulation** into:
  - device-side global `block_values[nnz_blocks, 3, 3]`
  - device-side global internal/body force vector
- CPU is only used as a **finalization step** when a SciPy CSR matrix is still required by the remaining solve path

This removes the worst CPU-side `COO` aggregation bottleneck and large repeated host-side concatenation.

### 2) Nonlinear continuum got a Warp assembly entry point

Added `src/geoai_simkit/solver/warp_nonlinear.py`.

Supported GPU families in this round:
- `HSS` / `HSsmall`: GPU update + internal force/tangent accumulation
- `Mohr-Coulomb`: GPU **surrogate** path based on a Drucker-Prager style invariant return mapping

The nonlinear Warp path now does the following inside kernels:
- compute Hex8 `B`-operator contributions at each Gauss point
- update Gauss-point state
- accumulate internal force directly to the global device vector
- accumulate tangent blocks directly to the global device block matrix
- emit updated state arrays back to Python only once per assembly call

### 3) Stable sparsity pattern is reused more aggressively

Both the linear Warp path and the nonlinear Warp path now share the idea of:
- node-block pattern precomputation
- stable element->block slot mapping
- device-side block accumulation

That means repeated nonlinear iterations avoid rebuilding row/col triplet layouts from scratch.

## Important accuracy note

The new HSS Warp path follows the existing code's Drucker-Prager/cap style approximation and is aligned with the current CPU model intent.

For Mohr-Coulomb, the current GPU path is intentionally marked as a **surrogate**:
- exact principal-space active-plane return mapping is still the authoritative CPU path
- the GPU path uses an invariant DP-style surrogate to keep the workflow on GPU and remove Python loops
- if tensile cut-off is active, the solver falls back to CPU for safety

## What is still not fully eliminated

### A) Final CSR materialization can still occur on CPU
The strongest remaining CPU dependency is the final conversion from device block-values into SciPy CSR when the rest of the solve stack still expects SciPy sparse matrices.

To remove this completely, the next step would be:
- keep the global stiffness as a Warp `BSR` object end-to-end
- apply BC elimination/reduction on the Warp sparse structure directly
- pass that reduced Warp matrix directly into the GPU linear solver without host conversion

### B) Direct GPU sparse solver is still not available in the current Warp-centric stack
This round strengthens the **GPU iterative** path, but it does not add a true sparse direct GPU factorization backend.

Current implication:
- for large and well-conditioned systems, Warp iterative solves are preferred
- for difficult systems, CPU fallback/direct sparse still remains the most robust emergency path

### C) Structures / interfaces are not fully on GPU
Continuum assembly is further down-sunk, but structural and interface contributions are still host-dominant.

## Practical next step recommendation

If the goal is **near-full GPU solve path**, the next most valuable step is:
1. keep the global continuum tangent in Warp `BSR`
2. implement GPU-side BC elimination / masking for free DOFs
3. solve the reduced system directly through `warp.optim.linear`
4. only copy final displacement/state results back to host


## Gpu Fullpath Next Config

# GPU Full-Path Configuration Notes

## New main-path settings

Use these in `SolverSettings.metadata`:

```python
metadata={
    "require_warp": True,
    "warp_full_gpu_linear_solve": True,
    "warp_gpu_global_assembly": True,
    "warp_solver": "cg",           # or bicgstab / gmres
    "warp_preconditioner": "diag", # warp-side preconditioner hint
    "dirichlet_penalty": 1.0e8,      # full-system GPU Dirichlet enforcement
    "warp_nonlinear_enabled": True,
    "warp_nonlinear_force": False,
    "warp_mc_surrogate": True,
}
```

## What changed in this round

- Warp block-sparse assembly now keeps the assembled 3x3 block system in a device-oriented container instead of immediately materializing a SciPy CSR matrix.
- When `warp_full_gpu_linear_solve=True`, the solver can now try a **full-system GPU solve with Dirichlet penalty enforcement**, avoiding the earlier CPU-side `Kff = K[free][:, free]` reduction path.
- Nonlinear Warp continuum assembly now returns the same block-sparse container when the translational DOF system is not padded by extra rotational DOFs.

## Current practical boundaries

- The strongest path is still **3 translational DOFs per node** (`block_size=3`).
- If structural/interface DOFs are added and require matrix summation with non-block contributions, the code may still materialize to SciPy CSR.
- The Mohr-Coulomb GPU path remains the fast surrogate route; the CPU path is still the reference for the most exact return-mapping behavior.


## Gpu Scan And Mapping

# GPU Scan and Mapping Summary

This iteration pushes more of the solver chain toward the GPU-oriented block-sparse path and maps the compute-panel settings more explicitly into that path.

## Newly integrated into the GPU-oriented block sparse main path

- Continuum Hex8 block sparse pattern can now be built from a **union connectivity set** instead of only continuum cells.
- Interface node-pair contributions can now be assembled as **3x3 nodal block values** on the same translational block pattern.
- Structural element contributions now expose a **hybrid assembly**:
  - translational-translational sub-blocks are accumulated into the same 3x3 nodal block pattern,
  - rotational and translation-rotation couplings remain in a tail sparse matrix.
- Nonlinear state evaluation now tries to keep the tangent in custom block-sparse form as long as possible.
- The solve panel now maps three extra controls into solver metadata:
  - `warp_interface_enabled`
  - `warp_structural_enabled`
  - `warp_unified_block_merge`

## Practical effect

For cases dominated by:

- continuum translational DOFs,
- contact/interface translational pairs,
- truss-like structural coupling,

more of the matrix stays in the block-sparse path until the linear solve stage.

For beam/shell/frame cases with rotation couplings, the translational-translational part still merges into block-sparse form, while the remaining coupling terms are kept in the sparse tail.

## Remaining limits

The following are still not fully GPU-native end-to-end:

- beam/shell rotational couplings are not yet represented as a pure GPU block sparse solve path,
- the final solve may still materialize to CSR when rotational/coupling tails are present,
- Mohr-Coulomb GPU path still uses a surrogate path for the fast GPU branch.

## New solver metadata keys

- `warp_interface_enabled`
- `warp_structural_enabled`
- `warp_unified_block_merge`

These are now emitted from the solver compute panel and consumed in the nonlinear solve path.


## Multi Gpu And Warp Fix Notes

# Warp GPU / multi-GPU 修复说明

## 本轮修复

### 1. 修复 `warp.optim.linear ... (error)` 噪声与不稳定问题
- GPU 线性求解现在默认走更稳妥的调用组合：
  - 不再默认先尝试 `check_every=0`
  - 不再默认开启 `use_cuda_graph=True`
- Warp 迭代求解会在以下顺序中选择更稳的求解器：
  - 对称系统：`cg -> cr`
  - 非对称系统：`bicgstab -> gmres`
- 某个设备/求解器/预条件组合一旦在 Warp 侧失败，会被缓存为失败组合，后续本次进程内不再重复触发同类编译/加载错误。

### 2. 多卡机器自动检测与设备选择
- 新增 `solver/gpu_runtime.py`
- 自动检测全部 CUDA 设备
- 设备下拉框现在支持：
  - `auto-best`：自动选择显存/排序最优 GPU
  - `auto-round-robin`：多卡机器按轮询方式选卡
  - `cpu`
  - 所有已检测到的 `cuda:i`
- 求解 metadata 中会保存：
  - `warp_device`
  - `warp_selected_device`

### 3. 面板与后台求解映射增强
- 求解模块界面会显示更完整的硬件摘要
- 设备选择已真正映射到后端 Warp 设备选择，而不是只改 UI 文案
- `auto-round-robin` 会在多次求解/多阶段任务中按序选择 GPU

## 关键实现点

### 设备选择
- `choose_cuda_device()` 统一处理：
  - 自动选卡
  - 轮询选卡
  - 指定 `cuda:i`
- `WarpBackend`、`warp_hex8`、`warp_nonlinear`、`linear_algebra` 已统一使用这套逻辑

### Warp 线性求解稳定性
- 全 GPU block-sparse solve 与稀疏 solve 都改成：
  - 更稳的 solver fallback 链
  - 更稳的 kwargs 组合
  - 对失败组合做缓存，避免反复刷错误

## 当前建议

### 单卡 RTX 40 系列
- 设备：`auto-best`
- 预设：`gpu-fullpath`
- Warp 预条件：`diag`
- Warp CUDA Graph：保持关闭（当前默认）

### 多卡机器
- 单次求解：优先 `auto-best`
- 多次连续求解/批处理：可用 `auto-round-robin`

## 回归
- `41 passed, 3 skipped`


## Progress And Gpu Notes

本轮继续优化并重点修复“界面看起来在算，但长时间没有任何进展”的问题。

主要改动：

1. 非线性求解新增细粒度进度事件
- step-start
- iteration-start
- assembly-start / assembly-done
- linear-solve-start / linear-solve-done
- line-search-start / line-search-done
- step-converged / cutback / step-stopped

这样在第一轮装配、GPU kernel 首次编译、线性求解、线搜索期间，界面都会持续更新，不再只在“某一轮迭代全部完成后”才刷新。

2. 进度条支持“忙碌态”到“确定进度”切换
- 求解刚开始时使用不定进度条
- 一旦收到带 fraction 的进度事件，自动切换为确定进度条

3. 心跳提示带当前阶段信息
- 后台求解心跳现在会显示最近的子阶段信息
- 例如：正在装配、正在线性求解、正在线搜索

4. 进度估算器支持显式 fraction
- 如果求解器提供 stage_fraction / fraction，则优先使用
- 避免一直停在 0% 的视觉假象

5. 保持 GPU 主路径
- 本轮没有削弱 GPU / Warp 路径
- 主要修复的是“长阶段无可见进展”的可观测性问题

测试：
- 39 passed, 3 skipped


## Commercial-style nonlinear control defaults

The GUI now boots safely with a populated GPU selection list on the Solve / Results page.

Nonlinear staged construction also defaults to a more commercial-FEA-like control policy:
- adaptive increment growth/shrink
- predictor warm start between steps/stages
- modified-Newton tangent reuse
- tighter stagnation detection and cutback control
- explicit stage abort on repeated failed substeps

These defaults are applied automatically unless stage metadata overrides them.

## Solver Compute Panel

# Solver Compute Panel

The solver/results page now includes an explicit **Backend Compute Configuration** panel.

## What can be configured

- Device: `auto`, `cpu`, `cuda`
- CPU threads / cores used by the backend (`0 = auto`)
- Require Warp
- Warp Hex8 assembly
- Warp nonlinear continuum assembly
- GPU linear main path
- GPU global assembly
- Reordering: `auto`, `rcm`, `colamd`, `amd`, `mmd_ata`, `mmd_at_plus_a`, `natural`
- Preconditioner: `auto`, `block-jacobi`, `spilu`, `jacobi`, `none`
- Solver strategy: `auto`, `cg`, `minres`, `bicgstab`, `gmres`, `direct`
- Warp preconditioner: `diag`, `none`
- Iterative tolerance and iterative max iterations

## Presets

- `auto`: choose GPU when CUDA is available, otherwise CPU
- `cpu-safe`: conservative CPU-only profile
- `gpu-throughput`: GPU-first profile with aggressive throughput settings
- `gpu-fullpath`: require Warp/CUDA and keep the main linear path on GPU when possible

## Persistence

The panel values are stored into `model.metadata["solver_settings"]` and then propagated into `SolverSettings.metadata` during solve submission.

## Practical recommendation

For large Hex8 models on a machine with CUDA:

- Profile: `gpu-fullpath`
- Device: `cuda`
- Threads: `0` or `CPU cores - 1`
- Ordering: `auto`
- Preconditioner: `auto`
- Strategy: `auto`
- Require Warp: enabled

For debugging or small models:

- Profile: `cpu-safe`
- Device: `cpu`
- Threads: about half of available CPU cores


## Commercial-style nonlinear control defaults

The GUI now boots safely with a populated GPU selection list on the Solve / Results page.

Nonlinear staged construction also defaults to a more commercial-FEA-like control policy:
- adaptive increment growth/shrink
- predictor warm start between steps/stages
- modified-Newton tangent reuse
- tighter stagnation detection and cutback control
- explicit stage abort on repeated failed substeps

These defaults are applied automatically unless stage metadata overrides them.

## Solver Strategy Analysis

# 求解策略问题分析与修复说明

本次重点检查了用户提出的 5 个潜在问题，并对当前代码做了相应修复。

## 1. 可能在用通用稀疏解法，甚至不合适的解法

**结论：存在。**

之前的 `solve_linear_system()` 主要是：

- 小系统：`numpy.linalg.solve`
- 大稀疏系统：先 `CG` 试一下
- 再回退 `spsolve`

这对真正的工程网格并不够细分，因为没有充分区分：

- 对称正定
- 对称不定
- 一般非对称

### 本次修复

现在会按矩阵性质选择：

- **对称**：优先 `CG`，再尝试 `MINRES`
- **一般非对称**：优先 `BiCGSTAB`，再尝试 `GMRES`
- **最终回退**：`SPLU`

并保留直接解回退，提高稳健性。

## 2. 没有做重排序（AMD / METIS / RCM）

**结论：基本存在。**

之前几乎没有真正的重排序策略。

### 本次修复

- 迭代路径支持 `RCM`
- 直接分解路径支持 `COLAMD / MMD_ATA / MMD_AT_PLUS_A`
- 在上下文中缓存 permutation，重复求解时可复用

> 说明：SciPy 生态里更容易直接稳定接入的是 `RCM + SuperLU permc_spec(COLAMD/MMD_*)`。真正的 METIS 还没有作为强依赖接入。

## 3. 没有好的预条件

**结论：存在。**

之前顶多相当于对角预条件或无预条件。

### 本次修复

- 新增 `block-jacobi`，针对每节点 3 自由度的 Hex8 位移块更合适
- 新增 `SPILU` 预条件选项
- Warp GPU 路径接入 `warp.optim.linear.preconditioner` 接口

## 4. 没有复用分解

**结论：存在。**

之前每次都近似重新开始，没有系统复用：

- 稀疏 pattern
- permutation
- 预条件器
- 分解器

### 本次修复

新增 `LinearSolverContext`：

- 复用 pattern signature
- 复用 permutation
- 复用 `block-jacobi` / `SPILU` 预条件器
- 数值完全相同时可复用 `SPLU` 分解

## 5. 没有利用矩阵对称性、块结构、稀疏模式稳定性

**结论：存在。**

### 本次修复

- 自动检测近似对称矩阵
- Hex8 默认按 `block_size=3` 处理
- 非线性牛顿迭代里的线性子问题引入上下文复用
- 更适合 Hex8 位移场的块 Jacobi 预条件

## Warp / CUDA 路径

本次还新增了 **GPU 优先**的线性求解路径：

- `warp_hex8`：Hex8 单元级 Warp/CUDA 装配
- `solve_linear_system()`：当 `warp_full_gpu_linear_solve=True` 且设备为 CUDA 时，优先尝试 Warp 稀疏矩阵 + GPU 迭代解法

## 仍可继续优化的部分

最值得继续做的方向：

1. 把非线性 `_assemble_continuum_response()` 全部下沉到 Warp kernel
2. 进一步做 **3x3 block BSR** 的全 GPU 装配与求解闭环
3. 若后续允许引入额外依赖，可进一步接：
   - `sksparse/cholmod`（更强的 SPD 直接解）
   - `PyAMG` / `AMGX`（更强的多重网格预条件）
   - `METIS`（更强的图重排序）


## Warp Cuda Config

# Warp/CUDA 核心配置说明（GPU 优先版）

当前版本将 **`warp-lang` 作为必装依赖**，并将线性求解主流程调整为 **GPU 优先**：

- **Warp/CUDA 负责**
  - Hex8 单元级刚度与体力装配
  - 稀疏线性系统的 GPU 迭代求解（优先）
- **CPU 负责**
  - 边界条件消元、部分回退求解、以及当前尚未完全下沉的非线性材料更新逻辑

> 建议生产环境直接安装 `warp-lang>=1.12` 并使用 NVIDIA CUDA 设备运行。

## 安装

```bash
pip install -U warp-lang>=1.12
```

Warp 官方文档说明：Warp 提供 `warp.sparse` 稀疏矩阵模块以及 `warp.optim.linear` 的 GPU 迭代线性求解器（CG / BiCGSTAB / CR / GMRES），适合把稀疏求解主循环放到 CUDA 上。citeturn652422view0turn652422view1turn214200search5

## 推荐配置

```python
from geoai_simkit.solver.base import SolverSettings

settings = SolverSettings(
    device="cuda",
    thread_count=0,
    prefer_sparse=True,
    max_iterations=32,
    tolerance=1.0e-6,
    metadata={
        # 强制要求 Warp 存在
        "require_warp": True,

        # 单元级 Warp/CUDA 装配
        "warp_hex8_enabled": True,
        "warp_hex8_force": True,
        "warp_hex8_min_cells": 1,
        "warp_hex8_precision": "float32",
        "warp_hex8_fallback_to_cpu": False,

        # GPU 稀疏线性求解
        "warp_full_gpu_linear_solve": True,
        "warp_solver": "cg",              # 对称正定优先 cg
        "warp_preconditioner": "diag",    # Warp 预条件器名（按实际安装版本可调整）

        # CPU 回退 / 通用稀疏解法的策略层
        "solver_strategy": "auto",
        "ordering": "rcm",               # 也可用 natural / colamd / mmd_ata / mmd_at_plus_a
        "preconditioner": "block-jacobi",# 也可用 spilu / jacobi / none
        "block_size": 3,
        "iterative_tolerance": 1.0e-8,
        "iterative_maxiter": 4000,
        "gmres_restart": 60,
        "spilu_drop_tol": 1.0e-3,
        "spilu_fill_factor": 8.0,
    },
)
```

## 关键参数解释

### 1) 必装 Warp

- `require_warp=True`
  - 未安装 Warp 或无法初始化 CUDA 时，直接报错而不是悄悄回退。

### 2) GPU 单元装配

- `warp_hex8_enabled`
  - 开启 Hex8 单元级 Warp kernel。
- `warp_hex8_force`
  - 无论模型大小，都优先尝试 Warp kernel。
- `warp_hex8_fallback_to_cpu=False`
  - 生产环境建议和 `require_warp=True` 一起用，确保真正走 GPU 主路径。

### 3) GPU 稀疏线性求解

- `warp_full_gpu_linear_solve=True`
  - 尝试使用 Warp 稀疏矩阵 + GPU 迭代解法。
- `warp_solver`
  - `cg`：适合对称正定系统。
  - `bicgstab` / `gmres`：适合一般非对称系统。

Warp 官方文档明确提供了 `warp.sparse` 稀疏矩阵和 `warp.optim.linear` 中的 `cg`、`bicgstab`、`cr`、`gmres` 以及 `preconditioner` 接口。citeturn652422view0turn652422view1

### 4) 重排序与预条件

- `ordering`
  - `rcm`：当前默认推荐，适合迭代路径降低带宽。
  - `colamd` / `mmd_ata` / `mmd_at_plus_a`：主要给直接分解回退路径使用。
- `preconditioner`
  - `block-jacobi`：优先利用 3 自由度节点块结构。
  - `spilu`：一般稀疏系统更稳健，但构建成本更高。

### 5) 结构块大小

- `block_size=3`
  - Hex8 位移自由度天然是每节点 3 自由度，建议保持 3。
  - 这样更容易利用块对角预条件和块 BSR 思路。

## 当前版本已经修复/改进的求解问题

### 已修复 1：不再只用“通用稀疏解法”

现在会根据矩阵特性做选择：

- 对称系统：优先 `CG / MINRES`
- 一般系统：优先 `BiCGSTAB / GMRES`
- 失败时：回退到 `SPLU`

### 已修复 2：加入重排序

- 迭代路径支持 `RCM`
- 直接分解路径支持 `COLAMD / MMD_*`

### 已修复 3：加入更合适的预条件

- 新增 `block-jacobi`
- 新增 `SPILU`
- Warp GPU 路径支持 Warp 自带预条件器接口

### 已修复 4：加入 pattern / 预条件 / 分解复用

- 稀疏 pattern 会缓存
- RCM permutation 会复用
- `block-jacobi` / `SPILU` 预条件器支持复用
- 相同矩阵数值时可复用 `SPLU` 因子

### 已修复 5：开始利用对称性、块结构、稀疏模式稳定性

- 自动检测近似对称矩阵
- Hex8 默认按 `block_size=3` 处理
- 非线性牛顿迭代内部引入 `LinearSolverContext`，可复用 pattern 和预条件器

## 运行后可检查的元数据

线性 Hex8 路径可检查：

```python
model.metadata.get("linear_element_assembly", {})
```

通常可看到：

- `backend`
- `device`
- `used_warp`
- `linear_solver`
- `linear_ordering`
- `linear_preconditioner`
- `warnings`

## 建议的实际使用方式

### 线性大模型

- `device="cuda"`
- `require_warp=True`
- `warp_full_gpu_linear_solve=True`
- `warp_solver="cg"`
- `ordering="rcm"`
- `preconditioner="block-jacobi"`

### 非线性模型

- 当前版本已经把 **牛顿迭代里的线性子问题** 升级成“重排序 + 预条件 + 复用”的策略层
- 但 **Gauss 点材料更新 / 一致切线装配** 还没有完全下沉成 Warp kernel
- 下一步最值得继续做的是：把 `_assemble_continuum_response()` 的材料更新和块装配一起搬到 Warp


## Warp Gpu Solve Shape Fix

# Warp GPU solve shape / fallback fix

This update fixes a runtime error where the nonlinear solve could fail with:

`IndexError: index ... is out of bounds for axis 0 with size 1`

## Root cause

The Warp linear solver wrappers were reading the **solver return value** as if it were the solution vector.
In Warp 1.12.x, iterative solvers such as `cg`, `bicgstab`, and `gmres` update the provided `x` buffer in place and return solver statistics instead.
That caused the code to sometimes treat the iteration counter tuple as the displacement vector.

## Fixes

- Read the mutated `x` buffer after the Warp solve finishes.
- Synchronize the Warp device before converting the solution buffer back to NumPy.
- Validate the returned solution size before indexing it with free DOFs.
- Add safe fallback to the CPU reduced-system solve if the GPU full-system solve returns an unexpected shape or raises.
- Apply the same guard to the linear and nonlinear Hex8 paths.

## Extra improvements

- Report the actual Warp iteration count in `LinearSolveInfo`.
- Added regression tests for Warp solution extraction and iteration parsing.

## Validation

- Full test suite: `41 passed, 3 skipped`


## Warp Runtime Fix Notes

# Warp runtime fix and continued optimization

This update fixes a real runtime failure seen on Warp 1.12.1 when launching nonlinear GPU solves:

- Removed `from __future__ import annotations` from:
  - `src/geoai_simkit/solver/warp_nonlinear.py`
  - `src/geoai_simkit/solver/warp_hex8.py`
- This prevents local Warp vector aliases such as `vec6f` / `vec8f` from being turned into deferred string annotations inside nested `@wp.func` kernels.
- Without this fix, Warp may fail during function parsing with errors like:
  - `NameError: name 'vec6f' is not defined`

Additional robustness improvements:

- Wrapped Warp kernel bundle creation in guarded fallback paths for:
  - nonlinear continuum assembly
  - linear hex8 GPU assembly
- If bundle construction fails, the solver now:
  - records the device failure
  - emits a warning
  - cleanly falls back to CPU instead of crashing the background solve thread

Regression coverage added:

- `tests/test_warp_bundle_failures.py`
  - verifies nonlinear Warp bundle creation failure falls back safely
  - verifies linear Warp bundle creation failure falls back safely

Validation result:

- `39 passed, 3 skipped`


## Pre-solve convergence guard

This build adds a stronger pre-solve checker before launching the background solver. It now blocks or warns on:

- stages with no effective activation/deactivation/load changes
- excavation/unloading stages whose activation map does not actually deactivate any region
- active regions without material assignments
- stages with no active cells
- risky nonlinear settings such as overly large `initial_increment`

The nonlinear solver also now honors per-stage metadata such as `initial_increment`, `max_iterations`, and `line_search`.



## Recent updates
- Added commercial-style adaptive controls with iteration-history-based increment scaling, cutback tracing, and automatic stage-failure advice.
