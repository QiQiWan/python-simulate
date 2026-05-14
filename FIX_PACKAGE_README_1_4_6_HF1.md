# GeoAI SimKit 1.4.6-hf1 修复包说明

## 已修复

1. GUI 启动崩溃：移除了会在 PySide6/Qt 中抛错的 `QStyle.StandardPixmap.SP_ArrowCursor`，改为安全的字符串枚举解析和多级 fallback。
2. face / edge 级鼠标拾取：PyVista 视口新增 VTK cell-aware picking，支持读取 actor cell data 中的 `geoai_topology_id`、`geoai_kind`、`geoai_source_entity_id`。
3. GUI 拓扑 ID 自动填充：视口选中 face/edge 后，语义/材料/阶段面板会自动填充 `Face/Edge/Solid ID`，并保留源体实体 ID。
4. CAD 拓扑可视化绑定：ViewportState 会从 CadShapeStore 拓扑记录生成可拾取 face/edge primitive；block actor 在存在 face topology 记录时写入 per-cell topology metadata。
5. 编辑手柄深化：选中对象后会生成中心手柄和 X/Y/Z gizmo-axis actor；拖拽/复制工具会识别 `handle_axis` 并进行轴向约束。
6. 建模实时预览：Extrude、Cut、Boolean 工具增加鼠标移动预览输出，执行前能看到拉伸包围、切割平面、布尔目标包围范围。
7. 布尔 lineage 深化：boolean lineage 服务新增 `native_occ_history_map` / `occ_history_map` 入口；真实 OCC history map 可直接生成 native confidence 的 split/merge/preserved lineage。
8. STEP/IFC persistent naming 验证：新增 `tools/run_persistent_naming_benchmark.py`，用于在真实桌面 OCP/IfcOpenShell/Gmsh 环境中对复杂 STEP/IFC 文件执行 persistent naming 稳定性 benchmark。

## 建议验证命令

```powershell
conda activate ifc
cd E:\OneDrive\python\research\python_simu
python .\start_gui.py
```

依赖自检通过后，GUI 应不再因 `SP_ArrowCursor` 退出。

基础回归测试：

```powershell
$env:PYTHONPATH="src"
python -m pytest -q tests/test_borehole_csv_importer.py tests/test_layer_surface_meshing.py tests/test_layered_mesh_workflow_command.py tests/test_stl_geology_loader.py tests/test_gui_hotfix_picking_contract.py
```

复杂 STEP/IFC benchmark 示例：

```powershell
$env:PYTHONPATH="src"
python .\tools\run_persistent_naming_benchmark.py .\benchmarks\step_ifc --output .\reports\persistent_naming_benchmark.json
```

如果只是想确认 benchmark 管线可运行、不做 native 认证，可增加：

```powershell
python .\tools\run_persistent_naming_benchmark.py .\benchmarks\step_ifc --allow-fallback
```

## 本次环境验证结果

在当前容器环境完成了语法编译与 dependency-light 回归测试：

```text
12 passed in 2.59s
```

由于当前容器没有你的 Windows 桌面 Qt/PyVista/OCP/IfcOpenShell 图形运行环境，未能实际打开桌面 GUI 或对真实复杂曲面 STEP 文件做 native-certified benchmark。该部分需要在你的 `ifc` conda 环境中执行上面的 GUI 与 benchmark 命令。
