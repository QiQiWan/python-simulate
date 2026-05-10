# GeoAI SimKit v0.8.22-solver-benchmark

本轮聚焦求解器可信度与结果包验收，而不是新增 GUI 页面。

## 已新增

- Tet4 affine patch test：验证常应变四面体在仿射位移场下的应变/应力精度。
- Cantilever benchmark：Tet4 悬臂梁弯曲位移与 Euler-Bernoulli 解析解对比。
- K0 geostatic benchmark：土柱初始地应力与闭式深度分布对比。
- Truss support stiffness benchmark：验证 truss/strut 支护构件进入全局刚度后降低侧向位移。
- Bad mesh strict rejection benchmark：严格模式下坏网格质量报告阻断求解入口。
- Result package acceptance gate：导出结果包时生成 package-level acceptance，拒绝 synthetic/invalid/unaccepted 包。

## 新增代码

- `src/geoai_simkit/solver/benchmarks.py`
- `src/geoai_simkit/results/acceptance.py`
- `tests/solver/test_iter82_solver_benchmarks.py`

## 验证命令

```bash
python -m pytest -q tests/solver/test_iter82_solver_benchmarks.py
```

预期结果：

```text
8 passed
```

## 仍需继续推进

- Tet4 benchmark 仍为参考求解器级别，Hex8/GPU/native 还需要同等 benchmark。
- 悬臂梁 benchmark 使用粗 Tet4 网格，当前作为回归门槛，不能替代高阶单元/网格收敛研究。
- Truss/anchor/strut 已进入全局刚度，beam/plate/shell/wall 仍需完整结构单元耦合。
- Result package acceptance 已具备，但还应继续接入 GUI Solve/Export 按钮状态。
