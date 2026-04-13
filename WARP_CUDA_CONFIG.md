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
