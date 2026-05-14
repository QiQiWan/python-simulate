# GeoAI SimKit 1.5.6 — Engineering Snap Constraints

本次迭代把 1.5.5 的基础网格/端点/中点吸附继续深化为工程语义吸附和约束捕捉。

## 新增能力

- 墙端点、梁端点、锚杆端点语义吸附。
- 地层边界交点、开挖轮廓线交点吸附。
- 水平、垂直、沿边、沿法向约束投影。
- 结构建模面板新增语义吸附与约束开关。
- 创建线、面、体预览时携带 constraint metadata，viewport 可渲染约束点与标签。
- CAD structure workflow 契约升级为 `geoai_simkit_cad_structure_workflow_v5`。
- GUI geometry interaction 契约升级为 `phase_workbench_geometry_interaction_v6`。

## 交互约定

- Shift：水平约束。
- Ctrl：垂直约束。
- 沿边与沿法向作为显式约束模式保留给工具面板或后续快捷键绑定。
- SnapController 在 Qt-free 环境下可测试，真实 GUI 通过 PyVista adapter 消费 metadata 渲染辅助点和标签。

## 验证

- `tests/gui/test_iter156_engineering_snap_constraints.py`
- `tests/gui/test_iter155_snap_crosshair_surface_menu.py`
- `tests/gui/test_iter154_viewport_workplane_hover_creation.py`
- `tests/gui/test_iter153_structure_mouse_material_workflow.py`
