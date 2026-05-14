from __future__ import annotations

"""Modern six-phase workbench visual contract and styling helpers.

The helpers in this module are intentionally Qt-light at import time.  They can
be used by headless tests and by both the PySide-only fallback shell and the
PyVista workbench shell.
"""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.services.workbench_phase_service import build_workbench_phases


@dataclass(frozen=True)
class PhaseVisualToken:
    key: str
    icon: str
    accent: str
    accent_soft: str
    purpose: str
    primary_output: str

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "icon": self.icon,
            "accent": self.accent,
            "accent_soft": self.accent_soft,
            "purpose": self.purpose,
            "primary_output": self.primary_output,
        }


_PHASE_TOKENS: dict[str, PhaseVisualToken] = {
    "geology": PhaseVisualToken(
        key="geology",
        icon="◒",
        accent="#2F7D5A",
        accent_soft="#EAF7F0",
        purpose="地层、地形、STL/地质体导入与材料准备",
        primary_output="可赋材料的地质体与地层面",
    ),
    "structures": PhaseVisualToken(
        key="structures",
        icon="⌁",
        accent="#7C4DFF",
        accent_soft="#F1ECFF",
        purpose="墙、板、梁、桩、锚杆、界面等结构语义建模",
        primary_output="结构对象、截面、界面关系",
    ),
    "mesh": PhaseVisualToken(
        key="mesh",
        icon="▦",
        accent="#1E88E5",
        accent_soft="#EAF4FF",
        purpose="Gmsh/OCC Tet4 物理组、Hex8 fallback、网格质量门控",
        primary_output="带 block/material/phase tag 的体网格",
    ),
    "staging": PhaseVisualToken(
        key="staging",
        icon="◷",
        accent="#F59E0B",
        accent_soft="#FFF7E6",
        purpose="施工阶段、激活失活、荷载、水位、接触状态配置",
        primary_output="可编译的 PhaseActivationMatrix",
    ),
    "solve": PhaseVisualToken(
        key="solve",
        icon="⚙",
        accent="#D14343",
        accent_soft="#FFF0F0",
        purpose="检查、编译、Mohr-Coulomb Newton、固结和接触迭代",
        primary_output="分阶段求解记录和结果包",
    ),
    "results": PhaseVisualToken(
        key="results",
        icon="◇",
        accent="#00A3A3",
        accent_soft="#E7FAFA",
        purpose="位移、应力、孔压、塑性区、接触状态、报告与 VTK 导出",
        primary_output="可审查的后处理结果与工程报告",
    ),
}


def phase_visual_token(phase_key: str) -> PhaseVisualToken:
    return _PHASE_TOKENS.get(
        phase_key,
        PhaseVisualToken(
            key=phase_key,
            icon="•",
            accent="#56616F",
            accent_soft="#F3F5F7",
            purpose="阶段化模块计算",
            primary_output="阶段输出",
        ),
    )


def modern_phase_cards(active_phase: str = "geology") -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for phase in build_workbench_phases():
        token = phase_visual_token(phase.key)
        cards.append(
            {
                "key": phase.key,
                "order": phase.order,
                "label": phase.label,
                "active": phase.key == active_phase,
                "icon": token.icon,
                "accent": token.accent,
                "accent_soft": token.accent_soft,
                "purpose": token.purpose,
                "primary_output": token.primary_output,
                "tool_count": len(phase.toolbar.tools),
                "panel_count": len(phase.panels),
                "selection_filter": list(phase.allowed_selection_kinds),
            }
        )
    return cards


