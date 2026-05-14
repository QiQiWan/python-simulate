# GeoAI SimKit 1.4.0 Beta-2 Multi-template Tutorial

## 目标
1.4.0 将 1.3 的单一基坑 Demo 扩展为多工程模板中心。用户可以在六阶段 GUI 中选择模板，一键加载，并运行完整计算流程。

## 内置模板
- `accepted_1_4_0_template` **三维基坑分阶段施工 Beta Demo** — 分阶段开挖和支护激活后，墙体位移、沉降和孔压响应是否可接受？
- `accepted_1_4_0_template` **边坡稳定分阶段降雨 Beta Demo** — 坡脚扰动和水位变化后，塑性区、位移和有效应力响应是否提示失稳风险？
- `accepted_1_4_0_template` **桩-土相互作用加载 Beta Demo** — 竖向/水平加载后，桩顶位移、桩周界面状态和土体塑性响应是否满足要求？

## GUI 操作
1. 启动软件并通过依赖检查。
2. 进入六阶段工作台，打开 `1.4 Demo` 页签。
3. 选择 `基坑`、`边坡` 或 `桩土` 模板。
4. 点击 `一键加载模板`。
5. 点击 `运行当前模板完整流程` 或 `运行全部 1.4 模板`。
6. 在结果阶段查看结果，并导出审查包。

## Acceptance
- Status: `blocked_1_4_0_beta2`
- Accepted: `False`
- Completed templates: `3/3`

## Boundary of use
1.4.1-geometry is a multi-template engineering Beta build. It is suitable for workflow demonstrations and regression review; certified production analysis still requires native Gmsh/OCC, full desktop GUI validation and solver benchmark sign-off.
