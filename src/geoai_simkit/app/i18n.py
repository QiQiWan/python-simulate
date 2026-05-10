from __future__ import annotations

EXACT = {
    'zh': {
        'geoai-simkit': 'geoai-simkit',
        'Project': '项目', 'Geometry / IFC': '几何 / IFC', 'Regions & Materials': '区域 / 材料', 'Boundary / Stages': '边界 / 阶段', 'Solve / Results': '求解 / 结果',
        'Logs': '日志', 'Tasks': '任务', 'Validation': '校验', 'History': '收敛',
        'Selection': '选择', 'Actions': '操作', 'Solver': '求解',
        'Workflow': '工序条', 'Model Validation': '模型校验', 'Inspector': '属性检查器',
        'Hide Selected': '隐藏选中', 'Show Selected': '显示选中', 'Show All': '全部显示', 'Isolate Selected': '仅显示选中',
        'Language': '语言', 'English': '英文', 'Chinese': '中文', 'Auto collapse': '自动折叠', 'Pin inspector': '锚定检查器',
        'No model loaded': '未载入模型', 'Ready': '就绪',
        'Run': '求解', 'Cancel': '取消', 'Export VTK': '导出 VTK', 'Export ParaView Bundle': '导出 ParaView Bundle',
        'Background solve': '后台求解', 'Cancel solve': '取消求解',
        'Validation failed': '模型校验未通过', 'Solver failed': '求解失败',
        'Running': '运行中', 'Failed': '失败', 'Completed': '已完成', 'Canceled': '已取消',
        'ETA': '预计剩余', 'Elapsed': '已用时间',
        'Project overview': '项目概览',
    },
    'en': {
        '项目': 'Project', '几何 / IFC': 'Geometry / IFC', '区域 / 材料': 'Regions & Materials', '边界 / 阶段': 'Boundary / Stages', '求解 / 结果': 'Solve / Results',
        '日志': 'Logs', '任务': 'Tasks', '模型校验': 'Validation', '收敛': 'History', '选择': 'Selection', '操作': 'Actions', '求解': 'Solver',
        '工序条': 'Workflow', '属性检查器': 'Inspector', '隐藏选中': 'Hide Selected', '显示选中': 'Show Selected', '全部显示': 'Show All', '仅显示选中': 'Isolate Selected',
        '语言': 'Language', '英文': 'English', '中文': 'Chinese', '自动折叠': 'Auto collapse', '锚定检查器': 'Pin inspector',
        '未载入模型': 'No model loaded', '就绪': 'Ready', '导入 IFC': 'Import IFC', '新建参数化基坑': 'New Parametric Pit', '导出 VTK': 'Export VTK',
        '导出 ParaView Bundle': 'Export ParaView Bundle', '后台求解': 'Run in Background', '取消求解': 'Cancel Solve', '项目概览': 'Project overview',
        '参数化几何': 'Parametric Geometry', 'IFC 导入选项': 'IFC Import Options', '网格划分流程': 'Meshing Workflow',
        '区域 / 材料': 'Regions & Materials', 'Stage 编辑器': 'Stage Editor', '边界条件': 'Boundary Conditions', '荷载': 'Loads', '结果预览': 'Result Preview', '导出': 'Export',
        '请先创建或导入模型。': 'Please create or import a model first.', '模型校验未通过，请先修正参数。': 'Model validation failed. Please fix parameters first.',
        '求解器正在运行。': 'Solver is already running.', '后台求解已启动 ...': 'Background solve started ...',
        '已请求取消，等待当前迭代结束 ...': 'Cancel requested. Waiting for the current iteration to finish ...',
        '求解异常，请查看日志': 'Solver exception. Please check the logs.', '求解失败': 'Solver failed', '已导出': 'Exported',
        '未选择对象': 'Nothing selected', '对象选择': 'Object selection', '项目': 'Project', '几何': 'Geometry', '边界/阶段': 'Boundary / Stages',
        '对象 / Region 编辑': 'Object / Region Editing', '创建参数化示例': 'Create Parametric Demo', '项目': 'Project',
    },
}

