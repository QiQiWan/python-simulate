# geoai_simkit v0.1.37

## 本次修复
- 修复 `normalize_boundary_target` 未导入导致的 `NameError`，恢复边界别名 `bottom/top/left/right/front/back` 在 Hex8 求解路径中的可用性。
- 改进 Stage 表格选择保持与自动选择逻辑，边界模板、边界条件、荷载编辑在未手动点选 Stage 时会自动回到当前或第一阶段。
- 将参数化基坑多结构耦合 demo 的默认非线性控制调得更保守：更小初始增量、更低最大负载分数、禁用 modified Newton 切线复用、提高 cutback 容忍度。

## 影响
- 解决了“创建示例后点击求解立即在 `_dirichlet_data()` 崩溃”的阻断错误。
- 降低了墙-土-interface-支撑自动耦合示例在 `initial` 阶段就早停的概率。
- 减少了 GUI 中频繁出现“请先选择一个 Stage”的无效操作提示。
