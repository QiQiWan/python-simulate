# GeoAI SimKit 1.7.3 visual selection tree optimized

本次版本针对导入地质模型的可视化花影、对象选择和模型树复杂度做了集中修复。

## 可视化框架

- 导入的 VTU/MSH 地质网格使用独立 surface actor、surface grid line actor、outline actor 和四侧轮廓 actor 渲染，避免同一 actor 同时开启 `show_edges=True` 引起的 z-fighting/moire 花影。
- 从 meshio 导入生成的包围盒占位 volume 默认只绘制 outline，不再以半透明实体压在真实导入网格上。
- 普通 surface/block primitive 也改为“实体面 + 单独边线”的绘制方式，降低几何面和线框共面叠绘产生的闪烁。

## 导入地质模型选择

- 主地质面 actor、外表面网格线、四侧轮廓线、外轮廓线均带 `geoai` selection metadata。
- 点选地质单元时可解析出 `geology_layer:<layer>`，点选轮廓或网格线时回退选择 `imported_geology_model`。
- 选择高亮使用导入地质模型或对应地层的 bounds，并显示中心编辑 handle。

## 左侧模型树

- Qt 工作台默认使用精简工程树，仅显示：地质体、围护墙、水平支撑、梁、锚杆。
- 对导入网格场景，地质体目录只保留“导入地质模型”和地层子节点，隐藏由导入流程自动生成的 soil cluster / volume 占位对象，避免重复。
- 地层节点支持显示用户编辑后的地层名和材料名。

## 属性编辑

- 属性面板新增“名称”输入和“应用名称/材料”按钮。
- 支持编辑体、面、线、结构记录、土簇、导入地质模型和单个地层的名称/材料。
- 对 `geology_layer:<value>` 的材料编辑会写入 mesh `layer_properties`，并同步更新 `cell_tags['material_id']` 中对应层的单元。

## 校验

- `tests/gui/test_vtu_paraview_style_visualization.py`
- `tests/test_gui_hotfix_picking_contract.py`
- `tests/gui/test_visual_selection_tree_optimized_v173.py`