def build_next_optimization_roadmap() -> list[dict[str, str]]:
    return [
        {
            "milestone": "1.2.5",
            "theme": "桌面 GUI 体验硬化",
            "goal": "完成 PySide 与 PyVista 两条启动路径的现代化外观统一、快捷键、面板状态记忆和高 DPI 适配。",
            "acceptance": "启动后默认进入六阶段工作台；阶段卡片、Ribbon、左中右面板和状态栏一致；旧 GUI 只能显式启用。",
        },
        {
            "milestone": "1.2.6",
            "theme": "真实三维交互建模",
            "goal": "完善捕捉、工作平面、选择过滤、预览、撤销重做和属性联动，形成可用的 3D CAD/CAE 建模体验。",
            "acceptance": "用户可在视口中创建点线面体并完成语义/材料/阶段赋值，所有操作进入 CommandStack。",
        },
        {
            "milestone": "1.2.7",
            "theme": "Native Gmsh/OCC 闭环",
            "goal": "在安装 gmsh/meshio 环境时生成真实 OCC/Tet4 physical groups，并导回 GeoProjectDocument。",
            "acceptance": "Review Bundle 明确 native_backend=True，physical group 标签可用于材料、边界、阶段和结果映射。",
        },
        {
            "milestone": "1.2.8",
            "theme": "求解器可信度提升",
            "goal": "引入全局 Newton 收敛容差、切线刚度验证、塑性积分单元测试和基准算例容差报告。",
            "acceptance": "每个 benchmark 输出残差曲线、反力平衡、位移容差和 acceptance JSON。",
        },
        {
            "milestone": "1.3.0",
            "theme": "工程 Beta",
            "goal": "形成基坑/边坡/桩基三个模板工作流，完成报告模板、教程和桌面交互录制回归。",
            "acceptance": "三个模板均可从 GUI 完成建模、网格、阶段、求解、结果和报告导出。",
        },
    ]


def build_modern_phase_ui_contract(active_phase: str = "geology") -> dict[str, Any]:
    return {
        "contract": "modern_phase_workbench_ui_v1",
        "design_language": "dark-header light-canvas engineering-cards",
        "active_phase": active_phase,
        "phase_cards": modern_phase_cards(active_phase),
        "layout_regions": [
            {"key": "header", "label": "工程标题、版本、求解 readiness、旧 GUI 状态"},
            {"key": "phase_cards", "label": "六阶段横向卡片导航"},
            {"key": "contextual_ribbon", "label": "当前阶段专属工具组"},
            {"key": "left_browser", "label": "模型树/阶段树/结果树"},
            {"key": "viewport", "label": "3D 建模与结果查看区域"},
            {"key": "right_inspector", "label": "属性、材料、阶段、求解和结果检查器"},
            {"key": "bottom_console", "label": "日志、审查、求解和质量门控"},
        ],
        "quality_gates": [
            "旧版 flat GUI 不能作为默认入口",
            "每个阶段只显示当前阶段工具",
            "工具栏动作必须有 runtime/action route",
            "结果/求解状态必须在 UI 上显式标记为 preview/basic/native",
            "Gmsh/OCC fallback 必须在界面和报告中可见",
        ],
        "roadmap": build_next_optimization_roadmap(),
    }