PREFIX = {
    'en': [
        ('已导出: ', 'Exported: '), ('已将 ', 'Assigned '), ('已保存 ', 'Saved '), ('已删除 ', 'Deleted '), ('已复制 ', 'Cloned '), ('已创建', 'Created '), ('已新增', 'Added '), ('已应用', 'Applied '), ('已自动赋默认边界条件：', 'Automatically applied default boundary conditions: '),
        ('请先在场景树中选择一个或多个 IFC 对象。', 'Please select one or more IFC objects in the scene tree first.'), ('请选择目标 Region。', 'Please select a target region.'), ('模型校验未通过', 'Validation failed'), ('后台求解已启动', 'Background solve started'), ('预览失败: ', 'Preview failed: '),
    ],
    'zh': [
        ('Exported: ', '已导出: '),
    ],
}


def translate_text(text: str, lang: str) -> str:
    if not text:
        return text
    exact = EXACT.get(lang, {})
    if text in exact:
        return exact[text]
    for prefix, repl in PREFIX.get(lang, []):
        if text.startswith(prefix):
            return repl + text[len(prefix):]
    return text


EXACT['en'].update({
    '1 项目': '1 Project', '2 几何 / IFC': '2 Geometry / IFC', '3 区域 / 材料': '3 Regions / Materials', '4 Stage / 工况': '4 Boundary / Stages', '5 求解 / 结果': '5 Solve / Results',
    '材料库 / 属性检查器': 'Material Library / Inspector', '区域与赋值': 'Regions and Assignments', '材料名称': 'Material Name', '本构模型': 'Constitutive Model', '参数数': 'Parameter Count',
    '新增/更新': 'Create / Update', '删除': 'Delete', '赋值到选中区域': 'Assign to selected regions', '清除选中区域材料': 'Clear material from selected regions', '当前参数 -> 选中区域': 'Current parameters -> selected regions',
    '求解与进度': 'Solve and Progress', '结果预览': 'Result Preview', '边界条件': 'Boundary Conditions', '荷载': 'Loads', 'Stage 编辑器': 'Stage Editor',
    '名称': 'Name', '类型': 'Type', '目标': 'Target', '状态': 'Status', '对象': 'Object', '属性': 'Properties', '元数据': 'Metadata', '区域': 'Region', '值': 'Value', '字段': 'Field',
    '导入 IFC': 'Import IFC', '创建参数化示例': 'Create Parametric Demo', '求解': 'Run', '取消求解': 'Cancel solve', '导出': 'Export', '导出当前数据集': 'Export current dataset',
    '模型': 'Model', '来源': 'Source', '统计': 'Statistics', '概览': 'Overview', '父级': 'Parent', '参数': 'Parameters', '数值': 'Numerics', '约束': 'Constraints',
    '对象 / Region 编辑': 'Object / Region Editing', '新区域名': 'New region name', '目标区域': 'Target region', '结构角色': 'Object role', '选中对象 -> 新区域': 'Selected objects -> new region',
    '选中对象 -> 现有区域': 'Selected objects -> existing region', '设为新 Region': 'Assign to new region', '设为现有 Region': 'Assign to existing region', '设置对象角色': 'Set object role',
    '激活区域': 'Active regions', '失活区域': 'Inactive regions', '激活区域 / 失活区域（复选框控制）': 'Active / inactive regions (checkbox control)', '阶段名称': 'Stage name',
    '新增 Stage': 'Add stage', '保存 Stage': 'Save stage', '复制当前 Stage': 'Clone current stage', '步数': 'Steps', '初始增量': 'Initial increment', '最大迭代': 'Max iterations', '备注': 'Notes',
    '新增 / 更新 BC': 'Add / update BC', '删除 BC': 'Delete BC', '新增 / 更新荷载': 'Add / update load', '删除荷载': 'Delete load', '类型/区域': 'Type / Region',
    '参数化几何': 'Parametric Geometry', '重建参数化几何': 'Rebuild parametric geometry', '单元尺寸': 'Element size', '方法': 'Method', '执行网格划分': 'Run meshing', '网格划分流程': 'Meshing workflow',
    '自动建议角色/材料': 'Auto-suggest roles/materials', '体网格': 'Volume mesh', '表面网格': 'Surface mesh', '边界/阶段': 'Boundary / Stages', '区域/材料': 'Regions / Materials',
    '已赋值': 'Assigned', '未赋值': 'Unassigned', '线搜索': 'Line search', '变形放大': 'Displacement scale', '来源': 'Source', '模型校验未通过': 'Validation failed'
})
EXACT['zh'].update({v:k for k,v in EXACT['en'].items() if k != v})


