# 分布式 GPU 加速有限元系统设计蓝图（v4·文件级重构与接口总设计书）

> 面向当前 `geoai_simkit` 代码库的下一代系统蓝图。  
> 本版在 v3 基础上继续下压，不再停留于架构层，而是直接补齐到 **文件级重构落点、运行时契约、状态机、错误恢复、性能观测、配置规范、任务拆分与验收标准**。  
> 目标不是“讲清楚大方向”，而是 **让这份文档可以直接拿来指导持续几周到几个月的系统重构工作**。

---

## 0. 文档信息

- 文档名称：Distributed GPU FEM System Blueprint v4
- 目标代码库：`src/geoai_simkit/`
- 当前适配对象：本轮上传代码包中体现出的目录、类名、调用链和产品壳层
- 文档定位：
  - 架构总设计书
  - 文件级重构说明书
  - 运行时数据契约文档
  - 模块接口草案
  - 实施路线与验收文档
- 面向读者：
  - 你本人
  - 未来协同开发者
  - 后续继续协助编码的模型代理
- 非目标：
  - 不在本文中直接实现全部内核代码
  - 不在本文中穷尽所有有限元公式推导
  - 不在本文中确定所有第三方库最终绑定方案
  - 不把 GUI 视觉设计细节写成产品 PRD

---

## 1. 当前代码库的真实基础与系统定位

当前代码库不是一个“单文件求解器”，而是已经形成了完整的软件雏形。根据现有目录与代码，系统大致分为以下几层：

```text
geoai_simkit/
├─ app/                 # Workbench / window / service / validation / job
├─ core/                # SimulationModel and engineering semantic objects
├─ geometry/            # IFC / parametric / regioning / meshing
├─ materials/           # Elastic / Mohr-Coulomb / HSS
├─ pipeline/            # Case spec / builder / preprocess / runner / execution
├─ solver/              # Hex8 / Tet4 / staging / linear algebra / Warp GPU path
├─ post/                # Exporters / viewer support
└─ results/             # Lightweight result database
```

### 1.1 当前已具备的关键工程语义

从 `core/model.py` 可以确认系统已具备如下工程对象：

- `MaterialBinding`
- `MaterialDefinition`
- `GeometryObjectRecord`
- `BlockRecord`
- `BoundaryCondition`
- `LoadDefinition`
- `StructuralElementDefinition`
- `InterfaceDefinition`
- `InterfaceElementDefinition`
- `AnalysisStage`
- `SimulationModel`

这说明：

1. 当前系统已经不是单步、单材料、单域的教学型 FEM 原型。  
2. 已经支持工程上有意义的对象：块、区域、阶段、界面、结构单元。  
3. 未来分布式升级 **不需要推翻工程建模层**，只需要将运行时从 `SimulationModel` 解耦。

### 1.2 当前 Case / Pipeline 层已经有很好的承载点

从 `pipeline/specs.py`、`pipeline/builder.py`、`pipeline/runner.py` 可以确认，系统已经有：

- `AnalysisCaseSpec`
- `PreparedAnalysisCase`
- `StageSpec`
- `MeshPreparationSpec`
- `ContactPairSpec`
- `StructureGeneratorSpec`
- `InterfaceGeneratorSpec`
- `AnalysisTaskSpec`
- `AnalysisExportSpec`
- `GeneralFEMSolver`

尤其是：

- `StageSpec.predecessor` 已经存在，说明阶段图语义已经开始形成；
- `GeneralFEMSolver.prepare_case()` / `solve_case()` / `run_task()` 已经构成天然 orchestration 落点；
- `build_execution_plan()` 和 `build_solver_settings()` 已有轻量执行计划体系。

这意味着：

> 下一代系统最合适的升级路线，不是重新发明 case 格式，而是把 `pipeline` 从“组装模型”扩展为“编译运行输入”。

### 1.3 当前求解层的真实情况

从 `solver/` 目录可以看出，系统已经具备：

- 连续体单元：`hex8_linear.py`、`hex8_nonlinear.py`、`tet4_linear.py`
- 阶段逻辑：`staging.py`
- 线性代数：`linear_algebra.py`
- GPU 路径：`warp_hex8.py`、`warp_nonlinear.py`、`gpu_runtime.py`
- 统一入口：`warp_backend.py`
- 辅助对象：`mesh_graph.py`、`interface_elements.py`、`structural_elements.py`

优点：

- 已经不是只有 CPU 的单元刚度实现；
- 已经尝试走 GPU 路径；
- 已经有阶段、界面、结构单元的真实工程需求。

问题：

- 当前求解层仍以 **单进程 + 单内存模型对象** 为前提；
- `WarpBackend` 明显承担过多角色；
- 所谓“多 GPU”目前还不是 domain decomposition runtime。

### 1.4 当前应用壳层足够完整，不应推翻

`app/workbench.py`、`app/job_service.py`、`app/results_service.py` 已经形成：

- 文档打开 / 保存
- case 修改
- stage 修改
- material 修改
- 预处理与校验
- 任务规划与执行
- 结果总览

这意味着：

> 真正要重做的是 **运行时内核**，不是 GUI 和服务壳层。

---

## 2. 当前系统的根本瓶颈

### 2.1 `SimulationModel` 既是工程模型，又被当成求解态对象

`SimulationModel` 当前同时承载：

- mesh
- region tags
- materials
- material library
- boundary conditions
- stages
- structures
- interfaces
- interface elements
- metadata
- results

这对单机原型很方便，但对分布式系统来说存在根本冲突：

1. 假定所有状态都能在单进程整体访问；
2. 没有地方表达 partition-local 视图；
3. 无法表达 ghost 节点和 halo；
4. 结果直接回写 mesh，不利于 checkpoint/restart；
5. 工程语义与计算状态耦合，导致后续接口爆炸。

### 2.2 `WarpBackend` 过肥

从调用链看，`GeneralFEMSolver.solve_case()` 直接把 `prepared.model` 交给 `self.backend.solve(prepared.model, settings)`，默认 backend 是 `WarpBackend`。

这意味着 `WarpBackend` 现在实际上扮演了：

- 运行总控
- 路径选择器
- 设备管理器
- stage 驱动器
- 非线性控制器
- CPU/GPU fallback 分流器
- 求解结果回填器

这不是长期可维护的结构。

### 2.3 当前 `compute_preferences.py` 的多 GPU 语义还停留在设备选择层

当前已有：

- `multi_gpu_mode`
- `allowed_gpu_devices`
- `warp_selected_device`
- `warp_device`
- `stage_state_sync`

但缺少：

- partition count
- rank count
- communicator
- halo plan
- distributed numbering
- global reduction policy
- per-rank memory budget
- stage-wise repartition policy

所以：

> 当前多 GPU 更接近“在哪张 GPU 上跑”，不是“多张 GPU 协同求解同一问题”。

### 2.4 Stage 图语义停留在建模层，没有落到执行层

虽然 `StageSpec.predecessor` 已存在，但执行时仍基本等价于线性 stage 列表。

缺少：

- stage execution plan
- activation inheritance rule
- stage-local state commit boundary
- stage-level checkpoint boundary
- stage branch replay policy
- stage-failure recovery policy

### 2.5 结果数据库还是浏览视图，不是运行时资产

`results/database.py` 中的 `ResultDatabase` 更像后处理层汇总：

- `fields`
- `stages`
- `metadata`

它适合 GUI 浏览，但不适合作为：

- 增量 checkpoint 的主存储
- 分布式写出层
- 断点续算恢复资产
- 性能追踪来源

---

## 3. 目标系统的转型原则

### 3.1 原则一：保留工程建模层，彻底重构运行时

保留：

- `core/`
- `geometry/`
- `materials/` 中的参数/语义定义
- `pipeline/specs.py` 的 case 表达能力
- `app/` 的工作台壳层
- `post/` / `results/` 的浏览与导出接口

重构：

- `pipeline` 与 `solver` 中间的运行时边界
- 分区与通信
- stage 执行器
- 线性系统接口
- GPU 常驻状态
- checkpoint 和 telemetry

### 3.2 原则二：先把边界做对，再追求极限性能

第一优先级不是“峰值 TFLOPS”，而是：

- 数据边界清晰
- 模块职责单一
- 支持检查点
- 支持失败恢复
- 支持单分区和多分区共用同一 runtime
- 支持后续再接 PETSc/NCCL/MPI 等外部能力

### 3.3 原则三：MVP 必须足够窄

首版分布式 runtime 必须先限定能力边界：

- 先支持 Hex8 连续体
- 先支持 staged static / quasi-static
- 先支持 partition_count=1 与 partition_count>1 共用框架
- 先支持 block sparse 组装式线性系统
- 先支持 checkpoint/restart
- 先支持单节点多 GPU

不要第一版就把这些全部同时做满：

- Tet4 非线性
- mortar contact
- shell/beam 全功能耦合
- matrix-free 全路线
- 动力学显式/隐式全套
- 自适应重剖分