def modern_phase_workbench_stylesheet() -> str:
    """Return a Qt stylesheet shared by the phase workbench shells."""

    return """
    QMainWindow, QWidget {
        background: #F5F7FB;
        color: #1F2937;
        font-family: "Inter", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
        font-size: 13px;
    }
    QFrame#modern-header {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #111827, stop:1 #243B53);
        border-radius: 18px;
        margin: 10px 12px 6px 12px;
        padding: 14px;
    }
    QLabel#modern-header-title {
        color: #FFFFFF;
        font-size: 22px;
        font-weight: 800;
    }
    QLabel#modern-header-subtitle {
        color: #C7D2FE;
        font-size: 12px;
    }
    QLabel#status-pill {
        background: rgba(255,255,255,0.16);
        color: #ECFDF5;
        border: 1px solid rgba(255,255,255,0.24);
        border-radius: 12px;
        padding: 6px 10px;
        font-weight: 650;
    }
    QFrame#phase-card-strip {
        background: transparent;
        margin: 0 12px 6px 12px;
    }
    QToolButton#phase-card {
        background: #FFFFFF;
        color: #243040;
        border: 1px solid #DDE4EE;
        border-radius: 16px;
        padding: 10px 12px;
        min-height: 64px;
        font-weight: 700;
        text-align: left;
    }
    QToolButton#phase-card:checked {
        background: #111827;
        color: #FFFFFF;
        border: 2px solid #60A5FA;
    }
    QToolButton#phase-card:hover {
        border: 1px solid #93C5FD;
        background: #F8FBFF;
    }
    QToolButton#phase-card:checked:hover {
        background: #111827;
    }
    QToolBar#phase-workbench-contextual-ribbon, QToolBar#phase-ribbon-toolbar {
        background: #FFFFFF;
        border: 1px solid #DDE4EE;
        border-radius: 16px;
        padding: 8px;
        spacing: 7px;
        margin: 0 12px 8px 12px;
    }
    QToolBar#project-quick-toolbar, QToolBar#phase-tabs-toolbar {
        background: #FFFFFF;
        border-bottom: 1px solid #E5EAF2;
        spacing: 6px;
    }
    QToolButton, QPushButton {
        background: #FFFFFF;
        border: 1px solid #D5DEE9;
        border-radius: 10px;
        padding: 7px 10px;
        font-weight: 650;
    }
    QToolButton:hover, QPushButton:hover {
        border-color: #60A5FA;
        background: #F0F7FF;
    }
    QToolButton:checked {
        background: #2563EB;
        color: white;
        border-color: #1D4ED8;
    }
    QFrame#panel-card, QTabWidget::pane, QTreeWidget, QTableWidget, QTextEdit, QPlainTextEdit {
        background: #FFFFFF;
        border: 1px solid #DDE4EE;
        border-radius: 14px;
    }
    QTreeWidget::item, QTableWidget::item {
        padding: 6px;
    }
    QHeaderView::section {
        background: #EEF2F8;
        color: #334155;
        border: none;
        padding: 7px;
        font-weight: 700;
    }
    QTabBar::tab {
        background: #EDF2F7;
        border: 1px solid #DDE4EE;
        padding: 8px 12px;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        margin-right: 4px;
        font-weight: 650;
    }
    QTabBar::tab:selected {
        background: #FFFFFF;
        color: #1D4ED8;
        border-bottom-color: #FFFFFF;
    }
    QLabel#phase-workbench-title {
        color: #111827;
        font-size: 18px;
        font-weight: 800;
    }
    QTextEdit#phase-workbench-3d-placeholder {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #EAF4FF);
        border: 1px dashed #93C5FD;
        border-radius: 18px;
        padding: 18px;
        color: #334155;
        font-size: 14px;
    }
    QStatusBar {
        background: #111827;
        color: #E5E7EB;
        font-weight: 600;
    }

/* 1.4.6 CAD workbench compact/dockable layout */
QToolBar#cad-top-navigation-toolbar {
    background: #0F172A;
    color: #E5E7EB;
    border: none;
    spacing: 6px;
    padding: 4px 8px;
}
QToolBar#cad-top-navigation-toolbar QToolButton {
    background: transparent;
    color: #E5E7EB;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 4px 8px;
    min-width: 64px;
}
QToolBar#cad-top-navigation-toolbar QToolButton:checked {
    background: #2563EB;
    color: #FFFFFF;
    border-color: #60A5FA;
}
QToolBar#phase-workbench-contextual-ribbon, QToolBar#phase-workbench-modeling-controls {
    background: #FFFFFF;
    border: 1px solid #DDE4EE;
    spacing: 6px;
    padding: 5px;
}
QDockWidget {
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
    font-weight: 700;
}
QDockWidget::title {
    background: #EAF0F8;
    color: #1F2937;
    padding: 5px 8px;
    border: 1px solid #DDE4EE;
}
QWidget#phase-workbench-3d-model-view {
    background: #0B1120;
    border: 1px solid #1E293B;
}
QLabel#ribbon-group-label {
    color: #1D4ED8;
    font-weight: 800;
    padding: 0 8px;
}
    """


__all__ = [
    "PhaseVisualToken",
    "build_modern_phase_ui_contract",
    "build_next_optimization_roadmap",
    "modern_phase_cards",
    "modern_phase_workbench_stylesheet",
    "phase_visual_token",
]
