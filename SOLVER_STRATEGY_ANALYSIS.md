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
