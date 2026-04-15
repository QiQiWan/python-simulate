# GeoAI SimKit v0.1.36

## 本次升级重点

### 1. 自动界面从“黑盒”升级为“可控流程”
- 新增可勾选的界面组：
  - `outer`
  - `inner_upper`
  - `inner_lower`
- 新增可勾选的支撑组：
  - `crown_beam`
  - `strut_level_1`
  - `strut_level_2`
- GUI 中可直接决定哪些组参与自动生成，而不是只能整套启用。

### 2. 最近土层吸附半径可调
- 新增 `最近土层吸附半径因子` 控件。
- 会写入 `demo_interface_nearest_radius_factor`，用于控制 node-pair 自动吸附跨度。
- 有助于在“严格匹配”和“稳健自动匹配”之间切换。

### 3. 界面向导支持导出诊断
- 新增导出 JSON
- 新增导出 CSV
- 可保存每一面墙界面的：
  - 分组
  - 激活阶段
  - 匹配土层
  - 选点模式
  - 配对数量
  - 未匹配数量
  - 最大配对距离

### 4. 界面向导增加推荐设置
- 新增“应用推荐设置”按钮。
- 可一键恢复：
  - `plaxis_like_auto`
  - `manual_like_nearest_soil`
  - 半径因子 `1.75`
  - 全界面组启用
  - 全支撑组启用

### 5. 求解前检查更尊重用户选择
- `pre-solve` 现在会按启用的界面组/支撑组做检查。
- 如果你主动禁用了某一组，不再误报“缺失”。
- 如果启用了某一组但自动生成后确实缺失，仍会明确报错。

## 主要修改文件
- `src/geoai_simkit/geometry/demo_pit.py`
- `src/geoai_simkit/app/main_window.py`
- `src/geoai_simkit/app/presolve.py`
- `tests/test_demo_interface_auto.py`
- `tests/test_demo_pit_workflow.py`

## 校验结果
- `python -m compileall -q src`
- `17 passed, 1 skipped`
