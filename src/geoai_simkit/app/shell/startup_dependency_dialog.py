from __future__ import annotations

"""Startup dependency preflight dialog.

This module deliberately uses tkinter instead of PySide so it can display a
status window even when PySide6 itself is missing.  When every required
runtime dependency is available, the dialog closes automatically and the main
six-phase workbench launches.  When dependencies are missing, it lists exactly
which packages need installation and exits without falling into legacy GUI.
"""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.services.dependency_preflight import build_dependency_preflight_report, render_dependency_preflight_text


@dataclass(frozen=True, slots=True)
class StartupPreflightDecision:
    contract: str
    ok: bool
    user_continue: bool
    report: dict[str, Any]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": self.ok,
            "user_continue": self.user_continue,
            "report": self.report,
            "message": self.message,
        }


def build_startup_dependency_payload() -> dict[str, Any]:
    report = build_dependency_preflight_report().to_dict()
    return {
        "contract": "geoai_simkit_startup_dependency_screen_v1",
        "title": "GeoAI SimKit 启动依赖检查",
        "status": "passed" if report["ok"] else "blocked",
        "auto_enter_main": bool(report["ok"]),
        "main_workbench": "six_phase_workbench",
        "legacy_fallback": False,
        "report": report,
        "install_commands": list(report.get("install_commands", [])),
    }


def _run_console_preflight(payload: dict[str, Any]) -> StartupPreflightDecision:
    report = dict(payload.get("report", {}) or {})
    message = render_dependency_preflight_text(report)
    print(message)
    return StartupPreflightDecision(
        contract="geoai_simkit_startup_preflight_decision_v1",
        ok=bool(report.get("ok")),
        user_continue=bool(report.get("ok")),
        report=report,
        message="All required dependencies are installed." if report.get("ok") else "Required dependencies are missing.",
    )


