# GeoAI SimKit 1.3.0 Beta Demo Tutorial

## 一键 Demo
启动 GUI 后进入六阶段工作台，打开右侧 `1.3 Demo` 页签，点击：

1. `一键加载 1.3 Demo`：加载三维基坑 Beta 示例工程。
2. `运行完整计算流程`：依次完成地质/结构数据、Tet4 网格、阶段编译、Mohr-Coulomb Newton、固结、界面迭代和结果写入。
3. `导出 Demo 审查包`：导出工程文件、结果、VTK、JSON 和 Markdown 报告。

## Calculation pipeline
- `done` 一键加载三维基坑 Demo (geology)
- `done` 生成地质体、开挖体、支护墙和支撑 (geology/structures)
- `done` 生成 Tet4 网格与物理组标签 (mesh)
- `done` 编译阶段施工求解输入 (staging)
- `done` 运行全局 Mohr-Coulomb Newton 求解 (solve)
- `done` 运行固结耦合与界面开闭合迭代 (solve/results)
- `done` 生成结果查看、VTK、JSON 和工程报告 (results)

## Acceptance
- Project: `GeoAI SimKit 1.3.0 Beta Foundation Pit Demo`
- Release: `1.3.0-beta`
- Phases: `initial, excavation_1, support_1, excavation_2, support_2`
- Status: `blocked_1_3_0_beta`
- Accepted: `False`

## Boundary of use
1.3.0-beta is an engineering Beta demonstration build. It can run the complete built-in calculation workflow, but native Gmsh/OCC and desktop GUI interaction should still be verified on the target workstation before production sign-off.
