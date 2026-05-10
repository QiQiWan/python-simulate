from __future__ import annotations

"""Minimal cross-platform fallback GUI used when PySide/PyVista is unavailable."""

import json
import webbrowser
from pathlib import Path
from typing import Any

from geoai_simkit.app.shell.unified_workbench_window import UnifiedWorkbenchController


def build_fallback_payload() -> dict[str, Any]:
    controller = UnifiedWorkbenchController()
    payload = controller.refresh_payload()
    benchmark = payload.get('benchmark_panel', {}) if isinstance(payload, dict) else {}
    return {
        'title': 'GeoAI SimKit fallback workbench',
        'message': 'PySide6 desktop widgets are unavailable, so a lightweight fallback UI is running.',
        'case': dict(payload.get('header', {}) or {}),
        'workspace': dict(payload.get('workspace', {}) or {}),
        'benchmark_panel': benchmark,
        'visual_modeling': payload.get('visual_modeling', {}) if isinstance(payload, dict) else {},
        'pages': payload.get('pages', {}) if isinstance(payload, dict) else {},
    }


def launch_tk_fallback_workbench(error_message: str = '') -> None:
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception:
        payload = build_fallback_payload()
        print('GeoAI SimKit fallback workbench')
        if error_message:
            print(error_message)
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return

    payload = build_fallback_payload()
    root = tk.Tk()
    root.title('GeoAI SimKit — Fallback Workbench')
    root.geometry('980x680')
    frame = ttk.Frame(root, padding=12)
    frame.pack(fill='both', expand=True)
    title = ttk.Label(frame, text='GeoAI SimKit Fallback Workbench', font=('Arial', 16, 'bold'))
    title.pack(anchor='w')
    msg = 'Desktop Qt/PyVista stack is incomplete. The project model and benchmark reports can still be inspected.'
    if error_message:
        msg += '\n' + error_message
    ttk.Label(frame, text=msg, wraplength=920).pack(anchor='w', pady=(6, 10))
    nb = ttk.Notebook(frame)
    nb.pack(fill='both', expand=True)

    def add_text_tab(name: str, data: object) -> None:
        page = ttk.Frame(nb)
        text = tk.Text(page, wrap='word')
        text.insert('1.0', json.dumps(data, indent=2, ensure_ascii=False, default=str))
        text.configure(state='disabled')
        text.pack(fill='both', expand=True)
        nb.add(page, text=name)

    add_text_tab('Project', payload.get('case', {}))
    add_text_tab('Workspace', payload.get('workspace', {}))
    add_text_tab('Modeling', payload.get('visual_modeling', {}))
    add_text_tab('Pages', payload.get('pages', {}))
    add_text_tab('Benchmark', payload.get('benchmark_panel', {}))

    buttons = ttk.Frame(frame)
    buttons.pack(fill='x', pady=(8, 0))

    def open_benchmark_folder() -> None:
        bench = payload.get('benchmark_panel', {}) or {}
        folder = Path(str(bench.get('report_dir') or 'benchmark_reports')).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        webbrowser.open(folder.as_uri())

    def show_help() -> None:
        messagebox.showinfo('GeoAI SimKit', 'Install PySide6 for the full desktop UI. PyVista/pyvistaqt are optional for the embedded 3D viewport.')

    ttk.Button(buttons, text='Open benchmark folder', command=open_benchmark_folder).pack(side='left')
    ttk.Button(buttons, text='Help', command=show_help).pack(side='left', padx=8)
    ttk.Button(buttons, text='Close', command=root.destroy).pack(side='right')
    root.mainloop()
