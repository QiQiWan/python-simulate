from __future__ import annotations

from pathlib import Path
import os
import time
import traceback
from typing import Any

from geoai_simkit.app.validation import validate_model
from geoai_simkit.app.presolve import analyze_presolve_state, ensure_default_global_bcs, ProgressEtaEstimator, format_seconds
from geoai_simkit.app.mesh_check import analyze_mesh, MeshCheckReport
from geoai_simkit.app.ifc_suggestions import apply_suggestion_subset, apply_suggestions, build_suggestions
from geoai_simkit.app.i18n import translate_text
from geoai_simkit.validation_rules import (
    ParameterIssue,
    validate_bc_inputs,
    validate_geometry_params,
    validate_ifc_options,
    validate_load_inputs,
    validate_material_parameters,
    validate_solver_settings,
    validate_stage_inputs,
)
from geoai_simkit.core.model import (
    AnalysisStage,
    BoundaryCondition,
    GeometryObjectRecord,
    LoadDefinition,
    MaterialDefinition,
    SimulationModel,
)
from geoai_simkit.geometry.ifc_import import IfcImportOptions, IfcImporter
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.geometry.voxelize import VoxelMesher, VoxelizeOptions
from geoai_simkit.geometry.gmsh_mesher import GmshMesher, GmshMesherOptions
from geoai_simkit.materials import registry
from geoai_simkit.post.exporters import ExportManager
from geoai_simkit.post.viewer import PreviewBuilder
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.compute_preferences import BackendComputePreferences, recommended_compute_preferences
from geoai_simkit.solver.gpu_runtime import describe_cuda_hardware, detect_cuda_devices
from geoai_simkit.solver.linear_algebra import default_thread_count
from geoai_simkit.solver.warp_backend import WarpBackend
from geoai_simkit.utils import optional_import


MATERIAL_SPECS: dict[str, list[tuple[str, float]]] = {
    'linear_elastic': [('E', 3.0e7), ('nu', 0.30), ('rho', 1800.0)],
    'mohr_coulomb': [('E', 3.0e7), ('nu', 0.30), ('cohesion', 15000.0), ('friction_deg', 28.0), ('dilation_deg', 0.0), ('tensile_strength', 0.0), ('rho', 1800.0)],
    'hss': [('E50ref', 2.0e7), ('Eoedref', 1.5e7), ('Eurref', 6.0e7), ('nu_ur', 0.2), ('pref', 100000.0), ('m', 0.5), ('c', 10000.0), ('phi_deg', 28.0), ('psi_deg', 0.0), ('G0ref', 8.0e7), ('gamma07', 1.0e-4), ('Rf', 0.9), ('rho', 1800.0)],
    'hs_small': [('E50ref', 2.0e7), ('Eoedref', 1.5e7), ('Eurref', 6.0e7), ('nu_ur', 0.2), ('pref', 100000.0), ('m', 0.5), ('c', 10000.0), ('phi_deg', 28.0), ('psi_deg', 0.0), ('G0ref', 8.0e7), ('gamma07', 1.0e-4), ('Rf', 0.9), ('rho', 1800.0)],
}
STEP_NAMES = ['1 项目', '2 几何 / IFC', '3 区域 / 材料', '4 Stage / 工况', '5 求解 / 结果']
STEP_KEYS = ['项目', '几何', '区域/材料', '边界/阶段', '求解/结果']

class UIStyle:
    INVALID_STYLE = "QWidget { border: 1px solid #d9534f; background-color: rgba(217,83,79,0.10); border-radius: 6px; }"
    VALID_STYLE = ""
    WARNING_STYLE = "QWidget { border: 1px solid #f0ad4e; background-color: rgba(240,173,78,0.08); border-radius: 6px; }"

    @staticmethod
    def modern_stylesheet() -> str:
        return """
        QMainWindow { background: #f6f7fb; }
        QToolBar { spacing: 6px; padding: 6px; border-bottom: 1px solid #d9dee7; background: #ffffff; }
        QGroupBox { font-weight: 600; border: 1px solid #d9dee7; border-radius: 10px; margin-top: 10px; padding-top: 10px; background: #ffffff; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #1f2937; }
        QPushButton { background: #ffffff; border: 1px solid #cfd6e3; border-radius: 8px; padding: 6px 12px; }
        QPushButton:hover { background: #eef4ff; border-color: #8fb4ff; }
        QPushButton:pressed { background: #dbe8ff; }
        QPushButton:disabled { color: #9aa4b2; background: #f2f4f7; }
        QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QListWidget, QTreeWidget, QTableWidget, QTabWidget::pane { background: #ffffff; border: 1px solid #d9dee7; border-radius: 8px; }
        QTabBar::tab { background: #eef2f7; border: 1px solid #d9dee7; border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; padding: 6px 10px; margin-right: 4px; }
        QTabBar::tab:selected { background: #ffffff; color: #0f172a; }
        QProgressBar { border: 1px solid #d9dee7; border-radius: 7px; background: #eef2f7; text-align: center; }
        QProgressBar::chunk { background: #4f8cff; border-radius: 7px; }
        QListWidget#gpuDeviceList::item:selected { background: #dbeafe; color: #0f172a; border-radius: 6px; }
        """


INVALID_STYLE = UIStyle.INVALID_STYLE
VALID_STYLE = UIStyle.VALID_STYLE
WARNING_STYLE = UIStyle.WARNING_STYLE


def resolve_app_icon() -> Path:
    return Path(__file__).resolve().parents[1] / 'assets' / 'geoai_simkit.ico'

def _set_table_item(table, row: int, col: int, value: str, editable: bool = False):
    item = table.item(row, col)
    if item is None:
        item = table.widget().QTableWidgetItem(value) if hasattr(table, 'widget') else None
    

