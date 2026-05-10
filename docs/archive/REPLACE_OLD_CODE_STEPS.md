# 完整替换旧代码步骤

1. 备份旧目录中的个人数据、算例、结果包和自定义模型。
2. 删除旧项目目录中的全部旧代码。
3. 解压本完整替换包。
4. 进入解压后的根目录。
5. 运行 `python start_gui.py --check` 检查环境。
6. Windows 运行 `启动GUI.bat`；macOS/Linux 运行 `./start_gui.sh`。

如果你之前没有安装 GUI 依赖，需要先在你的 Python 环境中安装 `requirements.txt` 中的依赖，至少需要 PySide6、pyvista、pyvistaqt。