### 3.4 原则四：单机与分布式要共享同一个运行时模型

不能做成：

- 单机一套代码
- 分布式另一套平行宇宙代码

而应该做成：

- `partition_count=1` 时就是单机模式
- `partition_count>1` 时就是分布式模式
- Operator、StageExecutor、Checkpoint、Telemetry 共用

这样后续调试和维护才可控。

---

## 4. 总体目标架构

```text
[Application Plane]
Workbench / CLI / JobService / Validation / ResultsService

        ↓

[Compile Plane]
CaseSpec → PreparedModel → RuntimeModel → PartitionedRuntimeModel → StageExecutionPlan

        ↓

[Runtime Plane]
DistributedRuntime
  ├─ RuntimeConfig
  ├─ RankContext
  ├─ DeviceContext
  ├─ Communicator
  ├─ PartitionManager
  ├─ StageExecutor
  ├─ NonlinearController
  ├─ LinearSystemBridge
  ├─ CheckpointManager
  └─ TelemetryRecorder

        ↓

[Kernel Plane]
ContinuumOperator / InterfaceOperator / StructuralOperator / ConstitutiveKernels

        ↓

[Result Plane]
RuntimeResultStore → ExportAdapter → ResultDatabaseAdapter → GUI / VTU / Stage Bundle
```

### 4.1 Plane 解释

#### Application Plane
负责：

- case 编辑
- 校验
- 任务规划
- 启动任务
- 浏览结果

不负责：

- 直接持有 GPU 缓冲
- 直接操作分区
- 直接写分布式检查点

#### Compile Plane
负责将工程表达转成运行输入：

- mesh 统一
- region 归属
- material 编码
- stage 编译
- partition 生成
- DOF 编号
- halo 计划

#### Runtime Plane
负责执行：

- 初始化 rank/device
- 执行 stage / increment
- 调 operator
- 组装残量与切线
- 调线性求解器
- commit / rollback
- telemetry
- checkpoint

#### Kernel Plane
负责局部数值算子：

- 单元积分
- 本构更新
- 接触/界面贡献
- 结构单元贡献

#### Result Plane
负责：

- stage/increment 级结果收集
- 并行写出
- 检查点写出
- GUI 可读数据适配

---

## 5. 领域边界与上下文划分

为了避免未来代码再回到“一个 backend 管一切”的状态，建议明确四个 bounded context：

### 5.1 Engineering Model Context

目录归属：

- `core/`
- `geometry/`
- `materials/`（参数语义层）
- `pipeline/specs.py`

负责：

- 工程语义对象
- 业务可编辑对象
- 可序列化 case 结构

### 5.2 Compilation Context

建议新建目录：

- `runtime/compiler/`

负责：

- case 到运行输入的编译
- stage 编译
- partition 编译
- numbering 编译
- buffer layout 规划

### 5.3 Execution Context

建议新建目录：

- `runtime/`
- `solver/backends/`

负责：

- stage 执行
- increment 推进
- residual/tangent 求值
- distributed solve
- failure / rollback / checkpoint

### 5.4 Result & Observability Context

建议新建目录：

- `runtime/checkpoint.py`
- `runtime/telemetry.py`
- `results/runtime_store.py`
- `results/runtime_adapter.py`

负责：

- checkpoint
- telemetry
- runtime result asset
- GUI / exporter adapter

---

## 6. 分层数据模型设计

### 6.1 四类模型必须严格分离

```text
AnalysisCaseSpec           # 用户 / case 输入
PreparedAnalysisCase       # 前处理后的工程模型
RuntimeModel               # 运行时全局模型（尚未切分）
PartitionedRuntimeModel    # 分区后的运行时模型
```

### 6.2 `SimulationModel` 的未来定位

`SimulationModel` 保留，但只用于：

- 工程编辑
- 工作台预览
- 前处理结果检查
- 结果回填/导出适配

不要再让它作为：

- distributed runtime 主对象
- GPU resident state 主对象
- checkpoint 主对象

### 6.3 新增 `RuntimeModel`

建议定义：

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class RuntimeModel:
    name: str
    mesh_kind: str
    node_count: int
    cell_count: int
    spatial_dim: int
    dof_per_node: int
    node_coords: Any
    cell_conn: Any
    cell_type_codes: Any
    region_codes: Any
    material_codes: Any
    bc_table: Any
    load_table: Any
    structure_table: Any
    interface_table: Any
    stage_plan: 'CompiledStagePlan'
    metadata: dict[str, Any] = field(default_factory=dict)
```

语义：

- 不再存 pyvista mesh 对象；
- 用扁平数组和编码表表示运行输入；
- 保留最小但完整的全局视图。

### 6.4 新增 `PartitionedRuntimeModel`

```python
@dataclass(slots=True)
class PartitionedRuntimeModel:
    global_model: RuntimeModel
    partitions: tuple['MeshPartition', ...]
    numbering: 'DistributedDofNumbering'
    communication_graph: 'PartitionCommunicationGraph'
    stage_plan: 'StageExecutionPlan'
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 6.5 `MeshPartition`

```python
@dataclass(slots=True)
class MeshPartition:
    partition_id: int
    owned_cell_ids: Any
    owned_node_ids: Any
    ghost_node_ids: Any
    boundary_face_ids: Any
    neighbor_partition_ids: tuple[int, ...]
    local_node_coords: Any
    local_cell_conn: Any
    local_cell_type_codes: Any
    local_region_codes: Any
    local_material_codes: Any
    metadata: dict[str, Any] = field(default_factory=dict)
```

关键约束：

- `owned_*` 与 `ghost_*` 必须严格区分；
- 本地单元连接必须统一映射为 local node id；
- 本地持有的材料码、区域码、stage mask 必须是局部压缩表示；
- 不允许 runtime 再频繁回查原始 `SimulationModel`。

### 6.6 `DistributedDofNumbering`

```python
@dataclass(slots=True)
class DistributedDofNumbering:
    dof_per_node: int
    global_dof_count: int
    owned_dof_ranges: tuple[tuple[int, int], ...]
    local_to_global_node: tuple[Any, ...]
    global_to_local_node_maps: tuple[dict[int, int], ...]
    owned_dof_ids: tuple[Any, ...]
    ghost_dof_ids: tuple[Any, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
```

职责：

- 提供 rank-local 和 global 编号关系；
- 为 halo 同步、线性系统装配和结果聚合提供统一索引基础。

### 6.7 `RuntimeExecutionState`

```python
@dataclass(slots=True)
class RuntimeExecutionState:
    current_stage_index: int = 0
    current_increment: int = 0
    committed_stage_index: int = -1
    committed_increment: int = -1
    wallclock_seconds: float = 0.0
    last_checkpoint_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 6.8 `PartitionExecutionState`

```python
@dataclass(slots=True)
class PartitionExecutionState:
    partition_id: int
    u: Any
    du: Any
    residual: Any
    velocity: Any | None = None
    acceleration: Any | None = None
    material_states: dict[str, Any] = field(default_factory=dict)
    scratch: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
```

说明：

- `u`、`du`、`residual` 等必须是扁平 GPU/CPU 缓冲；
- `scratch` 用于本地临时算子缓冲；
- `material_states` 保存高斯点状态表。

---

## 7. 数据布局规范

### 7.1 原则：运行时数据必须优先为数组和编码表

当前工程对象层偏 Python object 风格，适合编辑，不适合 GPU 和 distributed runtime。

运行时一律优先：

- SoA（Structure of Arrays）
- 索引表
- 编码表
- 稳定的 dtype 和 shape

### 7.2 节点字段布局

```text
node_coords          : float64[n_nodes, 3]
u                   : float64[n_local_nodes, dof_per_node]
du                  : float64[n_local_nodes, dof_per_node]
velocity            : float64[n_local_nodes, dof_per_node]
acceleration        : float64[n_local_nodes, dof_per_node]
external_force      : float64[n_local_nodes, dof_per_node]
internal_force      : float64[n_local_nodes, dof_per_node]
node_flags          : uint32[n_local_nodes]
```

`node_flags` 建议 bitmask：

- owned
- ghost
- boundary
- constrained
- interface
- structure-coupled

### 7.3 单元拓扑布局

```text
cell_conn           : int32[n_local_cells, nen_max]
cell_arity          : int8[n_local_cells]
cell_type_code      : int16[n_local_cells]
cell_region_code    : int16[n_local_cells]
cell_material_code  : int16[n_local_cells]
cell_stage_mask     : uint64[n_local_cells]   # or bit-packed array
```

### 7.4 高斯点状态布局

```text
stress              : float64[n_local_cells, n_gp_max, 6]
strain              : float64[n_local_cells, n_gp_max, 6]
plastic_strain      : float64[n_local_cells, n_gp_max, 6]
state_scalar_k      : float64[n_local_cells, n_gp_max]
state_tensor_k      : float64[n_local_cells, n_gp_max, m]
active_gp_mask      : uint8[n_local_cells, n_gp_max]
```

### 7.5 材料参数布局

不要在 kernel 内频繁访问 Python dict。

建议：

```text
material_model_code : int16[n_materials]
material_param_base : float64[n_materials, p_max]
```

配合 registry 解释参数语义。

### 7.6 接口和结构单元布局

```text
interface_slave_conn     : int32[n_intf, ns]
interface_master_conn    : int32[n_intf, nm]
interface_type_code      : int16[n_intf]
interface_stage_mask     : uint64[n_intf]