def run_startup_dependency_dialog(*, show_success: bool = True, auto_close_ms: int = 900) -> StartupPreflightDecision:
    """Run the dependency preflight screen and return a launch decision.

    The dialog never imports PySide/PyVista.  In headless/no-tk environments it
    falls back to a console report and blocks launch when required deps are
    missing.
    """

    payload = build_startup_dependency_payload()
    report = dict(payload.get("report", {}) or {})
    if report.get("ok") and not show_success:
        return StartupPreflightDecision(
            contract="geoai_simkit_startup_preflight_decision_v1",
            ok=True,
            user_continue=True,
            report=report,
            message="All required dependencies are installed.",
        )
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return _run_console_preflight(payload)

    decision = {"continue": bool(report.get("ok"))}
    root = tk.Tk()
    root.title("GeoAI SimKit 启动依赖检查")
    root.geometry("880x620")
    root.minsize(780, 520)
    root.configure(bg="#0f172a")

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("Title.TLabel", background="#0f172a", foreground="#f8fafc", font=("Microsoft YaHei UI", 17, "bold"))
    style.configure("Sub.TLabel", background="#0f172a", foreground="#cbd5e1", font=("Microsoft YaHei UI", 10))
    style.configure("Card.TFrame", background="#111827", relief="flat")
    style.configure("Ok.TLabel", background="#111827", foreground="#22c55e", font=("Microsoft YaHei UI", 10, "bold"))
    style.configure("Bad.TLabel", background="#111827", foreground="#f97316", font=("Microsoft YaHei UI", 10, "bold"))
    style.configure("Info.TLabel", background="#111827", foreground="#e5e7eb", font=("Microsoft YaHei UI", 10))

    header = ttk.Frame(root, style="Card.TFrame", padding=(18, 16, 18, 10))
    header.pack(fill="x", padx=14, pady=(14, 8))
    ttk.Label(header, text="GeoAI SimKit 启动依赖检查", style="Title.TLabel").pack(anchor="w")
    subtitle = "全部必需依赖通过后自动进入六阶段主界面；否则列出需要补充安装的依赖。"
    ttk.Label(header, text=subtitle, style="Sub.TLabel").pack(anchor="w", pady=(4, 0))

    summary = ttk.Frame(root, style="Card.TFrame", padding=(18, 10, 18, 10))
    summary.pack(fill="x", padx=14, pady=8)
    required_text = f"必需依赖：{report.get('available_required_count')}/{report.get('required_count')} 已安装"
    status_text = "检查通过，即将进入六阶段主界面。" if report.get("ok") else "检查未通过，请先补充安装下列依赖。"
    ttk.Label(summary, text=required_text, style="Ok.TLabel" if report.get("ok") else "Bad.TLabel").pack(anchor="w")
    ttk.Label(summary, text=status_text, style="Info.TLabel").pack(anchor="w", pady=(4, 0))

    body = ttk.Frame(root, style="Card.TFrame", padding=(12, 10, 12, 10))
    body.pack(fill="both", expand=True, padx=14, pady=8)
    columns = ("status", "group", "dependency", "version", "purpose")
    tree = ttk.Treeview(body, columns=columns, show="headings", height=12)
    tree.heading("status", text="状态")
    tree.heading("group", text="模块")
    tree.heading("dependency", text="依赖")
    tree.heading("version", text="版本")
    tree.heading("purpose", text="用途")
    tree.column("status", width=74, anchor="center")
    tree.column("group", width=136)
    tree.column("dependency", width=150)
    tree.column("version", width=130)
    tree.column("purpose", width=330)
    tree.pack(fill="both", expand=True)
    for row in report.get("checks", []):
        status = "✅ 通过" if row.get("ok") else ("❌ 缺失" if row.get("required") else "⚠ 可选")
        version = row.get("installed_version") or "未安装"
        tree.insert("", "end", values=(status, row.get("group"), row.get("label"), version, row.get("purpose")))

    install_frame = ttk.Frame(root, style="Card.TFrame", padding=(12, 8, 12, 8))
    install_frame.pack(fill="x", padx=14, pady=8)
    commands = list(report.get("install_commands", []))
    problem_lines: list[str] = []
    for row in report.get("checks", []):
        if row.get("ok"):
            continue
        label = row.get("label") or row.get("key")
        error = row.get("error") or "not installed"
        module_file = row.get("module_file")
        problem_lines.append(f"{label}: {error}")
        if module_file:
            problem_lines.append(f"  imported from: {module_file}")
    if commands:
        install_text = "问题详情:\n" + "\n".join(problem_lines) + "\n\n安装建议:\n" + "\n".join(commands)
    else:
        install_text = "无需补充安装，正在进入主界面。"
    text = tk.Text(install_frame, height=4, bg="#020617", fg="#e5e7eb", insertbackground="#e5e7eb", relief="flat")
    text.insert("1.0", install_text)
    text.configure(state="disabled")
    text.pack(fill="x")

    button_frame = ttk.Frame(root, style="Card.TFrame", padding=(12, 4, 12, 10))
    button_frame.pack(fill="x", padx=14, pady=(0, 14))

    def copy_install_command() -> None:
        try:
            root.clipboard_clear()
            root.clipboard_append(install_text)
        except Exception:
            pass

    def close_dialog() -> None:
        decision["continue"] = False
        root.destroy()

    def enter_main() -> None:
        decision["continue"] = True
        root.destroy()

    copy_button = ttk.Button(button_frame, text="复制安装命令", command=copy_install_command)
    copy_button.pack(side="left")
    if report.get("ok"):
        enter_button = ttk.Button(button_frame, text="立即进入主界面", command=enter_main)
        enter_button.pack(side="right")
        root.after(max(250, int(auto_close_ms)), enter_main)
    else:
        close_button = ttk.Button(button_frame, text="关闭，安装依赖后重新启动", command=close_dialog)
        close_button.pack(side="right")

    root.mainloop()
    return StartupPreflightDecision(
        contract="geoai_simkit_startup_preflight_decision_v1",
        ok=bool(report.get("ok")),
        user_continue=bool(decision.get("continue") and report.get("ok")),
        report=report,
        message="All required dependencies are installed." if report.get("ok") else "Required dependencies are missing.",
    )


__all__ = [
    "StartupPreflightDecision",
    "build_startup_dependency_payload",
    "run_startup_dependency_dialog",
]
