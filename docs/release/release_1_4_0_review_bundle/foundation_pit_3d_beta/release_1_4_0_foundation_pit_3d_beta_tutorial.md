# GeoAI SimKit 1.4.0 Beta-2 Template Tutorial — 三维基坑分阶段施工 Beta Demo

## 一键模板流程
在六阶段工作台中打开 `1.4 Demo` 页签，选择模板后依次执行：

1. `一键加载模板`：加载当前工程模板。
2. `运行当前模板完整流程`：执行网格、阶段编译、非线性求解、固结、接触迭代和结果导出。
3. `导出当前模板审查包`：输出工程文件、VTK、JSON 和 Markdown 报告。
4. `运行全部 1.4 模板`：批量运行基坑、边坡、桩-土三类模板。

## 工程问题
分阶段开挖和支护激活后，墙体位移、沉降和孔压响应是否可接受？

## 预期输出
- 墙体水平位移
- 地表沉降
- 支撑轴力
- 孔压变化
- VTK 云图

## Calculation pipeline
- `done` 一键加载三维基坑 Demo (geology)
- `done` 生成地质体、开挖体、支护墙和支撑 (geology/structures)
- `done` 生成 Tet4 网格与物理组标签 (mesh)
- `done` 编译阶段施工求解输入 (staging)
- `done` 运行全局 Mohr-Coulomb Newton 求解 (solve)
- `done` 运行固结耦合与界面开闭合迭代 (solve/results)
- `done` 生成结果查看、VTK、JSON 和工程报告 (results)

## Acceptance
- Project: `GeoAI SimKit 1.4.0 Beta-2 三维基坑分阶段施工 Beta Demo`
- Demo: `foundation_pit_3d_beta`
- Family: `foundation_pit`
- Status: `accepted_1_4_0_template`
- Accepted: `True`

## Boundary of use
1.4.1-geometry is a multi-template engineering Beta. It demonstrates complete calculation and export flows for built-in scenarios; native Gmsh/OCC and desktop GUI interaction should still be validated on the target workstation before production sign-off.