structure_conn           : int32[n_struct, nk]
structure_type_code      : int16[n_struct]
structure_stage_mask     : uint64[n_struct]
structure_param_base     : float64[n_struct, q_max]
```

### 7.7 dtype 约束

首版建议：

- 几何、位移、应力、应变：`float64`
- 单元和节点索引：`int32`
- 编码表：`int16` / `uint32`
- bitmask：`uint64`

原因：

- 岩土问题对数值鲁棒性要求高；
- 首版先稳，不先追求全 float32 极限吞吐；
- 后续可将部分 scratch 缓冲切到 float32。

### 7.8 内存预算规则

建议新增静态估算器：

```python
@dataclass(slots=True)
class MemoryBudgetEstimate:
    geometry_bytes: int
    field_bytes: int
    gp_state_bytes: int
    linear_system_bytes: int
    halo_bytes: int
    checkpoint_peak_bytes: int
    total_peak_bytes: int
```

用途：

- 编译期判断是否适合 GPU；
- 决定 partition count；
- GUI 中提前提醒显存压力。

---

## 8. Compile Plane 设计

### 8.1 目标

Compile Plane 的职责是把 `AnalysisCaseSpec` / `PreparedAnalysisCase` 编译成 runtime 可执行输入，而不是只生成 `SimulationModel`。

### 8.2 建议主入口

```python
class RuntimeCompiler:
    def compile_case(self, prepared: 'PreparedAnalysisCase', config: 'CompileConfig') -> 'CompilationBundle':
        raise NotImplementedError
```

### 8.3 `CompileConfig`

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class CompileConfig:
    partition_count: int = 1
    partition_strategy: str = 'graph'
    numbering_strategy: str = 'contiguous-owned'
    enable_halo: bool = True
    enable_stage_masks: bool = True
    target_device_family: str = 'auto'
    memory_budget_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 8.4 `CompilationBundle`

```python
@dataclass(slots=True)
class CompilationBundle:
    prepared_case: 'PreparedAnalysisCase'
    runtime_model: 'RuntimeModel'
    partitioned_model: 'PartitionedRuntimeModel'
    compile_report: 'CompileReport'