def _stringify(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ', '.join(_stringify(v) for v in value)
    if isinstance(value, dict):
        return ', '.join(f'{k}={_stringify(v)}' for k, v in value.items())
    return str(value)


def _parse_components(text: str) -> tuple[int, ...]:
    out: list[int] = []
    for token in text.replace(';', ',').split(','):
        token = token.strip()
        if token:
            out.append(int(token))
    return tuple(out) if out else (0, 1, 2)


def _parse_values(text: str, fallback_len: int = 3) -> tuple[float, ...]:
    out: list[float] = []
    for token in text.replace(';', ',').split(','):
        token = token.strip()
        if token:
            out.append(float(token))
    if out:
        return tuple(out)
    return tuple(0.0 for _ in range(fallback_len))


TYPE_COLOR_MAP = {
    'IfcWall': '#5c6f82', 'IfcSlab': '#c28743', 'IfcBeam': '#8b6f3a', 'IfcColumn': '#6c7a89', 'IfcBuildingElementProxy': '#c95f5f',
    'soil': '#b9965b', 'wall': '#5c6f82', 'support': '#6b8e23', 'beam': '#8b6f3a', 'column': '#6c7a89', 'slab': '#c28743', 'boundary': '#7b68ee', 'opening': '#e67e22',
}


def _color_for_type(role: str | None, ifc_type: str | None) -> str:
    for key in (role, ifc_type):
        if key and key in TYPE_COLOR_MAP:
            return TYPE_COLOR_MAP[key]
    return '#90a4ae'


def _set_qtable_row(QtWidgets, table, row: int, values: list[str]) -> None:
    table.insertRow(row)
    for col, value in enumerate(values):
        table.setItem(row, col, QtWidgets.QTableWidgetItem(value))


def launch_main_window() -> None:
    QtWidgets = optional_import('PySide6.QtWidgets')
    QtCore = optional_import('PySide6.QtCore')
    QtGui = optional_import('PySide6.QtGui')
    QtInteractor = optional_import('pyvistaqt').QtInteractor

    class _LogicalPage(QtWidgets.QWidget):
        page_name = 'page'

        def __init__(self, owner, builder) -> None:
            super().__init__()
            self.owner = owner
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(builder())

    class ProjectPage(_LogicalPage):
        page_name = 'project'

        def __init__(self, owner) -> None:
            super().__init__(owner, owner._build_project_page)

    class GeometryPage(_LogicalPage):
        page_name = 'geometry'

        def __init__(self, owner) -> None:
            super().__init__(owner, owner._build_geometry_page)

    class MaterialPage(_LogicalPage):
        page_name = 'material'

        def __init__(self, owner) -> None:
            super().__init__(owner, owner._build_material_page)

    class StagePage(_LogicalPage):
        page_name = 'stage'

        def __init__(self, owner) -> None:
            super().__init__(owner, owner._build_stage_page)

    class ResultsPage(_LogicalPage):
        page_name = 'results'

        def __init__(self, owner) -> None:
            super().__init__(owner, owner._build_results_page)

    class SolverWorker(QtCore.QObject):
        progress = QtCore.Signal(object)
        finished = QtCore.Signal(object, bool)
        failed = QtCore.Signal(str)

        def __init__(self, backend: WarpBackend, model: SimulationModel, settings: SolverSettings) -> None:
            super().__init__()
            self.backend = backend
            self.model = model
            self.settings = settings
            self._cancel = False

        @QtCore.Slot()
        def run(self) -> None:
            try:
                self.progress.emit({'phase': 'worker-start', 'message': 'Worker thread entered solve()'})
                solved = self.backend.solve(
                    self.model,
                    self.settings,
                    progress_callback=self._on_progress,
                    cancel_check=lambda: self._cancel,
                )
                self.finished.emit(solved, self._cancel)
            except Exception:
                self.failed.emit(traceback.format_exc())

        def cancel(self) -> None:
            self._cancel = True

        def _on_progress(self, payload: object) -> None:
            self.progress.emit(payload)

    class MeshingWorker(QtCore.QObject):
        progress = QtCore.Signal(object)
        finished = QtCore.Signal(object, str)
        failed = QtCore.Signal(str)

        def __init__(self, model: SimulationModel, method: str, element_size: float, padding: float) -> None:
            super().__init__()
            self.model = model
            self.method = method
            self.element_size = float(element_size)
            self.padding = float(padding)

        @QtCore.Slot()
        def run(self) -> None:
            try:
                self.progress.emit({'phase': 'prepare', 'value': 5, 'message': 'Preparing meshing job', 'log': True})
                model = self.model

                def _forward(payload: object) -> None:
                    if isinstance(payload, dict):
                        self.progress.emit(payload)

                if self.method == 'gmsh_tet':
                    self.progress.emit({'phase': 'gmsh-start', 'value': 12, 'message': 'Launching local gmsh mesher', 'log': True})
                    try:
                        model = GmshMesher(
                            GmshMesherOptions(element_size=self.element_size),
                            progress_callback=_forward,
                        ).mesh_model(model)
                    except Exception as exc:
                        self.progress.emit({
                            'phase': 'gmsh-fallback',
                            'value': 18,
                            'message': f'Gmsh failed and will fall back to voxelization: {exc}',
                            'severity': 'warning',
                            'hint': 'Inspect the gmsh diagnostics and consider fixing non-closed solids later.',
                            'log': True,
                        })
                        model = VoxelMesher(
                            VoxelizeOptions(cell_size=self.element_size, padding=self.padding),
                            progress_callback=_forward,
                        ).voxelize_model(model)
                        self.method = 'voxel_hex8'
                else:
                    self.progress.emit({'phase': 'voxelize-start', 'value': 12, 'message': 'Voxelizing model', 'log': True})
                    model = VoxelMesher(
                        VoxelizeOptions(cell_size=self.element_size, padding=self.padding),
                        progress_callback=_forward,
                    ).voxelize_model(model)
                model.ensure_regions()
                self.progress.emit({'phase': 'finalize', 'value': 95, 'message': 'Finalizing mesh data', 'log': True})
                self.finished.emit(model, self.method)
            except Exception:
                self.failed.emit(traceback.format_exc())

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle('geoai-simkit')
            self._apply_window_icon()
            self.resize(1512, 944)
            self.current_model: SimulationModel | None = None
            self.export_manager = ExportManager()
            self.preview_builder = PreviewBuilder()
            self.solver = WarpBackend()
            self._solver_thread = None
            self._solver_worker = None
            self._param_inputs: dict[str, object] = {}
            self._material_param_inputs: dict[str, object] = {}
            self._selected_object_key: str | None = None
            self._task_row = None
            self._loading_stage_editor = False
            self._loading_material_editor = False
            self._viewer_actor_map: dict[str, dict[str, str]] = {}
            self._eta_estimator: ProgressEtaEstimator | None = None
            self._refresh_form_validation()
            self._highlight_regions: list[str] = []
            self._highlight_blocks: list[str] = []
            self._last_mesh_report = None
            self._validation_labels: dict[str, object] = {}
            self._latest_suggestions = []
            self._rejected_suggestion_keys: set[str] = set()
            self._lang = 'en'
            self._inspector_pinned = False
            self._last_selection_payload: tuple[str, str] | None = None
            self._solver_progress_dialog = None
            self._solver_heartbeat_timer = None
            self._heartbeat_counter = 0
            self._last_solver_payload: dict[str, object] | None = None
            self._last_solver_fraction = 0.0
            self._meshing_thread = None
            self._meshing_worker = None
            self._meshing_progress_dialog = None
            self._meshing_heartbeat_timer = None
            self._meshing_started_at = None
            self._last_meshing_payload: dict[str, object] | None = None
            self._inspector_dismissed = False
            self._flash_timer = QtCore.QTimer(self)
            self._flash_timer.setInterval(180)
            self._flash_timer.timeout.connect(self._on_flash_tick)
            self._flash_payload = None

            self._build_ui()
            self._apply_modern_ui_style()
            self._apply_action_icons()
            self._apply_screen_adaptive_layout()
            self._configure_default_compute_preferences()
            QtWidgets.QApplication.instance().installEventFilter(self)
            self._populate_material_model_combo()
            self._rebuild_material_param_form()
            self._update_validation()
            self._refresh_form_validation()


        def _apply_modern_ui_style(self) -> None:
            try:
                self.setStyleSheet(UIStyle.modern_stylesheet())
            except Exception:
                pass

        def _standard_icon(self, pixmap_name: str):
            try:
                return self.style().standardIcon(getattr(QtWidgets.QStyle.StandardPixmap, pixmap_name))
            except Exception:
                return QtGui.QIcon()

        def _apply_action_icons(self) -> None:
            icon_map = {
                'act_new_demo': 'SP_FileDialogNewFolder',
                'act_import_ifc': 'SP_DialogOpenButton',
                'act_run': 'SP_MediaPlay',
                'act_cancel': 'SP_BrowserStop',
                'act_export': 'SP_DialogSaveButton',
                'act_export_bundle': 'SP_DriveFDIcon',
                'act_hide_selected': 'SP_TitleBarShadeButton',
                'act_show_all_objects': 'SP_DialogResetButton',
                'act_clear_selection': 'SP_DialogDiscardButton',
                'act_toggle_inspector': 'SP_FileDialogDetailedView',
            }
            for name, pix in icon_map.items():
                obj = getattr(self, name, None)
                if obj is not None:
                    try:
                        obj.setIcon(self._standard_icon(pix))
                    except Exception:
                        pass
            for btn_name, pix in {
                'btn_run_solver': 'SP_MediaPlay',
                'btn_cancel_solver': 'SP_BrowserStop',
                'btn_solver_profile_auto': 'SP_BrowserReload',
                'btn_solver_profile_cpu': 'SP_ComputerIcon',
                'btn_solver_profile_gpu': 'SP_DriveHDIcon',
            }.items():
                btn = getattr(self, btn_name, None)
                if btn is not None:
                    try:
                        btn.setIcon(self._standard_icon(pix))
                    except Exception:
                        pass

        def _apply_window_icon(self) -> None:
            try:
                icon = QtGui.QIcon(str(resolve_app_icon()))
                if not icon.isNull():
                    self.setWindowIcon(icon)
            except Exception:
                pass

        def _detect_cuda_available(self) -> bool:
            return bool(detect_cuda_devices())

        def _detected_cuda_devices(self):
            try:
                return detect_cuda_devices()
            except Exception:
                return []

        def _selected_gpu_aliases(self) -> list[str]:
            if not hasattr(self, 'solver_gpu_list'):
                return []
            vals: list[str] = []
            for item in self.solver_gpu_list.selectedItems():
                alias = str(item.data(QtCore.Qt.ItemDataRole.UserRole) or '').strip()
                if alias:
                    vals.append(alias)
            return vals

        def _populate_gpu_device_list(self, selected_aliases: list[str] | tuple[str, ...] | None = None) -> None:
            if not hasattr(self, 'solver_gpu_list'):
                return
            selected = {str(v).lower() for v in (selected_aliases or []) if str(v).strip()}
            devices = self._detected_cuda_devices()
            self.solver_gpu_list.blockSignals(True)
            self.solver_gpu_list.clear()
            for dev in devices:
                item = QtWidgets.QListWidgetItem(f"{dev.alias}  |  {dev.name}  |  {dev.memory_gib:.1f} GiB")
                item.setData(QtCore.Qt.ItemDataRole.UserRole, dev.alias)
                item.setToolTip(self._tt(f'Select / highlight {dev.alias} to include it in GPU scheduling.'))
                self.solver_gpu_list.addItem(item)
                if not selected or dev.alias.lower() in selected:
                    item.setSelected(True)
            self.solver_gpu_list.blockSignals(False)
            if hasattr(self, 'solver_gpu_hint_label'):
                count = max(0, self.solver_gpu_list.count())
                self.solver_gpu_hint_label.setText(self._tt(f'Detected GPUs: {count}. Highlight one or more devices to constrain scheduling.'))

        def _populate_solver_compute_device_options(self) -> None:
            devices = self._detected_cuda_devices()
            values = ['auto-best', 'auto-round-robin', 'cpu']
            if devices:
                values.extend([dev.alias for dev in devices])
            elif getattr(self, '_cuda_available', False):
                values.append('cuda:0')
            if hasattr(self, 'solver_compute_device_combo'):
                current = self.solver_compute_device_combo.currentText() or 'auto-best'
                self.solver_compute_device_combo.blockSignals(True)
                self.solver_compute_device_combo.clear()
                self.solver_compute_device_combo.addItems(values)
                idx = self.solver_compute_device_combo.findText(current)
                self.solver_compute_device_combo.setCurrentIndex(idx if idx >= 0 else 0)
                self.solver_compute_device_combo.blockSignals(False)
            if hasattr(self, 'solver_device_combo'):
                current = self.solver_device_combo.currentText() or 'auto-best'
                self.solver_device_combo.blockSignals(True)
                self.solver_device_combo.clear()
                self.solver_device_combo.addItems(values)
                idx = self.solver_device_combo.findText(current)
                self.solver_device_combo.setCurrentIndex(idx if idx >= 0 else 0)
                self.solver_device_combo.blockSignals(False)

        def _configure_default_compute_preferences(self) -> None:
            total = max(1, int(os.cpu_count() or 1))
            half = default_thread_count()
            self._cpu_core_total = total
            self._default_thread_count = half
            self._cuda_available = self._detect_cuda_available()
            self._cuda_devices = self._detected_cuda_devices()
            self._populate_solver_compute_device_options()
            self._populate_gpu_device_list()
            if hasattr(self, 'solver_threads_spin'):
                self.solver_threads_spin.setRange(0, max(8, total))
                self.solver_threads_spin.setValue(half)
                self.solver_threads_spin.setToolTip(self._tt(f'0 means auto. Default suggestion uses nearly all available CPU cores while leaving one core free ({half}/{total}).'))
            if hasattr(self, 'solver_device_combo'):
                self.solver_device_combo.setCurrentText('auto-best' if self._cuda_available else 'cpu')
                self.solver_device_combo.setToolTip(self._tt('Auto-best chooses the strongest detected CUDA device. Auto-round-robin cycles across GPUs on multi-card machines.'))
            if hasattr(self, 'solver_compute_threads_spin'):
                self.solver_compute_threads_spin.setRange(0, max(8, total))
            prefs = recommended_compute_preferences('gpu-throughput' if self._cuda_available else 'cpu-safe', cuda_available=self._cuda_available, cpu_total=total)
            self._apply_compute_preferences_to_controls(prefs, update_summary=False)
            self._update_solver_compute_summary()

        def _read_solver_compute_preferences(self) -> BackendComputePreferences:
            device = self.solver_compute_device_combo.currentText() if hasattr(self, 'solver_compute_device_combo') else (self.solver_device_combo.currentText() if hasattr(self, 'solver_device_combo') else 'auto-best')
            threads = int(self.solver_compute_threads_spin.value()) if hasattr(self, 'solver_compute_threads_spin') else (int(self.solver_threads_spin.value()) if hasattr(self, 'solver_threads_spin') else 0)
            ordering = self.solver_compute_ordering_combo.currentText() if hasattr(self, 'solver_compute_ordering_combo') else 'auto'
            preconditioner = self.solver_compute_preconditioner_combo.currentText() if hasattr(self, 'solver_compute_preconditioner_combo') else 'auto'
            solver_strategy = self.solver_compute_strategy_combo.currentText() if hasattr(self, 'solver_compute_strategy_combo') else 'auto'
            warp_preconditioner = self.solver_compute_warp_preconditioner_combo.currentText() if hasattr(self, 'solver_compute_warp_preconditioner_combo') else 'diag'
            multi_gpu_mode = self.solver_compute_multi_gpu_combo.currentText() if hasattr(self, 'solver_compute_multi_gpu_combo') else 'single'
            profile = self.solver_compute_profile_combo.currentText() if hasattr(self, 'solver_compute_profile_combo') else 'manual'
            tol_text = self.solver_compute_iter_tol_edit.text().strip() if hasattr(self, 'solver_compute_iter_tol_edit') else '1e-10'
            maxiter = int(self.solver_compute_iter_max_spin.value()) if hasattr(self, 'solver_compute_iter_max_spin') else 2000
            try:
                iter_tol = float(tol_text)
            except Exception:
                iter_tol = 1.0e-10
            return BackendComputePreferences(
                backend='warp',
                profile=profile,
                device=device,
                thread_count=threads,
                require_warp=bool(self.solver_compute_require_warp_check.isChecked()) if hasattr(self, 'solver_compute_require_warp_check') else False,
                warp_hex8_enabled=bool(self.solver_compute_hex8_check.isChecked()) if hasattr(self, 'solver_compute_hex8_check') else True,
                warp_nonlinear_enabled=bool(self.solver_compute_nonlinear_check.isChecked()) if hasattr(self, 'solver_compute_nonlinear_check') else True,
                warp_full_gpu_linear_solve=bool(self.solver_compute_full_gpu_check.isChecked()) if hasattr(self, 'solver_compute_full_gpu_check') else False,
                warp_gpu_global_assembly=bool(self.solver_compute_gpu_assembly_check.isChecked()) if hasattr(self, 'solver_compute_gpu_assembly_check') else False,
                warp_interface_enabled=bool(self.solver_compute_interface_check.isChecked()) if hasattr(self, 'solver_compute_interface_check') else True,
                warp_structural_enabled=bool(self.solver_compute_structural_check.isChecked()) if hasattr(self, 'solver_compute_structural_check') else True,
                warp_unified_block_merge=bool(self.solver_compute_block_merge_check.isChecked()) if hasattr(self, 'solver_compute_block_merge_check') else True,
                stage_state_sync=bool(self.solver_compute_stage_sync_check.isChecked()) if hasattr(self, 'solver_compute_stage_sync_check') else True,
                ordering=ordering,
                preconditioner=preconditioner,
                solver_strategy=solver_strategy,
                warp_preconditioner=warp_preconditioner,
                multi_gpu_mode=multi_gpu_mode,
                iterative_tolerance=iter_tol,
                iterative_maxiter=maxiter,
                block_size=3,
                selected_gpu_aliases=tuple(self._selected_gpu_aliases()),
            )

        def _apply_compute_preferences_to_controls(self, prefs: BackendComputePreferences, *, update_summary: bool = True) -> None:
            self._updating_compute_controls = True
            try:
                if hasattr(self, 'solver_compute_profile_combo'):
                    idx = self.solver_compute_profile_combo.findText(prefs.profile)
                    if idx >= 0:
                        self.solver_compute_profile_combo.setCurrentIndex(idx)
                if hasattr(self, 'solver_compute_device_combo'):
                    idx = self.solver_compute_device_combo.findText(prefs.device)
                    if idx >= 0:
                        self.solver_compute_device_combo.setCurrentIndex(idx)
                if hasattr(self, 'solver_compute_threads_spin'):
                    self.solver_compute_threads_spin.setValue(int(prefs.thread_count))
                if hasattr(self, 'solver_compute_multi_gpu_combo'):
                    idx = self.solver_compute_multi_gpu_combo.findText(getattr(prefs, 'multi_gpu_mode', 'single'))
                    if idx >= 0:
                        self.solver_compute_multi_gpu_combo.setCurrentIndex(idx)
                self._populate_gpu_device_list(getattr(prefs, 'selected_gpu_aliases', ()))
                if hasattr(self, 'solver_compute_require_warp_check'):
                    self.solver_compute_require_warp_check.setChecked(bool(prefs.require_warp))
                if hasattr(self, 'solver_compute_hex8_check'):
                    self.solver_compute_hex8_check.setChecked(bool(prefs.warp_hex8_enabled))
                if hasattr(self, 'solver_compute_nonlinear_check'):
                    self.solver_compute_nonlinear_check.setChecked(bool(prefs.warp_nonlinear_enabled))
                if hasattr(self, 'solver_compute_full_gpu_check'):
                    self.solver_compute_full_gpu_check.setChecked(bool(prefs.warp_full_gpu_linear_solve))
                if hasattr(self, 'solver_compute_gpu_assembly_check'):
                    self.solver_compute_gpu_assembly_check.setChecked(bool(prefs.warp_gpu_global_assembly))
                if hasattr(self, 'solver_compute_interface_check'):
                    self.solver_compute_interface_check.setChecked(bool(prefs.warp_interface_enabled))
                if hasattr(self, 'solver_compute_structural_check'):
                    self.solver_compute_structural_check.setChecked(bool(prefs.warp_structural_enabled))
                if hasattr(self, 'solver_compute_block_merge_check'):
                    self.solver_compute_block_merge_check.setChecked(bool(prefs.warp_unified_block_merge))
                if hasattr(self, 'solver_compute_stage_sync_check'):
                    self.solver_compute_stage_sync_check.setChecked(bool(getattr(prefs, 'stage_state_sync', True)))
                if hasattr(self, 'solver_compute_ordering_combo'):
                    idx = self.solver_compute_ordering_combo.findText(prefs.ordering)
                    if idx >= 0:
                        self.solver_compute_ordering_combo.setCurrentIndex(idx)
                if hasattr(self, 'solver_compute_preconditioner_combo'):
                    idx = self.solver_compute_preconditioner_combo.findText(prefs.preconditioner)
                    if idx >= 0:
                        self.solver_compute_preconditioner_combo.setCurrentIndex(idx)
                if hasattr(self, 'solver_compute_strategy_combo'):
                    idx = self.solver_compute_strategy_combo.findText(prefs.solver_strategy)
                    if idx >= 0:
                        self.solver_compute_strategy_combo.setCurrentIndex(idx)
                if hasattr(self, 'solver_compute_warp_preconditioner_combo'):
                    idx = self.solver_compute_warp_preconditioner_combo.findText(prefs.warp_preconditioner)
                    if idx >= 0:
                        self.solver_compute_warp_preconditioner_combo.setCurrentIndex(idx)
                if hasattr(self, 'solver_compute_iter_tol_edit'):
                    self.solver_compute_iter_tol_edit.setText(f'{float(prefs.iterative_tolerance):.1e}')
                if hasattr(self, 'solver_compute_iter_max_spin'):
                    self.solver_compute_iter_max_spin.setValue(int(prefs.iterative_maxiter))
                if hasattr(self, 'solver_device_combo'):
                    idx = self.solver_device_combo.findText(prefs.device)
                    if idx >= 0:
                        self.solver_device_combo.setCurrentIndex(idx)
                if hasattr(self, 'solver_threads_spin'):
                    self.solver_threads_spin.setValue(int(prefs.thread_count))
            finally:
                self._updating_compute_controls = False
            if update_summary:
                self._update_solver_compute_summary()

        def _apply_solver_compute_profile(self, profile: str) -> None:
            prefs = recommended_compute_preferences(profile, cuda_available=getattr(self, '_cuda_available', False), cpu_total=getattr(self, '_cpu_core_total', max(1, int(os.cpu_count() or 1))))
            self._apply_compute_preferences_to_controls(prefs)

        def _on_solver_compute_profile_changed(self, profile: str) -> None:
            if getattr(self, '_updating_compute_controls', False):
                return
            self._apply_solver_compute_profile(profile)

        def _update_solver_compute_summary(self, *_args) -> None:
            prefs = self._read_solver_compute_preferences()
            cpu_total = getattr(self, '_cpu_core_total', max(1, int(os.cpu_count() or 1)))
            summary = prefs.summary(cpu_total=cpu_total, cuda_available=getattr(self, '_cuda_available', False))
            hw = f"Detected CPU cores: {cpu_total} | {describe_cuda_hardware(self._selected_gpu_aliases())}"
            if hasattr(self, 'solver_compute_summary_label'):
                self.solver_compute_summary_label.setText(self._tt(summary))
            if hasattr(self, 'solver_compute_hardware_label'):
                self.solver_compute_hardware_label.setText(self._tt(hw))

        def _apply_screen_adaptive_layout(self) -> None:
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen is None:
                return
            geom = screen.availableGeometry()
            sw, sh = max(1200, geom.width()), max(800, geom.height())
            target_w = min(max(int(sw * 0.92), 1260), 1800)
            target_h = min(max(int(sh * 0.90), 820), 1200)
            self.resize(target_w, target_h)
            self.setMinimumSize(1180, 760)
            compact = sw < 1600 or sh < 950
            if hasattr(self, 'page_stack'):
                self.page_stack.setMinimumWidth(380 if compact else 440)
            if hasattr(self, 'main_splitter'):
                left = int(target_w * (0.64 if compact else 0.67))
                right = target_w - left
                self.main_splitter.setSizes([left, right])
                self.main_splitter.setChildrenCollapsible(False)
            if hasattr(self, 'center_splitter'):
                top = int(target_h * (0.66 if compact else 0.70))
                bottom = target_h - top
                self.center_splitter.setSizes([top, bottom])
                self.center_splitter.setChildrenCollapsible(False)
            if hasattr(self, 'progress_overall'):
                self.progress_overall.setFixedWidth(150 if compact else 180)
            if hasattr(self, 'progress_iter'):
                self.progress_iter.setFixedWidth(130 if compact else 160)
            if hasattr(self, 'inspector_dock'):
                self.inspector_dock.setMinimumWidth(300 if compact else 340)

        def _widget_is_inside(self, widget, container) -> bool:
            while widget is not None:
                if widget is container:
                    return True
                widget = widget.parentWidget() if hasattr(widget, 'parentWidget') else None
            return False

        def eventFilter(self, obj, event):
            try:
                if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                    if hasattr(self, 'inspector_dock') and self.inspector_dock.isVisible() and not self._inspector_pinned:
                        widget = obj if isinstance(obj, QtWidgets.QWidget) else None
                        if widget is None:
                            widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
                        if widget is not None and not self._widget_is_inside(widget, self.inspector_dock):
                            self._inspector_dismissed = True
                            self._update_inspector_collapse()
            except Exception:
                pass
            return super().eventFilter(obj, event)

        # ---------- UI ----------
        def _build_ui(self) -> None:
            central = QtWidgets.QWidget()
            self.setCentralWidget(central)
            root = QtWidgets.QVBoxLayout(central)
            root.setContentsMargins(4, 4, 4, 4)
            root.setSpacing(4)

            toolbar = QtWidgets.QToolBar('Main')
            toolbar.setMovable(False)
            self.addToolBar(toolbar)
            self.act_new_demo = toolbar.addAction('New Parametric Pit')
            self.act_import_ifc = toolbar.addAction('Import IFC')
            toolbar.addSeparator()
            self.act_hide_selected = toolbar.addAction('Hide Selected')
            self.act_isolate_selected = toolbar.addAction('Isolate Selected')
            self.act_show_all_objects = toolbar.addAction('Show All')
            self.act_lock_selected = toolbar.addAction('Lock Selected')
            self.act_unlock_selected = toolbar.addAction('Unlock Selected')
            self.act_box_select = toolbar.addAction('Box Select')
            self.act_lasso_select = toolbar.addAction('Lasso Select')
            self.act_clear_selection = toolbar.addAction('Clear Selection')
            toolbar.addWidget(QtWidgets.QLabel(' Select'))
            self.selection_filter_combo = QtWidgets.QComboBox(); self.selection_filter_combo.addItems(['all', 'structures', 'soil', 'supports', 'visible_only'])
            toolbar.addWidget(self.selection_filter_combo)
            toolbar.addSeparator()
            self.act_run = toolbar.addAction('Run')
            self.act_cancel = toolbar.addAction('Cancel')
            self.act_cancel.setEnabled(False)
            toolbar.addSeparator()
            self.act_export = toolbar.addAction('Export VTK')
            self.act_export_bundle = toolbar.addAction('Export ParaView Bundle')
            toolbar.addSeparator()
            toolbar.addWidget(QtWidgets.QLabel('Language'))
            self.lang_combo = QtWidgets.QComboBox(); self.lang_combo.addItems(['English', '中文'])
            toolbar.addWidget(self.lang_combo)
            self.act_toggle_inspector = toolbar.addAction('Inspector')
            self.act_toggle_inspector.setCheckable(True); self.act_toggle_inspector.setChecked(True)

            self.step_list = QtWidgets.QListWidget()
            self.step_list.setFlow(QtWidgets.QListView.Flow.LeftToRight)
            self.step_list.setWrapping(False)
            self.step_list.setMaximumHeight(54)
            self.step_list.setSpacing(8)
            self.step_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.step_list.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.step_list.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
            self.step_list.setMovement(QtWidgets.QListView.Movement.Static)
            self.step_list.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
            for name in ['1 Project', '2 Geometry / IFC', '3 Regions / Materials', '4 Boundary / Stages', '5 Solve / Results']:
                item = QtWidgets.QListWidgetItem(name)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.step_list.addItem(item)
            self.step_list.setCurrentRow(0)
            root.addWidget(self.step_list, 0)

            splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
            self.main_splitter = splitter
            root.addWidget(splitter, 1)

            center_split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
            self.center_splitter = center_split
            self.plotter = QtInteractor(self)
            center_split.addWidget(self.plotter.interactor)
            tabs = QtWidgets.QTabWidget()
            self.log_text = QtWidgets.QPlainTextEdit(); self.log_text.setReadOnly(True)
            tabs.addTab(self.log_text, 'Logs')
            self.task_table = QtWidgets.QTableWidget(0, 5)
            self.task_table.setHorizontalHeaderLabels(['Task', 'Stage', 'Status', 'Details', 'Advice'])
            self.task_table.horizontalHeader().setStretchLastSection(True)
            tabs.addTab(self.task_table, 'Tasks')
            self.validation_list = QtWidgets.QListWidget()
            tabs.addTab(self.validation_list, 'Validation')
            self.diagnostics_table = QtWidgets.QTableWidget(0, 4)
            self.diagnostics_table.setHorizontalHeaderLabels(['Severity', 'Source', 'Message', 'Remedy'])
            self.diagnostics_table.horizontalHeader().setStretchLastSection(True)
            tabs.addTab(self.diagnostics_table, 'Diagnostics')
            self.history_table = QtWidgets.QTableWidget(0, 8)
            self.history_table.setHorizontalHeaderLabels(['Stage', 'Step', 'Iter', 'Ratio', 'Lambda', 'Linear', 'Alpha', 'State'])
            self.history_table.horizontalHeader().setStretchLastSection(True)
            tabs.addTab(self.history_table, 'History')
            center_split.addWidget(tabs)
            center_split.setSizes([640, 220])
            splitter.addWidget(center_split)

            self.page_stack = QtWidgets.QStackedWidget()
            self.page_stack.setMinimumWidth(460)
            self.page_stack.addWidget(self._wrap_scroll_page(ProjectPage(self)))
            self.page_stack.addWidget(self._wrap_scroll_page(GeometryPage(self)))
            self.page_stack.addWidget(MaterialPage(self))
            self.page_stack.addWidget(StagePage(self))
            self.page_stack.addWidget(self._wrap_scroll_page(ResultsPage(self)))
            splitter.addWidget(self.page_stack)
            splitter.setSizes([920, 560])
            self._build_inspector_dock()

            self.status_label = QtWidgets.QLabel('Ready')
            self.statusBar().addWidget(self.status_label, 1)
            self.progress_overall = QtWidgets.QProgressBar(); self.progress_overall.setFixedWidth(180); self.progress_overall.setFormat('Overall %p%')
            self.progress_iter = QtWidgets.QProgressBar(); self.progress_iter.setFixedWidth(160); self.progress_iter.setFormat('Inner %p%')
            self.statusBar().addPermanentWidget(self.progress_overall)
            self.statusBar().addPermanentWidget(self.progress_iter)
            self._solver_heartbeat_timer = QtCore.QTimer(self)
            self._solver_heartbeat_timer.setInterval(600)
            self._solver_heartbeat_timer.timeout.connect(self._solver_heartbeat_tick)
            self._meshing_heartbeat_timer = QtCore.QTimer(self)
            self._meshing_heartbeat_timer.setInterval(500)
            self._meshing_heartbeat_timer.timeout.connect(self._meshing_heartbeat_tick)

            self.step_list.currentRowChanged.connect(self.page_stack.setCurrentIndex)
            self.act_new_demo.triggered.connect(self.create_demo)
            self.act_import_ifc.triggered.connect(self.import_ifc)
            self.act_run.triggered.connect(self.run_solver_async)
            self.act_cancel.triggered.connect(self.cancel_solver)
            self.act_export.triggered.connect(self.export_current)
            self.act_export_bundle.triggered.connect(self.export_bundle)
            self.act_hide_selected.triggered.connect(self.hide_selected_objects)
            self.act_isolate_selected.triggered.connect(self.isolate_selected_objects)
            self.act_show_all_objects.triggered.connect(self.show_all_objects)
            self.act_lock_selected.triggered.connect(self.lock_selected_objects)
            self.act_unlock_selected.triggered.connect(self.unlock_selected_objects)
            self.act_box_select.triggered.connect(self.activate_box_selection)
            self.act_lasso_select.triggered.connect(self.activate_lasso_selection)
            self.act_clear_selection.triggered.connect(self.clear_all_selection)
            self.act_box_select.triggered.connect(self.enable_box_select_mode)
            self.act_lasso_select.triggered.connect(self.enable_lasso_select_mode)
            self.act_toggle_inspector.triggered.connect(self._on_toggle_inspector_requested)
            self.selection_filter_combo.currentTextChanged.connect(self._on_pick_filter_changed)
            self.lang_combo.currentTextChanged.connect(self._on_language_combo_changed)
            self.result_stage_combo.currentTextChanged.connect(self.refresh_view)
            self.result_field_combo.currentTextChanged.connect(self.refresh_view)
            self.result_view_mode_combo.currentTextChanged.connect(self.refresh_view)
            self.scene_tree.itemSelectionChanged.connect(self._on_scene_selection_changed)
            self.scene_tree.customContextMenuRequested.connect(self._show_scene_context_menu)
            self.scene_tree.itemChanged.connect(self._on_scene_item_changed)
            self.region_table.itemSelectionChanged.connect(self._on_region_selection_changed)
            self.material_library_table.itemSelectionChanged.connect(self._on_material_library_selection_changed)
            self.material_model_combo.currentTextChanged.connect(self._on_material_model_changed)
            self.stage_table.itemSelectionChanged.connect(self._on_stage_selection_changed)
            self.stage_activation_tree.itemChanged.connect(lambda *_: self.refresh_view())
            self.bc_table.itemSelectionChanged.connect(self._on_bc_selection_changed)
            self.load_table.itemSelectionChanged.connect(self._on_load_selection_changed)
            self.step_list.currentRowChanged.connect(self._update_global_inspector)
            self.validation_list.itemActivated.connect(self._jump_from_validation_item)
            self.validation_list.itemClicked.connect(self._jump_from_validation_item)
            self.diagnostics_table.itemActivated.connect(self._jump_from_diagnostic_item)
            self.diagnostics_table.itemClicked.connect(self._jump_from_diagnostic_item)
            self._connect_validation_signals()
            self._apply_language('en')

        def _build_inspector_dock(self):
            dock = QtWidgets.QDockWidget('Inspector', self)
            dock.setObjectName('InspectorDock')
            dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable)
            dock.setAllowedAreas(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea | QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
            container = QtWidgets.QWidget(); lay = QtWidgets.QVBoxLayout(container)
            top = QtWidgets.QHBoxLayout()
            self.inspector_pin = QtWidgets.QToolButton(); self.inspector_pin.setCheckable(True); self.inspector_pin.setText('Pin inspector')
            self.inspector_collapse = QtWidgets.QToolButton(); self.inspector_collapse.setCheckable(True); self.inspector_collapse.setText('Auto collapse'); self.inspector_collapse.setChecked(True)
            top.addWidget(self.inspector_pin); top.addWidget(self.inspector_collapse); top.addStretch(1)
            lay.addLayout(top)
            self.inspector_stack = QtWidgets.QStackedWidget()
            collapsed = QtWidgets.QWidget(); cl = QtWidgets.QVBoxLayout(collapsed); self.inspector_collapsed_label = QtWidgets.QLabel('Inspector'); self.inspector_collapsed_label.setWordWrap(True); cl.addWidget(self.inspector_collapsed_label); cl.addStretch(1)
            expanded = QtWidgets.QWidget(); el = QtWidgets.QVBoxLayout(expanded)
            self.inspector_tabs = QtWidgets.QTabWidget()

            selection_tab = QtWidgets.QWidget(); sl = QtWidgets.QVBoxLayout(selection_tab)
            self.inspector_title = QtWidgets.QLabel('Nothing selected')
            self.inspector_title.setWordWrap(True)
            self.inspector_summary = QtWidgets.QTextEdit(); self.inspector_summary.setReadOnly(True); self.inspector_summary.setMinimumHeight(110)
            self.inspector_props = QtWidgets.QTableWidget(0, 2); self.inspector_props.setHorizontalHeaderLabels(['Property', 'Value']); self.inspector_props.horizontalHeader().setStretchLastSection(True)
            vis_row = QtWidgets.QHBoxLayout()
            self.inspector_visible_check = QtWidgets.QCheckBox('Visible'); self.inspector_pickable_check = QtWidgets.QCheckBox('Pickable'); self.inspector_locked_check = QtWidgets.QCheckBox('Locked')
            self.inspector_hide_btn = QtWidgets.QPushButton('Hide Selected'); self.inspector_show_btn = QtWidgets.QPushButton('Show Selected')
            self.inspector_lock_btn = QtWidgets.QPushButton('Lock'); self.inspector_unlock_btn = QtWidgets.QPushButton('Unlock')
            vis_row.addWidget(self.inspector_visible_check); vis_row.addWidget(self.inspector_pickable_check); vis_row.addWidget(self.inspector_locked_check); vis_row.addStretch(1); vis_row.addWidget(self.inspector_hide_btn); vis_row.addWidget(self.inspector_show_btn); vis_row.addWidget(self.inspector_lock_btn); vis_row.addWidget(self.inspector_unlock_btn)
            sl.addWidget(self.inspector_title)
            sl.addWidget(self.inspector_summary)
            sl.addLayout(vis_row)
            sl.addWidget(self.inspector_props, 1)
            self.inspector_tabs.addTab(selection_tab, 'Selection')

            action_tab = QtWidgets.QWidget(); al = QtWidgets.QFormLayout(action_tab)
            self.inspector_region_edit = QtWidgets.QLineEdit('new_region')
            self.inspector_region_combo = QtWidgets.QComboBox()
            self.inspector_role_combo = QtWidgets.QComboBox(); self.inspector_role_combo.addItems(['soil', 'wall', 'slab', 'beam', 'column', 'support', 'opening', 'boundary'])
            self.inspector_assign_new_btn = QtWidgets.QPushButton('Objects -> New region')
            self.inspector_assign_existing_btn = QtWidgets.QPushButton('Objects -> Existing region')
            self.inspector_merge_regions_btn = QtWidgets.QPushButton('Merge selected regions')
            self.inspector_apply_role_btn = QtWidgets.QPushButton('Apply object role')
            al.addRow('New region name', self.inspector_region_edit)
            al.addRow('Target region', self.inspector_region_combo)
            al.addRow('Role', self.inspector_role_combo)
            self.inspector_pick_filter_combo = QtWidgets.QComboBox(); self.inspector_pick_filter_combo.addItems(['all', 'structures', 'soil', 'supports', 'visible_only'])
            self.inspector_pick_note = QtWidgets.QLabel('Pick filter limits 3D clicking/box selection without changing model data.')
            self.inspector_pick_note.setWordWrap(True)
            al.addRow('Pick filter', self.inspector_pick_filter_combo)
            al.addRow(self.inspector_pick_note)
            al.addRow(self.inspector_assign_new_btn)
            al.addRow(self.inspector_assign_existing_btn)
            al.addRow(self.inspector_merge_regions_btn)
            al.addRow(self.inspector_apply_role_btn)
            self.inspector_nudge_step = QtWidgets.QDoubleSpinBox(); self.inspector_nudge_step.setDecimals(3); self.inspector_nudge_step.setRange(0.001, 1000.0); self.inspector_nudge_step.setValue(0.2)
            self.inspector_nudge_dx = QtWidgets.QDoubleSpinBox(); self.inspector_nudge_dx.setDecimals(3); self.inspector_nudge_dx.setRange(-1000.0, 1000.0); self.inspector_nudge_dx.setValue(0.0)
            self.inspector_nudge_dy = QtWidgets.QDoubleSpinBox(); self.inspector_nudge_dy.setDecimals(3); self.inspector_nudge_dy.setRange(-1000.0, 1000.0); self.inspector_nudge_dy.setValue(0.0)
            self.inspector_nudge_dz = QtWidgets.QDoubleSpinBox(); self.inspector_nudge_dz.setDecimals(3); self.inspector_nudge_dz.setRange(-1000.0, 1000.0); self.inspector_nudge_dz.setValue(0.0)
            self.inspector_apply_nudge_btn = QtWidgets.QPushButton('Apply 3D nudge')
            nudge_row = QtWidgets.QHBoxLayout(); nudge_row.addWidget(self.inspector_nudge_dx); nudge_row.addWidget(self.inspector_nudge_dy); nudge_row.addWidget(self.inspector_nudge_dz)
            quick_row = QtWidgets.QHBoxLayout();
            self.inspector_nudge_xp = QtWidgets.QPushButton('+X'); self.inspector_nudge_xm = QtWidgets.QPushButton('-X'); self.inspector_nudge_yp = QtWidgets.QPushButton('+Y'); self.inspector_nudge_ym = QtWidgets.QPushButton('-Y'); self.inspector_nudge_zp = QtWidgets.QPushButton('+Z'); self.inspector_nudge_zm = QtWidgets.QPushButton('-Z')
            for _b in [self.inspector_nudge_xp, self.inspector_nudge_xm, self.inspector_nudge_yp, self.inspector_nudge_ym, self.inspector_nudge_zp, self.inspector_nudge_zm]: quick_row.addWidget(_b)
            al.addRow('Nudge step', self.inspector_nudge_step)
            al.addRow('Δx Δy Δz', nudge_row)
            al.addRow(self.inspector_apply_nudge_btn)
            al.addRow(quick_row)
            self.inspector_tabs.addTab(action_tab, 'Actions')

            solver_tab = QtWidgets.QWidget(); fol = QtWidgets.QFormLayout(solver_tab)
            self.solver_max_iter_spin = QtWidgets.QSpinBox(); self.solver_max_iter_spin.setRange(1, 500); self.solver_max_iter_spin.setValue(24)
            self.solver_tol_edit = QtWidgets.QLineEdit('1e-5')
            self.solver_prefer_sparse = QtWidgets.QCheckBox(); self.solver_prefer_sparse.setChecked(True)
            self.solver_line_search = QtWidgets.QCheckBox(); self.solver_line_search.setChecked(True)
            self.solver_max_cutbacks_spin = QtWidgets.QSpinBox(); self.solver_max_cutbacks_spin.setRange(0, 20); self.solver_max_cutbacks_spin.setValue(5)
            self.solver_device_combo = QtWidgets.QComboBox(); self.solver_device_combo.addItems(['auto-best','auto-round-robin','cpu'])
            self.solver_threads_spin = QtWidgets.QSpinBox(); self.solver_threads_spin.setRange(0, 64); self.solver_threads_spin.setValue(0)
            fol.addRow('Max iterations', self.solver_max_iter_spin)
            fol.addRow('Tolerance', self.solver_tol_edit)
            fol.addRow('Prefer sparse', self.solver_prefer_sparse)
            fol.addRow('Line search', self.solver_line_search)
            fol.addRow('Max cutbacks', self.solver_max_cutbacks_spin)
            fol.addRow('Device', self.solver_device_combo)
            fol.addRow('Threads (0=auto)', self.solver_threads_spin)
            self.inspector_tabs.addTab(solver_tab, 'Solver')

            el.addWidget(self.inspector_tabs)
            self.inspector_stack.addWidget(collapsed)
            self.inspector_stack.addWidget(expanded)
            lay.addWidget(self.inspector_stack)
            dock.setWidget(container)
            self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
            self.inspector_assign_new_btn.clicked.connect(self.assign_selected_objects_to_new_region)
            self.inspector_assign_existing_btn.clicked.connect(self.assign_selected_objects_to_existing_region)
            self.inspector_merge_regions_btn.clicked.connect(self.merge_selected_regions)
            self.inspector_apply_role_btn.clicked.connect(self.apply_selected_object_role)
            self.inspector_apply_nudge_btn.clicked.connect(self.apply_nudge_to_selected_objects)
            self.inspector_nudge_xp.clicked.connect(lambda: self.quick_nudge_selected_objects('x', +1.0))
            self.inspector_nudge_xm.clicked.connect(lambda: self.quick_nudge_selected_objects('x', -1.0))
            self.inspector_nudge_yp.clicked.connect(lambda: self.quick_nudge_selected_objects('y', +1.0))
            self.inspector_nudge_ym.clicked.connect(lambda: self.quick_nudge_selected_objects('y', -1.0))
            self.inspector_nudge_zp.clicked.connect(lambda: self.quick_nudge_selected_objects('z', +1.0))
            self.inspector_nudge_zm.clicked.connect(lambda: self.quick_nudge_selected_objects('z', -1.0))
            self.inspector_hide_btn.clicked.connect(self.hide_selected_objects)
            self.inspector_show_btn.clicked.connect(self.show_selected_objects)
            self.inspector_lock_btn.clicked.connect(self.lock_selected_objects)
            self.inspector_unlock_btn.clicked.connect(self.unlock_selected_objects)
            self.inspector_visible_check.toggled.connect(self._on_inspector_visibility_toggled)
            self.inspector_pickable_check.toggled.connect(self._on_inspector_pickable_toggled)
            self.inspector_locked_check.toggled.connect(self._on_inspector_locked_toggled)
            self.inspector_pin.toggled.connect(self._on_inspector_pin_toggled)
            self.inspector_collapse.toggled.connect(lambda *_: self._update_inspector_collapse())
            self.inspector_pick_filter_combo.currentTextChanged.connect(self._on_pick_filter_changed)
            self.inspector_dock = dock
            self._update_inspector_collapse()

        def _build_project_page(self):
            page = QtWidgets.QWidget(); lay = QtWidgets.QVBoxLayout(page)
            info = QtWidgets.QGroupBox('项目'); form = QtWidgets.QFormLayout(info)
            self.project_name_label = QtWidgets.QLabel('未载入')
            self.project_stats_label = QtWidgets.QLabel('-')
            self.project_source_label = QtWidgets.QLabel('-')
            self.project_schema_label = QtWidgets.QLabel('-')
            form.addRow('名称', self.project_name_label)
            form.addRow('统计', self.project_stats_label)
            form.addRow('来源', self.project_source_label)
            form.addRow('IFC Schema', self.project_schema_label)
            lay.addWidget(info)
            row = QtWidgets.QHBoxLayout()
            b1 = QtWidgets.QPushButton('创建参数化示例'); b2 = QtWidgets.QPushButton('导入 IFC')
            b1.clicked.connect(self.create_demo); b2.clicked.connect(self.import_ifc)
            row.addWidget(b1); row.addWidget(b2)
            lay.addLayout(row)
            self.project_summary_table = QtWidgets.QTableWidget(0, 2)
            self.project_summary_table.setHorizontalHeaderLabels(['项目', '值'])
            self.project_summary_table.horizontalHeader().setStretchLastSection(True)
            lay.addWidget(self.project_summary_table, 1)
            return page

        def _build_geometry_page(self):
            page = QtWidgets.QWidget(); lay = QtWidgets.QVBoxLayout(page)
            param_box = QtWidgets.QGroupBox('参数化几何')
            form = QtWidgets.QFormLayout(param_box)
            specs = {
                'length': (60.0, 1.0, 10000.0, 2),
                'width': (30.0, 1.0, 10000.0, 2),
                'depth': (20.0, 1.0, 500.0, 2),
                'soil_depth': (40.0, 1.0, 1000.0, 2),
                'wall_thickness': (0.8, 0.05, 20.0, 3),
            }
            for name, (val, mn, mx, dec) in specs.items():
                w = QtWidgets.QDoubleSpinBox(); w.setRange(mn, mx); w.setDecimals(dec); w.setValue(val)
                form.addRow(name, w); self._param_inputs[name] = w
            for name, (val, mn, mx) in {'nx': (16, 4, 200), 'ny': (10, 4, 200), 'nz': (12, 4, 200)}.items():
                w = QtWidgets.QSpinBox(); w.setRange(mn, mx); w.setValue(val)
                form.addRow(name, w); self._param_inputs[name] = w
            lay.addWidget(param_box)

            ifc_box = QtWidgets.QGroupBox('IFC 导入选项')
            ifc_form = QtWidgets.QFormLayout(ifc_box)
            self.ifc_include_entities_edit = QtWidgets.QLineEdit('IfcWall,IfcBeam,IfcBuildingElementProxy,IfcSlab,IfcColumn')
            self.ifc_region_strategy_combo = QtWidgets.QComboBox(); self.ifc_region_strategy_combo.addItems(['type_and_name', 'name', 'ifc_type', 'storey'])
            self.ifc_apply_default_materials = QtWidgets.QCheckBox(); self.ifc_apply_default_materials.setChecked(True)
            self.ifc_extract_psets = QtWidgets.QCheckBox(); self.ifc_extract_psets.setChecked(True)
            self.ifc_use_world_coords = QtWidgets.QCheckBox(); self.ifc_use_world_coords.setChecked(True)
            self.ifc_weld_vertices = QtWidgets.QCheckBox(); self.ifc_weld_vertices.setChecked(False)
            self.ifc_include_openings = QtWidgets.QCheckBox(); self.ifc_include_openings.setChecked(False)
            ifc_form.addRow('Include entities', self.ifc_include_entities_edit)
            ifc_form.addRow('Region strategy', self.ifc_region_strategy_combo)
            ifc_form.addRow('Apply default materials', self.ifc_apply_default_materials)
            ifc_form.addRow('Extract property sets', self.ifc_extract_psets)
            ifc_form.addRow('Use world coords', self.ifc_use_world_coords)
            ifc_form.addRow('Weld vertices', self.ifc_weld_vertices)
            ifc_form.addRow('Include openings', self.ifc_include_openings)
            self.geometry_validation_label = QtWidgets.QLabel('')
            self.geometry_validation_label.setWordWrap(True)
            self.ifc_validation_label = QtWidgets.QLabel('')
            self.ifc_validation_label.setWordWrap(True)
            self._validation_labels['geometry'] = self.geometry_validation_label
            self._validation_labels['ifc'] = self.ifc_validation_label
            lay.addWidget(ifc_box)
            lay.addWidget(self.geometry_validation_label)
            lay.addWidget(self.ifc_validation_label)

            mesh_box = QtWidgets.QGroupBox('网格划分流程')
            mesh_form = QtWidgets.QFormLayout(mesh_box)
            self.mesh_method_combo = QtWidgets.QComboBox(); self.mesh_method_combo.addItems(['voxel_hex8', 'gmsh_tet'])
            self.mesh_size_spin = QtWidgets.QDoubleSpinBox(); self.mesh_size_spin.setRange(0.05, 1.0e6); self.mesh_size_spin.setDecimals(3); self.mesh_size_spin.setValue(2.0)
            self.mesh_padding_spin = QtWidgets.QDoubleSpinBox(); self.mesh_padding_spin.setRange(0.0, 1000.0); self.mesh_padding_spin.setDecimals(3); self.mesh_padding_spin.setValue(0.0)
            self.mesh_workflow_note = QtWidgets.QLabel('若 IFC 导入的是表面几何，请先执行网格划分；gmsh 不可用时会提示回退到体素化。')
            self.mesh_workflow_note.setWordWrap(True)
            mesh_form.addRow('方法', self.mesh_method_combo)
            mesh_form.addRow('单元尺寸', self.mesh_size_spin)
            mesh_form.addRow('Padding', self.mesh_padding_spin)
            mesh_form.addRow(self.mesh_workflow_note)
            lay.addWidget(mesh_box)
            mesh_tools = QtWidgets.QHBoxLayout()
            self.btn_check_mesh = QtWidgets.QPushButton('检查网格')
            self.btn_locate_mesh_region = QtWidgets.QPushButton('定位选中区域')
            self.mesh_show_edges_check = QtWidgets.QCheckBox('三维显示网格线')
            self.mesh_show_edges_check.setChecked(True)
            self.mesh_show_edges_check.toggled.connect(self.refresh_view)
            self.btn_check_mesh.clicked.connect(self.run_mesh_check)
            self.btn_locate_mesh_region.clicked.connect(self.locate_selected_mesh_region)
            mesh_tools.addWidget(self.btn_check_mesh)
            mesh_tools.addWidget(self.btn_locate_mesh_region)
            mesh_tools.addWidget(self.mesh_show_edges_check)
            mesh_tools.addStretch(1)
            lay.addLayout(mesh_tools)
            self.mesh_stats_label = QtWidgets.QLabel('尚未检查网格')
            self.mesh_stats_label.setWordWrap(True)
            lay.addWidget(self.mesh_stats_label)
            self.mesh_quality_label = QtWidgets.QLabel('-')
            self.mesh_quality_label.setWordWrap(True)
            lay.addWidget(self.mesh_quality_label)
            self.mesh_check_table = QtWidgets.QTableWidget(0, 6)
            self.mesh_check_table.setHorizontalHeaderLabels(['Region', 'Cells', 'Bad', 'MinVol', 'MaxAR', 'Center / Bounds'])
            self.mesh_check_table.horizontalHeader().setStretchLastSection(True)
            self.mesh_check_table.setMinimumHeight(180)
            self.mesh_check_table.itemSelectionChanged.connect(self._on_mesh_check_region_selected)
            lay.addWidget(self.mesh_check_table)

            btn_row = QtWidgets.QHBoxLayout()
            self.btn_build_parametric = QtWidgets.QPushButton('重建参数化几何')
            self.btn_import_ifc = QtWidgets.QPushButton('导入 IFC')
            self.btn_voxelize = QtWidgets.QPushButton('执行网格划分')
            self.btn_apply_suggestions = QtWidgets.QPushButton('自动建议角色/材料')
            self.btn_build_suggestions = QtWidgets.QPushButton('生成建议面板')
            self.btn_accept_suggestions = QtWidgets.QPushButton('接受选中建议')
            self.btn_reject_suggestions = QtWidgets.QPushButton('拒绝选中建议')
            self.btn_apply_accepted = QtWidgets.QPushButton('应用已接受建议')
            self.btn_build_parametric.clicked.connect(self.create_demo)
            self.btn_import_ifc.clicked.connect(self.import_ifc)
            self.btn_voxelize.clicked.connect(self.run_meshing_workflow)
            self.btn_apply_suggestions.clicked.connect(self.apply_ifc_role_material_suggestions)
            self.btn_build_suggestions.clicked.connect(self.build_ifc_suggestion_panel)
            self.btn_accept_suggestions.clicked.connect(self.accept_selected_suggestions)
            self.btn_reject_suggestions.clicked.connect(self.reject_selected_suggestions)
            self.btn_apply_accepted.clicked.connect(self.apply_accepted_suggestions)
            btn_row.addWidget(self.btn_build_parametric); btn_row.addWidget(self.btn_import_ifc); btn_row.addWidget(self.btn_voxelize); btn_row.addWidget(self.btn_apply_suggestions); btn_row.addWidget(self.btn_build_suggestions)
            lay.addLayout(btn_row)
            quick_row = QtWidgets.QHBoxLayout()
            quick_row.addWidget(self.btn_accept_suggestions)
            quick_row.addWidget(self.btn_reject_suggestions)
            quick_row.addWidget(self.btn_apply_accepted)
            lay.addLayout(quick_row)
            self.suggestion_summary_label = QtWidgets.QLabel('')
            self.suggestion_summary_label.setWordWrap(True)
            lay.addWidget(self.suggestion_summary_label)

            suggestion_box = QtWidgets.QGroupBox('IFC Material Template Suggestions')
            suggestion_lay = QtWidgets.QVBoxLayout(suggestion_box)
            self.suggestion_table = QtWidgets.QTableWidget(0, 6)
            self.suggestion_table.setHorizontalHeaderLabels(['Use', 'Object', 'Role', 'Region', 'Material', 'Reason'])
            self.suggestion_table.horizontalHeader().setStretchLastSection(True)
            suggestion_lay.addWidget(self.suggestion_table)
            sbtn = QtWidgets.QHBoxLayout()
            self.btn_apply_selected_suggestions = QtWidgets.QPushButton('Accept Checked')
            self.btn_reject_selected_suggestions = QtWidgets.QPushButton('Reject Checked')
            self.btn_accept_all_suggestions = QtWidgets.QPushButton('Accept All')
            sbtn.addWidget(self.btn_apply_selected_suggestions)
            sbtn.addWidget(self.btn_reject_selected_suggestions)
            sbtn.addWidget(self.btn_accept_all_suggestions)
            suggestion_lay.addLayout(sbtn)
            self.btn_apply_selected_suggestions.clicked.connect(self.apply_selected_suggestions)
            self.btn_reject_selected_suggestions.clicked.connect(self.reject_selected_suggestions)
            self.btn_accept_all_suggestions.clicked.connect(self.accept_all_suggestions)
            lay.addWidget(suggestion_box)

            split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
            self.scene_tree = QtWidgets.QTreeWidget(); self.scene_tree.setHeaderLabels(['V', 'L', 'Object', 'Type / Region']); self.scene_tree.setColumnWidth(0, 28); self.scene_tree.setColumnWidth(1, 28); self.scene_tree.setColumnWidth(2, 220)
            self.scene_tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
            self.scene_tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            split.addWidget(self.scene_tree)
            inspector_tabs = QtWidgets.QTabWidget()
            general = QtWidgets.QWidget(); gf = QtWidgets.QFormLayout(general)
            self.obj_name_label = QtWidgets.QLabel('-')
            self.obj_type_label = QtWidgets.QLabel('-')
            self.obj_guid_label = QtWidgets.QLabel('-')
            self.obj_region_label = QtWidgets.QLabel('-')
            self.obj_parent_label = QtWidgets.QLabel('-')
            gf.addRow('名称', self.obj_name_label)
            gf.addRow('类型', self.obj_type_label)
            gf.addRow('GUID', self.obj_guid_label)
            gf.addRow('Region', self.obj_region_label)
            gf.addRow('父级', self.obj_parent_label)
            inspector_tabs.addTab(general, '概览')
            self.obj_property_table = QtWidgets.QTableWidget(0, 2); self.obj_property_table.setHorizontalHeaderLabels(['属性', '值']); self.obj_property_table.horizontalHeader().setStretchLastSection(True)
            inspector_tabs.addTab(self.obj_property_table, '属性')
            self.obj_metadata_table = QtWidgets.QTableWidget(0, 2); self.obj_metadata_table.setHorizontalHeaderLabels(['字段', '值']); self.obj_metadata_table.horizontalHeader().setStretchLastSection(True)
            inspector_tabs.addTab(self.obj_metadata_table, '元数据')
            split.addWidget(inspector_tabs)
            split.setSizes([280, 240])
            lay.addWidget(split, 1)
            edit_box = QtWidgets.QGroupBox('对象 / Region 编辑')
            edit_form = QtWidgets.QFormLayout(edit_box)
            self.scene_region_name_edit = QtWidgets.QLineEdit('region_new')
            self.scene_region_target_combo = QtWidgets.QComboBox()
            self.scene_object_role_combo = QtWidgets.QComboBox(); self.scene_object_role_combo.addItems(['soil', 'wall', 'slab', 'beam', 'column', 'support', 'opening', 'boundary'])
            self.btn_assign_new_region = QtWidgets.QPushButton('选中对象 -> 新区域')
            self.btn_assign_existing_region = QtWidgets.QPushButton('选中对象 -> 现有区域')
            self.btn_merge_region = QtWidgets.QPushButton('合并选中 Region')
            self.btn_apply_object_role = QtWidgets.QPushButton('设置对象角色')
            edit_form.addRow('新区域名', self.scene_region_name_edit)
            edit_form.addRow('目标区域', self.scene_region_target_combo)
            edit_form.addRow('结构角色', self.scene_object_role_combo)
            edit_form.addRow(self.btn_assign_new_region)
            edit_form.addRow(self.btn_assign_existing_region)
            edit_form.addRow(self.btn_merge_region)
            edit_form.addRow(self.btn_apply_object_role)
            self.btn_assign_new_region.clicked.connect(self.assign_selected_objects_to_new_region)
            self.btn_assign_existing_region.clicked.connect(self.assign_selected_objects_to_existing_region)
            self.btn_merge_region.clicked.connect(self.merge_selected_regions)
            self.btn_apply_object_role.clicked.connect(self.apply_selected_object_role)
            lay.addWidget(edit_box)
            return page

        def _build_material_page(self):
            page = QtWidgets.QWidget(); lay = QtWidgets.QVBoxLayout(page)
            upper = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
            # regions
            rg = QtWidgets.QGroupBox('区域与赋值'); rgl = QtWidgets.QVBoxLayout(rg)
            self.region_table = QtWidgets.QTableWidget(0, 7)
            self.region_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            self.region_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
            self.region_table.setHorizontalHeaderLabels(['Region', 'Cells', 'Center', 'Bounds', 'Material', 'Library', 'Status'])
            self.region_table.horizontalHeader().setStretchLastSection(True)
            self.region_table.setMinimumHeight(260)
            rgl.addWidget(self.region_table)
            rr = QtWidgets.QHBoxLayout()
            self.region_name_edit = QtWidgets.QLineEdit(); self.btn_rename_region = QtWidgets.QPushButton('重命名区域')
            rr.addWidget(self.region_name_edit); rr.addWidget(self.btn_rename_region)
            self.btn_rename_region.clicked.connect(self.rename_selected_region)
            rgl.addLayout(rr)
            self.region_info = QtWidgets.QLabel('选择区域后可查看对象数量和材料绑定。')
            self.region_info.setWordWrap(True)
            rgl.addWidget(self.region_info)
            upper.addWidget(rg)
            # material library
            mg = QtWidgets.QGroupBox('材料库 / 属性检查器'); mgl = QtWidgets.QVBoxLayout(mg)
            self.material_library_table = QtWidgets.QTableWidget(0, 4)
            self.material_library_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            self.material_library_table.setHorizontalHeaderLabels(['名称', '模型', '参数数', '备注'])
            self.material_library_table.horizontalHeader().setStretchLastSection(True)
            mgl.addWidget(self.material_library_table)
            form = QtWidgets.QFormLayout()
            self.material_name_edit = QtWidgets.QLineEdit('Soil_MC')
            self.material_model_combo = QtWidgets.QComboBox()
            form.addRow('材料名称', self.material_name_edit)
            form.addRow('本构模型', self.material_model_combo)
            mgl.addLayout(form)
            self.material_param_form = QtWidgets.QFormLayout()
            mgl.addLayout(self.material_param_form)
            lib_btns = QtWidgets.QHBoxLayout()
            self.btn_new_material = QtWidgets.QPushButton('新建')
            self.btn_save_material = QtWidgets.QPushButton('新增/更新')
            self.btn_delete_material = QtWidgets.QPushButton('删除')
            lib_btns.addWidget(self.btn_new_material); lib_btns.addWidget(self.btn_save_material); lib_btns.addWidget(self.btn_delete_material)
            mgl.addLayout(lib_btns)
            assign_btns = QtWidgets.QHBoxLayout()
            self.btn_assign_material = QtWidgets.QPushButton('赋值到选中区域')
            self.btn_assign_custom_material = QtWidgets.QPushButton('当前参数 -> 选中区域')
            self.btn_clear_material = QtWidgets.QPushButton('清除选中区域材料')
            assign_btns.addWidget(self.btn_assign_material); assign_btns.addWidget(self.btn_assign_custom_material); assign_btns.addWidget(self.btn_clear_material)
            mgl.addLayout(assign_btns)
            self.material_validation_label = QtWidgets.QLabel('')
            self.material_validation_label.setWordWrap(True)
            self._validation_labels['material'] = self.material_validation_label
            mgl.addWidget(self.material_validation_label)
            self.btn_new_material.clicked.connect(self.new_material_definition)
            self.btn_save_material.clicked.connect(self.save_material_definition)
            self.btn_delete_material.clicked.connect(self.delete_material_definition)
            self.btn_assign_material.clicked.connect(self.assign_material_to_regions)
            self.btn_assign_custom_material.clicked.connect(self.assign_current_material_to_regions)
            self.btn_clear_material.clicked.connect(self.clear_material_from_regions)
            upper.addWidget(mg)
            upper.setSizes([420, 520])
            lay.addWidget(upper, 1)
            return page

        def _build_stage_page(self):
            page = QtWidgets.QWidget(); lay = QtWidgets.QVBoxLayout(page)
            split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
            # Stage list
            left = QtWidgets.QWidget(); ll = QtWidgets.QVBoxLayout(left)
            self.stage_table = QtWidgets.QTableWidget(0, 5)
            self.stage_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            self.stage_table.setHorizontalHeaderLabels(['Name', 'Steps', 'Activate', 'Deactivate', 'BC/Loads'])
            self.stage_table.setMinimumHeight(220)
            self.stage_table.horizontalHeader().setStretchLastSection(True)
            ll.addWidget(self.stage_table)
            row = QtWidgets.QHBoxLayout()
            self.btn_add_stage = QtWidgets.QPushButton('新增 Stage')
            self.btn_remove_stage = QtWidgets.QPushButton('删除 Stage')
            row.addWidget(self.btn_add_stage); row.addWidget(self.btn_remove_stage)
            self.btn_add_stage.clicked.connect(self.add_stage)
            self.btn_remove_stage.clicked.connect(self.remove_selected_stage)
            ll.addLayout(row)
            split.addWidget(left)
            # Stage inspector/editor
            editor = QtWidgets.QTabWidget()
            stage_editor = QtWidgets.QWidget(); sl = QtWidgets.QVBoxLayout(stage_editor)
            form = QtWidgets.QFormLayout()
            self.stage_name_edit = QtWidgets.QLineEdit('stage_1')
            self.stage_steps_spin = QtWidgets.QSpinBox(); self.stage_steps_spin.setRange(1, 10000); self.stage_steps_spin.setValue(6)
            self.stage_initial_increment = QtWidgets.QDoubleSpinBox(); self.stage_initial_increment.setDecimals(3); self.stage_initial_increment.setRange(0.001, 1.0); self.stage_initial_increment.setValue(0.25)
            self.stage_max_iterations = QtWidgets.QSpinBox(); self.stage_max_iterations.setRange(1, 200); self.stage_max_iterations.setValue(24)
            self.stage_line_search = QtWidgets.QCheckBox(); self.stage_line_search.setChecked(True)
            self.stage_notes_edit = QtWidgets.QPlainTextEdit(); self.stage_notes_edit.setMaximumHeight(70)
            form.addRow('阶段名称', self.stage_name_edit)
            form.addRow('步数', self.stage_steps_spin)
            form.addRow('初始增量', self.stage_initial_increment)
            form.addRow('最大迭代', self.stage_max_iterations)
            form.addRow('线搜索', self.stage_line_search)
            form.addRow('备注', self.stage_notes_edit)
            sl.addLayout(form)
            self.stage_activation_tree = QtWidgets.QTreeWidget()
            self.stage_activation_tree.setHeaderLabels(['区域', '状态'])
            self.stage_activation_tree.setAlternatingRowColors(True)
            self.stage_activation_tree.itemChanged.connect(self._on_stage_activation_item_changed)
            self.activate_region_list = self.stage_activation_tree
            self.deactivate_region_list = self.stage_activation_tree
            sl.addWidget(self._wrap_groupbox('激活区域 / 失活区域（复选框控制）', self.stage_activation_tree), 1)
            stage_btns = QtWidgets.QHBoxLayout()
            self.btn_apply_stage = QtWidgets.QPushButton('保存 Stage')
            self.btn_clone_stage = QtWidgets.QPushButton('复制当前 Stage')
            stage_btns.addWidget(self.btn_apply_stage); stage_btns.addWidget(self.btn_clone_stage)
            self.stage_validation_label = QtWidgets.QLabel('')
            self.stage_validation_label.setWordWrap(True)
            self._validation_labels['stage'] = self.stage_validation_label
            sl.addWidget(self.stage_validation_label)
            self.btn_apply_stage.clicked.connect(self.save_current_stage)
            self.btn_clone_stage.clicked.connect(self.clone_current_stage)
            sl.addLayout(stage_btns)
            editor.addTab(stage_editor, 'Stage 编辑器')
            # Boundary conditions
            bc_editor = QtWidgets.QWidget(); bcl = QtWidgets.QVBoxLayout(bc_editor)
            self.bc_table = QtWidgets.QTableWidget(0, 4)
            self.bc_table.setHorizontalHeaderLabels(['Name', 'Kind', 'Target', 'Values'])
            self.bc_table.horizontalHeader().setStretchLastSection(True)
            bcl.addWidget(self.bc_table)
            bc_form = QtWidgets.QFormLayout()
            self.bc_name_edit = QtWidgets.QLineEdit('bc_1')
            self.bc_kind_combo = QtWidgets.QComboBox(); self.bc_kind_combo.addItems(['displacement', 'roller', 'symmetry'])
            self.bc_target_edit = QtWidgets.QLineEdit('bottom')
            self.bc_components_edit = QtWidgets.QLineEdit('0,1,2')
            self.bc_values_edit = QtWidgets.QLineEdit('0,0,0')
            bc_form.addRow('名称', self.bc_name_edit)
            bc_form.addRow('类型', self.bc_kind_combo)
            bc_form.addRow('目标', self.bc_target_edit)
            bc_form.addRow('分量', self.bc_components_edit)
            bc_form.addRow('数值', self.bc_values_edit)
            bcl.addLayout(bc_form)
            bc_btns = QtWidgets.QHBoxLayout()
            self.btn_add_bc = QtWidgets.QPushButton('新增 / 更新 BC')
            self.btn_remove_bc = QtWidgets.QPushButton('删除 BC')
            bc_btns.addWidget(self.btn_add_bc); bc_btns.addWidget(self.btn_remove_bc)
            self.btn_add_bc.clicked.connect(self.add_or_update_bc)
            self.btn_remove_bc.clicked.connect(self.remove_selected_bc)
            bcl.addLayout(bc_btns)
            self.bc_validation_label = QtWidgets.QLabel('')
            self.bc_validation_label.setWordWrap(True)
            self._validation_labels['bc'] = self.bc_validation_label
            bcl.addWidget(self.bc_validation_label)
            editor.addTab(bc_editor, '边界条件')
            # Loads
            load_editor = QtWidgets.QWidget(); ll2 = QtWidgets.QVBoxLayout(load_editor)
            self.load_table = QtWidgets.QTableWidget(0, 4)
            self.load_table.setHorizontalHeaderLabels(['Name', 'Kind', 'Target', 'Values'])
            self.load_table.horizontalHeader().setStretchLastSection(True)
            ll2.addWidget(self.load_table)
            load_form = QtWidgets.QFormLayout()
            self.load_name_edit = QtWidgets.QLineEdit('load_1')
            self.load_kind_combo = QtWidgets.QComboBox(); self.load_kind_combo.addItems(['nodal_force', 'gravity_scale', 'pressure'])
            self.load_target_edit = QtWidgets.QLineEdit('top')
            self.load_values_edit = QtWidgets.QLineEdit('0,0,-1000')
            load_form.addRow('名称', self.load_name_edit)
            load_form.addRow('类型', self.load_kind_combo)
            load_form.addRow('目标', self.load_target_edit)
            load_form.addRow('数值', self.load_values_edit)
            ll2.addLayout(load_form)
            load_btns = QtWidgets.QHBoxLayout()
            self.btn_add_load = QtWidgets.QPushButton('新增 / 更新荷载')
            self.btn_remove_load = QtWidgets.QPushButton('删除荷载')
            load_btns.addWidget(self.btn_add_load); load_btns.addWidget(self.btn_remove_load)
            self.btn_add_load.clicked.connect(self.add_or_update_load)
            self.btn_remove_load.clicked.connect(self.remove_selected_load)
            ll2.addLayout(load_btns)
            self.load_validation_label = QtWidgets.QLabel('')
            self.load_validation_label.setWordWrap(True)
            self._validation_labels['load'] = self.load_validation_label
            ll2.addWidget(self.load_validation_label)
            editor.addTab(load_editor, '荷载')
            split.addWidget(editor)
            split.setSizes([340, 520])
            lay.addWidget(split, 1)
            return page

        def _build_results_page(self):
            page = QtWidgets.QWidget(); lay = QtWidgets.QVBoxLayout(page)
            solver_group = QtWidgets.QGroupBox('求解与进度')
            sgl = QtWidgets.QVBoxLayout(solver_group)
            row = QtWidgets.QHBoxLayout()
            self.btn_run_solver = QtWidgets.QPushButton('后台求解')
            self.btn_cancel_solver = QtWidgets.QPushButton('取消求解'); self.btn_cancel_solver.setEnabled(False)
            self.btn_run_solver.clicked.connect(self.run_solver_async)
            self.btn_cancel_solver.clicked.connect(self.cancel_solver)
            row.addWidget(self.btn_run_solver); row.addWidget(self.btn_cancel_solver)
            sgl.addLayout(row)
            self.solver_note = QtWidgets.QLabel('尚未求解')
            sgl.addWidget(self.solver_note)

            compute_group = QtWidgets.QGroupBox('后台计算配置')
            cgl = QtWidgets.QVBoxLayout(compute_group)
            preset_row = QtWidgets.QHBoxLayout()
            self.solver_compute_profile_combo = QtWidgets.QComboBox(); self.solver_compute_profile_combo.addItems(['auto', 'cpu-safe', 'gpu-throughput', 'gpu-fullpath'])
            self.solver_compute_profile_combo.currentTextChanged.connect(self._on_solver_compute_profile_changed)
            self.btn_solver_profile_auto = QtWidgets.QPushButton('自动推荐')
            self.btn_solver_profile_cpu = QtWidgets.QPushButton('CPU 保守')
            self.btn_solver_profile_gpu = QtWidgets.QPushButton('GPU 全路径')
            self.btn_solver_profile_auto.clicked.connect(lambda: self._apply_solver_compute_profile('auto'))
            self.btn_solver_profile_cpu.clicked.connect(lambda: self._apply_solver_compute_profile('cpu-safe'))
            self.btn_solver_profile_gpu.clicked.connect(lambda: self._apply_solver_compute_profile('gpu-fullpath'))
            preset_row.addWidget(self.solver_compute_profile_combo)
            preset_row.addWidget(self.btn_solver_profile_auto)
            preset_row.addWidget(self.btn_solver_profile_cpu)
            preset_row.addWidget(self.btn_solver_profile_gpu)
            cgl.addLayout(preset_row)
            cform = QtWidgets.QFormLayout()
            self.solver_compute_backend_combo = QtWidgets.QComboBox(); self.solver_compute_backend_combo.addItems(['warp'])
            self.solver_compute_device_combo = QtWidgets.QComboBox(); self.solver_compute_device_combo.addItems(['auto-best', 'auto-round-robin', 'cpu'])
            self.solver_compute_multi_gpu_combo = QtWidgets.QComboBox(); self.solver_compute_multi_gpu_combo.addItems(['single', 'round-robin'])
            self.solver_compute_threads_spin = QtWidgets.QSpinBox(); self.solver_compute_threads_spin.setRange(0, 128); self.solver_compute_threads_spin.setValue(0)
            self.solver_compute_require_warp_check = QtWidgets.QCheckBox(); self.solver_compute_require_warp_check.setChecked(True)
            self.solver_compute_hex8_check = QtWidgets.QCheckBox(); self.solver_compute_hex8_check.setChecked(True)
            self.solver_compute_nonlinear_check = QtWidgets.QCheckBox(); self.solver_compute_nonlinear_check.setChecked(True)
            self.solver_compute_full_gpu_check = QtWidgets.QCheckBox(); self.solver_compute_full_gpu_check.setChecked(True)
            self.solver_compute_gpu_assembly_check = QtWidgets.QCheckBox(); self.solver_compute_gpu_assembly_check.setChecked(True)
            self.solver_compute_interface_check = QtWidgets.QCheckBox(); self.solver_compute_interface_check.setChecked(True)
            self.solver_compute_structural_check = QtWidgets.QCheckBox(); self.solver_compute_structural_check.setChecked(True)
            self.solver_compute_block_merge_check = QtWidgets.QCheckBox(); self.solver_compute_block_merge_check.setChecked(True)
            self.solver_compute_stage_sync_check = QtWidgets.QCheckBox(); self.solver_compute_stage_sync_check.setChecked(True)
            self.solver_compute_ordering_combo = QtWidgets.QComboBox(); self.solver_compute_ordering_combo.addItems(['auto', 'rcm', 'colamd', 'amd', 'mmd_ata', 'mmd_at_plus_a', 'natural'])
            self.solver_compute_preconditioner_combo = QtWidgets.QComboBox(); self.solver_compute_preconditioner_combo.addItems(['auto', 'block-jacobi', 'spilu', 'jacobi', 'none'])
            self.solver_compute_strategy_combo = QtWidgets.QComboBox(); self.solver_compute_strategy_combo.addItems(['auto', 'cg', 'minres', 'bicgstab', 'gmres', 'direct'])
            self.solver_compute_warp_preconditioner_combo = QtWidgets.QComboBox(); self.solver_compute_warp_preconditioner_combo.addItems(['diag', 'none'])
            self.solver_compute_iter_tol_edit = QtWidgets.QLineEdit('1e-10')
            self.solver_compute_iter_max_spin = QtWidgets.QSpinBox(); self.solver_compute_iter_max_spin.setRange(25, 20000); self.solver_compute_iter_max_spin.setValue(2000)
            cform.addRow('Backend', self.solver_compute_backend_combo)
            cform.addRow('设备 Device', self.solver_compute_device_combo)
            cform.addRow('CPU 核心数 / Threads (0=auto)', self.solver_compute_threads_spin)
            cform.addRow('多卡策略 Multi-GPU', self.solver_compute_multi_gpu_combo)
            cform.addRow('必须使用 Warp', self.solver_compute_require_warp_check)
            cform.addRow('Warp Hex8 装配', self.solver_compute_hex8_check)
            cform.addRow('Warp 非线性连续体', self.solver_compute_nonlinear_check)
            cform.addRow('GPU 线性主路径', self.solver_compute_full_gpu_check)
            cform.addRow('GPU 全局装配', self.solver_compute_gpu_assembly_check)
            cform.addRow('GPU Interface 装配', self.solver_compute_interface_check)
            cform.addRow('GPU Structural 合并', self.solver_compute_structural_check)
            cform.addRow('统一 Block Merge', self.solver_compute_block_merge_check)
            cform.addRow('多 Stage 状态同步', self.solver_compute_stage_sync_check)
            cform.addRow('重排序 Ordering', self.solver_compute_ordering_combo)
            cform.addRow('预条件 Preconditioner', self.solver_compute_preconditioner_combo)
            cform.addRow('求解策略 Strategy', self.solver_compute_strategy_combo)
            cform.addRow('Warp 预条件', self.solver_compute_warp_preconditioner_combo)
            cform.addRow('迭代容差', self.solver_compute_iter_tol_edit)
            cform.addRow('迭代上限', self.solver_compute_iter_max_spin)
            cgl.addLayout(cform)
            self.solver_compute_hardware_label = QtWidgets.QLabel('')
            self.solver_compute_hardware_label.setWordWrap(True)
            self.solver_compute_summary_label = QtWidgets.QLabel('')
            self.solver_compute_summary_label.setWordWrap(True)
            self.solver_gpu_hint_label = QtWidgets.QLabel('')
            self.solver_gpu_hint_label.setWordWrap(True)
            self.solver_gpu_list = QtWidgets.QListWidget()
            self.solver_gpu_list.setObjectName('gpuDeviceList')
            self.solver_gpu_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
            self.solver_gpu_list.setMaximumHeight(112)
            cgl.addWidget(self.solver_compute_hardware_label)
            cgl.addWidget(self.solver_compute_summary_label)
            cgl.addWidget(QtWidgets.QLabel('参与调度的显卡 / Highlight GPUs for scheduling'))
            cgl.addWidget(self.solver_gpu_hint_label)
            cgl.addWidget(self.solver_gpu_list)
            for _w in (self.solver_compute_backend_combo, self.solver_compute_device_combo, self.solver_compute_multi_gpu_combo, self.solver_compute_threads_spin, self.solver_compute_require_warp_check, self.solver_compute_hex8_check, self.solver_compute_nonlinear_check, self.solver_compute_full_gpu_check, self.solver_compute_gpu_assembly_check, self.solver_compute_interface_check, self.solver_compute_structural_check, self.solver_compute_block_merge_check, self.solver_compute_stage_sync_check, self.solver_compute_ordering_combo, self.solver_compute_preconditioner_combo, self.solver_compute_strategy_combo, self.solver_compute_warp_preconditioner_combo, self.solver_compute_iter_tol_edit, self.solver_compute_iter_max_spin, self.solver_gpu_list):
                try:
                    _w.currentTextChanged.connect(self._update_solver_compute_summary)
                except Exception:
                    pass
                try:
                    _w.valueChanged.connect(self._update_solver_compute_summary)
                except Exception:
                    pass
                try:
                    _w.toggled.connect(self._update_solver_compute_summary)
                except Exception:
                    pass
                try:
                    _w.textChanged.connect(self._update_solver_compute_summary)
                except Exception:
                    pass
            self.solver_gpu_list.itemSelectionChanged.connect(self._update_solver_compute_summary)
            sgl.addWidget(compute_group)

            sform = QtWidgets.QFormLayout()
            self.result_scale_spin = QtWidgets.QDoubleSpinBox(); self.result_scale_spin.setRange(0.01, 1e6); self.result_scale_spin.setValue(1.0); self.result_scale_spin.setDecimals(3)
            self.result_scale_spin.valueChanged.connect(self.refresh_view)
            sform.addRow('变形放大', self.result_scale_spin)
            sgl.addLayout(sform)
            self.solver_validation_label = QtWidgets.QLabel('')
            self.solver_validation_label.setWordWrap(True)
            self._validation_labels['solver'] = self.solver_validation_label
            sgl.addWidget(self.solver_validation_label)
            lay.addWidget(solver_group)
            result_group = QtWidgets.QGroupBox('结果预览')
            rg = QtWidgets.QFormLayout(result_group)
            self.result_stage_combo = QtWidgets.QComboBox(); self.result_stage_combo.addItem('(latest)')
            self.result_field_combo = QtWidgets.QComboBox(); self.result_field_combo.addItem('(geometry only)')
            self.result_view_mode_combo = QtWidgets.QComboBox(); self.result_view_mode_combo.addItems(['normal', 'stage_activity', 'validation_regions', 'mesh_quality'])
            rg.addRow('Stage', self.result_stage_combo)
            rg.addRow('Field', self.result_field_combo)
            rg.addRow('View', self.result_view_mode_combo)
            lay.addWidget(result_group)
            vis_group = QtWidgets.QGroupBox('Visualization')
            vg = QtWidgets.QFormLayout(vis_group)
            self.result_cmap_combo = QtWidgets.QComboBox(); self.result_cmap_combo.addItems(['viridis','plasma','coolwarm','turbo','jet'])
            self.result_opacity_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal); self.result_opacity_slider.setRange(10, 100); self.result_opacity_slider.setValue(100)
            self.result_scalar_bar_check = QtWidgets.QCheckBox(); self.result_scalar_bar_check.setChecked(True)
            self.result_auto_range_check = QtWidgets.QCheckBox(); self.result_auto_range_check.setChecked(True)
            self.result_range_min_edit = QtWidgets.QLineEdit(''); self.result_range_max_edit = QtWidgets.QLineEdit('')
            self.result_clip_axis_combo = QtWidgets.QComboBox(); self.result_clip_axis_combo.addItems(['none','x','y','z'])
            self.result_clip_ratio_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal); self.result_clip_ratio_slider.setRange(0, 100); self.result_clip_ratio_slider.setValue(50)
            for _w in (self.result_cmap_combo, self.result_opacity_slider, self.result_scalar_bar_check, self.result_auto_range_check, self.result_range_min_edit, self.result_range_max_edit, self.result_clip_axis_combo, self.result_clip_ratio_slider):
                try:
                    _w.currentTextChanged.connect(self.refresh_view)
                except Exception:
                    pass
                try:
                    _w.valueChanged.connect(self.refresh_view)
                except Exception:
                    pass
                try:
                    _w.toggled.connect(self.refresh_view)
                except Exception:
                    pass
                try:
                    _w.textChanged.connect(self.refresh_view)
                except Exception:
                    pass
            vg.addRow('Colormap', self.result_cmap_combo)
            vg.addRow('Opacity', self.result_opacity_slider)
            vg.addRow('Scalar bar', self.result_scalar_bar_check)
            vg.addRow('Auto range', self.result_auto_range_check)
            vg.addRow('Range min', self.result_range_min_edit)
            vg.addRow('Range max', self.result_range_max_edit)
            vg.addRow('Clip axis', self.result_clip_axis_combo)
            vg.addRow('Clip ratio', self.result_clip_ratio_slider)
            lay.addWidget(vis_group)
            mesh_group = QtWidgets.QGroupBox('Mesh summary')
            mg = QtWidgets.QVBoxLayout(mesh_group)
            self.result_mesh_summary = QtWidgets.QLabel('-')
            self.result_mesh_summary.setWordWrap(True)
            mg.addWidget(self.result_mesh_summary)
            lay.addWidget(mesh_group)
            export_group = QtWidgets.QGroupBox('导出')
            ex = QtWidgets.QHBoxLayout(export_group)
            self.btn_export_current = QtWidgets.QPushButton('导出当前数据集')
            self.btn_export_bundle = QtWidgets.QPushButton('导出 ParaView Bundle')
            self.btn_export_current.clicked.connect(self.export_current)
            self.btn_export_bundle.clicked.connect(self.export_bundle)
            ex.addWidget(self.btn_export_current); ex.addWidget(self.btn_export_bundle)
            lay.addWidget(export_group)
            lay.addStretch(1)
            return page

        def _wrap_groupbox(self, title: str, child):
            box = QtWidgets.QGroupBox(title)
            lay = QtWidgets.QVBoxLayout(box)
            lay.addWidget(child)
            return box

        def _wrap_scroll_page(self, child):
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            scroll.setWidget(child)
            return scroll

        def _create_solver_progress_dialog(self) -> None:
            dlg = QtWidgets.QProgressDialog(self._tt('Preparing solver...'), self._tt('Cancel'), 0, 0, self)
            dlg.setWindowTitle(self._tt('Solver progress'))
            dlg.setWindowModality(QtCore.Qt.WindowModality.NonModal)
            dlg.setAutoClose(False)
            dlg.setAutoReset(False)
            dlg.setMinimumDuration(0)
            dlg.setValue(0)
            dlg.canceled.connect(self.cancel_solver)
            self._solver_progress_dialog = dlg
            dlg.show()

        def _update_solver_progress_dialog(self, value: int | None = None, text: str | None = None) -> None:
            dlg = getattr(self, '_solver_progress_dialog', None)
            if dlg is None:
                return
            if text is not None:
                dlg.setLabelText(self._tt(text))
            if value is not None:
                if dlg.maximum() == 0 and int(value) > 0:
                    dlg.setRange(0, 100)
                dlg.setValue(max(0, min(100, int(value))))

        def _close_solver_progress_dialog(self) -> None:
            dlg = getattr(self, '_solver_progress_dialog', None)
            if dlg is not None:
                dlg.close()
                dlg.deleteLater()
            self._solver_progress_dialog = None

        def _create_meshing_progress_dialog(self) -> None:
            dlg = QtWidgets.QProgressDialog(self._tt('Preparing meshing...'), self._tt('Close'), 0, 100, self)
            dlg.setWindowTitle(self._tt('Meshing progress'))
            dlg.setWindowModality(QtCore.Qt.WindowModality.NonModal)
            dlg.setAutoClose(False)
            dlg.setAutoReset(False)
            dlg.setMinimumDuration(0)
            dlg.setValue(0)
            dlg.setCancelButton(None)
            self._meshing_progress_dialog = dlg
            dlg.show()

        def _update_meshing_progress_dialog(self, value: int | None = None, text: str | None = None) -> None:
            dlg = getattr(self, '_meshing_progress_dialog', None)
            if dlg is None:
                return
            if text is not None:
                dlg.setLabelText(self._tt(text))
            if value is not None:
                dlg.setValue(max(0, min(100, int(value))))

        def _close_meshing_progress_dialog(self) -> None:
            dlg = getattr(self, '_meshing_progress_dialog', None)
            if dlg is not None:
                dlg.close()
                dlg.deleteLater()
            self._meshing_progress_dialog = None

        def _meshing_heartbeat_tick(self) -> None:
            if self._meshing_thread is None or self._meshing_started_at is None:
                return
            elapsed = max(0.0, time.time() - self._meshing_started_at)
            dots = '.' * ((getattr(self, '_heartbeat_counter', 0) % 3) + 1)
            self._heartbeat_counter = getattr(self, '_heartbeat_counter', 0) + 1
            tail = ''
            payload = getattr(self, '_last_meshing_payload', None) or {}
            current = str(payload.get('message', '') or '').strip()
            if current:
                tail = f" | {current}"
            message = f"{self._tt('Meshing is running in background')} {dots} | {self._tt('Elapsed')} {format_seconds(elapsed)}{tail}"
            self.status_label.setText(message)
            self._update_meshing_progress_dialog(text=message)

        def _solver_heartbeat_tick(self) -> None:
            if self._solver_thread is None or self._eta_estimator is None:
                return
            elapsed, eta = self._eta_estimator.update(float(getattr(self, '_last_solver_fraction', 0.0) or 0.0))
            dots = '.' * ((getattr(self, '_heartbeat_counter', 0) % 3) + 1)
            self._heartbeat_counter = getattr(self, '_heartbeat_counter', 0) + 1
            tail = ''
            payload = getattr(self, '_last_solver_payload', None) or {}
            current = str(payload.get('message', '') or '').strip()
            if not current and isinstance(payload, dict):
                phase = str(payload.get('phase', '') or '').strip()
                if phase:
                    current = phase
            if current:
                tail = f" | {current}"
            eta_text = f" | ETA {format_seconds(eta)}" if eta is not None else ''
            message = f"{self._tt('Solver is running in background')} {dots} | {self._tt('Elapsed')} {format_seconds(elapsed)}{eta_text}{tail}"
            self.status_label.setText(message)
            self._update_solver_progress_dialog(text=message)

        def _on_language_combo_changed(self, text: str) -> None:
            self._apply_language('zh' if '中' in text else 'en')

        def _apply_language(self, lang: str) -> None:
            self._lang = lang
            if hasattr(self, 'lang_combo'):
                self.lang_combo.blockSignals(True)
                self.lang_combo.setCurrentText('中文' if lang == 'zh' else 'English')
                self.lang_combo.blockSignals(False)
            self.setWindowTitle(translate_text('geoai-simkit', lang))
            def walk(widget):
                for child in widget.findChildren(object):
                    try:
                        if hasattr(child, 'text') and callable(child.text) and hasattr(child, 'setText'):
                            t = child.text()
                            if isinstance(t, str):
                                child.setText(translate_text(t, lang))
                    except Exception:
                        pass
                    try:
                        if hasattr(child, 'title') and callable(child.title) and hasattr(child, 'setTitle'):
                            t = child.title()
                            if isinstance(t, str):
                                child.setTitle(translate_text(t, lang))
                    except Exception:
                        pass
                for action in self.findChildren(QtGui.QAction):
                    try:
                        action.setText(translate_text(action.text(), lang))
                    except Exception:
                        pass
                for table in self.findChildren(QtWidgets.QTableWidget):
                    try:
                        headers = []
                        for c in range(table.columnCount()):
                            item = table.horizontalHeaderItem(c)
                            headers.append(translate_text(item.text() if item else '', lang))
                        if headers:
                            table.setHorizontalHeaderLabels(headers)
                    except Exception:
                        pass
                for tree in self.findChildren(QtWidgets.QTreeWidget):
                    try:
                        labels = [translate_text(tree.headerItem().text(i), lang) for i in range(tree.columnCount())]
                        tree.setHeaderLabels(labels)
                    except Exception:
                        pass
                for tabs in self.findChildren(QtWidgets.QTabWidget):
                    try:
                        for i in range(tabs.count()):
                            tabs.setTabText(i, translate_text(tabs.tabText(i), lang))
                    except Exception:
                        pass
            walk(self)
            for i in range(self.step_list.count()):
                self.step_list.item(i).setText(translate_text(self.step_list.item(i).text(), lang))
            self.progress_overall.setFormat(translate_text(self.progress_overall.format(), lang))
            self.progress_iter.setFormat(translate_text(self.progress_iter.format(), lang))
            self._update_validation()
            self._update_global_inspector()

        def _tt(self, text: str) -> str:
            return translate_text(text, self._lang)

        def _suggest_fix_lines(self, text: str) -> list[str]:
            lower = text.lower()
            fixes: list[str] = []
            if 'surface mesh' in lower or '表面网格' in text or '体网格' in text:
                fixes.append(self._tt('Suggestion: run the Meshing step first (voxel_hex8 or gmsh_tet).'))
            if 'material' in lower or '材料' in text:
                fixes.append(self._tt('Suggestion: assign materials to all active regions in Regions & Materials.'))
            if 'boundary' in lower or '约束' in text:
                fixes.append(self._tt('Suggestion: check default side/bottom displacement constraints or add missing BCs.'))
            if 'converge' in lower or '收敛' in text or 'newton' in lower:
                fixes.append(self._tt('Suggestion: reduce initial increment, increase max iterations, and keep line search enabled.'))
            if 'ifc' in lower or 'meshio' in lower or 'gmsh' in lower:
                fixes.append(self._tt('Suggestion: verify IFC import, then generate a valid volume mesh before solving.'))
            if not fixes:
                fixes.append(self._tt('Suggestion: open the Validation tab and fix all errors before solving again.'))
            return fixes

        def _on_toggle_inspector_requested(self, checked: bool) -> None:
            if checked:
                self._inspector_dismissed = False
                self.inspector_dock.setVisible(True)
            else:
                self._inspector_dismissed = True
                self.inspector_dock.setVisible(False)

        def _on_inspector_pin_toggled(self, checked: bool) -> None:
            self._inspector_pinned = checked
            if checked:
                self._inspector_dismissed = False
            self._update_inspector_collapse()

        def _inspector_has_explicit_selection(self) -> bool:
            if self.current_model is None:
                return False
            has_object_or_region = bool(self._selected_scene_payloads() or self._selected_region_names())
            stage_rows = False
            try:
                stage_rows = bool(self.stage_table.selectionModel() and self.stage_table.selectionModel().selectedRows() and self.stage_table.hasFocus())
            except Exception:
                stage_rows = False
            return bool(has_object_or_region or stage_rows)

        def _update_inspector_collapse(self) -> None:
            has_selection = self._inspector_has_explicit_selection()
            auto_collapse = bool(self.inspector_collapse.isChecked()) if hasattr(self, 'inspector_collapse') else False
            expanded = self._inspector_pinned or ((has_selection or not auto_collapse) and (not self._inspector_dismissed or self._inspector_pinned))
            self.inspector_stack.setCurrentIndex(1 if expanded else 0)
            if not expanded and hasattr(self, 'inspector_collapsed_label'):
                self.inspector_collapsed_label.setText(self._tt('Inspector (auto hidden)'))
            visible = True if self._inspector_pinned else (expanded if auto_collapse else not self._inspector_dismissed)
            self.inspector_dock.setVisible(bool(visible))
            if hasattr(self, 'act_toggle_inspector'):
                self.act_toggle_inspector.setChecked(self.inspector_dock.isVisible())

        def _selected_pickable_object_keys(self) -> list[str]:
            if self.current_model is None:
                return []
            visible = self.current_model.pickable_object_keys()
            return [k for k in self._selected_object_keys() if k in visible]

        def _on_scene_item_changed(self, item, column: int) -> None:
            if self.current_model is None:
                return
            payload = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if not payload:
                return
            kind, key = payload
            if kind != 'object':
                return
            if column == 0:
                state = item.checkState(0) == QtCore.Qt.CheckState.Checked
                self.current_model.set_object_visibility([key], state)
                self.refresh_view()
                self._update_global_inspector()
            elif column == 1:
                locked = item.checkState(1) == QtCore.Qt.CheckState.Checked
                self.current_model.set_object_locked([key], locked)
                self.refresh_view()
                self._update_global_inspector()
        def _set_visibility_for_keys(self, object_keys: list[str], visible: bool, isolate: bool = False) -> None:
            if self.current_model is None or not object_keys:
                return
            if isolate:
                visible_set = set(object_keys)
                for rec in self.current_model.object_records:
                    self.current_model.set_object_visibility([rec.key], rec.key in visible_set)
            else:
                self.current_model.set_object_visibility(object_keys, visible)
            self._sync_all_views()
            self._set_status(self._tt('Objects updated.'))

        def hide_selected_objects(self) -> None:
            keys = self._selected_object_keys()
            if not keys:
                self._set_status(self._tt('Please select one or more objects first.'))
                return
            self._set_visibility_for_keys(keys, False)

        def show_selected_objects(self) -> None:
            keys = self._selected_object_keys()
            if not keys:
                self._set_status(self._tt('Please select one or more objects first.'))
                return
            self.current_model.set_object_visibility(keys, True, pickable=True)
            self._sync_all_views()

        def isolate_selected_objects(self) -> None:
            keys = self._selected_object_keys()
            if not keys:
                self._set_status(self._tt('Please select one or more objects first.'))
                return
            self._set_visibility_for_keys(keys, True, isolate=True)

        def show_all_objects(self) -> None:
            if self.current_model is None:
                return
            self.current_model.show_all_objects()
            self._sync_all_views()

        def lock_selected_objects(self) -> None:
            if self.current_model is None:
                return
            keys = self._selected_object_keys()
            if not keys:
                self._set_status(self._tt('Please select one or more objects first.'))
                return
            self.current_model.set_object_locked(keys, True)
            self._sync_all_views()
            self._set_status(self._tt('Selected objects are now locked from 3D picking.'))

        def unlock_selected_objects(self) -> None:
            if self.current_model is None:
                return
            keys = self._selected_object_keys()
            if not keys:
                self._set_status(self._tt('Please select one or more objects first.'))
                return
            self.current_model.set_object_locked(keys, False)
            self._sync_all_views()
            self._set_status(self._tt('Selected objects are now unlocked for 3D picking.'))

        def _object_passes_selection_filter(self, object_key: str) -> bool:
            if self.current_model is None:
                return False
            rec = self.current_model.object_record(object_key)
            if rec is None:
                return False
            mode = self.selection_filter_combo.currentText() if hasattr(self, 'selection_filter_combo') else 'all'
            role = str(rec.metadata.get('role', '')).lower()
            if mode == 'all':
                return True
            if mode == 'visible_only':
                return bool(rec.visible) and (not rec.locked)
            if mode == 'structures':
                return role in {'wall', 'slab', 'beam', 'column', 'support'}
            if mode == 'soil':
                return role == 'soil'
            if mode == 'supports':
                return role in {'beam', 'column', 'support'}
            return True

        def _on_inspector_visibility_toggled(self, checked: bool) -> None:
            keys = self._selected_object_keys()
            if self.current_model is None or not keys:
                return
            self.current_model.set_object_visibility(keys, checked, pickable=self.inspector_pickable_check.isChecked())
            self._sync_all_views()

        def _on_inspector_pickable_toggled(self, checked: bool) -> None:
            if self.current_model is None:
                return
            keys = self._selected_object_keys()
            for rec in self.current_model.object_records:
                if rec.key in keys:
                    rec.pickable = checked and rec.visible and (not rec.locked)
            self.refresh_view()

        def _on_inspector_locked_toggled(self, checked: bool) -> None:
            if self.current_model is None:
                return
            keys = self._selected_object_keys()
            if not keys:
                return
            self.current_model.set_object_locked(keys, checked)
            self._sync_all_views()

        def apply_nudge_to_selected_objects(self) -> None:
            if self.current_model is None:
                return
            keys = self._selected_object_keys()
            if not keys:
                self._set_status(self._tt('No object is selected for 3D adjustment.'))
                return
            dx = float(self.inspector_nudge_dx.value()) if hasattr(self, 'inspector_nudge_dx') else 0.0
            dy = float(self.inspector_nudge_dy.value()) if hasattr(self, 'inspector_nudge_dy') else 0.0
            dz = float(self.inspector_nudge_dz.value()) if hasattr(self, 'inspector_nudge_dz') else 0.0
            moved = self.current_model.translate_object_blocks(keys, (dx, dy, dz))
            if moved <= 0:
                self._set_status(self._tt('3D adjustment is currently available for block-backed scene objects only.'))
                return
            self._sync_all_views()
            self._set_status(self._tt(f'Applied 3D nudge to {moved} object(s): Δ=({dx:g}, {dy:g}, {dz:g})'))

        def quick_nudge_selected_objects(self, axis: str, sign: float) -> None:
            step = float(self.inspector_nudge_step.value()) if hasattr(self, 'inspector_nudge_step') else 0.2
            dx = dy = dz = 0.0
            if axis == 'x':
                dx = sign * step
            elif axis == 'y':
                dy = sign * step
            else:
                dz = sign * step
            if hasattr(self, 'inspector_nudge_dx'):
                self.inspector_nudge_dx.setValue(dx)
                self.inspector_nudge_dy.setValue(dy)
                self.inspector_nudge_dz.setValue(dz)
            self.apply_nudge_to_selected_objects()

        def _on_pick_filter_changed(self, value: str) -> None:
            if hasattr(self, 'selection_filter_combo') and self.selection_filter_combo.currentText() != value:
                self.selection_filter_combo.blockSignals(True)
                self.selection_filter_combo.setCurrentText(value)
                self.selection_filter_combo.blockSignals(False)
            if hasattr(self, 'inspector_pick_filter_combo') and self.inspector_pick_filter_combo.currentText() != value:
                self.inspector_pick_filter_combo.blockSignals(True)
                self.inspector_pick_filter_combo.setCurrentText(value)
                self.inspector_pick_filter_combo.blockSignals(False)
            self._set_status(f'Pick filter set to {value}.')

        # ---------- Logging / status ----------
        def _log(self, text: str) -> None:
            self.log_text.appendPlainText(self._tt(text))

        def _set_status(self, text: str) -> None:
            msg = self._tt(text)
            self.status_label.setText(msg)
            self.solver_note.setText(msg)
            self._log(msg)

        def _mesh_summary_text(self, model: SimulationModel | None) -> str:
            if model is None:
                return ''
            summary = dict(getattr(model, 'metadata', {}).get('mesh_summary', {}) or {})
            try:
                grid = model.to_unstructured_grid()
                summary.setdefault('cells', int(getattr(grid, 'n_cells', 0) or 0))
                summary.setdefault('points', int(getattr(grid, 'n_points', 0) or 0))
            except Exception:
                pass
            summary.setdefault('regions', len(getattr(model, 'region_tags', []) or []))
            method = str(summary.get('method', getattr(model, 'metadata', {}).get('meshed_by', 'mesh')))
            parts = [f"{method}: {int(summary.get('cells', 0) or 0)} cells", f"{int(summary.get('points', 0) or 0)} points", f"{int(summary.get('regions', 0) or 0)} regions"]
            if 'object_count' in summary:
                parts.append(f"objects {int(summary.get('objects_succeeded', summary.get('object_count', 0)) or 0)}/{int(summary.get('object_count', 0) or 0)}")
            if 'elapsed_seconds' in summary:
                parts.append(f"elapsed {float(summary.get('elapsed_seconds', 0.0)):.2f}s")
            return ', '.join(parts)

        def _extract_meshing_failure_details(self, error_text: str) -> tuple[str, str]:
            lines = [line.strip() for line in str(error_text).splitlines() if line.strip()]
            if not lines:
                return self._tt('Meshing failed.'), self._tt('Review the traceback in the log pane.')
            detail = lines[-1]
            lower = detail.lower()
            remedy = self._tt('Review the traceback in the log pane.')
            if 'background voxel grid would be too large' in lower:
                remedy = self._tt('Increase the mesh size / cell size, reduce padding, or voxelize large objects separately.')
            elif 'no interior cells were selected' in lower or 'open/non-manifold' in lower or 'watertight' in lower:
                remedy = self._tt('The object is likely not a closed solid. Repair the IFC/body geometry or use a coarser voxel size.')
            elif 'surface extraction returned no usable faces' in lower or 'effectively zero' in lower:
                remedy = self._tt('The selected object is empty or too thin for volume meshing. Check visibility, thickness, and source geometry.')
            elif 'gmsh executable was not found' in lower:
                remedy = self._tt('Install gmsh and ensure it is available on PATH, or switch to voxel_hex8.')
            elif 'meshio is not installed' in lower:
                remedy = self._tt('Install meshio / meshing dependencies before using gmsh_tet.')
            elif 'failed while recovering the volume' in lower or 'non-manifold' in lower:
                remedy = self._tt('Repair self-intersections/open shells, then retry gmsh_tet or switch to voxel_hex8.')
            return detail, remedy

        def _solver_settings(self) -> SolverSettings:
            try:
                tol = float(self.solver_tol_edit.text().strip())
            except Exception:
                tol = 1.0e-5
            prefs = self._read_solver_compute_preferences()
            requested_device = prefs.resolved_device(getattr(self, '_cuda_available', False))
            tc = prefs.resolved_thread_count(getattr(self, '_cpu_core_total', None))
            settings = SolverSettings(
                backend=prefs.backend,
                prefer_sparse=self.solver_prefer_sparse.isChecked(),
                line_search=self.solver_line_search.isChecked(),
                max_cutbacks=int(self.solver_max_cutbacks_spin.value()),
                max_iterations=int(self.solver_max_iter_spin.value()),
                tolerance=tol,
                device=requested_device,
                thread_count=tc,
            )
            settings.metadata.update(prefs.to_metadata(cuda_available=getattr(self, '_cuda_available', False)))
            if self.current_model is not None:
                self.current_model.metadata['solver_settings'] = {
                    'backend': settings.backend,
                    'max_iterations': settings.max_iterations,
                    'tolerance': settings.tolerance,
                    'max_cutbacks': settings.max_cutbacks,
                    'prefer_sparse': settings.prefer_sparse,
                    'line_search': settings.line_search,
                    'device': settings.device,
                    'thread_count': settings.thread_count,
                    **settings.metadata,
                }
            return settings

        def _infer_role_for_record(self, rec: GeometryObjectRecord) -> str:
            if rec.metadata.get('role'):
                return str(rec.metadata.get('role'))
            typ = rec.object_type or ''
            name = rec.name or ''
            if 'Wall' in typ:
                return 'wall'
            if 'Slab' in typ:
                return 'slab'
            if 'Beam' in typ:
                return 'beam'
            if 'Column' in typ:
                return 'column'
            if 'Excavation' in name or 'Shell' in name:
                return 'soil'
            if 'Proxy' in typ:
                return 'support'
            return 'soil'

        def _clear_diagnostics(self) -> None:
            self._diagnostic_rows = []
            if hasattr(self, 'diagnostics_table'):
                self.diagnostics_table.setRowCount(0)

        def _append_diagnostic(self, severity: str, source: str, message: str, remedy: str = '') -> None:
            row_data = (severity, source, message, remedy)
            self._diagnostic_rows.append(row_data)
            if not hasattr(self, 'diagnostics_table'):
                return
            row = self.diagnostics_table.rowCount()
            self.diagnostics_table.insertRow(row)
            for col, value in enumerate(row_data):
                item = QtWidgets.QTableWidgetItem(self._tt(str(value)))
                if col == 0:
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, {'severity': severity, 'source': source, 'message': message, 'remedy': remedy})
                self.diagnostics_table.setItem(row, col, item)

        def _sync_diagnostics_from_validation(self, issues=None) -> None:
            if issues is None:
                issues = validate_model(self.current_model)
            self._clear_diagnostics()
            for issue in issues:
                remedy = ''
                lower = issue.message.lower()
                if '材料' in issue.message or 'material' in lower:
                    remedy = self._tt('Assign materials to all active regions or accept automatic material templates.')
                elif '网格' in issue.message or 'mesh' in lower or '体网格' in issue.message:
                    remedy = self._tt('Run the Meshing workflow and generate a volume mesh before solving.')
                elif '阶段' in issue.message or 'stage' in lower:
                    remedy = self._tt('Review active/inactive regions and remove conflicts in the current stage.')
                elif '边界' in issue.message or 'boundary' in lower:
                    remedy = self._tt('Apply side and bottom displacement constraints or use the default boundary assignment.')
                self._append_diagnostic(issue.level, issue.step, issue.message, remedy)

        def _selected_suggestion_rows(self) -> list[int]:
            if not hasattr(self, 'suggestion_table'):
                return []
            rows = sorted({idx.row() for idx in self.suggestion_table.selectionModel().selectedRows()})
            if not rows and self.suggestion_table.currentRow() >= 0:
                rows = [self.suggestion_table.currentRow()]
            return rows

        def _populate_suggestion_table(self) -> None:
            if not hasattr(self, 'suggestion_table'):
                return
            self.suggestion_table.setRowCount(0)
            for row, sug in enumerate(self._latest_suggestions):
                self.suggestion_table.insertRow(row)
                apply_item = QtWidgets.QTableWidgetItem('')
                apply_item.setFlags(apply_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                decision = self._suggestion_decisions.get(sug.object_key, True)
                apply_item.setCheckState(QtCore.Qt.CheckState.Checked if decision is not False else QtCore.Qt.CheckState.Unchecked)
                self.suggestion_table.setItem(row, 0, apply_item)
                values = [sug.object_key, sug.role, sug.region_name or '-', sug.material_definition or '-', sug.reason, 'accepted' if decision is not False else 'rejected']
                for offset, value in enumerate(values, start=1):
                    self.suggestion_table.setItem(row, offset, QtWidgets.QTableWidgetItem(str(value)))
            self.suggestion_table.resizeColumnsToContents()

        def build_ifc_suggestion_panel(self) -> None:
            if self.current_model is None:
                return
            self._ensure_default_material_library()
            self._latest_suggestions = build_suggestions(self.current_model)
            self._suggestion_decisions = {s.object_key: True for s in self._latest_suggestions}
            self._populate_suggestion_table()
            if self._latest_suggestions:
                mapped = sum(1 for s in self._latest_suggestions if s.material_definition)
                self.suggestion_summary_label.setText(self._tt(f'Generated {len(self._latest_suggestions)} suggestions; {mapped} include material templates.'))
            else:
                self.suggestion_summary_label.setText(self._tt('No automatic suggestions are available for the current model.'))

        def accept_selected_suggestions(self) -> None:
            for row in self._selected_suggestion_rows():
                if 0 <= row < len(self._latest_suggestions):
                    self._suggestion_decisions[self._latest_suggestions[row].object_key] = True
            self._populate_suggestion_table()

        def reject_selected_suggestions(self) -> None:
            for row in self._selected_suggestion_rows():
                if 0 <= row < len(self._latest_suggestions):
                    self._suggestion_decisions[self._latest_suggestions[row].object_key] = False
            self._populate_suggestion_table()

        def apply_accepted_suggestions(self) -> None:
            if self.current_model is None or not self._latest_suggestions:
                return
            accepted = [k for k, v in self._suggestion_decisions.items() if v is not False]
            applied = apply_suggestion_subset(self.current_model, self._latest_suggestions, accepted, assign_materials=True)
            self._sync_all_views()
            self._populate_suggestion_table()
            self.suggestion_summary_label.setText(self._tt(f'Applied {len(applied)} accepted suggestions.'))

        def _selection_bounds_from_pick(self, picked) -> tuple[float, float, float, float, float, float] | None:
            try:
                b = getattr(picked, 'bounds', None)
                if b is not None and len(b) == 6:
                    return tuple(float(x) for x in b)
            except Exception:
                pass
            if isinstance(picked, (list, tuple)) and len(picked) == 6:
                try:
                    return tuple(float(x) for x in picked)
                except Exception:
                    return None
            return None

        def _bounds_intersect(self, a, b) -> bool:
            if not a or not b or len(a) != 6 or len(b) != 6:
                return False
            return not (a[1] < b[0] or a[0] > b[1] or a[3] < b[2] or a[2] > b[3] or a[5] < b[4] or a[4] > b[5])

        def _apply_multi_selection_from_pick(self, picked, additive: bool = True) -> None:
            bounds = self._selection_bounds_from_pick(picked)
            if bounds is None or self.current_model is None:
                return
            keys = []
            pickable = self.current_model.pickable_object_keys()
            for meta in self._viewer_actor_map.values():
                object_key = str(meta.get('object_key') or '')
                if not object_key or object_key not in pickable:
                    continue
                if self._bounds_intersect(meta.get('bounds'), bounds):
                    keys.append(object_key)
            if not keys:
                self._set_status('No pickable object was found inside the current selection window.')
                return
            for key in keys:
                self._select_scene_payload('object', key, additive=additive)
            self._set_status(f'Selected {len(keys)} objects from the 3D selection window.')

        def activate_box_selection(self) -> None:
            try:
                self.plotter.enable_rectangle_picking(callback=lambda picked: self._apply_multi_selection_from_pick(picked, additive=True), show_frustum=False)
                self._set_status('Box selection is active. Drag a rectangle in the 3D view.')
            except Exception as exc:
                self._log(f'Box selection is unavailable: {exc}')
                self._set_status('Box selection is unavailable in the current visualization backend.')

        def activate_lasso_selection(self) -> None:
            try:
                if hasattr(self.plotter, 'enable_path_picking'):
                    self.plotter.enable_path_picking(callback=lambda picked: self._apply_multi_selection_from_pick(picked, additive=True), show_message=False)
                    self._set_status('Lasso selection is active. Draw a closed path in the 3D view.')
                else:
                    self.activate_box_selection()
                    self._set_status('Lasso selection is not available; box selection has been enabled instead.')
            except Exception as exc:
                self._log(f'Lasso selection is unavailable: {exc}')
                self.activate_box_selection()

        def clear_all_selection(self) -> None:
            try:
                self.scene_tree.clearSelection()
            except Exception:
                pass
            self._highlight_regions = []
            self._highlight_blocks = []
            self.refresh_view()
            self._update_global_inspector()

        def _apply_default_object_roles(self) -> None:
            if self.current_model is None:
                return
            for rec in self.current_model.object_records:
                rec.metadata.setdefault('role', self._infer_role_for_record(rec))

        def _populate_suggestion_table(self) -> None:
            if not hasattr(self, 'suggestion_table'):
                return
            self.suggestion_table.setRowCount(0)
            for row, sug in enumerate(self._latest_suggestions):
                if sug.object_key in self._rejected_suggestion_keys:
                    continue
                row_idx = self.suggestion_table.rowCount()
                self.suggestion_table.insertRow(row_idx)
                use_item = QtWidgets.QTableWidgetItem('')
                use_item.setFlags(use_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled)
                use_item.setCheckState(QtCore.Qt.CheckState.Checked)
                use_item.setData(QtCore.Qt.ItemDataRole.UserRole, sug.object_key)
                self.suggestion_table.setItem(row_idx, 0, use_item)
                rec = self.current_model.object_record(sug.object_key) if self.current_model else None
                values = [rec.name if rec else sug.object_key, sug.role, sug.region_name or '', sug.material_definition or '', sug.reason]
                for col, value in enumerate(values, start=1):
                    self.suggestion_table.setItem(row_idx, col, QtWidgets.QTableWidgetItem(str(value)))

        def _checked_suggestion_keys(self) -> list[str]:
            keys: list[str] = []
            if not hasattr(self, 'suggestion_table'):
                return keys
            for row in range(self.suggestion_table.rowCount()):
                item = self.suggestion_table.item(row, 0)
                if item and item.checkState() == QtCore.Qt.CheckState.Checked:
                    key = str(item.data(QtCore.Qt.ItemDataRole.UserRole) or '')
                    if key:
                        keys.append(key)
            return keys

        def apply_selected_suggestions(self) -> None:
            if self.current_model is None:
                return
            keys = self._checked_suggestion_keys()
            if not keys:
                self._set_status('No suggestion rows are checked.')
                return
            self._ensure_default_material_library()
            applied = apply_suggestion_subset(self.current_model, self._latest_suggestions, accepted_keys=keys, assign_materials=True)
            self._latest_suggestions = [s for s in self._latest_suggestions if s.object_key not in set(keys)]
            self._populate_suggestion_table()
            self._sync_all_views()
            self._set_status(f'Applied {len(applied)} selected IFC suggestions.')

        def reject_selected_suggestions(self) -> None:
            keys = self._checked_suggestion_keys()
            if not keys:
                self._set_status('No suggestion rows are checked.')
                return
            self._rejected_suggestion_keys.update(keys)
            self._latest_suggestions = [s for s in self._latest_suggestions if s.object_key not in set(keys)]
            self._populate_suggestion_table()
            self._set_status(f'Rejected {len(keys)} suggestion rows.')

        def accept_all_suggestions(self) -> None:
            if self.current_model is None:
                return
            self._ensure_default_material_library()
            applied = apply_suggestion_subset(self.current_model, self._latest_suggestions, assign_materials=True)
            self._latest_suggestions = []
            self._populate_suggestion_table()
            self._sync_all_views()
            self._set_status(f'Applied all IFC suggestions ({len(applied)} items).')

        def apply_ifc_role_material_suggestions(self) -> None:
            if self.current_model is None:
                return
            self._ensure_default_material_library()
            suggestions = apply_suggestions(self.current_model, assign_materials=True)
            self._latest_suggestions = []
            self._populate_suggestion_table()
            if suggestions:
                mapped = sum(1 for s in suggestions if s.material_definition)
                self.suggestion_summary_label.setText(f'Applied {len(suggestions)} automatic suggestions, including {mapped} material assignments.')
            else:
                self.suggestion_summary_label.setText('No IFC suggestions are currently available.')
            self._sync_all_views()
            self._set_status('Applied IFC role/material suggestions.')

        def _apply_default_boundary_conditions(self, announce: bool = False) -> None:
            if self.current_model is None:
                return
            added = ensure_default_global_bcs(self.current_model)
            if added and announce:
                self._set_status('已自动赋默认边界条件：四周与底部位移固定。')

        def _estimate_progress_fraction(self, payload: dict) -> float:
            explicit = payload.get('fraction', payload.get('stage_fraction', None))
            stage_index = int(payload.get('stage_index', 1) or 1)
            stage_count = max(1, int(payload.get('stage_count', 1) or 1))
            if explicit is not None:
                try:
                    inner = max(0.0, min(0.999, float(explicit)))
                    return min(0.999, ((stage_index - 1) + inner) / stage_count)
                except Exception:
                    pass
            step = int(payload.get('step', 1) or 1)
            iteration = int(payload.get('iteration', 0) or 0)
            phase = str(payload.get('phase', '') or '')
            if phase == 'stage-complete':
                return stage_index / stage_count
            phase_bias = {
                'worker-start': 0.01,
                'stage-start': 0.02,
                'step-start': 0.04,
                'iteration-start': 0.06,
                'assembly-start': 0.08,
                'assembly-done': 0.18,
                'linear-solve-start': 0.22,
                'linear-solve-done': 0.32,
                'line-search-start': 0.36,
                'line-search-done': 0.42,
            }.get(phase, 0.0)
            inner = min(0.95, phase_bias + (max(step, 1) - 1) * 0.12 + min(iteration, 12) / 12.0 * 0.12)
            return min(0.99, ((stage_index - 1) + inner) / stage_count)

        # ---------- Project/model helpers ----------
        def _default_material_definitions(self) -> list[MaterialDefinition]:
            return [
                MaterialDefinition(name='Soil_MC', model_type='mohr_coulomb', parameters=dict(MATERIAL_SPECS['mohr_coulomb']), metadata={'preset': 'soil'}),
                MaterialDefinition(name='Soil_HSsmall', model_type='hs_small', parameters=dict(MATERIAL_SPECS['hs_small']), metadata={'preset': 'soil'}),
                MaterialDefinition(name='Wall_Elastic', model_type='linear_elastic', parameters=dict(MATERIAL_SPECS['linear_elastic']), metadata={'preset': 'structure'}),
            ]

        def _populate_material_model_combo(self) -> None:
            self.material_model_combo.clear()
            available = registry.available() or list(MATERIAL_SPECS)
            for name in sorted(set(available) | set(MATERIAL_SPECS)):
                self.material_model_combo.addItem(name)

        def _rebuild_material_param_form(self, model_type: str | None = None, params: dict[str, Any] | None = None) -> None:
            while self.material_param_form.rowCount() > 0:
                self.material_param_form.removeRow(0)
            self._material_param_inputs.clear()
            model_type = model_type or self.material_model_combo.currentText() or 'linear_elastic'
            for key, default in MATERIAL_SPECS.get(model_type, MATERIAL_SPECS['linear_elastic']):
                widget = QtWidgets.QLineEdit(str(params.get(key, default) if params else default))
                widget.textChanged.connect(self._refresh_form_validation)
                self.material_param_form.addRow(key, widget)
                self._material_param_inputs[key] = widget
            self._refresh_form_validation()

        def _collect_material_parameters(self) -> dict[str, float]:
            out: dict[str, float] = {}
            for key, widget in self._material_param_inputs.items():
                try:
                    out[key] = float(widget.text())
                except Exception:
                    out[key] = 0.0
            return out

        def _ensure_default_material_library(self) -> None:
            if self.current_model is None:
                return
            if not self.current_model.material_library:
                for item in self._default_material_definitions():
                    self.current_model.upsert_material_definition(item)

        def _create_demo_object_records(self, model: SimulationModel) -> None:
            model.object_records = [
                GeometryObjectRecord(key='soil', name='soil', object_type='Volume', region_name='soil', source_block='soil', metadata={'source': 'parametric'}),
                GeometryObjectRecord(key='retaining_wall', name='retaining_wall', object_type='RetainingWall', region_name='wall', source_block='retaining_wall', metadata={'source': 'parametric'}),
            ]

        def create_demo(self) -> None:
            if self._apply_validation_result('geometry', self._validate_geometry_form(), block=True, title='参数化几何校验失败'):
                return
            scene = ParametricPitScene(**{name: widget.value() for name, widget in self._param_inputs.items()})
            data = scene.build()
            model = SimulationModel(name='pit-demo', mesh=data)
            model.metadata['source'] = 'parametric_pit'
            model.metadata['parametric_scene'] = {k: float(v.value()) if hasattr(v, 'decimals') else int(v.value()) for k, v in self._param_inputs.items()}
            model.ensure_regions()
            self._create_demo_object_records(model)
            self.current_model = model
            self._apply_default_object_roles()
            for item in self._default_material_definitions():
                model.upsert_material_definition(item)
            model.assign_material_definition(['soil'], 'Soil_MC')
            model.assign_material_definition(['wall'], 'Wall_Elastic')
            activation_map = {region.name: True for region in model.region_tags}
            model.stages = [
                AnalysisStage(name='initial', steps=4, metadata={'activation_map': dict(activation_map), 'initial_increment': 0.25, 'max_iterations': 24, 'line_search': True}),
                AnalysisStage(name='excavate_level_1', steps=6, metadata={'activation_map': dict(activation_map), 'initial_increment': 0.25, 'max_iterations': 24, 'line_search': True}),
                AnalysisStage(name='excavate_level_2', steps=6, metadata={'activation_map': dict(activation_map), 'initial_increment': 0.25, 'max_iterations': 24, 'line_search': True}),
            ]
            self._apply_default_boundary_conditions()
            self._sync_all_views()
            self._set_status('已创建参数化基坑示例。')

        def import_ifc(self) -> None:
            filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Open IFC', str(Path.cwd()), 'IFC files (*.ifc)')
            if not filename:
                return
            if self._apply_validation_result('ifc', self._validate_ifc_form(file_path=filename), block=True, title='IFC 导入参数校验失败'):
                return
            try:
                include = tuple(s.strip() for s in self.ifc_include_entities_edit.text().split(',') if s.strip())
                options = IfcImportOptions(
                    include_entities=include,
                    apply_default_materials=self.ifc_apply_default_materials.isChecked(),
                    extract_property_sets=self.ifc_extract_psets.isChecked(),
                    region_strategy=self.ifc_region_strategy_combo.currentText(),
                    use_world_coords=self.ifc_use_world_coords.isChecked(),
                    weld_vertices=self.ifc_weld_vertices.isChecked(),
                    include_openings=self.ifc_include_openings.isChecked(),
                )
                blocks, records, summary = IfcImporter(filename, options).load_model_data()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, 'IFC 导入失败', str(exc))
                self._log(traceback.format_exc())
                return
            model = SimulationModel(name=Path(filename).stem, mesh=blocks)
            model.metadata['source'] = 'ifc'
            model.metadata['ifc_summary'] = summary
            model.object_records = records
            self.current_model = model
            self._apply_default_object_roles()
            model.ensure_regions()
            for item in self._default_material_definitions():
                model.upsert_material_definition(item)
            self._latest_suggestions = build_suggestions(model)
            self._rejected_suggestion_keys.clear()
            self._populate_suggestion_table()
            if self._latest_suggestions:
                mapped = sum(1 for s in self._latest_suggestions if s.material_definition)
                self.suggestion_summary_label.setText(f'Generated {len(self._latest_suggestions)} IFC suggestions, including {mapped} material suggestions.')
            self._sync_all_views()
            self._set_status(f'已导入 IFC: {filename} | objects={summary.get("n_objects", 0)}。请继续执行网格划分。')

        def voxelize_current(self) -> None:
            if self.current_model is None:
                self._set_status('请先创建或导入模型。')
                return
            value = float(self.mesh_size_spin.value()) if hasattr(self, 'mesh_size_spin') else 2.0
            self._set_status(f'开始体素化，cell size={value:g} ...')
            mesher = VoxelMesher(VoxelizeOptions(cell_size=float(value), padding=float(self.mesh_padding_spin.value()) if hasattr(self, 'mesh_padding_spin') else 0.0))
            self.current_model = mesher.voxelize_model(self.current_model)
            self.current_model.ensure_regions()
            self._sync_all_views()
            if hasattr(self, 'mesh_show_edges_check'): self.mesh_show_edges_check.setChecked(True)
            self.run_mesh_check()
            self._set_status(f'体素化完成，cell size={value:g}')

        def run_meshing_workflow(self) -> None:
            if self.current_model is None:
                self._set_status('请先创建或导入模型。')
                return
            method = self.mesh_method_combo.currentText() if hasattr(self, 'mesh_method_combo') else 'voxel_hex8'
            h = float(self.mesh_size_spin.value()) if hasattr(self, 'mesh_size_spin') else 2.0
            if method == 'gmsh_tet':
                try:
                    self.current_model = GmshMesher(GmshMesherOptions(element_size=h)).mesh_model(self.current_model)
                    self.current_model.ensure_regions()
                    self._sync_all_views()
                    if hasattr(self, 'mesh_show_edges_check'): self.mesh_show_edges_check.setChecked(True)
                    self.run_mesh_check()
                    self._set_status(f'Gmsh 网格划分完成，size={h:g}')
                    return
                except Exception as exc:
                    QtWidgets.QMessageBox.warning(self, 'Gmsh 网格划分失败', f'{exc}\n将回退到体素化流程。')
                    self._log(traceback.format_exc())
            self.voxelize_current()

        def _on_meshing_progress(self, payload: object) -> None:
            if not isinstance(payload, dict):
                return
            self._last_meshing_payload = dict(payload)
            value = int(payload.get('value', 0) or 0)
            message = str(payload.get('message', 'Meshing...'))
            phase = str(payload.get('phase', ''))
            self._update_meshing_progress_dialog(value, message)
            self.status_label.setText(self._tt(message))
            self._update_task_status(self._tt('Running'), message)
            if payload.get('log') or phase in {'object-complete', 'object-failed', 'object-warning', 'gmsh-object-complete', 'gmsh-object-failed', 'gmsh-fallback'}:
                self._log(message)
            if phase in {'object-failed', 'gmsh-object-failed'}:
                self._append_diagnostic('error', 'mesh', message, self._tt(str(payload.get('hint', 'Check object geometry closure, mesh size, and meshing dependencies.'))))
            elif phase in {'object-warning', 'gmsh-fallback'}:
                self._append_diagnostic('warning', 'mesh', message, self._tt(str(payload.get('hint', 'Review logs and consider switching meshing method.'))))

        def _on_meshing_finished(self, meshed_model: object, method: str) -> None:
            self.current_model = meshed_model
            self._meshing_heartbeat_timer.stop()
            summary_text = self._mesh_summary_text(self.current_model)
            self._update_meshing_progress_dialog(100, self._tt('Meshing finished'))
            self._sync_all_views()
            if hasattr(self, 'mesh_show_edges_check'):
                self.mesh_show_edges_check.setChecked(True)
            self.run_mesh_check()
            self._set_status(self._tt(f'{method} meshing finished. {summary_text}'))
            self._update_task_status(self._tt('Completed'), self._tt(f'{method} meshing finished. {summary_text}'), self._tt('Review mesh statistics, region counts, and quality indicators before solving.'))
            self._log(summary_text)
            for warning in (self.current_model.metadata.get('mesh_warnings', []) or [])[:8]:
                self._append_diagnostic('warning', 'mesh', str(warning), self._tt('Review the object and meshing method; warnings may indicate coarse fallback or geometry defects.'))
            self._close_meshing_progress_dialog()

        def _on_meshing_failed(self, error_text: str) -> None:
            self._meshing_heartbeat_timer.stop()
            self._update_task_status(self._tt('Failed'), self._tt('Meshing failed; see logs and diagnostics.'), self._tt('Try voxel_hex8, check IFC closure, or verify local gmsh/meshio availability.'))
            self._append_diagnostic('error', 'mesh', self._tt('Meshing failed; see logs and diagnostics.'), self._tt('Try voxel_hex8, check IFC closure, or verify local gmsh/meshio availability.'))
            self._log(error_text)
            QtWidgets.QMessageBox.critical(self, self._tt('Meshing failed'), self._tt('Meshing failed. Please review the traceback and diagnostics.') + '\n\n' + error_text.splitlines()[-1])
            self._set_status(self._tt('Meshing failed'))
            self._close_meshing_progress_dialog()

        def _cleanup_meshing_thread(self) -> None:
            self._meshing_worker = None
            self._meshing_thread = None
            self._meshing_started_at = None
            self._last_meshing_payload = None
            self.btn_voxelize.setEnabled(True); self.btn_import_ifc.setEnabled(True); self.btn_build_parametric.setEnabled(True)
            self._meshing_heartbeat_timer.stop()

        # ---------- Populate UI ----------
        def _refresh_scene_tree(self) -> None:
            self.scene_tree.blockSignals(True)
            self.scene_tree.clear()
            if self.current_model is None:
                self.scene_tree.blockSignals(False)
                return
            root = QtWidgets.QTreeWidgetItem(['', '', self.current_model.name, self.current_model.metadata.get('source', '-')])
            self.scene_tree.addTopLevelItem(root)
            if self.current_model.object_records:
                for rec in self.current_model.object_records:
                    label = rec.name or rec.key
                    info = (rec.region_name or rec.metadata.get('role') or rec.object_type)
                    item = QtWidgets.QTreeWidgetItem(['', '', label, info])
                    item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ('object', rec.key))
                    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0, QtCore.Qt.CheckState.Checked if rec.visible else QtCore.Qt.CheckState.Unchecked)
                    item.setCheckState(1, QtCore.Qt.CheckState.Checked if getattr(rec, 'locked', False) else QtCore.Qt.CheckState.Unchecked)
                    color = QtGui.QColor(_color_for_type(rec.metadata.get('role'), rec.object_type))
                    item.setBackground(2, color.lighter(165))
                    item.setForeground(3, QtGui.QBrush(color.darker(170) if rec.visible else QtGui.QColor('#9e9e9e')))
                    if not rec.visible:
                        font = item.font(2); font.setStrikeOut(True); item.setFont(2, font)
                    if getattr(rec, 'locked', False):
                        item.setForeground(2, QtGui.QBrush(QtGui.QColor('#8e24aa')))
                    root.addChild(item)
            else:
                mesh = self.current_model.mesh
                if hasattr(mesh, 'keys'):
                    for name in mesh.keys():
                        block = mesh[name]
                        if block is None:
                            continue
                        item = QtWidgets.QTreeWidgetItem(['', '', str(name), f'cells={getattr(block, "n_cells", 0)}'])
                        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ('block', str(name)))
                        root.addChild(item)
            region_root = QtWidgets.QTreeWidgetItem(['', '', 'Regions', f'n={len(self.current_model.region_tags)}'])
            root.addChild(region_root)
            for region in self.current_model.region_tags:
                item = QtWidgets.QTreeWidgetItem(['', '', f'region:{region.name}', f'cells={len(region.cell_ids)}'])
                item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ('region', region.name))
                region_root.addChild(item)
            root.setExpanded(True)
            region_root.setExpanded(True)
            self._refresh_region_target_widgets()
            self.scene_tree.blockSignals(False)
        def _populate_project_info(self) -> None:
            if self.current_model is None:
                self.project_name_label.setText('未载入'); self.project_stats_label.setText('-'); self.project_source_label.setText('-'); self.project_schema_label.setText('-')
                self.project_summary_table.setRowCount(0)
                if hasattr(self, 'mesh_check_table'):
                    self.mesh_check_table.setRowCount(0)
                if hasattr(self, 'mesh_stats_label'):
                    self.mesh_stats_label.setText('-')
                if hasattr(self, 'result_mesh_summary'):
                    self.result_mesh_summary.setText('-')
                return
            mesh = self.current_model.mesh
            self.project_name_label.setText(self.current_model.name)
            report = analyze_mesh(self.current_model)
            self.project_stats_label.setText(report.summary_text())
            if hasattr(self, 'result_mesh_summary'):
                self.result_mesh_summary.setText(report.summary_text())
            if hasattr(self, 'mesh_stats_label'):
                self.mesh_stats_label.setText(report.summary_text())
            self._populate_mesh_check_table(report)
            self.project_source_label.setText(str(self.current_model.metadata.get('source', '-')))
            self.project_schema_label.setText(str(self.current_model.metadata.get('ifc_summary', {}).get('schema', '-')))
            self.project_summary_table.setRowCount(0)
            summary = self.current_model.metadata.get('ifc_summary', {}) if self.current_model else {}
            rows = [
                ('Objects', str(len(self.current_model.object_records))),
                ('Stages', str(len(self.current_model.stages))),
                ('Materials', str(len(self.current_model.material_library))),
                ('Assignments', str(len(self.current_model.materials))),
            ]
            for k, v in summary.get('counts_by_type', {}).items():
                rows.append((f'IFC {k}', str(v)))
            for idx, (k, v) in enumerate(rows):
                self.project_summary_table.insertRow(idx)
                self.project_summary_table.setItem(idx, 0, QtWidgets.QTableWidgetItem(k))
                self.project_summary_table.setItem(idx, 1, QtWidgets.QTableWidgetItem(v))

        def _populate_mesh_check_table(self, report: MeshCheckReport | None) -> None:
            if not hasattr(self, 'mesh_check_table'):
                return
            self.mesh_check_table.setRowCount(0)
            if report is None:
                return
            for row, info in enumerate(report.regions):
                self.mesh_check_table.insertRow(row)
                center_txt = '-' if info.center is None else f'({info.center[0]:.2f}, {info.center[1]:.2f}, {info.center[2]:.2f})'
                bounds_txt = '-' if info.bounds is None else f'[{info.bounds[0]:.2f},{info.bounds[1]:.2f}] x [{info.bounds[2]:.2f},{info.bounds[3]:.2f}] x [{info.bounds[4]:.2f},{info.bounds[5]:.2f}]'
                vals = [info.region_name, str(info.cells), str(info.bad_cells), '-' if info.min_volume is None else f'{info.min_volume:.3e}', '-' if info.max_aspect_ratio is None else f'{info.max_aspect_ratio:.2f}', f'{center_txt} | {bounds_txt}']
                for col, value in enumerate(vals):
                    self.mesh_check_table.setItem(row, col, QtWidgets.QTableWidgetItem(value))
            self.mesh_check_table.resizeColumnsToContents()

        def run_mesh_check(self) -> None:
            if self.current_model is None:
                self._set_status(self._tt('Please create or import a model first.'))
                return
            report = analyze_mesh(self.current_model)
            self._last_mesh_report = report
            self.mesh_stats_label.setText(report.summary_text())
            if hasattr(self, 'mesh_quality_label'):
                self.mesh_quality_label.setText(report.quality_summary or '-')
            if hasattr(self, 'result_mesh_summary'):
                self.result_mesh_summary.setText(report.summary_text())
            self._populate_mesh_check_table(report)
            for msg in report.messages:
                self._append_diagnostic('error', 'mesh', msg, self._tt('Generate a valid volume mesh before solving.'))
            for msg in report.warnings:
                self._append_diagnostic('warning', 'mesh', msg, self._tt('Review mesh statistics and region extraction before solving.'))
            if report.bad_cell_ids and hasattr(self, 'result_view_mode_combo'):
                self.result_view_mode_combo.setCurrentText('mesh_quality')
            if report.ok:
                QtWidgets.QMessageBox.information(self, self._tt('Mesh check'), report.summary_text())
                self._set_status(self._tt('Mesh check completed.'))
            else:
                QtWidgets.QMessageBox.warning(self, self._tt('Mesh check found issues'), '\n'.join(report.messages + report.warnings[:6]))
                self._set_status(self._tt('Mesh check found issues.'))
            self.refresh_view()

        def _populate_region_table(self) -> None:
            self.region_table.setRowCount(0)
            if self.current_model is None:
                return
            self.current_model.ensure_regions()
            for row, region in enumerate(self.current_model.region_tags):
                self.region_table.insertRow(row)
                binding = self.current_model.material_for_region(region.name)
                material_name = binding.material_name if binding else ''
                library_name = binding.metadata.get('library_name', '') if binding else ''
                status = '已赋值' if binding else '未赋值'
                center_txt, bounds_txt = '-', '-'
                try:
                    grid = self.current_model.to_unstructured_grid()
                    sub = grid.extract_cells(region.cell_ids)
                    if int(getattr(sub, 'n_cells', 0) or 0) > 0:
                        b = tuple(float(x) for x in sub.bounds)
                        center_txt = f'({(b[0]+b[1])/2:.2f}, {(b[2]+b[3])/2:.2f}, {(b[4]+b[5])/2:.2f})'
                        bounds_txt = f'[{b[0]:.2f},{b[1]:.2f}] x [{b[2]:.2f},{b[3]:.2f}] x [{b[4]:.2f},{b[5]:.2f}]'
                except Exception:
                    pass
                values = [region.name, str(len(region.cell_ids)), center_txt, bounds_txt, material_name, library_name, status]
                for col, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(value)
                    if col == 6:
                        item.setForeground(QtGui.QColor('#2e7d32') if binding else QtGui.QColor('#c62828'))
                    self.region_table.setItem(row, col, item)
            self.region_table.resizeColumnsToContents()
            self._update_region_selection_info()
            self._populate_stage_region_lists()
            self._refresh_region_target_widgets()

        def _populate_material_library(self) -> None:
            self.material_library_table.setRowCount(0)
            if self.current_model is None:
                return
            self._ensure_default_material_library()
            for row, mat in enumerate(self.current_model.material_library):
                self.material_library_table.insertRow(row)
                vals = [mat.name, mat.model_type, str(len(mat.parameters)), _stringify(mat.metadata)[:80]]
                for col, value in enumerate(vals):
                    self.material_library_table.setItem(row, col, QtWidgets.QTableWidgetItem(value))
            self.material_library_table.resizeColumnsToContents()

        def _populate_stage_table(self) -> None:
            self.stage_table.setRowCount(0)
            if self.current_model is None:
                return
            for row, stage in enumerate(self.current_model.stages):
                self.stage_table.insertRow(row)
                vals = [stage.name, str(stage.steps or ''), ', '.join(stage.activate_regions), ', '.join(stage.deactivate_regions), f'{len(stage.boundary_conditions)}/{len(stage.loads)}']
                for col, value in enumerate(vals):
                    self.stage_table.setItem(row, col, QtWidgets.QTableWidgetItem(value))
            self.stage_table.resizeColumnsToContents()
            self._populate_stage_combo()

        def _populate_stage_combo(self) -> None:
            current = self.result_stage_combo.currentText()
            self.result_stage_combo.blockSignals(True)
            self.result_stage_combo.clear(); self.result_stage_combo.addItem('(latest)')
            if self.current_model is not None:
                for name in self.current_model.result_stage_names():
                    self.result_stage_combo.addItem(name)
            idx = self.result_stage_combo.findText(current)
            self.result_stage_combo.setCurrentIndex(max(0, idx))
            self.result_stage_combo.blockSignals(False)

        def _populate_result_controls(self) -> None:
            current_field = self.result_field_combo.currentText()
            self.result_field_combo.blockSignals(True)
            self.result_field_combo.clear(); self.result_field_combo.addItem('(geometry only)')
            if self.current_model is not None:
                for field in self.current_model.list_result_base_names():
                    self.result_field_combo.addItem(field)
            idx = self.result_field_combo.findText(current_field)
            self.result_field_combo.setCurrentIndex(max(0, idx))
            self.result_field_combo.blockSignals(False)
            self._populate_stage_combo()

        def _default_stage_activation_map(self) -> dict[str, bool]:
            if self.current_model is None:
                return {}
            return {region.name: True for region in self.current_model.region_tags}

        def _previous_stage_activation_map(self, stage_name: str | None = None) -> dict[str, bool]:
            mapping = self._default_stage_activation_map()
            if self.current_model is None or not self.current_model.stages:
                return mapping
            target_idx = None
            if stage_name is not None:
                for idx, stage in enumerate(self.current_model.stages):
                    if stage.name == stage_name:
                        target_idx = idx
                        break
            if target_idx is None:
                target_idx = len(self.current_model.stages)
            for stage in self.current_model.stages[:target_idx]:
                amap = stage.metadata.get('activation_map')
                if amap:
                    mapping.update({str(k): bool(v) for k, v in amap.items()})
                else:
                    for name in stage.activate_regions:
                        mapping[str(name)] = True
                    for name in stage.deactivate_regions:
                        mapping[str(name)] = False
            return mapping

        def _stage_activation_map_from_editor(self) -> dict[str, bool]:
            mapping: dict[str, bool] = {}
            root = self.stage_activation_tree.invisibleRootItem()
            for i in range(root.childCount()):
                group = root.child(i)
                for j in range(group.childCount()):
                    child = group.child(j)
                    region = str(child.data(0, QtCore.Qt.ItemDataRole.UserRole) or child.text(0))
                    mapping[region] = child.checkState(0) == QtCore.Qt.CheckState.Checked
            return mapping

        def _populate_stage_region_lists(self, activation_map: dict[str, bool] | None = None) -> None:
            self.stage_activation_tree.blockSignals(True)
            self.stage_activation_tree.clear()
            if self.current_model is None:
                self.stage_activation_tree.blockSignals(False)
                return
            activation_map = dict(activation_map or self._default_stage_activation_map())
            active_root = QtWidgets.QTreeWidgetItem(['激活区域', 'Active'])
            inactive_root = QtWidgets.QTreeWidgetItem(['失活区域', 'Inactive'])
            active_root.setFirstColumnSpanned(True)
            inactive_root.setFirstColumnSpanned(True)
            self.stage_activation_tree.addTopLevelItem(active_root)
            self.stage_activation_tree.addTopLevelItem(inactive_root)
            for region in self.current_model.region_tags:
                is_active = bool(activation_map.get(region.name, True))
                parent = active_root if is_active else inactive_root
                item = QtWidgets.QTreeWidgetItem([region.name, '激活' if is_active else '失活'])
                item.setData(0, QtCore.Qt.ItemDataRole.UserRole, region.name)
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
                item.setCheckState(0, QtCore.Qt.CheckState.Checked if is_active else QtCore.Qt.CheckState.Unchecked)
                parent.addChild(item)
            active_root.setExpanded(True)
            inactive_root.setExpanded(True)
            self.stage_activation_tree.blockSignals(False)

        def _on_stage_activation_item_changed(self, item, column) -> None:
            if item is None or item.childCount() > 0:
                return
            item.setText(1, '激活' if item.checkState(0) == QtCore.Qt.CheckState.Checked else '失活')
            self._refresh_form_validation()

        def _populate_bc_table(self, stage: AnalysisStage | None = None) -> None:
            self.bc_table.setRowCount(0)
            if stage is None:
                return
            for row, bc in enumerate(stage.boundary_conditions):
                self.bc_table.insertRow(row)
                vals = [bc.name, bc.kind, bc.target, ', '.join(str(v) for v in bc.values)]
                for col, value in enumerate(vals):
                    self.bc_table.setItem(row, col, QtWidgets.QTableWidgetItem(value))

        def _populate_load_table(self, stage: AnalysisStage | None = None) -> None:
            self.load_table.setRowCount(0)
            if stage is None:
                return
            for row, load in enumerate(stage.loads):
                self.load_table.insertRow(row)
                vals = [load.name, load.kind, load.target, ', '.join(str(v) for v in load.values)]
                for col, value in enumerate(vals):
                    self.load_table.setItem(row, col, QtWidgets.QTableWidgetItem(value))

        def _clear_plotter_cached_actors(self) -> None:
            removed = False
            for meta in list(getattr(self, '_viewer_actor_map', {}).values()):
                actor = meta.get('actor') if isinstance(meta, dict) else None
                if actor is None:
                    continue
                try:
                    self.plotter.remove_actor(actor, reset_camera=False, render=False)
                    removed = True
                except Exception:
                    pass
            if not removed:
                try:
                    self.plotter.clear()
                except Exception:
                    pass
            self._viewer_actor_map = {}

        def _show_model(self) -> None:
            self._clear_plotter_cached_actors()
            if self.current_model is None:
                return
            field = self.result_field_combo.currentText()
            stage_txt = self.result_stage_combo.currentText()
            stage = None if stage_txt in {'', '(latest)'} else stage_txt
            scalars = None if field == '(geometry only)' else field
            view_mode = self.result_view_mode_combo.currentText() if hasattr(self, 'result_view_mode_combo') else 'normal'
            stage_activation = self._current_stage_activation_map_for_view(stage)
            try:
                unassigned_regions, conflict_regions = self._compute_visual_issue_regions(stage)
                mesh_bad_ids = []
                try:
                    mesh_bad_ids = list(getattr(self, '_last_mesh_report', None).bad_cell_ids or [])
                except Exception:
                    mesh_bad_ids = []
                self._viewer_actor_map = self.preview_builder.add_model(
                    self.plotter,
                    self.current_model,
                    scalars=scalars,
                    stage=stage,
                    selected_regions=self._highlight_regions,
                    selected_blocks=self._highlight_blocks,
                    displacement_scale=float(self.result_scale_spin.value()) if hasattr(self, 'result_scale_spin') else 1.0,
                    view_mode=view_mode,
                    stage_activation=stage_activation,
                    unassigned_regions=unassigned_regions,
                    conflict_regions=conflict_regions,
                    show_edges=bool(getattr(self, 'mesh_show_edges_check', None).isChecked()) if hasattr(self, 'mesh_show_edges_check') else False,
                    bad_cell_ids=mesh_bad_ids,
                    visual_options=self._result_visual_options(),
                )
            except Exception as exc:
                self._log(f'预览失败: {exc}')
                self._viewer_actor_map = self.preview_builder.add_model(self.plotter, self.current_model, scalars=None, stage=None, show_edges=bool(getattr(self, 'mesh_show_edges_check', None).isChecked()) if hasattr(self, 'mesh_show_edges_check') else False, visual_options=self._result_visual_options())
            self._enable_viewport_picking()
            self.plotter.reset_camera()

        def _enable_viewport_picking(self) -> None:
            try:
                self.plotter.enable_mesh_picking(callback=self._on_picked_mesh, use_actor=False, left_clicking=True, show=False)
            except Exception:
                pass

        def enable_box_select_mode(self) -> None:
            try:
                self.plotter.enable_rectangle_picking(callback=self._on_rectangle_picked, show_frustum=False, style='wireframe')
                self._set_status('Box selection enabled. Drag in the 3D view to add visible objects.')
            except Exception as exc:
                self._log(f'Box selection is unavailable: {exc}')

        def enable_lasso_select_mode(self) -> None:
            try:
                self.plotter.enable_rectangle_picking(callback=self._on_rectangle_picked, show_frustum=False, style='surface')
                self._set_status('Lasso selection uses the current visible-frustum selection in this build. Drag in the 3D view to add visible objects.')
            except Exception as exc:
                self._log(f'Lasso selection is unavailable: {exc}')

        @staticmethod
        def _bounds_intersect(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
            if len(a) != 6 or len(b) != 6:
                return False
            return not (a[1] < b[0] or a[0] > b[1] or a[3] < b[2] or a[2] > b[3] or a[5] < b[4] or a[4] > b[5])

        def _on_rectangle_picked(self, selection) -> None:
            if self.current_model is None or selection is None:
                return
            sel_bounds = tuple(getattr(selection, 'bounds', ()))
            if len(sel_bounds) != 6:
                return
            picked: list[tuple[str, str]] = []
            for _, meta in self._viewer_actor_map.items():
                object_key = str(meta.get('object_key') or '')
                region_name = str(meta.get('region_name') or '')
                bounds = tuple(meta.get('bounds') or ())
                if object_key and bounds and self._bounds_intersect(bounds, sel_bounds) and self._object_passes_selection_filter(object_key):
                    picked.append(('object', object_key))
                elif region_name and bounds and self._bounds_intersect(bounds, sel_bounds):
                    picked.append(('region', region_name))
            if not picked:
                self._set_status('No visible selectable objects were captured by the current selection box.')
                return
            self.scene_tree.blockSignals(True)
            self.scene_tree.clearSelection()
            self.scene_tree.blockSignals(False)
            for kind, key in list(dict.fromkeys(picked)):
                self._select_scene_payload(kind, key, additive=True)
            self._set_status(f'Selected {len(list(dict.fromkeys(picked)))} items from the 3D viewport.')

        def _on_picked_mesh(self, mesh) -> None:
            if self.current_model is None or mesh is None:
                return
            object_key = ''
            region_name = ''
            try:
                fd = getattr(mesh, 'field_data', {})
                if 'object_key' in fd and len(fd['object_key']):
                    object_key = str(fd['object_key'][0])
                if 'region_name' in fd and len(fd['region_name']):
                    region_name = str(fd['region_name'][0])
            except Exception:
                pass
            modifiers = QtWidgets.QApplication.keyboardModifiers()
            additive = bool(modifiers & (QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier))
            if object_key and self._object_passes_selection_filter(object_key):
                self._select_scene_payload('object', object_key, additive=additive)
            elif region_name:
                self._select_scene_payload('region', region_name, additive=additive)

        def _select_scene_payload(self, kind: str, key: str, additive: bool = False) -> None:
            self.scene_tree.blockSignals(True)
            if not additive:
                self.scene_tree.clearSelection()
            root = self.scene_tree.invisibleRootItem()
            stack = [root]
            found = None
            while stack:
                node = stack.pop()
                for i in range(node.childCount()):
                    child = node.child(i)
                    if child.data(0, QtCore.Qt.ItemDataRole.UserRole) == (kind, key):
                        found = child
                        break
                    stack.append(child)
                if found is not None:
                    break
            self.scene_tree.blockSignals(False)
            if found is not None:
                found.setSelected(True)
                self.scene_tree.setCurrentItem(found)
                self.scene_tree.scrollToItem(found)
                self._on_scene_selection_changed()


        def _compute_visual_issue_regions(self, stage_name: str | None = None) -> tuple[list[str], list[str]]:
            if self.current_model is None:
                return [], []
            region_names = {r.name for r in self.current_model.region_tags}
            unassigned = [r.name for r in self.current_model.region_tags if self.current_model.material_for_region(r.name) is None]
            conflict: set[str] = set()
            stage = self.current_model.stage_by_name(stage_name) if stage_name else self._selected_stage()
            if stage is not None:
                overlap = set(stage.activate_regions) & set(stage.deactivate_regions)
                conflict.update(r for r in overlap if r in region_names)
                amap = stage.metadata.get('activation_map') if isinstance(stage.metadata, dict) else None
                if isinstance(amap, dict):
                    inactive_targets = {name for name, active in amap.items() if not active}
                    for bc in getattr(stage, 'boundary_conditions', ()):
                        if bc.target in inactive_targets and bc.target in region_names:
                            conflict.add(bc.target)
                    for ld in getattr(stage, 'loads', ()):
                        if ld.target in inactive_targets and ld.target in region_names:
                            conflict.add(ld.target)
                for name in list(stage.activate_regions) + list(stage.deactivate_regions):
                    if name and name not in region_names:
                        conflict.update([])
            return sorted(set(unassigned)), sorted(conflict)

        def _current_stage_activation_map_for_view(self, stage_name: str | None) -> dict[str, bool] | None:
            if self.current_model is None:
                return None
            if stage_name:
                stage = self.current_model.stage_by_name(stage_name)
                if stage is not None:
                    amap = stage.metadata.get('activation_map')
                    if isinstance(amap, dict):
                        return dict(amap)
            if hasattr(self, 'stage_activation_tree') and self.stage_activation_tree.topLevelItemCount() > 0 and self.step_list.currentRow() == 3:
                try:
                    return self._stage_activation_map_from_editor()
                except Exception:
                    return None
            return None

        def _unassigned_regions_for_view(self) -> list[str]:
            if self.current_model is None:
                return []
            return [region.name for region in self.current_model.region_tags if self.current_model.material_for_region(region.name) is None]

        def _conflict_regions_for_view(self, stage_name: str | None) -> list[str]:
            if self.current_model is None:
                return []
            conflicts: set[str] = set()
            stage = self.current_model.stage_by_name(stage_name) if stage_name else self._selected_stage()
            if stage is not None:
                conflicts.update(set(stage.activate_regions) & set(stage.deactivate_regions))
            try:
                amap = self._stage_activation_map_from_editor()
                prev = self._previous_stage_activation_map(stage.name if stage else None)
                activate = {name for name, state in amap.items() if state and not prev.get(name, True)}
                deactivate = {name for name, state in amap.items() if (not state) and prev.get(name, True)}
                conflicts.update(activate & deactivate)
            except Exception:
                pass
            return sorted(conflicts)

        def refresh_view(self) -> None:
            self._show_model()

        def _sync_all_views(self) -> None:
            self._populate_project_info()
            self._refresh_scene_tree()
            self._populate_region_table()
            self._populate_material_library()
            self._populate_stage_table()
            self._populate_result_controls()
            self._update_validation()
            self._refresh_form_validation()
            self._show_model()
            self._update_global_inspector()
            self._refresh_form_validation()

        def _result_visual_options(self) -> dict:
            opts = {
                'opacity': (float(self.result_opacity_slider.value()) / 100.0) if hasattr(self, 'result_opacity_slider') else 1.0,
                'cmap': self.result_cmap_combo.currentText() if hasattr(self, 'result_cmap_combo') else 'viridis',
                'show_scalar_bar': bool(self.result_scalar_bar_check.isChecked()) if hasattr(self, 'result_scalar_bar_check') else True,
                'clip_axis': self.result_clip_axis_combo.currentText() if hasattr(self, 'result_clip_axis_combo') else 'none',
                'clip_ratio': (float(self.result_clip_ratio_slider.value()) / 100.0) if hasattr(self, 'result_clip_ratio_slider') else 0.5,
            }
            if hasattr(self, 'result_auto_range_check') and not self.result_auto_range_check.isChecked():
                try:
                    vmin = float(self.result_range_min_edit.text().strip())
                    vmax = float(self.result_range_max_edit.text().strip())
                    if vmax > vmin:
                        opts['scalar_range'] = (vmin, vmax)
                except Exception:
                    pass
            return opts

        def _focus_region_in_view(self, region_name: str) -> None:
            if self.current_model is None or not region_name:
                return
            region = self.current_model.get_region(region_name)
            if region is None:
                return
            self._highlight_regions = [region_name]
            self._show_model()
            try:
                grid = self.current_model.to_unstructured_grid().extract_cells(region.cell_ids)
                self.plotter.reset_camera(bounds=grid.bounds)
            except Exception:
                try:
                    self.plotter.reset_camera()
                except Exception:
                    pass

        def _on_mesh_check_region_selected(self) -> None:
            if not hasattr(self, 'mesh_check_table'):
                return
            rows = self.mesh_check_table.selectionModel().selectedRows() if self.mesh_check_table.selectionModel() else []
            if not rows:
                return
            item = self.mesh_check_table.item(rows[0].row(), 0)
            if item is not None:
                self._focus_region_in_view(item.text())

        def locate_selected_mesh_region(self) -> None:
            self._on_mesh_check_region_selected()

        def _update_validation(self) -> None:
            self.validation_list.clear()
            issues = validate_model(self.current_model)
            self._sync_diagnostics_from_validation(issues)
            by_step = {key: [] for key in STEP_KEYS}
            for issue in issues:
                prefix = {'error': '⛔', 'warning': '⚠', 'info': 'ℹ'}.get(issue.level, '•')
                item = QtWidgets.QListWidgetItem(f'{prefix} [{issue.step}] {issue.message}')
                item.setData(QtCore.Qt.ItemDataRole.UserRole, {'step': issue.step, 'message': issue.message})
                self.validation_list.addItem(item)
                by_step.setdefault(issue.step, []).append(issue)
            for idx, step_key in enumerate(STEP_KEYS):
                item = self.step_list.item(idx)
                if item is None:
                    continue
                step_issues = by_step.get(step_key, [])
                if any(i.level == 'error' for i in step_issues):
                    item.setBackground(QtGui.QColor('#f8d7da'))
                elif any(i.level == 'warning' for i in step_issues):
                    item.setBackground(QtGui.QColor('#fff3cd'))
                elif step_issues:
                    item.setBackground(QtGui.QColor('#d1ecf1'))
                else:
                    item.setBackground(QtGui.QBrush())



        def _jump_to_step_key(self, step_key: str) -> None:
            if step_key in STEP_KEYS:
                self.step_list.setCurrentRow(STEP_KEYS.index(step_key))

        def _jump_from_validation_item(self, item) -> None:
            payload = None
            try:
                payload = item.data(QtCore.Qt.ItemDataRole.UserRole)
            except Exception:
                payload = None
            step_key = None
            message = ''
            if isinstance(payload, dict):
                step_key = payload.get('step')
                message = str(payload.get('message') or '')
            elif payload:
                step_key = payload
            if step_key:
                self._jump_to_step_key(str(step_key))
            target = self._find_visual_target_from_text(message)
            if target:
                self._select_and_focus_target(*target, flash=True)

        def _jump_from_diagnostic_item(self, item) -> None:
            row = item.row() if hasattr(item, 'row') else -1
            if row < 0 or not hasattr(self, 'diagnostics_table'):
                return
            payload = None
            base = self.diagnostics_table.item(row, 0)
            if base is not None:
                payload = base.data(QtCore.Qt.ItemDataRole.UserRole)
            source = ''
            message = ''
            if isinstance(payload, dict):
                source = str(payload.get('source') or '')
                message = str(payload.get('message') or '')
            else:
                source_item = self.diagnostics_table.item(row, 1)
                source = str(source_item.text()) if source_item else ''
            mapping = {
                'project': 'project', 'geometry': 'geometry', 'ifc': 'geometry', 'mesh': 'geometry',
                'materials': 'materials', 'stages': 'stages', 'solver': 'results',
            }
            self._jump_to_step_key(mapping.get(source, 'results'))
            target = self._find_visual_target_from_text(message)
            if target:
                self._select_and_focus_target(*target, flash=True)

        def _find_visual_target_from_text(self, text: str) -> tuple[str, str] | None:
            if self.current_model is None or not text:
                return None
            lowered = text.lower()
            region_names = sorted([r.name for r in self.current_model.region_tags], key=len, reverse=True)
            for name in region_names:
                if name and name.lower() in lowered:
                    return ('region', name)
            for rec in sorted(self.current_model.object_records, key=lambda r: len(r.name or r.key), reverse=True):
                if rec.name and rec.name.lower() in lowered:
                    return ('object', rec.key)
                if rec.key and rec.key.lower() in lowered:
                    return ('object', rec.key)
            return None

        def _select_and_focus_target(self, kind: str, key: str, flash: bool = False) -> None:
            self._select_scene_payload(kind, key, additive=False)
            if kind == 'region':
                self._focus_region_in_view(key)
            elif kind == 'object':
                self._focus_object_in_view(key)
            if flash:
                self._start_flash(kind, key)

        def _focus_object_in_view(self, object_key: str) -> None:
            if not object_key:
                return
            rec = self.current_model.object_record(object_key) if self.current_model is not None else None
            if rec and rec.region_name:
                self._highlight_regions = [rec.region_name]
            self._highlight_blocks = [object_key]
            self._show_model()
            try:
                for meta in self._viewer_actor_map.values():
                    if str(meta.get('object_key') or '') == object_key:
                        bounds = meta.get('bounds')
                        if bounds is not None:
                            self.plotter.reset_camera(bounds=bounds)
                            return
                self.plotter.reset_camera()
            except Exception:
                pass

        def _start_flash(self, kind: str, key: str) -> None:
            if not hasattr(self, '_flash_timer'):
                return
            self._flash_payload = {
                'kind': kind,
                'key': key,
                'remaining': 6,
                'on': False,
                'base_regions': list(self._highlight_regions),
                'base_blocks': list(self._highlight_blocks),
            }
            self._flash_timer.start()

        def _on_flash_tick(self) -> None:
            payload = getattr(self, '_flash_payload', None)
            if not payload:
                self._flash_timer.stop()
                return
            kind = payload['kind']; key = payload['key']
            payload['on'] = not payload['on']
            if kind == 'region':
                self._highlight_regions = [key] if payload['on'] else list(payload.get('base_regions', []))
                self._highlight_blocks = list(payload.get('base_blocks', []))
            else:
                self._highlight_blocks = [key] if payload['on'] else list(payload.get('base_blocks', []))
                self._highlight_regions = list(payload.get('base_regions', []))
            payload['remaining'] -= 1
            self._show_model()
            if payload['remaining'] <= 0:
                self._flash_timer.stop()
                self._highlight_regions = list(payload.get('base_regions', []))
                self._highlight_blocks = list(payload.get('base_blocks', []))
                self._show_model()
                self._flash_payload = None

        def _connect_validation_signals(self) -> None:
            for widget in self._param_inputs.values():
                if hasattr(widget, 'valueChanged'):
                    widget.valueChanged.connect(self._refresh_form_validation)
            self.ifc_include_entities_edit.textChanged.connect(self._refresh_form_validation)
            self.ifc_region_strategy_combo.currentTextChanged.connect(self._refresh_form_validation)
            self.material_name_edit.textChanged.connect(self._refresh_form_validation)
            self.material_model_combo.currentTextChanged.connect(self._refresh_form_validation)
            self.stage_name_edit.textChanged.connect(self._refresh_form_validation)
            self.stage_steps_spin.valueChanged.connect(self._refresh_form_validation)
            self.stage_initial_increment.valueChanged.connect(self._refresh_form_validation)
            self.stage_max_iterations.valueChanged.connect(self._refresh_form_validation)
            self.stage_activation_tree.itemChanged.connect(lambda *_: self._refresh_form_validation())
            self.stage_activation_tree.itemSelectionChanged.connect(self._refresh_form_validation)
            self.bc_name_edit.textChanged.connect(self._refresh_form_validation)
            self.bc_target_edit.textChanged.connect(self._refresh_form_validation)
            self.bc_components_edit.textChanged.connect(self._refresh_form_validation)
            self.bc_values_edit.textChanged.connect(self._refresh_form_validation)
            self.bc_kind_combo.currentTextChanged.connect(self._refresh_form_validation)
            self.load_name_edit.textChanged.connect(self._refresh_form_validation)
            self.load_target_edit.textChanged.connect(self._refresh_form_validation)
            self.load_values_edit.textChanged.connect(self._refresh_form_validation)
            self.load_kind_combo.currentTextChanged.connect(self._refresh_form_validation)
            self.solver_max_iter_spin.valueChanged.connect(self._refresh_form_validation)
            self.solver_tol_edit.textChanged.connect(self._refresh_form_validation)
            self.solver_max_cutbacks_spin.valueChanged.connect(self._refresh_form_validation)

        def _set_widget_validation_state(self, widget, level: str | None, message: str = '') -> None:
            if widget is None:
                return
            if level == 'error':
                widget.setStyleSheet(INVALID_STYLE)
            elif level == 'warning':
                widget.setStyleSheet(WARNING_STYLE)
            else:
                widget.setStyleSheet(VALID_STYLE)
            if hasattr(widget, 'setToolTip'):
                widget.setToolTip(message or '')

        def _field_issue_map(self, issues: list[ParameterIssue]) -> dict[str, ParameterIssue]:
            out: dict[str, ParameterIssue] = {}
            severity = {'error': 2, 'warning': 1, 'info': 0}
            for issue in issues:
                prev = out.get(issue.field)
                if prev is None or severity.get(issue.level, 0) > severity.get(prev.level, 0):
                    out[issue.field] = issue
            return out

        def _render_validation_label(self, key: str, issues: list[ParameterIssue]) -> None:
            label = self._validation_labels.get(key)
            if label is None:
                return
            if not issues:
                label.setText('✓ 参数校验通过')
                label.setStyleSheet('color: #2e7d32;')
            else:
                prefix = {'error': '⛔', 'warning': '⚠', 'info': 'ℹ'}
                label.setText('\n'.join(f"{prefix.get(i.level, '•')} {i.message}" for i in issues[:4]))
                if any(i.level == 'error' for i in issues):
                    label.setStyleSheet('color: #c62828;')
                elif any(i.level == 'warning' for i in issues):
                    label.setStyleSheet('color: #b26a00;')
                else:
                    label.setStyleSheet('color: #1565c0;')

        def _apply_validation_result(self, key: str, issues: list[ParameterIssue], block: bool = False, title: str = '参数校验失败') -> bool:
            self._render_validation_label(key, issues)
            if block and any(i.level == 'error' for i in issues):
                QtWidgets.QMessageBox.warning(self, title, '\n'.join(i.message for i in issues if i.level == 'error'))
                return True
            return False

        def _validate_geometry_form(self) -> list[ParameterIssue]:
            params = {name: widget.value() for name, widget in self._param_inputs.items()}
            issues = validate_geometry_params(params)
            m = self._field_issue_map(issues)
            for name, widget in self._param_inputs.items():
                issue = m.get(name)
                self._set_widget_validation_state(widget, issue.level if issue else None, issue.message if issue else '')
            self._render_validation_label('geometry', issues)
            return issues

        def _validate_ifc_form(self, file_path: str | None = None) -> list[ParameterIssue]:
            issues = validate_ifc_options(self.ifc_include_entities_edit.text(), self.ifc_region_strategy_combo.currentText(), file_path=file_path)
            m = self._field_issue_map(issues)
            issue = m.get('include_entities')
            self._set_widget_validation_state(self.ifc_include_entities_edit, issue.level if issue else None, issue.message if issue else '')
            issue = m.get('region_strategy')
            self._set_widget_validation_state(self.ifc_region_strategy_combo, issue.level if issue else None, issue.message if issue else '')
            self._render_validation_label('ifc', issues)
            return issues

        def _validate_material_form(self) -> list[ParameterIssue]:
            issues = validate_material_parameters(self.material_model_combo.currentText() or 'linear_elastic', self._collect_material_parameters(), self.material_name_edit.text())
            m = self._field_issue_map(issues)
            issue = m.get('name')
            self._set_widget_validation_state(self.material_name_edit, issue.level if issue else None, issue.message if issue else '')
            issue = m.get('model_type')
            self._set_widget_validation_state(self.material_model_combo, issue.level if issue else None, issue.message if issue else '')
            for key, widget in self._material_param_inputs.items():
                issue = m.get(key)
                self._set_widget_validation_state(widget, issue.level if issue else None, issue.message if issue else '')
            self._render_validation_label('material', issues)
            return issues

        def _validate_stage_form(self) -> list[ParameterIssue]:
            current = self._selected_stage()
            amap = self._stage_activation_map_from_editor() if hasattr(self, 'stage_activation_tree') else {}
            prev = self._previous_stage_activation_map(current.name if current else None)
            activate = [name for name, state in amap.items() if state and not prev.get(name, True)]
            deactivate = [name for name, state in amap.items() if (not state) and prev.get(name, True)]
            issues = validate_stage_inputs(
                self.stage_name_edit.text(),
                self.stage_steps_spin.value(),
                self.stage_initial_increment.value(),
                self.stage_max_iterations.value(),
                activate,
                deactivate,
                existing_names=[s.name for s in self.current_model.stages] if self.current_model else (),
                current_name=current.name if current else None,
            )
            m = self._field_issue_map(issues)
            for field, widget in [('stage_name', self.stage_name_edit), ('stage_steps', self.stage_steps_spin), ('stage_initial_increment', self.stage_initial_increment), ('stage_max_iterations', self.stage_max_iterations)]:
                issue = m.get(field)
                self._set_widget_validation_state(widget, issue.level if issue else None, issue.message if issue else '')
            issue = m.get('stage_regions')
            self._set_widget_validation_state(self.stage_activation_tree, issue.level if issue else None, issue.message if issue else '')
            self._render_validation_label('stage', issues)
            return issues

        def _validate_bc_form(self) -> list[ParameterIssue]:
            issues = validate_bc_inputs(self.bc_name_edit.text(), self.bc_kind_combo.currentText(), self.bc_target_edit.text(), _parse_components(self.bc_components_edit.text()), _parse_values(self.bc_values_edit.text()))
            m = self._field_issue_map(issues)
            for field, widget in [('bc_name', self.bc_name_edit), ('bc_kind', self.bc_kind_combo), ('bc_target', self.bc_target_edit), ('bc_components', self.bc_components_edit), ('bc_values', self.bc_values_edit)]:
                issue = m.get(field)
                self._set_widget_validation_state(widget, issue.level if issue else None, issue.message if issue else '')
            self._render_validation_label('bc', issues)
            return issues

        def _validate_load_form(self) -> list[ParameterIssue]:
            issues = validate_load_inputs(self.load_name_edit.text(), self.load_kind_combo.currentText(), self.load_target_edit.text(), _parse_values(self.load_values_edit.text()))
            m = self._field_issue_map(issues)
            for field, widget in [('load_name', self.load_name_edit), ('load_kind', self.load_kind_combo), ('load_target', self.load_target_edit), ('load_values', self.load_values_edit)]:
                issue = m.get(field)
                self._set_widget_validation_state(widget, issue.level if issue else None, issue.message if issue else '')
            self._render_validation_label('load', issues)
            return issues

        def _validate_solver_form(self) -> list[ParameterIssue]:
            issues = validate_solver_settings(self.solver_max_iter_spin.value(), self.solver_tol_edit.text(), self.solver_max_cutbacks_spin.value())
            m = self._field_issue_map(issues)
            for field, widget in [('solver_max_iterations', self.solver_max_iter_spin), ('solver_tolerance', self.solver_tol_edit), ('solver_max_cutbacks', self.solver_max_cutbacks_spin)]:
                issue = m.get(field)
                self._set_widget_validation_state(widget, issue.level if issue else None, issue.message if issue else '')
            self._render_validation_label('solver', issues)
            return issues

        def _refresh_form_validation(self) -> None:
            try:
                self._validate_geometry_form()
                self._validate_ifc_form()
                self._validate_material_form()
                self._validate_stage_form()
                self._validate_bc_form()
                self._validate_load_form()
                self._validate_solver_form()
            except Exception:
                pass

        def _selected_scene_payloads(self) -> list[tuple[str, str]]:
            out: list[tuple[str, str]] = []
            for item in self.scene_tree.selectedItems():
                payload = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if payload:
                    out.append(tuple(payload))
            return out

        def _selected_object_keys(self) -> list[str]:
            return [key for kind, key in self._selected_scene_payloads() if kind == 'object']

        def _selected_scene_region_names(self) -> list[str]:
            return [key for kind, key in self._selected_scene_payloads() if kind == 'region']

        def _refresh_region_target_widgets(self) -> None:
            names = [region.name for region in self.current_model.region_tags] if self.current_model else []
            for combo in [getattr(self, 'scene_region_target_combo', None), getattr(self, 'inspector_region_combo', None)]:
                if combo is None:
                    continue
                current = combo.currentText()
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(names)
                if current and current in names:
                    combo.setCurrentText(current)
                combo.blockSignals(False)

        def _update_highlight_selection(self) -> None:
            self._highlight_regions = self._selected_region_names() + self._selected_scene_region_names()
            self._highlight_blocks = self._selected_object_keys()
            self.refresh_view()
            self._update_global_inspector()

        def _update_global_inspector(self) -> None:
            if self.current_model is None:
                self.inspector_title.setText('未载入模型')
                self.inspector_summary.setPlainText('')
                self._set_key_value_table(self.inspector_props, [])
                return
            object_keys = self._selected_object_keys()
            regions = self._selected_region_names() or self._selected_scene_region_names()
            stage = self._selected_stage()
            payload: tuple[str, str] | None = None
            if object_keys:
                payload = ('object', '|'.join(sorted(object_keys)))
            elif regions:
                payload = ('region', '|'.join(sorted(regions)))
            elif stage is not None:
                payload = ('stage', stage.name)
            if payload != self._last_selection_payload:
                self._inspector_dismissed = False
            self._last_selection_payload = payload
            if object_keys:
                names = []
                props = []
                for key in object_keys[:8]:
                    rec = self.current_model.object_record(key)
                    if rec is None:
                        continue
                    names.append(rec.name)
                    props.extend([('object', rec.key), ('type', rec.object_type), ('region', rec.region_name or '-'), ('role', rec.metadata.get('role', '-'))])
                first = self.current_model.object_record(object_keys[0]) if object_keys else None
                self.inspector_title.setText(f'Object selection ({len(object_keys)})')
                self.inspector_summary.setPlainText('\n'.join(names))
                self.inspector_visible_check.blockSignals(True); self.inspector_visible_check.setChecked(bool(first.visible) if first else True); self.inspector_visible_check.blockSignals(False)
                self.inspector_pickable_check.blockSignals(True); self.inspector_pickable_check.setChecked(bool(first.pickable) if first else True); self.inspector_pickable_check.blockSignals(False)
                self.inspector_locked_check.blockSignals(True); self.inspector_locked_check.setChecked(bool(first.locked) if first else False); self.inspector_locked_check.blockSignals(False)
                props.extend([('visible', str(bool(first.visible)) if first else '-'), ('pickable', str(bool(first.pickable)) if first else '-'), ('locked', str(bool(first.locked)) if first else '-')])
                self._set_key_value_table(self.inspector_props, props[:20])
                self._update_inspector_collapse()
                return
            if regions:
                self.inspector_title.setText(f'Region selection ({len(regions)})')
                lines = []
                props = []
                for name in regions[:8]:
                    region = self.current_model.get_region(name)
                    binding = self.current_model.material_for_region(name)
                    lines.append(name)
                    props.append((name, f'cells={len(region.cell_ids) if region else 0}, material={binding.metadata.get("library_name", binding.material_name) if binding else "-"}'))
                self.inspector_summary.setPlainText('\n'.join(lines))
                self._set_key_value_table(self.inspector_props, props)
                self._update_inspector_collapse()
                return
            if stage is not None:
                self.inspector_title.setText(f'Stage: {stage.name}')
                self.inspector_summary.setPlainText(stage.metadata.get('notes', ''))
                props = [('steps', str(stage.steps or '')), ('activate', ', '.join(stage.activate_regions)), ('deactivate', ', '.join(stage.deactivate_regions)), ('BCs', str(len(stage.boundary_conditions))), ('Loads', str(len(stage.loads)))]
                self._set_key_value_table(self.inspector_props, props)
                self._update_inspector_collapse()
                return
            self.inspector_title.setText(self._tt('Project overview'))
            self.inspector_summary.setPlainText(self.current_model.name)
            self.inspector_visible_check.blockSignals(True); self.inspector_visible_check.setChecked(True); self.inspector_visible_check.blockSignals(False)
            self.inspector_pickable_check.blockSignals(True); self.inspector_pickable_check.setChecked(True); self.inspector_pickable_check.blockSignals(False)
            self.inspector_locked_check.blockSignals(True); self.inspector_locked_check.setChecked(False); self.inspector_locked_check.blockSignals(False)
            if self._inspector_has_explicit_selection() or self._inspector_pinned or not self.inspector_collapse.isChecked():
                self._set_key_value_table(self.inspector_props, [('regions', str(len(self.current_model.region_tags))), ('objects', str(len(self.current_model.object_records))), ('stages', str(len(self.current_model.stages))), ('materials', str(len(self.current_model.material_library)))])
            else:
                self.inspector_summary.setPlainText('')
                self._set_key_value_table(self.inspector_props, [])
            self._update_inspector_collapse()

        def _show_scene_context_menu(self, pos) -> None:
            if not self._selected_scene_payloads():
                return
            menu = QtWidgets.QMenu(self)
            act_hide = menu.addAction(self._tt('Hide Selected'))
            act_isolate = menu.addAction(self._tt('Isolate Selected'))
            act_show_selected = menu.addAction(self._tt('Show Selected'))
            act_show_all = menu.addAction(self._tt('Show All'))
            act_lock = menu.addAction(self._tt('Lock Selected'))
            act_unlock = menu.addAction(self._tt('Unlock Selected'))
            menu.addSeparator()
            act_new_region = menu.addAction(self._tt('设为新 Region'))
            act_existing_region = menu.addAction(self._tt('设为现有 Region'))
            act_merge_region = menu.addAction(self._tt('合并选中 Region'))
            menu.addSeparator()
            role_menu = menu.addMenu(self._tt('设置对象角色'))
            role_actions = {role: role_menu.addAction(role) for role in ['soil', 'wall', 'slab', 'beam', 'column', 'support', 'opening', 'boundary']}
            chosen = menu.exec(self.scene_tree.viewport().mapToGlobal(pos))
            if chosen == act_hide:
                self.hide_selected_objects()
            elif chosen == act_isolate:
                self.isolate_selected_objects()
            elif chosen == act_show_selected:
                self.show_selected_objects()
            elif chosen == act_show_all:
                self.show_all_objects()
            elif chosen == act_lock:
                self.lock_selected_objects()
            elif chosen == act_unlock:
                self.unlock_selected_objects()
            elif chosen == act_new_region:
                self.assign_selected_objects_to_new_region()
            elif chosen == act_existing_region:
                self.assign_selected_objects_to_existing_region()
            elif chosen == act_merge_region:
                self.merge_selected_regions()
            else:
                for role, action in role_actions.items():
                    if chosen == action:
                        self.apply_selected_object_role(role)
                        break

        def assign_selected_objects_to_new_region(self) -> None:
            if self.current_model is None:
                return
            object_keys = self._selected_object_keys()
            if not object_keys:
                self._set_status('请先在场景树中选择一个或多个 IFC 对象。')
                return
            region_name = (getattr(self, 'scene_region_name_edit', None).text().strip() if hasattr(self, 'scene_region_name_edit') else '') or self.inspector_region_edit.text().strip() or 'region_new'
            self.current_model.assign_objects_to_region(object_keys, region_name, create_region=True)
            self._sync_all_views()
            self._set_status(f'已将 {len(object_keys)} 个对象设为 Region: {region_name}')

        def assign_selected_objects_to_existing_region(self) -> None:
            if self.current_model is None:
                return
            object_keys = self._selected_object_keys()
            if not object_keys:
                self._set_status('请先在场景树中选择一个或多个 IFC 对象。')
                return
            region_name = (self.scene_region_target_combo.currentText() if hasattr(self, 'scene_region_target_combo') else '') or self.inspector_region_combo.currentText()
            if not region_name:
                self._set_status('请选择目标 Region。')
                return
            self.current_model.assign_objects_to_region(object_keys, region_name, create_region=True)
            self._sync_all_views()
            self._set_status(f'已将 {len(object_keys)} 个对象归并到 Region: {region_name}')

        def merge_selected_regions(self) -> None:
            if self.current_model is None:
                return
            region_names = self._selected_region_names() or self._selected_scene_region_names()
            if len(region_names) < 2:
                self._set_status('请至少选择两个 Region 再合并。')
                return
            target = (getattr(self, 'scene_region_name_edit', None).text().strip() if hasattr(self, 'scene_region_name_edit') else '') or self.inspector_region_edit.text().strip() or region_names[0]
            self.current_model.merge_regions(region_names, target)
            self._sync_all_views()
            self._set_status(f'已合并 {len(region_names)} 个 Region -> {target}')

        def apply_selected_object_role(self, role: str | None = None) -> None:
            if self.current_model is None:
                return
            object_keys = self._selected_object_keys()
            if not object_keys:
                self._set_status('请先选择 IFC 对象。')
                return
            role = role or (self.scene_object_role_combo.currentText() if hasattr(self, 'scene_object_role_combo') else '') or self.inspector_role_combo.currentText() or 'soil'
            self.current_model.set_object_role(object_keys, role)
            self._refresh_scene_tree()
            self._update_global_inspector()
            self._set_status(f'已设置 {len(object_keys)} 个对象角色为 {role}')

        # ---------- Inspector handlers ----------
        def _set_key_value_table(self, table, items: list[tuple[str, str]]) -> None:
            table.setRowCount(0)
            for row, (k, v) in enumerate(items):
                table.insertRow(row)
                table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(k)))
                table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(v)))
            table.resizeColumnsToContents()

        def _on_scene_selection_changed(self) -> None:
            items = self.scene_tree.selectedItems()
            if not items or self.current_model is None:
                self._update_highlight_selection()
                return
            kind, key = items[0].data(0, QtCore.Qt.ItemDataRole.UserRole) or (None, None)
            if kind == 'object':
                rec = self.current_model.object_record(key)
                if rec is None:
                    self._update_highlight_selection()
                    return
                self._selected_object_key = rec.key
                self.obj_name_label.setText(rec.name)
                self.obj_type_label.setText(rec.object_type)
                self.obj_guid_label.setText(rec.guid)
                self.obj_region_label.setText(rec.region_name or '-')
                self.obj_parent_label.setText(rec.parent or '-')
                self._set_key_value_table(self.obj_property_table, [(k, _stringify(v)) for k, v in sorted(rec.properties.items())])
                meta = list(sorted(rec.metadata.items()))
                self._set_key_value_table(self.obj_metadata_table, [(k, _stringify(v)) for k, v in meta])
            elif kind == 'region':
                self._show_region_in_inspector(key)
            self._update_highlight_selection()

        def _show_region_in_inspector(self, region_name: str) -> None:
            if self.current_model is None:
                return
            region = self.current_model.get_region(region_name)
            if region is None:
                return
            binding = self.current_model.material_for_region(region_name)
            objs = self.current_model.objects_for_region(region_name)
            self.obj_name_label.setText(region_name)
            self.obj_type_label.setText('Region')
            self.obj_guid_label.setText('-')
            self.obj_region_label.setText(region_name)
            self.obj_parent_label.setText('-')
            props = [('cells', str(len(region.cell_ids))), ('material', binding.material_name if binding else ''), ('objects', str(len(objs)))]
            self._set_key_value_table(self.obj_property_table, props)
            self._set_key_value_table(self.obj_metadata_table, [(k, _stringify(v)) for k, v in sorted(region.metadata.items())])

        def _on_region_selection_changed(self) -> None:
            names = self._selected_region_names()
            if names:
                self.region_name_edit.setText(names[0])
                if hasattr(self, 'scene_region_name_edit'):
                    self.scene_region_name_edit.setText(names[0])
                self.inspector_region_edit.setText(names[0])
            self._update_region_selection_info()
            self._update_highlight_selection()

        def _update_region_selection_info(self) -> None:
            if self.current_model is None:
                self.region_info.setText('未载入模型。')
                return
            names = self._selected_region_names()
            if not names:
                self.region_info.setText('选择区域后可查看对象数量和材料绑定。')
                return
            lines = []
            for name in names[:4]:
                objs = self.current_model.objects_for_region(name)
                binding = self.current_model.material_for_region(name)
                lines.append(f'{name}: objects={len(objs)}, material={binding.metadata.get("library_name", binding.material_name) if binding else "-"}')
            self.region_info.setText('\n'.join(lines))

        # ---------- Material library ----------
        def _on_material_model_changed(self) -> None:
            if self._loading_material_editor:
                return
            self._rebuild_material_param_form(self.material_model_combo.currentText())

        def new_material_definition(self) -> None:
            self._loading_material_editor = True
            self.material_name_edit.setText('NewMaterial')
            self.material_model_combo.setCurrentText('linear_elastic')
            self._rebuild_material_param_form('linear_elastic')
            self._loading_material_editor = False

        def _selected_material_definition_name(self) -> str | None:
            rows = self.material_library_table.selectionModel().selectedRows() if self.material_library_table.selectionModel() else []
            if not rows:
                return None
            item = self.material_library_table.item(rows[0].row(), 0)
            return item.text() if item else None

        def _on_material_library_selection_changed(self) -> None:
            if self.current_model is None:
                return
            self._update_global_inspector()
            name = self._selected_material_definition_name()
            if not name:
                return
            definition = self.current_model.material_definition(name)
            if definition is None:
                return
            self._loading_material_editor = True
            self.material_name_edit.setText(definition.name)
            self.material_model_combo.setCurrentText(definition.model_type)
            self._rebuild_material_param_form(definition.model_type, definition.parameters)
            self._loading_material_editor = False

        def save_material_definition(self) -> None:
            if self.current_model is None:
                return
            if self._apply_validation_result('material', self._validate_material_form(), block=True, title='材料参数校验失败'):
                return
            name = self.material_name_edit.text().strip() or 'Material'
            definition = MaterialDefinition(name=name, model_type=self.material_model_combo.currentText(), parameters=self._collect_material_parameters())
            self.current_model.upsert_material_definition(definition)
            self._populate_material_library()
            self._set_status(f'材料库已保存: {name}')

        def delete_material_definition(self) -> None:
            if self.current_model is None:
                return
            name = self._selected_material_definition_name()
            if not name:
                return
            self.current_model.remove_material_definition(name)
            self._populate_material_library()
            self._set_status(f'已删除材料库条目: {name}')

        def _selected_region_names(self) -> list[str]:
            rows = sorted({idx.row() for idx in self.region_table.selectionModel().selectedRows()}) if self.region_table.selectionModel() else []
            out: list[str] = []
            for row in rows:
                item = self.region_table.item(row, 0)
                if item:
                    out.append(item.text())
            return out

        def assign_material_to_regions(self) -> None:
            if self.current_model is None:
                return
            region_names = self._selected_region_names()
            material_name = self._selected_material_definition_name() or self.material_name_edit.text().strip()
            if not region_names or not material_name:
                self._set_status('请选择区域和材料库条目。')
                return
            try:
                self.current_model.assign_material_definition(region_names, material_name)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, '材料赋值失败', str(exc))
                return
            self._populate_region_table()
            self._update_validation()
            self._set_status(f'已将材料 {material_name} 赋给 {len(region_names)} 个区域。')

        def assign_current_material_to_regions(self) -> None:
            if self.current_model is None:
                return
            if self._apply_validation_result('material', self._validate_material_form(), block=True, title='材料参数校验失败'):
                return
            region_names = self._selected_region_names()
            if not region_names:
                self._set_status('请先选择一个或多个区域。')
                return
            model_type = self.material_model_combo.currentText() or 'linear_elastic'
            params = self._collect_material_parameters()
            for region_name in region_names:
                self.current_model.set_material(region_name, model_type, **params)
                binding = self.current_model.material_for_region(region_name)
                if binding is not None:
                    binding.metadata['library_name'] = '(custom)'
            self._populate_region_table(); self._update_validation(); self._set_status(f'已将当前参数赋给 {len(region_names)} 个区域。')

        def clear_material_from_regions(self) -> None:
            if self.current_model is None:
                return
            for name in self._selected_region_names():
                self.current_model.remove_material(name)
            self._populate_region_table(); self._update_validation(); self._set_status('已清除选中区域材料。')

        def rename_selected_region(self) -> None:
            if self.current_model is None:
                return
            names = self._selected_region_names()
            if len(names) != 1:
                self._set_status('请只选择一个区域进行重命名。')
                return
            new_name = self.region_name_edit.text().strip()
            if not new_name:
                self._set_status('请输入新的区域名称。')
                return
            self.current_model.rename_region(names[0], new_name)
            self._sync_all_views()
            self._set_status(f'区域已重命名为: {new_name}')

        # ---------- Stage editor ----------
        def _selected_stage_row(self) -> int | None:
            rows = self.stage_table.selectionModel().selectedRows() if self.stage_table.selectionModel() else []
            return rows[0].row() if rows else None

        def _selected_stage(self) -> AnalysisStage | None:
            if self.current_model is None:
                return None
            row = self._selected_stage_row()
            if row is None or row >= len(self.current_model.stages):
                return None
            return self.current_model.stages[row]

        def _on_stage_selection_changed(self) -> None:
            stage = self._selected_stage()
            self._loading_stage_editor = True
            if stage is None:
                self._loading_stage_editor = False
                return
            self.stage_name_edit.setText(stage.name)
            self.stage_steps_spin.setValue(int(stage.steps or 1))
            self.stage_initial_increment.setValue(float(stage.metadata.get('initial_increment', 0.25)))
            self.stage_max_iterations.setValue(int(stage.metadata.get('max_iterations', 24)))
            self.stage_line_search.setChecked(bool(stage.metadata.get('line_search', True)))
            self.stage_notes_edit.setPlainText(str(stage.metadata.get('notes', '')))
            amap = stage.metadata.get('activation_map') or self._previous_stage_activation_map(stage.name)
            self._populate_stage_region_lists(amap)
            self._populate_bc_table(stage)
            self._populate_load_table(stage)
            self._loading_stage_editor = False
            if hasattr(self, 'result_stage_combo') and self.result_stage_combo.findText(stage.name) >= 0:
                self.result_stage_combo.setCurrentText(stage.name)
            self._update_global_inspector()
            self.refresh_view()

        def add_stage(self) -> None:
            if self.current_model is None:
                return
            base = 'stage'
            idx = len(self.current_model.stages) + 1
            inherited = self._previous_stage_activation_map()
            self.current_model.stages.append(AnalysisStage(name=f'{base}_{idx}', steps=6, metadata={'activation_map': inherited, 'initial_increment': 0.25, 'max_iterations': 24, 'line_search': True}))
            self._populate_stage_table()
            if self.stage_table.rowCount() > 0:
                self.stage_table.selectRow(self.stage_table.rowCount() - 1)
            self._set_status('已新增 Stage（继承上一阶段激活状态）。')

        def remove_selected_stage(self) -> None:
            if self.current_model is None:
                return
            stage = self._selected_stage()
            if stage is None:
                return
            self.current_model.remove_stage(stage.name)
            self._populate_stage_table(); self._populate_bc_table(None); self._populate_load_table(None)
            self._set_status(f'已删除 Stage: {stage.name}')

        def save_current_stage(self) -> None:
            if self.current_model is None:
                return
            if self._apply_validation_result('stage', self._validate_stage_form(), block=True, title='Stage 参数校验失败'):
                return
            old_stage = self._selected_stage()
            name = self.stage_name_edit.text().strip() or (old_stage.name if old_stage else 'stage_1')
            steps = int(self.stage_steps_spin.value())
            activation_map = self._stage_activation_map_from_editor()
            prev = self._previous_stage_activation_map(old_stage.name if old_stage else None)
            activate = tuple(n for n, s in activation_map.items() if s and not prev.get(n, True))
            deactivate = tuple(n for n, s in activation_map.items() if (not s) and prev.get(n, True))
            metadata = dict(old_stage.metadata) if old_stage else {}
            metadata.update({'activation_map': dict(activation_map), 'initial_increment': float(self.stage_initial_increment.value()), 'max_iterations': int(self.stage_max_iterations.value()), 'line_search': bool(self.stage_line_search.isChecked()), 'notes': self.stage_notes_edit.toPlainText().strip()})
            if old_stage is None:
                stage = AnalysisStage(name=name, steps=steps, activate_regions=activate, deactivate_regions=deactivate, metadata=metadata)
            else:
                stage = AnalysisStage(name=name, steps=steps, activate_regions=activate, deactivate_regions=deactivate, boundary_conditions=old_stage.boundary_conditions, loads=old_stage.loads, metadata=metadata)
            self.current_model.upsert_stage(stage)
            self._populate_stage_table(); self._set_status(f'Stage 已保存: {name}')

        def clone_current_stage(self) -> None:
            if self.current_model is None:
                return
            stage = self._selected_stage()
            if stage is None:
                return
            clone_meta = dict(stage.metadata)
            clone_meta['activation_map'] = dict(stage.metadata.get('activation_map') or self._previous_stage_activation_map(stage.name))
            clone = AnalysisStage(name=f'{stage.name}_copy', activate_regions=stage.activate_regions, deactivate_regions=stage.deactivate_regions, boundary_conditions=tuple(stage.boundary_conditions), loads=tuple(stage.loads), steps=stage.steps, metadata=clone_meta)
            self.current_model.add_stage(clone)
            self._populate_stage_table(); self._set_status(f'已复制 Stage: {clone.name}')

        def _selected_bc_index(self) -> int | None:
            rows = self.bc_table.selectionModel().selectedRows() if self.bc_table.selectionModel() else []
            return rows[0].row() if rows else None

        def _selected_load_index(self) -> int | None:
            rows = self.load_table.selectionModel().selectedRows() if self.load_table.selectionModel() else []
            return rows[0].row() if rows else None

        def _on_bc_selection_changed(self) -> None:
            stage = self._selected_stage(); idx = self._selected_bc_index()
            if stage is None or idx is None or idx >= len(stage.boundary_conditions):
                return
            bc = stage.boundary_conditions[idx]
            self.bc_name_edit.setText(bc.name)
            self.bc_kind_combo.setCurrentText(bc.kind)
            self.bc_target_edit.setText(bc.target)
            self.bc_components_edit.setText(','.join(str(v) for v in bc.components))
            self.bc_values_edit.setText(','.join(str(v) for v in bc.values))
            self._refresh_form_validation()

        def _on_load_selection_changed(self) -> None:
            stage = self._selected_stage(); idx = self._selected_load_index()
            if stage is None or idx is None or idx >= len(stage.loads):
                return
            ld = stage.loads[idx]
            self.load_name_edit.setText(ld.name)
            self.load_kind_combo.setCurrentText(ld.kind)
            self.load_target_edit.setText(ld.target)
            self.load_values_edit.setText(','.join(str(v) for v in ld.values))
            self._refresh_form_validation()

        def add_or_update_bc(self) -> None:
            if self.current_model is None:
                return
            if self._apply_validation_result('bc', self._validate_bc_form(), block=True, title='边界条件参数校验失败'):
                return
            stage = self._selected_stage()
            if stage is None:
                self._set_status('请先选择一个 Stage。')
                return
            bc = BoundaryCondition(
                name=self.bc_name_edit.text().strip() or 'bc',
                kind=self.bc_kind_combo.currentText(),
                target=self.bc_target_edit.text().strip() or 'bottom',
                components=_parse_components(self.bc_components_edit.text()),
                values=_parse_values(self.bc_values_edit.text()),
            )
            items = list(stage.boundary_conditions)
            idx = self._selected_bc_index()
            if idx is not None and idx < len(items):
                items[idx] = bc
            else:
                items.append(bc)
            self.current_model.upsert_stage(AnalysisStage(name=stage.name, activate_regions=stage.activate_regions, deactivate_regions=stage.deactivate_regions, boundary_conditions=tuple(items), loads=stage.loads, steps=stage.steps, metadata=dict(stage.metadata)))
            self._on_stage_selection_changed(); self._populate_stage_table(); self._set_status(f'已保存 BC: {bc.name}')

        def remove_selected_bc(self) -> None:
            if self.current_model is None:
                return
            stage = self._selected_stage(); idx = self._selected_bc_index()
            if stage is None or idx is None:
                return
            items = list(stage.boundary_conditions)
            items.pop(idx)
            self.current_model.upsert_stage(AnalysisStage(name=stage.name, activate_regions=stage.activate_regions, deactivate_regions=stage.deactivate_regions, boundary_conditions=tuple(items), loads=stage.loads, steps=stage.steps, metadata=dict(stage.metadata)))
            self._on_stage_selection_changed(); self._populate_stage_table(); self._set_status('已删除 BC。')

        def add_or_update_load(self) -> None:
            if self.current_model is None:
                return
            if self._apply_validation_result('load', self._validate_load_form(), block=True, title='荷载参数校验失败'):
                return
            stage = self._selected_stage()
            if stage is None:
                self._set_status('请先选择一个 Stage。')
                return
            load = LoadDefinition(
                name=self.load_name_edit.text().strip() or 'load',
                kind=self.load_kind_combo.currentText(),
                target=self.load_target_edit.text().strip() or 'top',
                values=_parse_values(self.load_values_edit.text()),
            )
            items = list(stage.loads)
            idx = self._selected_load_index()
            if idx is not None and idx < len(items):
                items[idx] = load
            else:
                items.append(load)
            self.current_model.upsert_stage(AnalysisStage(name=stage.name, activate_regions=stage.activate_regions, deactivate_regions=stage.deactivate_regions, boundary_conditions=stage.boundary_conditions, loads=tuple(items), steps=stage.steps, metadata=dict(stage.metadata)))
            self._on_stage_selection_changed(); self._populate_stage_table(); self._set_status(f'已保存荷载: {load.name}')

        def remove_selected_load(self) -> None:
            if self.current_model is None:
                return
            stage = self._selected_stage(); idx = self._selected_load_index()
            if stage is None or idx is None:
                return
            items = list(stage.loads)
            items.pop(idx)
            self.current_model.upsert_stage(AnalysisStage(name=stage.name, activate_regions=stage.activate_regions, deactivate_regions=stage.deactivate_regions, boundary_conditions=stage.boundary_conditions, loads=tuple(items), steps=stage.steps, metadata=dict(stage.metadata)))
            self._on_stage_selection_changed(); self._populate_stage_table(); self._set_status('已删除荷载。')

        # ---------- Solver threading ----------
        def run_solver_async(self) -> None:
            if self.current_model is None:
                self._set_status('请先创建或导入模型。')
                return
            self._refresh_form_validation()
            blocking = [i for i in validate_model(self.current_model) if i.level == 'error']
            blocking += [i for i in self._validate_solver_form() if i.level == 'error']
            if blocking:
                self._update_validation()
                lines = []
                for i in blocking[:12]:
                    step = getattr(i, 'step', '参数')
                    lines.append(f'[{step}] {i.message}')
                QtWidgets.QMessageBox.warning(self, '模型校验未通过', '\n'.join(lines))
                self._set_status('模型校验未通过，请先修正参数。')
                return
            if self._solver_thread is not None:
                self._set_status('求解器正在运行。')
                return
            mesh_report = analyze_mesh(self.current_model)
            self.mesh_stats_label.setText(mesh_report.summary_text()) if hasattr(self, 'mesh_stats_label') else None
            if hasattr(self, 'result_mesh_summary'):
                self.result_mesh_summary.setText(mesh_report.summary_text())
            self._populate_mesh_check_table(mesh_report)
            if not mesh_report.ok:
                msg = '\n'.join(mesh_report.messages + mesh_report.warnings[:6])
                self._append_diagnostic('error', 'mesh', self._tt('Pre-solve mesh check failed.'), self._tt('Run the Meshing workflow and verify regions/materials before solving.'))
                QtWidgets.QMessageBox.warning(self, self._tt('Pre-solve mesh check failed'), msg)
                self._set_status(self._tt('Pre-solve mesh check failed.'))
                return
            self.current_model.clear_results()
            self._eta_estimator = ProgressEtaEstimator()
            self._clear_diagnostics()
            self.progress_overall.setRange(0, 0); self.progress_iter.setRange(0, 100); self.progress_overall.setValue(0); self.progress_iter.setValue(0); self.history_table.setRowCount(0)
            self._last_solver_payload = None
            self._last_solver_fraction = 0.0
            solver_settings = self._solver_settings()
            compute_summary = self._read_solver_compute_preferences().summary(cpu_total=getattr(self, '_cpu_core_total', None), cuda_available=getattr(self, '_cuda_available', False))
            self._append_task_row(self._tt('Solve'), '-', self._tt('Running'), self._tt(f'Background solve started: {compute_summary}'), self._tt('A progress dialog and status heartbeat will stay visible while solving.'))
            self._set_status(self._tt('Background solve started ...'))
            self.act_run.setEnabled(False); self.btn_run_solver.setEnabled(False); self.act_cancel.setEnabled(True); self.btn_cancel_solver.setEnabled(True)
            self._create_solver_progress_dialog()
            self._solver_heartbeat_timer.start()
            self._solver_thread = QtCore.QThread(self)
            self._solver_worker = SolverWorker(self.solver, self.current_model, solver_settings)
            self._solver_worker.moveToThread(self._solver_thread)
            self._solver_thread.started.connect(self._solver_worker.run)
            self._solver_worker.progress.connect(self._on_solver_progress)
            self._solver_worker.finished.connect(self._on_solver_finished)
            self._solver_worker.failed.connect(self._on_solver_failed)
            self._solver_worker.finished.connect(self._solver_thread.quit)
            self._solver_worker.failed.connect(self._solver_thread.quit)
            self._solver_thread.finished.connect(self._cleanup_solver_thread)
            self._solver_thread.start()

        def cancel_solver(self) -> None:
            if self._solver_worker is not None:
                self._solver_worker.cancel()
                self._set_status('已请求取消，等待当前迭代结束 ...')
                self._update_task_status('Canceling', self._tt('Waiting for the solver to exit at a safe checkpoint...'))
                self._update_solver_progress_dialog(text='Cancel requested... waiting for a safe checkpoint.')

        def _cleanup_solver_thread(self) -> None:
            self._solver_worker = None; self._solver_thread = None
            if self._solver_heartbeat_timer is not None:
                self._solver_heartbeat_timer.stop()
            self.act_run.setEnabled(True); self.btn_run_solver.setEnabled(True); self.act_cancel.setEnabled(False); self.btn_cancel_solver.setEnabled(False)

        def _on_solver_progress(self, payload: object) -> None:
            if not isinstance(payload, dict):
                return
            self._last_solver_payload = dict(payload)
            stage_index = int(payload.get('stage_index', 1) or 1)
            stage_count = int(payload.get('stage_count', 1) or 1)
            phase = str(payload.get('phase', ''))
            stage = str(payload.get('stage', ''))
            fraction = self._estimate_progress_fraction(payload)
            elapsed, eta = self._eta_estimator.update(fraction) if self._eta_estimator is not None else (0.0, None)
            self._last_solver_fraction = max(0.0, min(1.0, fraction))
            overall = int(100.0 * self._last_solver_fraction)
            detail = str(payload.get('message', ''))
            advice = ''
            state_text = phase or 'running'
            if phase == 'stage-complete':
                overall = int(100.0 * stage_index / max(stage_count, 1))
                self.progress_iter.setValue(100)
                self._append_task_row('Solve', stage, 'Stage complete', detail or 'Stage converged', '')
            elif 'iteration' in payload:
                iteration = int(payload.get('iteration', 0) or 0)
                step = int(payload.get('step', 0) or 0)
                ratio = float(payload.get('ratio', 0.0) or 0.0)
                alpha = float(payload.get('line_search_alpha', 1.0) or 1.0)
                self.progress_iter.setValue(max(1, min(99, iteration * 8)))
                self._append_history(payload)
                detail = f'step={step}, iter={iteration}, ratio={ratio:.3e}, alpha={alpha:.2f}'
                if ratio > 1e1:
                    advice = 'Residual is high; consider smaller increment or check material/BC settings.'
                    self._append_diagnostic('warning', stage or 'solver', f'High residual detected at step {step}, iteration {iteration}.', advice)
                elif alpha < 0.25:
                    advice = 'Line search is heavily damping the update; convergence may slow down.'
                state_text = 'nonlinear iteration'
            elif phase:
                state_text = phase
            eta_text = f'ETA {format_seconds(eta)} | Elapsed {format_seconds(elapsed)}'
            if self.progress_overall.maximum() == 0 and overall > 0:
                self.progress_overall.setRange(0, 100)
            self.progress_overall.setValue(max(0, min(100, overall)))
            self.progress_overall.setFormat(f'Overall %p% | {eta_text}')
            label_text = f'{stage} | {state_text} | {detail} | {eta_text}' if stage else f'{state_text} | {detail} | {eta_text}'
            self._update_task_status('Running', label_text, advice if advice else None)
            self.status_label.setText(self._tt(label_text.strip()))
            self._update_solver_progress_dialog(overall, label_text)

        def _on_solver_finished(self, solved_model: object, canceled: bool) -> None:
            self.current_model = solved_model
            self.progress_overall.setRange(0, 100); self.progress_overall.setValue(100); self.progress_iter.setValue(100 if not canceled else 0)
            self.progress_overall.setFormat('Overall %p%')
            self._update_solver_progress_dialog(100 if not canceled else 0, str(self.current_model.metadata.get('solver_note', 'Solve finished')) if self.current_model else 'Solve finished')
            self._sync_all_views()
            note = self.current_model.metadata.get('solver_note', 'Solve finished') if self.current_model else 'Solve finished'
            if canceled:
                note = f'Solve canceled (partial stage results were kept). {note}'
            self._set_status(str(note)); self._update_task_status('Completed' if not canceled else 'Canceled', str(note), 'Review result fields and convergence history.')
            self._append_diagnostic('info', 'solver', str(note), 'Open the History tab to review convergence and exported result fields.')
            self._close_solver_progress_dialog()

        def _on_solver_failed(self, error_text: str) -> None:
            self.progress_overall.setRange(0, 100)
            self.progress_iter.setValue(0)
            self.progress_overall.setFormat('Overall %p%')
            self._update_solver_progress_dialog(None, 'Solver failed. Preparing diagnostics...')
            fixes = self._suggest_fix_lines(error_text)
            advice = ' | '.join(fixes[:3])
            self._update_task_status('Failed', 'Solver exception, see logs for traceback.', advice)
            self._append_diagnostic('error', 'solver', 'Solver exception, see logs for traceback.', advice)
            self._log(error_text)
            tail = error_text.splitlines()[-1] if error_text.splitlines() else error_text
            msg = self._tt('Solver exception. Please review the traceback and repair suggestions below.') + "\n\n" + "\n".join(fixes[:5]) + "\n\n" + tail
            QtWidgets.QMessageBox.critical(self, self._tt('Solver failed'), msg)
            self._set_status('Solver failed')
            self._close_solver_progress_dialog()

        def _append_task_row(self, task: str, stage: str, status: str, detail: str, advice: str = '') -> None:
            self.task_table.insertRow(self.task_table.rowCount())
            row = self.task_table.rowCount() - 1
            self._task_row = row
            for col, value in enumerate([task, stage, status, detail, advice]):
                self.task_table.setItem(row, col, QtWidgets.QTableWidgetItem(self._tt(str(value))))
            self.task_table.scrollToBottom()

        def _update_task_status(self, status: str, detail: str, advice: str | None = None) -> None:
            if self._task_row is None:
                self._append_task_row('Solve', '-', status, detail, advice or '')
                return
            self.task_table.setItem(self._task_row, 2, QtWidgets.QTableWidgetItem(self._tt(status)))
            self.task_table.setItem(self._task_row, 3, QtWidgets.QTableWidgetItem(self._tt(detail)))
            if advice is not None:
                self.task_table.setItem(self._task_row, 4, QtWidgets.QTableWidgetItem(self._tt(advice)))

        def _append_history(self, payload: dict) -> None:
            row = self.history_table.rowCount(); self.history_table.insertRow(row)
            vals = [
                str(payload.get('stage', '')), str(payload.get('step', '')), str(payload.get('iteration', '')),
                f"{float(payload.get('ratio', 0.0)):.3e}", f"{float(payload.get('lambda', 0.0)):.3f}",
                str(payload.get('linear_backend', '')), f"{float(payload.get('line_search_alpha', 1.0)):.2f}", str(payload.get('phase', '')),
            ]
            for col, value in enumerate(vals):
                self.history_table.setItem(row, col, QtWidgets.QTableWidgetItem(value))
            self.history_table.scrollToBottom()

        # ---------- Export ----------
        def export_current(self) -> None:
            if self.current_model is None:
                self._set_status('No model loaded')
                return
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Export', str(Path.cwd() / 'model.vtu'), 'VTK/mesh (*.vtu *.vtk *.vtm *.xdmf *.obj *.ply *.stl *.vtp *.vtkhdf)')
            if not filename:
                return
            self.export_manager.export_model(self.current_model, filename)
            self._set_status(f'已导出: {filename}')

        def export_bundle(self) -> None:
            if self.current_model is None:
                self._set_status('No model loaded')
                return
            dirname = QtWidgets.QFileDialog.getExistingDirectory(self, 'Export ParaView bundle', str(Path.cwd() / 'bundle'))
            if not dirname:
                return
            files = self.export_manager.export_paraview_bundle(self.current_model, dirname)
            self._set_status(f'已导出 bundle，共 {len(files)} 个文件')

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    try:
        app.setWindowIcon(QtGui.QIcon(str(resolve_app_icon())))
    except Exception:
        pass
    window = MainWindow(); window.show(); app.exec()
