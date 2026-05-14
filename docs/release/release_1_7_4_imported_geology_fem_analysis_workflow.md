# GeoAI SimKit 1.7.4 — Imported Geology FEM Analysis Workflow

## 目标

本次迭代把导入地质模型后的有限元分析链路整理为模块化流程：导入状态准备、FEM 网格质量和材料状态检查、有限元网格划分/修复、自动地应力配置、阶段求解模型编译、稳态求解和结果查看。

## 核心改动

- 新增 `geoai_simkit.services.geology_fem_analysis_workflow` 服务模块，提供无 GUI 依赖的完整分析流程入口。
- 对 VTU/MSH 等导入网格的 `geology_layer_id` 建立显式地层体、土体材料、`block_id` 和 `material_id` 映射。
- 支持复用已导入的体网格；当只有表面网格或质量不满足要求时，走 Gmsh/OCC Tet4 体网格生成路线或确定性替代路线。
- 自动配置地应力计算所需的底部固定、侧向法向约束、材料重度体力和可选表面附加荷载。
- 调用阶段编译与增量平衡求解，输出位移、沉降、应力、等效应变、von Mises 等结果字段，并按相对残差判断稳态。
- GUI 新增“FEM分析流程”右侧流程面板，按检查、网格、求解、结果查看推进，也支持一键完整流程。
- 长耗时完整流程通过后台任务执行，并通过进度事件驱动进度条、状态文本和日志刷新。
- PyVista 和 Qt-only 视口均补充 FEM 结果叠加接口，便于查看 `displacement`、`uz`、`cell_stress_zz`、`cell_von_mises`、`cell_equivalent_strain`。

## 回归验证

执行以下测试通过：

```bash
PYTHONPATH=src pytest -q \
  tests/gui/test_vtu_paraview_style_visualization.py \
  tests/test_gui_hotfix_picking_contract.py \
  tests/gui/test_visual_selection_tree_optimized_v173.py \
  tests/services/test_imported_geology_fem_analysis_workflow.py \
  tests/gui/test_imported_geology_fem_analysis_panel.py
```

结果：11 passed。