EXACT['en'].update({
    'Box Select': 'Box Select', 'Lasso Select': 'Lasso Select', 'Clear Selection': 'Clear Selection',
    'Diagnostics': 'Diagnostics', 'Severity': 'Severity', 'Message': 'Message', 'Remedy': 'Remedy',
    'Automatic material templates': 'Automatic material templates', 'Build suggestions': 'Build suggestions', 'Accept selected': 'Accept selected', 'Reject selected': 'Reject selected', 'Apply accepted': 'Apply accepted', 'Decision': 'Decision',
    'Generated': 'Generated', 'Applied': 'Applied', 'accepted': 'accepted', 'rejected': 'rejected',
    'Validation failed. Please resolve the blocking issues before solving.': 'Validation failed. Please resolve the blocking issues before solving.',
    'Assign materials to all active regions or accept automatic material templates.': 'Assign materials to all active regions or accept automatic material templates.',
    'Run the Meshing workflow and generate a volume mesh before solving.': 'Run the Meshing workflow and generate a volume mesh before solving.',
    'Review active/inactive regions and remove conflicts in the current stage.': 'Review active/inactive regions and remove conflicts in the current stage.',
    'Apply side and bottom displacement constraints or use the default boundary assignment.': 'Apply side and bottom displacement constraints or use the default boundary assignment.',
    'No automatic suggestions are available for the current model.': 'No automatic suggestions are available for the current model.',
    'Applied accepted suggestions.': 'Applied accepted suggestions.',
    'No pickable object was found inside the current selection window.': 'No pickable object was found inside the current selection window.',
    'Selected': 'Selected', 'objects from the 3D selection window.': 'objects from the 3D selection window.',
    'Box selection is active. Drag a rectangle in the 3D view.': 'Box selection is active. Drag a rectangle in the 3D view.',
    'Lasso selection is active. Draw a closed path in the 3D view.': 'Lasso selection is active. Draw a closed path in the 3D view.',
    'Lasso selection is not available; box selection has been enabled instead.': 'Lasso selection is not available; box selection has been enabled instead.',
    'Box selection is unavailable in the current visualization backend.': 'Box selection is unavailable in the current visualization backend.',
    'No model loaded': 'No model loaded',
    'Object selection': 'Object selection', 'Region selection': 'Region selection'
})
EXACT['zh'].update({
    'Box Select': '框选', 'Lasso Select': '套索选择', 'Clear Selection': '清空选择',
    'Diagnostics': '诊断', 'Severity': '级别', 'Message': '消息', 'Remedy': '修复建议',
    'Automatic material templates': '自动材料模板', 'Build suggestions': '生成建议', 'Accept selected': '接受选中', 'Reject selected': '拒绝选中', 'Apply accepted': '应用已接受', 'Decision': '决定',
    'Assign materials to all active regions or accept automatic material templates.': '请为所有激活区域赋材料，或接受自动材料模板建议。',
    'Run the Meshing workflow and generate a volume mesh before solving.': '请先执行网格划分流程并生成体网格，再进行求解。',
    'Review active/inactive regions and remove conflicts in the current stage.': '请检查当前 Stage 的激活/失活区域并消除冲突。',
    'Apply side and bottom displacement constraints or use the default boundary assignment.': '请施加侧边与底部位移约束，或使用默认边界条件。',
    'No automatic suggestions are available for the current model.': '当前模型没有可用的自动建议。',
    'No pickable object was found inside the current selection window.': '当前选择窗口内没有找到可拾取对象。',
    'Box selection is active. Drag a rectangle in the 3D view.': '已启用框选，请在三维视图中拖出矩形。',
    'Lasso selection is active. Draw a closed path in the 3D view.': '已启用套索选择，请在三维视图中绘制闭合路径。',
    'Lasso selection is not available; box selection has been enabled instead.': '当前不支持套索选择，已自动改为框选。',
    'Box selection is unavailable in the current visualization backend.': '当前可视化后端不支持框选。',
    'Validation failed. Please resolve the blocking issues before solving.': '模型校验未通过，请先修复阻塞问题再求解。',
    'Object selection': '对象选择', 'Region selection': '区域选择'
})