```

### 8.5 编译子阶段

建议拆成以下流水线：

1. `prepare_engineering_model`
2. `normalize_mesh_topology`
3. `encode_regions_and_materials`
4. `compile_stage_plan`
5. `build_runtime_model`
6. `partition_runtime_model`
7. `build_dof_numbering`
8. `build_halo_plans`
9. `estimate_memory_budget`
10. `emit_compile_report`

### 8.6 编译阶段输入输出表

| 阶段 | 输入 | 输出 | 是否缓存 |
|---|---|---|---|
| geometry normalize | `PreparedAnalysisCase` | 统一拓扑 | 是 |
| region/material encode | 统一拓扑 | code tables | 是 |
| stage compile | case stages | `CompiledStagePlan` | 是 |
| partition | `RuntimeModel` | partitions | 是 |
| numbering | partitions | global/local dof maps | 是 |
| halo | partitions + numbering | `HaloExchangePlan` | 是 |
| budget estimate | 全部前序输出 | `MemoryBudgetEstimate` | 否 |

### 8.7 `CompiledStagePlan`

```python
@dataclass(slots=True)
class CompiledStagePlan:
    stage_names: tuple[str, ...]
    topo_order: tuple[int, ...]
    predecessor_index: tuple[int, ...]
    activation_masks: tuple['StageActivationMask', ...]
    bc_tables: tuple[Any, ...]
    load_tables: tuple[Any, ...]
    structure_masks: tuple[Any, ...]
    interface_masks: tuple[Any, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 8.8 `StageActivationMask`

```python
@dataclass(slots=True)
class StageActivationMask:
    active_region_codes: Any
    active_cell_mask: Any
    active_structure_mask: Any
    active_interface_mask: Any
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 8.9 编译输出应具备的校验项

`CompileReport` 至少包含：

- node/cell counts
- element family histogram
- region/material coverage
- stage coverage
- interface/structure coverage
- partition balance ratio
- halo volume ratio
- estimated peak memory
- warnings / errors

### 8.10 与当前 `pipeline` 的关系

保持：

- `AnalysisCaseBuilder` 继续负责从 case 构建工程模型

新增：

- `RuntimeCompiler` 负责从 `PreparedAnalysisCase` 构建运行时资产

新的 `GeneralFEMSolver` 路径应为：

```text
AnalysisCaseSpec
  → AnalysisCaseBuilder.build()
  → PreparedAnalysisCase
  → RuntimeCompiler.compile_case()
  → CompilationBundle
  → RuntimeBackend.execute()
  → RuntimeResultStore / Checkpoint / ExportAdapter
```

---

## 9. 分区系统设计

### 9.1 分区目标

分区必须同时满足：

- 负载平衡
- 边界通信尽量少
- 材料状态表局部化
- stage 激活切换成本可控
- 能映射到设备布局

### 9.2 `PartitionConfig`

```python
@dataclass(slots=True)
class PartitionConfig:
    partition_count: int
    strategy: str = 'graph'
    weight_by_gp_count: bool = True
    weight_by_material_cost: bool = True
    keep_regions_compact: bool = False
    keep_stage_locality: bool = True
    rebalance_policy: str = 'none'
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 9.3 权重建模建议

单元分区权重建议包含：

- 单元类型成本（Hex8 / Tet4 / Interface / Beam 等）
- 高斯点数量
- 材料模型成本（弹性 < MC < HSS）
- 接触/界面参与标记
- stage 活跃频率

### 9.4 `PartitionCommunicationGraph`

```python
@dataclass(slots=True)
class PartitionCommunicationGraph:
    partition_ids: tuple[int, ...]
    neighbor_pairs: tuple[tuple[int, int], ...]
    shared_node_counts: dict[tuple[int, int], int]
    shared_face_counts: dict[tuple[int, int], int]
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 9.5 `HaloExchangePlan`

```python
@dataclass(slots=True)
class HaloExchangePlan:
    partition_id: int
    send_neighbors: tuple[int, ...]
    recv_neighbors: tuple[int, ...]
    send_node_ids: tuple[Any, ...]
    recv_node_ids: tuple[Any, ...]
    send_dof_ids: tuple[Any, ...]
    recv_dof_ids: tuple[Any, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 9.6 halo 同步的粒度

首版只同步必要量：

- 位移 `u`
- 增量 `du`
- 残量边界贡献（按装配模式决定）
- 接触/界面需要的几何信息

不要一开始就同步所有状态。

### 9.7 分区策略分阶段建议

#### 阶段 1：最小可用分区

- 按单元邻接图切分
- 不做 stage-aware repartition
- 不做动态重平衡
- 不做 region-preserving 强约束

#### 阶段 2：工程增强分区

- 引入材料模型代价权重
- 引入界面/结构单元归属惩罚
- 引入 stage 活跃率权重
- 支持 partition diagnostics

#### 阶段 3：高级分区

- 按 stage cluster 预优化
- 支持部分重平衡
- 支持 failure-aware repartition

### 9.8 界面与结构单元的分区规则

#### 界面单元

优先归属规则：

1. slave 侧连续体所在 partition
2. 若跨 partition，则归属共享边界量更少的一侧
3. 若强制跨分区，则建立 interface halo view

#### 结构单元

优先归属规则：

1. 与其耦合节点最多的连续体 partition
2. 若为独立结构网格，则按结构图切分后再与连续体建立映射

### 9.9 分区诊断输出

每次编译都应输出：

- cells per partition
- dofs per partition
- gp states per partition
- interface / structure counts per partition
- max/min balance ratio
- halo node ratio
- estimated communication bytes per increment

---

## 10. DOF 编号与约束系统设计

### 10.1 为什么要单列这一层

当前代码里自由度很可能仍隐含在节点和组装逻辑中。分布式 runtime 必须将它显式对象化。

### 10.2 编号目标

必须同时支持：

- local owned DOF
- local ghost DOF
- global DOF
- constrained DOF
- eliminated DOF
- result-export DOF ordering

### 10.3 `DofConstraintTable`

```python
@dataclass(slots=True)
class DofConstraintTable:
    constrained_global_dofs: Any
    constrained_values: Any
    elimination_map: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 10.4 编号策略建议

首版建议：

- 按 partition contiguous owned DOF 编号
- ghost DOF 不进入 owned range
- 导出时通过 global mapping 还原

### 10.5 约束处理策略

首版优先：

- elimination 或 direct overwrite 二选一，保持一致
- 不同 operator 统一接受同一种约束表示

建议：

- 运行内核使用消元后的自由 DOF 视图
- 结果导出时重建全量节点向量

### 10.6 阶段性约束切换

阶段施工下，边界条件和荷载会变化，编号层需要与 stage plan 协同：

- 编号本身尽量不因 stage 改变而重建；
- 约束表、外载表按 stage 切换；
- 仅在极端情况下允许 stage-triggered renumbering。

---

## 11. Runtime Plane 设计

### 11.1 顶层总控 `DistributedRuntime`

```python
class DistributedRuntime:
    def __init__(self, config: 'RuntimeConfig') -> None:
        ...

    def initialize(self, bundle: 'CompilationBundle') -> None:
        ...

    def execute(self) -> 'RuntimeExecutionReport':
        ...

    def shutdown(self) -> None:
        ...
```

### 11.2 `RuntimeConfig`

```python
@dataclass(slots=True)
class RuntimeConfig:
    backend: str = 'distributed'
    communicator_backend: str = 'local'
    device_mode: str = 'single'
    partition_count: int = 1
    checkpoint_policy: str = 'stage-and-failure'
    telemetry_level: str = 'standard'
    fail_policy: str = 'rollback-cutback'
    deterministic: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 11.3 `RankContext`

```python
@dataclass(slots=True)
class RankContext:
    rank: int
    world_size: int
    local_rank: int
    partition_id: int
    hostname: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 11.4 `DeviceContext`

```python
@dataclass(slots=True)
class DeviceContext:
    device_kind: str
    device_name: str
    device_alias: str
    memory_limit_bytes: int | None = None
    stream_count: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 11.5 `Communicator`

```python
class Communicator:
    def barrier(self) -> None: ...
    def allreduce_sum(self, value): ...
    def allreduce_max(self, value): ...
    def exchange(self, plan: 'HaloExchangePlan', send_buffers: dict[str, object]) -> dict[str, object]: ...
```

首版可提供三种实现：

- `LocalCommunicator`：单进程假实现
- `ThreadCommunicator`：单机调试实现
- `MpiCommunicator`：未来正式实现

### 11.6 `RuntimeBootstrapper`

负责：

- 绑定 rank ↔ partition
- 绑定 rank ↔ device
- 分配本地缓冲
- 恢复 checkpoint（若有）
- 注册 telemetry
- 构造 stage executor

### 11.7 `RuntimeExecutionReport`

```python
@dataclass(slots=True)
class RuntimeExecutionReport:
    ok: bool
    stage_reports: tuple['StageRunReport', ...]
    telemetry_summary: dict[str, object]
    checkpoints: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

## 12. Stage 执行系统设计

### 12.1 为什么 stage 执行器必须独立成层

当前 stage 逻辑散落在工程对象、solver 和 metadata 中。未来必须有独立 stage runtime，原因是：

- stage 不是单纯循环索引；
- stage 决定哪些单元有效、哪些荷载生效、哪些界面参与；
- stage 是 checkpoint 和 failure 恢复的天然边界；
- 岩土施工问题中 stage 是最核心的业务轴线。

### 12.2 `StageExecutor`

```python
class StageExecutor:
    def run_stage(self, stage_index: int, context: 'RuntimeStageContext') -> 'StageRunReport':
        raise NotImplementedError
```

### 12.3 `RuntimeStageContext`

```python
@dataclass(slots=True)
class RuntimeStageContext:
    stage_index: int
    stage_name: str
    activation_mask: 'StageActivationMask'
    bc_table: object
    load_table: object
    structure_mask: object
    interface_mask: object
    increment_plan: 'IncrementPlan'
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 12.4 Stage 生命周期

```text
StageStart
  → inherit previous committed state
  → apply stage activation/deactivation
  → activate stage BC / load / interface / structure masks
  → initialize stage accumulators
  → increment loop
  → convergence / failure decision
  → stage commit
  → stage checkpoint
  → stage result flush
StageEnd
```

### 12.5 Increment 生命周期

```text
IncrementStart
  → predict increment size
  → apply trial step
  → operator evaluation
  → halo exchange
  → residual/tangent build
  → linear solve
  → update solution
  → convergence check
  → line search or cutback
  → commit increment or rollback
IncrementEnd
```

### 12.6 `IncrementPlan`

```python
@dataclass(slots=True)
class IncrementPlan:
    target_steps: int
    min_step_size: float
    max_step_size: float
    growth_factor: float
    shrink_factor: float
    target_iteration_low: int
    target_iteration_high: int
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 12.7 Stage 继承规则

建议定义 `StageStateTransferPolicy`：

```python
@dataclass(slots=True)
class StageStateTransferPolicy:
    inherit_displacement: bool = True
    inherit_material_state: bool = True
    reset_external_load_accumulator: bool = True
    reset_contact_cache: bool = False
    reset_line_search_history: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 12.8 Stage 失败恢复策略

首版建议：

- increment 失败先 cutback；
- 超过 cutback 上限则回滚到 stage 入口；
- stage 入口失败则终止运行并保留 checkpoint；
- 若配置允许，则尝试 CPU fallback 重新进入当前 stage。

---

## 13. Operator 架构设计

### 13.1 目标

统一所有局部数值贡献的调用方式，避免未来每加一种单元就继续膨胀 `WarpBackend`。

### 13.2 顶层接口

```python
class Operator:
    name: str

    def prepare(self, state: 'PartitionExecutionState', context: 'OperatorContext') -> None:
        ...

    def evaluate(self, state: 'PartitionExecutionState', context: 'OperatorContext') -> 'OperatorContribution':
        ...

    def commit(self, state: 'PartitionExecutionState', context: 'OperatorContext') -> None:
        ...

    def rollback(self, state: 'PartitionExecutionState', context: 'OperatorContext') -> None:
        ...
```

### 13.3 `OperatorContribution`

```python
@dataclass(slots=True)
class OperatorContribution:
    residual: object | None = None
    tangent: object | None = None
    energy: float | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)
```

### 13.4 `OperatorContext`

```python
@dataclass(slots=True)
class OperatorContext:
    stage_index: int
    increment_index: int
    communicator: object
    device_context: object
    halo_plan: object | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 13.5 子类划分

- `ContinuumOperator`
- `InterfaceOperator`
- `ContactOperator`
- `StructuralOperator`
- `BodyLoadOperator`
- `BoundaryOperator`

### 13.6 `OperatorAssembler`

```python
class OperatorAssembler:
    def assemble(self, contributions: list['OperatorContribution']) -> 'AssembledSystem':
        ...
```

### 13.7 `AssembledSystem`

```python
@dataclass(slots=True)
class AssembledSystem:
    residual: object
    tangent: object | None
    diagnostics: dict[str, object] = field(default_factory=dict)
```

### 13.8 首版 operator 顺序

建议顺序：

1. continuum
2. interface
3. contact（若启用）
4. structural
5. body load
6. boundary enforcement

### 13.9 为什么 `BoundaryOperator` 单列

因为边界条件在分布式系统中不只是“设置几个节点值”，还影响：

- 本地/全局 DOF 映射
- 残量修正
- 切线修正
- 导出结果重构

不要把它散落在多个算子里。

---

## 14. 连续体单元路线图

### 14.1 Hex8 是第一优先级

结合当前代码，Hex8 已经有：

- CPU 线性
- CPU 非线性
- Warp GPU 路径

因此最合理的首版路线是：

- 先把 Hex8 连续体做成 runtime 第一公民；
- 先支持线性和主干非线性；
- 先保证 stage + cutback + checkpoint 跑通。

### 14.2 `ContinuumHex8Operator` 建议接口

```python
class ContinuumHex8Operator(Operator):
    def evaluate(self, state: 'PartitionExecutionState', context: 'OperatorContext') -> 'OperatorContribution':
        ...
```

内部应拆：

- 几何预计算
- B 矩阵相关缓存
- Gauss 权重
- 本构调用
- 残量计算
- 切线装配

### 14.3 Tet4 路线

Tet4 当前基础存在，但不应在首版分布式 runtime 中同时上满。

建议分三步：

1. 线性 Tet4 接入统一 operator 框架；
2. 非线性 Tet4 复用连续体通用本构接口；
3. 混合网格下的 Hex8/Tet4 共存与局部优化。

### 14.4 混合网格约束

首版混合网格建议只支持：

- 同一 partition 中多单元类型共存；
- 不做过度特化的 fused kernel；
- kernel dispatch 以 `cell_type_code` 为主。

---

## 15. 本构系统设计

### 15.1 当前基础

当前 `materials/` 已有：

- `linear_elastic.py`
- `mohr_coulomb.py`
- `hss.py`
- `registry.py`

这说明参数语义层已经可用，但运行态状态管理还需要重构。

### 15.2 目标：语义层与运行层分离

- `materials/*.py` 保留参数解释、默认值、模型注册；
- runtime 使用扁平状态缓冲和 kernel registry。

### 15.3 `ConstitutiveModelDescriptor`

```python
@dataclass(slots=True)
class ConstitutiveModelDescriptor:
    name: str
    model_code: int
    parameter_names: tuple[str, ...]
    state_scalar_names: tuple[str, ...]
    state_tensor_names: tuple[str, ...]
    supports_tangent: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 15.4 `ConstitutiveKernelRegistry`

```python
class ConstitutiveKernelRegistry:
    def register(self, descriptor: 'ConstitutiveModelDescriptor', update_kernel, tangent_kernel=None) -> None:
        ...

    def resolve(self, model_code: int):
        ...
```

### 15.5 `GaussPointStateBuffer`

```python
@dataclass(slots=True)
class GaussPointStateBuffer:
    stress: object
    strain: object
    plastic_strain: object | None = None
    scalar_fields: dict[str, object] = field(default_factory=dict)
    tensor_fields: dict[str, object] = field(default_factory=dict)
    trial_shadow: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 15.6 commit / rollback 原则

首版最稳策略：

- 每次 increment 有 trial shadow；
- 收敛后覆盖 committed；
- cutback 时丢弃 trial；
- stage 失败时回滚到 stage 入口快照。

### 15.7 当前 `materials/` 的迁移方式

| 现有模块 | 保留内容 | 下沉到 runtime 的内容 |
|---|---|---|
| `linear_elastic.py` | 参数定义、语义注册 | GPU/CPU update/tangent kernel |
| `mohr_coulomb.py` | 参数定义、参数校验 | 增量更新、屈服判定、consistent tangent |
| `hss.py` | 参数与物理语义 | 状态变量布局、硬化更新 kernel |
| `registry.py` | 语义注册表 | runtime descriptor 索引桥接 |

### 15.8 状态布局版本化

建议给本构状态布局增加版本号，避免将来 checkpoint 不兼容：

```python
@dataclass(slots=True)
class StateSchemaVersion:
    model_code: int
    schema_version: int
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

## 16. 线性系统与非线性控制设计

### 16.1 `LinearSystemOperator`

```python
class LinearSystemOperator:
    def zero(self) -> None: ...
    def accumulate(self, contribution: 'OperatorContribution') -> None: ...
    def finalize(self) -> object: ...
```

### 16.2 `LinearSolver`

```python
class LinearSolver:
    def solve(self, system: object, rhs: object, x0: object | None = None) -> 'LinearSolveSummary':
        raise NotImplementedError
```

### 16.3 `LinearSolveSummary`

```python
@dataclass(slots=True)
class LinearSolveSummary:
    converged: bool
    iterations: int
    residual_norm: float
    solve_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 16.4 两条实现路线

#### 路线 A：装配式 block sparse

优点：

- 最贴近当前代码
- 容易调试
- 易于对比现有结果
- 易于阶段性验收

首版建议就走这条。

#### 路线 B：matrix-free

优点：

- 显存压力更低
- 超大规模问题更有优势
- 可减少全局装配开销

缺点：

- 本构、接触、边界都更难
- 调试和一致性验证更困难

建议放到 v1.2-DG 之后。

### 16.5 `NonlinearController`

```python
class NonlinearController:
    def solve_increment(self, runtime, stage_context, increment_index: int) -> 'IncrementSummary':
        ...
```

### 16.6 `IncrementSummary`

```python
@dataclass(slots=True)
class IncrementSummary:
    converged: bool
    iterations: int
    cutback_count: int
    residual_norm: float
    correction_norm: float
    step_scale: float
    diagnostics: dict[str, object] = field(default_factory=dict)
```

### 16.7 收敛判据

首版建议至少同时使用：

- 残量范数
- 位移增量范数
- 能量范数或功残差指标（可选）

### 16.8 线搜索触发规则

建议：

- 当残量下降不充分时触发；
- 当 correction 方向有效但步长过大时触发；
- 线搜索失败后直接 cutback，不做无限制重试。

### 16.9 Modified Newton 策略

可以保留当前 metadata 中已有的思路，但不要仅以 metadata 字典驱动，建议明确对象化：

```python
@dataclass(slots=True)
class NewtonPolicy:
    max_reuse: int = 2
    ratio_threshold: float = 0.35
    min_improvement: float = 0.15
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 16.10 commit / rollback 机制

每个 increment 必须明确：

- trial displacement
- trial material states
- trial contact/interface cache
- committed snapshots

不允许“部分字段已经覆盖、部分字段还没覆盖”的模糊状态。

---

## 17. GPU Kernel 与设备层设计

### 17.1 当前基础

- `gpu_runtime.py` 已可探测 CUDA 设备
- `compute_preferences.py` 已可选择设备和 profile
- `warp_hex8.py` / `warp_nonlinear.py` 已有 Warp 路径

这说明：

- 设备探测与设备选择已初步完成；
- GPU kernel 入口已有实践；
- 真正缺的是统一 runtime 设备层和缓冲管理。

### 17.2 `DeviceMemoryPool`

```python
class DeviceMemoryPool:
    def reserve(self, key: str, shape, dtype): ...
    def get(self, key: str): ...
    def release(self, key: str) -> None: ...
    def snapshot(self) -> dict[str, object]: ...
```

### 17.3 `KernelRegistry`

```python
class KernelRegistry:
    def register(self, name: str, family: str, impl) -> None: ...
    def resolve(self, name: str, family: str = 'default'):
        ...
```

### 17.4 首版 GPU 设计原则

- kernel 粒度优先按 operator 划分；
- 不急于追求超大 fused kernel；
- geometry / topology 预处理尽量缓存；
- 每个 stage 内尽量常驻 device 缓冲；
- 避免每个 increment 在 host/device 间来回搬运大数组。

### 17.5 stream 使用建议

首版建议保守：

- 主计算 stream 1 条
- halo/communication stream 1 条（可选）
- checkpoint / async copy 暂不激进展开

### 17.6 与 `compute_preferences.py` 的衔接

当前 `BackendComputePreferences` 需要继续保留，但要升级职责。

#### 现有字段继续保留

- `backend`
- `profile`
- `device`
- `thread_count`
- `multi_gpu_mode`
- `allowed_gpu_devices`
- `iterative_tolerance`
- `iterative_maxiter`
- `block_size`

#### 需要新增的字段

```python
partition_count: int = 1
communicator_backend: str = 'local'
runtime_mode: str = 'single-or-distributed'
checkpoint_policy: str = 'stage-and-failure'
telemetry_level: str = 'standard'
deterministic_mode: bool = False
memory_budget_fraction: float = 0.8
halo_overlap: bool = False
```

### 17.7 `gpu_runtime.py` 的未来定位

保留：

- 设备探测
- 设备别名与信息对象
- 设备选择工具函数

新增：

- rank-local device binding helper
- device memory capacity report
- device topology snapshot（后续）

---

## 18. 通信与同步设计

### 18.1 通信层必须抽象，不要硬编码到 operator

所有跨 partition 数据交换都必须通过 `Communicator` 和 `HaloExchangePlan`，而不是在算子内直接拼消息。

### 18.2 通信模式

首版建议只支持：

- halo exchange
- global residual norm reduction
- global max/min reduction
- failure state broadcast
- checkpoint barrier

### 18.3 `GlobalReductionSummary`

```python
@dataclass(slots=True)
class GlobalReductionSummary:
    residual_norm: float
    correction_norm: float
    energy_norm: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 18.4 halo 交换时机

建议固定在：

- local operator prepare 之后
- residual assembly 之前
- 某些 contact/interface operator evaluate 之前

不要在每个细粒度 kernel 后频繁同步。

### 18.5 同步一致性原则

- halo 数据必须带 generation id；
- increment 内多次同步时必须避免拿到旧版本；
- 所有 reduction 都要带 stage/increment 编号。

### 18.6 `SynchronizationToken`

```python
@dataclass(slots=True)
class SynchronizationToken:
    stage_index: int
    increment_index: int
    generation: int
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

## 19. 结果系统、检查点系统与遥测设计

### 19.1 `ResultDatabase` 的未来定位

保留为：

- GUI 结果浏览层
- 轻量导出层
- 结果标签与 stage 索引层

不要把它继续做成 runtime 主资产。

### 19.2 新增 `RuntimeResultStore`

```python
@dataclass(slots=True)
class RuntimeResultStore:
    stage_summaries: list[dict[str, object]] = field(default_factory=list)
    increment_summaries: list[dict[str, object]] = field(default_factory=list)
    field_snapshots: list[dict[str, object]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
```

### 19.3 `CheckpointManager`

```python
class CheckpointManager:
    def save_stage_checkpoint(self, runtime, stage_index: int) -> str: ...
    def save_failure_checkpoint(self, runtime, stage_index: int, increment_index: int) -> str: ...
    def load_checkpoint(self, checkpoint_id: str): ...
```

### 19.4 检查点内容清单

每个 checkpoint 至少包括：

- runtime schema version
- partition layout metadata
- numbering metadata
- current stage/increment
- owned displacement buffers
- owned velocity / acceleration（若有）
- material states
- stage activation state
- load/BC state
- nonlinear controller state
- telemetry partial summary

### 19.5 `CheckpointPolicy`

```python
@dataclass(slots=True)
class CheckpointPolicy:
    save_at_stage_end: bool = True
    save_at_failure: bool = True
    save_every_n_increments: int = 0
    keep_last_n: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 19.6 并行结果写出策略

首版建议：

- 每个 partition 写本地块结果；
- root 写 manifest；
- 提供后处理合并器；
- GUI 读 `ResultDatabaseAdapter`，不直接读原始 checkpoint。

### 19.7 `ResultDatabaseAdapter`

```python
class ResultDatabaseAdapter:
    def from_runtime_store(self, runtime_store: 'RuntimeResultStore') -> 'ResultDatabase':
        ...
```

### 19.8 `TelemetryRecorder`

```python
class TelemetryRecorder:
    def record_event(self, name: str, payload: dict[str, object]) -> None: ...
    def stage_summary(self, stage_index: int) -> dict[str, object]: ...
    def final_summary(self) -> dict[str, object]: ...
```

### 19.9 必须记录的性能指标

- compile time
- partition time
- halo bytes / halo time
- continuum operator time
- constitutive update time
- linear solve time
- line search time
- checkpoint write time
- peak device memory
- cutback count
- failed increments

### 19.10 GUI 侧可直接展示的摘要

- 总 stage 数
- 当前 stage
- 当前 increment
- 本 stage 迭代次数
- cutback 次数
- GPU 占用摘要
- 预计剩余 stage 数（仅信息性）
- 最近 checkpoint 时间点

---

## 20. 失败处理与恢复设计

### 20.1 失败类型分类

#### A. Compile Failure

例如：

- case 数据不完整
- material 缺失
- partition 构建失败
- 编号非法

处理：

- 不进入 runtime
- 返回 `CompileReport.errors`

#### B. Runtime Bootstrap Failure

例如：

- device 绑定失败
- buffer 分配失败
- communicator 初始化失败

处理：

- 写 bootstrap failure report
- 尝试 CPU fallback（如配置允许）

#### C. Increment Failure

例如：

- 非线性不收敛
- 线性求解失败
- halo 同步失败

处理：

- 当前 increment rollback
- cutback
- 超阈值则 stage fail

#### D. Fatal Failure

例如：

- 数据损坏
- checkpoint 无法写出
- device 异常不可恢复

处理：

- 尽量保存 failure checkpoint
- 终止执行

### 20.2 `FailurePolicy`

```python
@dataclass(slots=True)
class FailurePolicy:
    enable_cpu_fallback: bool = False
    rollback_to_stage_start: bool = True
    max_stage_retries: int = 0
    max_increment_cutbacks: int = 5
    write_failure_checkpoint: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 20.3 错误码建议

建议统一错误码前缀：

- `CMP-*`：编译错误
- `RTB-*`：runtime bootstrap 错误
- `INC-*`：increment 错误
- `CHK-*`：checkpoint 错误
- `COM-*`：communication 错误
- `DEV-*`：device 错误

例如：

- `CMP-001 missing material binding`
- `RTB-003 device allocation failed`
- `INC-007 nonlinear stagnation`
- `COM-004 halo exchange timeout`

### 20.4 恢复边界规则

- increment 失败：回滚到 increment entry
- stage 失败：回滚到 stage entry
- restart：回滚到最近 checkpoint
- 不允许跨 stage 使用半提交状态

---

## 21. 可重复性、确定性与调试模式

### 21.1 为什么必须单独设计

分布式 GPU 求解中，很多问题不是“算错了”，而是“这次对，下次不对”。因此必须内建可重复性配置。

### 21.2 `ReproducibilityConfig`

```python
@dataclass(slots=True)
class ReproducibilityConfig:
    deterministic_reduction: bool = False
    fixed_partition_seed: int | None = None
    fixed_ordering_seed: int | None = None
    stable_export_order: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 21.3 调试 profile 建议

- `cpu-debug`
- `single-partition-debug`
- `distributed-verify`
- `gpu-throughput`

### 21.4 distributed verify 模式建议行为

- partition_count > 1 但强制额外校验 halo consistency
- 增加 reduction 结果检查
- 记录更多 telemetry
- 禁止 aggressive async overlap

---

## 22. 应用层与产品接入方案

### 22.1 `GeneralFEMSolver` 的未来角色

当前它更像轻量 runner。未来应该升级为：

- orchestration 入口
- 选择 compile/runtime backend
- 管理 export / result adapter
- 保持与 `JobService` 的契约稳定

### 22.2 目标调用链

```text
JobService.run_case()
  → GeneralFEMSolver.run_task()
      → prepare_case()
      → compile_case()
      → runtime.execute()
      → export / result_db adapt
      → JobRunSummary
```

### 22.3 `JobService` 的扩展方向

建议新增：

```python
@dataclass(slots=True)
class JobPlanSummary:
    case_name: str
    profile: str
    device: str
    has_cuda: bool
    thread_count: int
    note: str
    metadata: dict[str, Any] = field(default_factory=dict)
    estimated_partitions: int | None = None
    estimated_peak_memory_bytes: int | None = None
```

```python
@dataclass(slots=True)
class JobRunSummary:
    case_name: str
    profile: str
    device: str
    out_path: Path
    stage_count: int
    field_count: int
    result_db: 'ResultDatabase'
    metadata: dict[str, Any] = field(default_factory=dict)
    checkpoint_ids: tuple[str, ...] = ()
    telemetry_summary: dict[str, object] = field(default_factory=dict)
```

### 22.4 `WorkbenchService` 的接入点

现有：

- `plan_document()`
- `run_document()`

继续保留，但在 UI 中补充：

- partition diagnostics
- memory estimate
- runtime profile selection
- failure checkpoint list
- stage-by-stage telemetry summary

### 22.5 CLI 接入点

CLI 应增加参数：

- `--partition-count`
- `--communicator`
- `--checkpoint-policy`
- `--telemetry-level`
- `--deterministic`
- `--resume-checkpoint`

---

## 23. 配置体系设计

### 23.1 当前问题

当前很多运行行为被塞在 `SolverSettings.metadata` 和 `BackendComputePreferences.to_metadata()` 中。

这对快速迭代有帮助，但长期会导致：

- key 无法治理
- 默认值不可见
- 运行契约不明确
- GUI/CLI/Runtime 各自理解不一致

### 23.2 建议分拆配置

建议至少分成四类：

- `CompileConfig`
- `RuntimeConfig`
- `SolverPolicy`
- `ExportPolicy`

### 23.3 `SolverPolicy`

```python
@dataclass(slots=True)
class SolverPolicy:
    nonlinear_max_iterations: int = 12
    tolerance: float = 1e-5
    line_search: bool = True
    max_cutbacks: int = 5
    preconditioner: str = 'auto'
    solver_strategy: str = 'auto'
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 23.4 `ExportPolicy`

```python
@dataclass(slots=True)
class ExportPolicy:
    export_model: bool = True
    export_stage_series: bool = True
    export_increment_snapshots: bool = False
    export_runtime_manifest: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 23.5 推荐 JSON 配置示例

```json
{
  "execution_profile": "gpu",
  "device": "auto-best",
  "compile": {
    "partition_count": 4,
    "partition_strategy": "graph",
    "enable_halo": true
  },
  "runtime": {
    "communicator_backend": "local",
    "checkpoint_policy": "stage-and-failure",
    "telemetry_level": "standard",
    "deterministic": false
  },
  "solver": {
    "nonlinear_max_iterations": 12,
    "tolerance": 1e-5,
    "line_search": true,
    "max_cutbacks": 5
  },
  "export": {
    "export_model": true,
    "export_stage_series": true,
    "export_increment_snapshots": false
  }
}
```

---

## 24. 目录重构蓝图

建议目录重构为：

```text
src/geoai_simkit/
  app/
  core/
  geometry/
  materials/
  pipeline/
  post/
  results/
  solver/
  runtime/
    __init__.py
    compiler.py
    compile_config.py
    bundle.py
    partition.py
    numbering.py
    halo.py
    communicator.py
    bootstrap.py
    runtime.py
    stage_executor.py
    nonlinear.py
    checkpoint.py
    telemetry.py
    result_store.py
    schemas.py
  solver/
    backends/
      __init__.py
      local_backend.py
      distributed_backend.py
      orchestrator.py
    operators/
      __init__.py
      base.py
      continuum_hex8.py
      continuum_tet4.py
      interface_operator.py
      structural_operator.py
      boundary_operator.py
      contact_operator.py
    constitutive/
      __init__.py
      registry.py
      elastic.py
      mohr_coulomb.py
      hss.py
    linsys/
      __init__.py
      operator.py
      sparse_block.py
      iterative.py
      preconditioners.py
    gpu/
      __init__.py
      device_pool.py
      registry.py
      kernels_hex8.py
      kernels_tet4.py
      kernels_interface.py
      kernels_structural.py
```

---

## 25. 新旧模块映射矩阵

| 当前模块 | 去留 | 未来角色 |
|---|---|---|
| `core/model.py` | 保留 | 工程语义层 |
| `pipeline/specs.py` | 保留 | case 描述层 |
| `pipeline/builder.py` | 保留+增强 | 工程模型构建器 |
| `pipeline/execution.py` | 保留+重构 | 执行计划桥接层 |
| `pipeline/runner.py` | 重构 | orchestration 入口 |
| `solver/warp_backend.py` | 拆分 | 分发至 runtime + backends + operators |
| `solver/hex8_linear.py` | 部分保留 | 迁移逻辑到 `operators/continuum_hex8.py` |
| `solver/hex8_nonlinear.py` | 部分保留 | 同上 |
| `solver/tet4_linear.py` | 部分保留 | 迁移到 `operators/continuum_tet4.py` |
| `solver/interface_elements.py` | 部分保留 | 迁移到 `operators/interface_operator.py` |
| `solver/structural_elements.py` | 部分保留 | 迁移到 `operators/structural_operator.py` |
| `solver/linear_algebra.py` | 拆分 | 迁移到 `solver/linsys/` |
| `solver/gpu_runtime.py` | 保留+增强 | device discover / bind utility |
| `results/database.py` | 保留 | GUI 浏览数据库 |
| `post/exporters.py` | 保留+适配 | runtime result export |
| `app/job_service.py` | 保留+增强 | 任务规划与汇总输出 |
| `app/workbench.py` | 保留+增强 | 前端壳层 |

---

## 26. 文件级重构任务清单

下面这一节是本版最关键的落地内容之一：**逐文件说明怎么改，不说空话。**

### 26.1 `pipeline/runner.py`

#### 当前角色

- `GeneralFEMSolver`
- `run_task()` 里直接 prepare → solve → export
- backend 默认直连 `WarpBackend`

#### 重构目标

- 变成 orchestration 入口
- 不再直接绑定 `WarpBackend`
- 插入 compile/runtime/result adapter 三段

#### 具体动作

1. 保留 `AnalysisTaskSpec` / `AnalysisRunResult` / `AnalysisExportSpec`
2. 给 `GeneralFEMSolver` 新增依赖注入：
   - `compiler`
   - `runtime_factory`
   - `result_adapter`
3. `solve_case()` 改为：
   - `prepare_case()`
   - `compile_case()`
   - `runtime.execute()`
   - `adapt_results()`
4. `backend` 字段退化为兼容旧路径的桥接接口，而非核心逻辑

### 26.2 `solver/warp_backend.py`

#### 当前问题

- 逻辑过肥
- 混合路径过多
- 未来无法支撑 distributed runtime

#### 重构目标

- 不再作为主 backend 总控
- 拆成若干 operator / device / solver utility

#### 具体动作

1. 把 Hex8 GPU 组装逻辑提到 `solver/operators/continuum_hex8.py`
2. 把非线性控制逻辑提到 `runtime/nonlinear.py`
3. 把 device fallback 逻辑提到 `solver/backends/local_backend.py`
4. `warp_backend.py` 最终只保留兼容旧 API 的薄封装，或逐步废弃

### 26.3 `solver/linear_algebra.py`

#### 当前角色

- 线程数建议
- 稀疏求解相关工具

#### 重构目标

- 拆到 `solver/linsys/`
- 分清 operator、solver、preconditioner 三类职责

#### 具体动作

- `default_thread_count()` 保留到 util 层或 `linsys/config.py`
- 稀疏装配逻辑迁移到 `sparse_block.py`
- 迭代求解逻辑迁移到 `iterative.py`
- 预条件器逻辑迁移到 `preconditioners.py`

### 26.4 `solver/gpu_runtime.py`

#### 当前角色

- 探测设备
- 选择设备

#### 重构目标

- 继续作为设备探测层
- 不把 runtime 生命周期放进这里

#### 具体动作

- 保留 `GpuDeviceInfo`
- 保留 `detect_cuda_devices()`
- 保留 `choose_cuda_device()`
- 新增 `bind_rank_device()`
- 新增 `device_capacity_snapshot()`

### 26.5 `solver/compute_preferences.py`

#### 当前角色

- 计算 profile
- metadata 汇总
- 设备选择

#### 重构目标

- 从“塞 metadata dict”转向“桥接 typed config”

#### 具体动作

1. 继续保留 `BackendComputePreferences`
2. 增加到 typed config 的转换方法：
   - `to_compile_config()`
   - `to_runtime_config()`
   - `to_solver_policy()`
3. `to_metadata()` 暂时保留兼容层，不作为新系统主接口

### 26.6 `results/database.py`

#### 当前角色

- GUI 结果浏览数据库

#### 重构目标

- 继续保持简单
- 通过 adapter 从 runtime store 构建

#### 具体动作

- 保留 `StageResultRecord`
- 保留 `ResultDatabase`
- `build_result_database(model)` 继续保留旧路径
- 新增 `build_result_database_from_runtime_store(runtime_store)`

### 26.7 `app/job_service.py`

#### 当前角色

- 计划 case
- 运行 case
- 产出 `JobRunSummary`

#### 重构目标

- 对用户保持接口稳定
- 内部切换到 compile/runtime 新路径

#### 具体动作

1. `plan_case()` 增加分区和显存估算摘要
2. `run_case()` 接入 `GeneralFEMSolver.run_task()` 新汇总结果
3. `JobRunSummary.metadata` 中增加：
   - `compile_report`
   - `telemetry_summary`
   - `checkpoint_ids`

### 26.8 `app/workbench.py`

#### 当前角色

- 工作台壳层
- plan / run document

#### 重构目标

- 保持壳层稳定
- 暴露新运行时诊断数据

#### 具体动作

- `plan_document()` 展示 compile diagnostics
- `run_document()` 存储 runtime telemetry 摘要
- `WorkbenchDocument` 新增：
  - `compile_report`
  - `telemetry_summary`
  - `checkpoint_ids`

---

## 27. 建议新增的文件与代码骨架

### 27.1 `runtime/compiler.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CompileReport:
    ok: bool
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeCompiler:
    def compile_case(self, prepared, config):
        """Compile prepared engineering model into runtime assets."""
        raise NotImplementedError
```

### 27.2 `runtime/runtime.py`

```python
from __future__ import annotations


class DistributedRuntime:
    def __init__(self, config, communicator=None, telemetry=None):
        self.config = config
        self.communicator = communicator
        self.telemetry = telemetry
        self._bundle = None

    def initialize(self, bundle):
        """Bind partitions, allocate buffers, and restore checkpoints if needed."""
        self._bundle = bundle

    def execute(self):
        """Execute all compiled stages and return a runtime report."""
        raise NotImplementedError

    def shutdown(self):
        """Release runtime resources and flush diagnostics."""
        self._bundle = None
```

### 27.3 `runtime/stage_executor.py`

```python
from __future__ import annotations


class StageExecutor:
    def __init__(self, nonlinear_controller, checkpoint_manager, telemetry):
        self.nonlinear_controller = nonlinear_controller
        self.checkpoint_manager = checkpoint_manager
        self.telemetry = telemetry

    def run_stage(self, stage_index, context):
        """Run one compiled stage with commit / rollback boundaries."""
        raise NotImplementedError
```

### 27.4 `runtime/checkpoint.py`

```python
from __future__ import annotations


class CheckpointManager:
    def save_stage_checkpoint(self, runtime, stage_index):
        """Persist a committed stage snapshot."""
        raise NotImplementedError

    def save_failure_checkpoint(self, runtime, stage_index, increment_index):
        """Persist a failure snapshot for later diagnosis or restart."""
        raise NotImplementedError

    def load_checkpoint(self, checkpoint_id):
        """Restore runtime state from a checkpoint asset."""
        raise NotImplementedError
```

### 27.5 `runtime/telemetry.py`

```python
from __future__ import annotations


class TelemetryRecorder:
    def record_event(self, name, payload):
        """Append one telemetry event."""
        raise NotImplementedError

    def final_summary(self):
        """Return aggregated runtime statistics."""
        raise NotImplementedError
```

### 27.6 `solver/backends/distributed_backend.py`

```python
from __future__ import annotations


class DistributedBackend:
    def __init__(self, compiler, runtime_factory, result_adapter):
        self.compiler = compiler
        self.runtime_factory = runtime_factory
        self.result_adapter = result_adapter

    def solve(self, prepared_case, settings):
        """Compile, execute, and adapt results for distributed runtime."""
        raise NotImplementedError
```

### 27.7 `solver/operators/base.py`

```python
from __future__ import annotations


class Operator:
    name = 'operator'

    def prepare(self, state, context):
        """Prepare local buffers before evaluation."""
        return None

    def evaluate(self, state, context):
        """Return residual/tangent contributions."""
        raise NotImplementedError

    def commit(self, state, context):
        """Commit operator-local trial state."""
        return None

    def rollback(self, state, context):
        """Discard operator-local trial state."""
        return None
```

---

## 28. 时序图

### 28.1 编译时序

```text
JobService.plan_case / run_case
  → GeneralFEMSolver.prepare_case
      → AnalysisCaseBuilder.build
          → PreparedAnalysisCase
  → RuntimeCompiler.compile_case
      → normalize topology
      → encode region/material/stage
      → partition
      → numbering
      → halo plan
      → compile report
  → CompilationBundle
```

### 28.2 运行时序

```text
GeneralFEMSolver.run_task
  → DistributedRuntime.initialize
      → bootstrap rank/device
      → allocate buffers
      → restore checkpoint if requested
  → DistributedRuntime.execute
      → for each stage:
          → StageExecutor.run_stage
              → for each increment:
                  → NonlinearController.solve_increment
                      → operators.evaluate
                      → communicator.exchange
                      → operator assembler
                      → linear solver
                      → convergence check
                      → commit or rollback
          → checkpoint save
          → runtime result flush
  → ResultDatabaseAdapter
  → ExportManager
```

### 28.3 失败恢复时序

```text
Increment failure
  → rollback increment trial state
  → cutback and retry
  → still fail?
      → rollback to stage start
      → write failure checkpoint
      → abort stage / runtime
```

---

## 29. MVP 边界定义

### 29.1 必做能力

- `partition_count=1` 与 `partition_count>1` 共用 runtime
- Hex8 连续体
- staged static / quasi-static
- 本构：linear elastic + Mohr-Coulomb 主路径
- block sparse 组装式线性系统
- halo exchange
- stage checkpoint
- failure checkpoint
- result adapter
- telemetry summary

### 29.2 暂不做

- 动态重平衡
- 完整 mortar contact
- matrix-free 主路径
- 全量 Tet4 非线性
- shell/beam 高阶特化
- 跨节点部署自动化
- 云端调度器集成

### 29.3 MVP 验收标准

- 单分区新 runtime 与旧路径结果可对齐
- 两分区与单分区结果差异在可接受阈值内
- stage rollback 行为正确
- failure checkpoint 可恢复到最近有效边界
- GUI 可读取结果摘要

---

## 30. 分阶段实施路线图

### Phase 1：边界重构

目标：把工程层、编译层、运行层边界分开。

交付：

- `runtime/` 目录建起来
- `GeneralFEMSolver` 新路径打通
- `partition_count=1` 编译产物形成

### Phase 2：单分区新 runtime 跑通

目标：新 runtime 在单分区条件下复现当前主流程。

交付：

- `RuntimeCompiler`
- `DistributedRuntime`（单分区模式）
- `StageExecutor`
- `CheckpointManager`
- `TelemetryRecorder`

### Phase 3：单节点多 GPU 真并行

目标：同一个问题跨多个 partition / GPU 协同求解。

交付：

- `Communicator`
- `HaloExchangePlan`
- `DistributedDofNumbering`
- 基础 reduction

### Phase 4：非线性土体主干

目标：Mohr-Coulomb / HSS 等状态管理纳入 runtime。

交付：

- `GaussPointStateBuffer`
- trial/commit/rollback
- cutback + line search + modified Newton

### Phase 5：界面与结构耦合

目标：界面和结构单元进入统一 operator 框架。

交付：

- `InterfaceOperator`
- `StructuralOperator`
- stage-aware masks

### Phase 6：产品化增强

目标：让 GUI、CLI、导出、恢复和诊断闭环。

交付：

- runtime manifest
- compile diagnostics
- restart from checkpoint
- richer telemetry in workbench

---

## 31. 测试体系设计

### 31.1 层级划分

1. unit test
2. operator test
3. stage execution test
4. distributed consistency test
5. regression benchmark
6. restart test
7. GUI integration smoke test

### 31.2 最少要有的测试用例

#### 编译层

- region/material 覆盖完整性
- partition count 合法性
- halo 计划正确性
- numbering 无重复 / 无遗漏

#### runtime 层

- 单 stage 收敛
- 多 stage 继承
- increment cutback
- stage rollback
- failure checkpoint

#### distributed 层

- 1 分区 vs 2 分区结果一致性
- 2 分区 vs 4 分区一致性
- halo 数据一致性
- 全局 reduction 正确性

#### result 层

- checkpoint restore
- runtime store → result db adapter
- export stage series

### 31.3 定量标准建议

- 位移场 L2 相对误差
- 关键应力/应变指标相对误差
- 收敛步数变化范围
- 最大不平衡残量阈值
- checkpoint 恢复后首步一致性

---

## 32. 开发任务拆分建议

### 32.1 适合并行推进的任务组

#### A 组：Compile & Partition

- `runtime/compiler.py`
- `runtime/partition.py`
- `runtime/numbering.py`
- `runtime/halo.py`

#### B 组：Runtime Core

- `runtime/runtime.py`
- `runtime/bootstrap.py`
- `runtime/stage_executor.py`
- `runtime/nonlinear.py`

#### C 组：Operators & Constitutive

- `solver/operators/*`
- `solver/constitutive/*`

#### D 组：Results & Observability

- `runtime/checkpoint.py`
- `runtime/telemetry.py`
- `results/runtime_store.py`
- `results/runtime_adapter.py`

#### E 组：Application Bridge

- `pipeline/runner.py`
- `app/job_service.py`
- `app/workbench.py`

### 32.2 最合适的开发顺序

1. A + E 先开路
2. B 打通单分区
3. C 接入 Hex8
4. D 补 checkpoint/telemetry
5. 再把 distributed communicator 接上

---

## 33. 风险清单与规避策略

### 33.1 风险：边界还没拆清就急着上多 GPU

后果：

- 代码不可维护
- bug 难查
- 旧路径和新路径互相污染

规避：

- 先做 compile/runtime/result 三层分离

### 33.2 风险：本构状态仍用 Python object 保存

后果：

- GPU 不能常驻
- checkpoint 复杂
- 性能差

规避：

- 统一 `GaussPointStateBuffer`

### 33.3 风险：Stage 语义没有落到 runtime state machine

后果：

- 施工阶段逻辑混乱
- rollback 边界错误

规避：

- 强制 `StageExecutor` 独立层

### 33.4 风险：结果系统与 checkpoint 混用

后果：

- 结果浏览和恢复逻辑互相影响

规避：

- `RuntimeResultStore` 与 `ResultDatabase` 严格分离

### 33.5 风险：一开始就追求 matrix-free

后果：

- 工程周期暴涨
- 很难验证正确性

规避：

- 首版先走装配式 block sparse

---

## 34. 版本目标定义

### v1.0-DG

- compile/runtime/result 三层打通
- Hex8 单分区新 runtime 跑通
- stage checkpoint
- telemetry summary

### v1.1-DG

- 单节点多 partition
- halo exchange
- 分布式 Krylov 主路径
- 1/2/4 分区一致性验证

### v1.2-DG

- 非线性土体主干稳定
- Mohr-Coulomb / HSS 运行时状态规范化
- failure checkpoint / restart

### v1.3-DG

- interface / structural operator 接入
- richer workbench diagnostics
- export / result manifest 完整化

### v1.4-DG

- Tet4 非线性与混合网格增强
- 更强的性能优化与观测能力
- 视情况评估 matrix-free 路线

---

## 35. 最终结论

这套代码现在最该做的，不是继续往 `WarpBackend.solve()` 里堆功能，而是完成一次真正的系统级分层重构：

1. **保留工程建模层与产品壳层**。  
2. **新建 Compile Plane，把 case 编译为 runtime 资产**。  
3. **新建 Runtime Plane，把 stage、partition、halo、checkpoint、telemetry 全部对象化**。  
4. **把单元与本构下沉为 operator/kernel，而不是继续堆在 monolithic backend 里**。  
5. **让 `partition_count=1` 与 `partition_count>1` 共用同一运行时框架**。  
6. **首版先稳稳做成 Hex8 + staged static/quasi-static + block sparse + checkpoint**。  
7. **等框架立住之后，再逐步接 Tet4、结构、界面、多物理场和更深层优化**。

一句话概括：

> 你的下一代系统，不该是“一个更大的 WarpBackend”，而应该是“一个可编译、可分区、可恢复、可观测的分布式 GPU 有限元运行时平台”。

---

## 36. 下一步最值得继续产出的文档

基于这版 v4，后续最值得继续往下压的不是再写泛泛蓝图，而是下面三类具体成果：

1. **代码级接口草案包**  
   直接输出各文件的 Python 类定义、方法签名、占位实现和导入关系。

2. **文件级重构任务看板**  
   按“新增 / 拆分 / 替换 / 废弃”四类把每个文件变成任务列表。

3. **MVP 首期代码骨架包**  
   直接生成 `runtime/`、`solver/backends/`、`solver/operators/` 的初始代码骨架。

