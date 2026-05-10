from __future__ import annotations

from pathlib import Path

from geoai_simkit._optional import require_optional_dependency
from geoai_simkit.app.workbench_panels import (
    build_alert_rows,
    build_blueprint_progress_rows,
    build_key_process_rows,
    build_runtime_log_lines,
    build_scene_summary_rows,
    build_workflow_metric_rows,
)
from geoai_simkit.examples.foundation_pit_showcase import build_foundation_pit_showcase_case
from geoai_simkit.post.viewer import PreviewBuilder


def launch_nextgen_workbench() -> None:
    require_optional_dependency('PySide6', feature='The desktop GUI', extra='gui')
    require_optional_dependency('pyvista', feature='The desktop GUI', extra='gui')
    require_optional_dependency('pyvistaqt', feature='The desktop GUI', extra='gui')

    from PySide6 import QtCore, QtGui, QtWidgets
    from pyvistaqt import QtInteractor

    from geoai_simkit.app.workbench import WorkbenchDocument, WorkbenchService

    class NextGenWorkbenchWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self._service = WorkbenchService()
            self._document = self._service.document_from_case(build_foundation_pit_showcase_case(), mode='geometry')
            self._ignore_table_events = False
            self._preview_builder = PreviewBuilder()
            self._viewport_actor_map: dict[str, dict[str, object]] = {}
            self._viewport_needs_reset = True
            self._build_ui()
            self._populate_all()
            self._update_window_title()

        def _build_ui(self) -> None:
            self.resize(1720, 1020)
            self._build_actions()
            splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
            self.setCentralWidget(splitter)

            self.left_tabs = QtWidgets.QTabWidget()
            self.model_tree = QtWidgets.QTreeWidget()
            self.model_tree.setHeaderLabels(['Model Browser'])
            self.model_tree.itemSelectionChanged.connect(self._sync_selection_from_model_tree)
            self.stage_tree = QtWidgets.QTreeWidget()
            self.stage_tree.setHeaderLabels(['Stages'])
            self.stage_tree.itemSelectionChanged.connect(self._sync_stage_selection_to_view)
            self.results_tree = QtWidgets.QTreeWidget()
            self.results_tree.setHeaderLabels(['Results'])
            self.results_tree.itemSelectionChanged.connect(self._sync_results_selection_to_view)
            self.left_tabs.addTab(self.model_tree, 'Model')
            self.left_tabs.addTab(self.stage_tree, 'Stages')
            self.left_tabs.addTab(self.results_tree, 'Results')

            center = QtWidgets.QWidget()
            center_layout = QtWidgets.QVBoxLayout(center)
            center_layout.setContentsMargins(0, 0, 0, 0)

            viewport_toolbar = QtWidgets.QHBoxLayout()
            viewport_toolbar.addWidget(QtWidgets.QLabel('Global mesh size'))
            self.mesh_size_spin = QtWidgets.QDoubleSpinBox()
            self.mesh_size_spin.setDecimals(3)
            self.mesh_size_spin.setRange(0.001, 1.0e6)
            self.mesh_size_spin.valueChanged.connect(self._apply_mesh_size)
            viewport_toolbar.addWidget(self.mesh_size_spin)
            viewport_toolbar.addSpacing(12)
            viewport_toolbar.addWidget(QtWidgets.QLabel('View'))
            self.view_mode_combo = QtWidgets.QComboBox()
            self.view_mode_combo.addItems(['normal', 'stage_activity', 'validation_regions', 'mesh_quality'])
            self.view_mode_combo.currentTextChanged.connect(lambda *_: self._populate_viewport())
            viewport_toolbar.addWidget(self.view_mode_combo)
            viewport_toolbar.addSpacing(8)
            viewport_toolbar.addWidget(QtWidgets.QLabel('Stage'))
            self.view_stage_combo = QtWidgets.QComboBox()
            self.view_stage_combo.currentTextChanged.connect(lambda *_: self._populate_viewport())
            viewport_toolbar.addWidget(self.view_stage_combo)
            self.view_edges_check = QtWidgets.QCheckBox('Edges')
            self.view_edges_check.setChecked(True)
            self.view_edges_check.toggled.connect(lambda *_: self._populate_viewport())
            viewport_toolbar.addWidget(self.view_edges_check)
            self.view_clip_combo = QtWidgets.QComboBox()
            self.view_clip_combo.addItems(['none', 'x', 'y', 'z'])
            self.view_clip_combo.currentTextChanged.connect(lambda *_: self._populate_viewport())
            viewport_toolbar.addWidget(QtWidgets.QLabel('Clip'))
            viewport_toolbar.addWidget(self.view_clip_combo)
            self.view_reset_btn = QtWidgets.QPushButton('Reset Camera')
            self.view_reset_btn.clicked.connect(self._reset_view_camera)
            viewport_toolbar.addWidget(self.view_reset_btn)
            self.view_showcase_btn = QtWidgets.QPushButton('Load Foundation Pit Demo')
            self.view_showcase_btn.clicked.connect(self._load_demo_case)
            viewport_toolbar.addWidget(self.view_showcase_btn)
            viewport_toolbar.addStretch(1)
            self.validation_badge = QtWidgets.QLabel('Validation: unknown')
            viewport_toolbar.addWidget(self.validation_badge)
            center_layout.addLayout(viewport_toolbar)

            center_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
            self.viewport = QtInteractor(center)
            center_splitter.addWidget(self.viewport.interactor)

            self.bottom_tabs = QtWidgets.QTabWidget()
            self.runtime_log = QtWidgets.QPlainTextEdit()
            self.runtime_log.setReadOnly(True)
            self.alert_table = QtWidgets.QTableWidget(0, 4)
            self.alert_table.setHorizontalHeaderLabels(['Severity', 'Source', 'Message', 'Hint'])
            self.alert_table.horizontalHeader().setStretchLastSection(True)
            self.workflow_metrics_table = QtWidgets.QTableWidget(0, 2)
            self.workflow_metrics_table.setHorizontalHeaderLabels(['Metric', 'Value'])
            self.workflow_metrics_table.horizontalHeader().setStretchLastSection(True)
            self.process_table = QtWidgets.QTableWidget(0, 3)
            self.process_table.setHorizontalHeaderLabels(['Process', 'State', 'Detail'])
            self.process_table.horizontalHeader().setStretchLastSection(True)
            self.scene_summary_table = QtWidgets.QTableWidget(0, 2)
            self.scene_summary_table.setHorizontalHeaderLabels(['Scene metric', 'Value'])
            self.scene_summary_table.horizontalHeader().setStretchLastSection(True)
            self.blueprint_progress_table = QtWidgets.QTableWidget(0, 7)
            self.blueprint_progress_table.setHorizontalHeaderLabels(['Plane', 'Module', 'Section', 'Progress', 'Status', 'Summary', 'Next'])
            self.blueprint_progress_table.horizontalHeader().setStretchLastSection(True)
            self.bottom_tabs.addTab(self.runtime_log, 'Runtime Log')
            self.bottom_tabs.addTab(self.alert_table, 'Alerts / Bugs')
            self.bottom_tabs.addTab(self.workflow_metrics_table, 'Workflow Metrics')
            self.bottom_tabs.addTab(self.process_table, 'Key Processes')
            self.bottom_tabs.addTab(self.scene_summary_table, 'Scene / View')
            self.bottom_tabs.addTab(self.blueprint_progress_table, 'Blueprint Progress')
            center_splitter.addWidget(self.bottom_tabs)
            center_splitter.setSizes([760, 250])
            center_layout.addWidget(center_splitter)

            self.right_tabs = QtWidgets.QTabWidget()
            self.properties = QtWidgets.QTableWidget(0, 2)
            self.properties.setHorizontalHeaderLabels(['Property', 'Value'])
            self.properties.horizontalHeader().setStretchLastSection(True)

            self.block_table = QtWidgets.QTableWidget(0, 4)
            self.block_table.setHorizontalHeaderLabels(['Block', 'Material', 'Visible', 'Locked'])
            self.block_table.horizontalHeader().setStretchLastSection(True)
            self.block_table.itemChanged.connect(self._on_block_item_changed)
            self.block_table.itemSelectionChanged.connect(self._sync_selection_from_block_table)

            self.stage_matrix = QtWidgets.QTableWidget(0, 0)
            self.stage_matrix.itemChanged.connect(self._on_stage_item_changed)

            self.validation_table = QtWidgets.QTableWidget(0, 4)
            self.validation_table.setHorizontalHeaderLabels(['Level', 'Code', 'Message', 'Hint'])
            self.validation_table.horizontalHeader().setStretchLastSection(True)
            self.validation_table.setWordWrap(True)

            self.jobs_table = QtWidgets.QTableWidget(0, 2)
            self.jobs_table.setHorizontalHeaderLabels(['Item', 'Value'])
            self.jobs_table.horizontalHeader().setStretchLastSection(True)

            self.mesh_preview_table = QtWidgets.QTableWidget(0, 9)
            self.mesh_preview_table.setHorizontalHeaderLabels(['Layer', 'Block', 'Cells', 'Material', 'Min thickness', 'Max thk ratio', 'Degenerate', 'Needs remesh', 'Warnings'])
            self.mesh_preview_table.horizontalHeader().setStretchLastSection(True)
            self.mesh_preview_table.setWordWrap(True)

            self.messages = QtWidgets.QPlainTextEdit()
            self.messages.setReadOnly(True)

            self.right_tabs.addTab(self.properties, 'Properties')
            self.right_tabs.addTab(self.block_table, 'Blocks')
            self.right_tabs.addTab(self.stage_matrix, 'Stage Matrix')
            self.right_tabs.addTab(self.validation_table, 'Validation')
            self.right_tabs.addTab(self.mesh_preview_table, 'Mesh Preview')
            self.right_tabs.addTab(self.jobs_table, 'Jobs')
            self.right_tabs.addTab(self.messages, 'Messages')

            splitter.addWidget(self.left_tabs)
            splitter.addWidget(center)
            splitter.addWidget(self.right_tabs)
            splitter.setSizes([300, 980, 470])

            self.statusBar().showMessage('NextGen workbench ready')

        def _build_actions(self) -> None:
            self.mode_bar = QtWidgets.QToolBar('Modes', self)
            self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, self.mode_bar)
            self._mode_actions: dict[str, QtGui.QAction] = {}
            mode_group = QtGui.QActionGroup(self)
            mode_group.setExclusive(True)
            for key, label in [('geometry', 'Geometry'), ('partition', 'Partition'), ('mesh', 'Mesh'), ('assign', 'Assign'), ('stage', 'Stage'), ('solve', 'Solve'), ('results', 'Results')]:
                act = self.mode_bar.addAction(label)
                act.setCheckable(True)
                act.triggered.connect(lambda checked=False, k=key: self._set_mode(k))
                mode_group.addAction(act)
                self._mode_actions[key] = act
            self._mode_actions['geometry'].setChecked(True)

            file_bar = QtWidgets.QToolBar('File', self)
            self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, file_bar)
            open_action = file_bar.addAction('Open Case…')
            open_action.triggered.connect(self._open_case)
            import_stl_action = file_bar.addAction('Import STL Geology…')
            import_stl_action.triggered.connect(self._import_stl_geology)
            import_borehole_csv_action = file_bar.addAction('Import Borehole CSV')
            import_borehole_csv_action.triggered.connect(self._import_borehole_csv)
            load_demo_action = file_bar.addAction('Load Demo')
            load_demo_action.triggered.connect(self._load_demo_case)
            load_showcase_action = file_bar.addAction('Load Foundation Pit Showcase')
            load_showcase_action.triggered.connect(self._load_demo_case)
            save_action = file_bar.addAction('Save')
            save_action.triggered.connect(self._save_case)
            save_as_action = file_bar.addAction('Save As…')
            save_as_action.triggered.connect(self._save_case_as)
            refresh_action = file_bar.addAction('Refresh')
            refresh_action.triggered.connect(self._refresh_document)
            validate_action = file_bar.addAction('Validate')
            validate_action.triggered.connect(self._validate_document)

            mesh_bar = QtWidgets.QToolBar('Mesh', self)
            self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, mesh_bar)
            layered_mesh_action = mesh_bar.addAction('Generate Layered Mesh')
            layered_mesh_action.triggered.connect(self._generate_layered_volume_mesh)

            stage_bar = QtWidgets.QToolBar('Stage', self)
            self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, stage_bar)
            add_stage_action = stage_bar.addAction('Add Stage')
            add_stage_action.triggered.connect(self._add_stage)
            clone_stage_action = stage_bar.addAction('Clone Stage')
            clone_stage_action.triggered.connect(self._clone_selected_stage)
            remove_stage_action = stage_bar.addAction('Remove Stage')
            remove_stage_action.triggered.connect(self._remove_selected_stage)
            predecessor_action = stage_bar.addAction('Set Predecessor')
            predecessor_action.triggered.connect(self._set_selected_stage_predecessor)

            solve_bar = QtWidgets.QToolBar('Solve', self)
            self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, solve_bar)
            plan_action = solve_bar.addAction('Plan Job')
            plan_action.triggered.connect(self._plan_job)
            run_action = solve_bar.addAction('Run CPU-Robust')
            run_action.triggered.connect(self._run_job)

        def _update_window_title(self) -> None:
            source = self._document.file_path or f'{self._document.case.name} (unsaved)'
            dirty_mark = '*' if self._document.dirty else ''
            self.setWindowTitle(f'geoai-simkit — NextGen Workbench {dirty_mark}— {source}')

        def _append_message(self, text: str) -> None:
            current = self.messages.toPlainText().strip()
            new_text = text if not current else current + '\n' + text
            self.messages.setPlainText(new_text)

        def _set_mode(self, mode: str) -> None:
            self._service.set_mode(self._document, mode)
            self.statusBar().showMessage(f'Mode: {mode}')
            self._populate_properties()
            self._update_window_title()

        def _confirm_discard_if_dirty(self) -> bool:
            if not self._document.dirty:
                return True
            result = QtWidgets.QMessageBox.question(
                self,
                'Unsaved changes',
                'Current document has unsaved changes. Continue and discard them?',
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            return result == QtWidgets.QMessageBox.StandardButton.Yes

        def _open_case(self) -> None:
            if not self._confirm_discard_if_dirty():
                self._fill_key_value_table(self.scene_summary_table, build_scene_summary_rows(self._document, actor_map={}, view_mode='normal', stage_name='<model>'))
                return
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Open case', self._document.file_path or '.', 'Case files (*.json *.yaml *.yml)')
            if not path:
                return
            try:
                self._document = self._service.load_document(path, mode=self._document.mode)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, 'Open case failed', str(exc))
                return
            self._populate_all()
            self._update_window_title()
            self.statusBar().showMessage(f'Opened {path}')

        def _import_stl_geology(self) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Import STL geological model', self._document.file_path or '.', 'STL files (*.stl);;All files (*.*)')
            if not path:
                return
            scale, ok = QtWidgets.QInputDialog.getDouble(self, 'STL unit scale', 'Scale to project length unit (m). Use 0.001 for mm, 1.0 for m.', 1.0, 1.0e-12, 1.0e12, 9)
            if not ok:
                return
            material, ok = QtWidgets.QInputDialog.getText(self, 'STL material id', 'Default material id for imported geological surface', text='imported_geology')
            if not ok:
                return
            try:
                summary = self._service.import_stl_geology(self._document, path, unit_scale=float(scale), material_id=str(material or 'imported_geology'), role='geology_surface', replace=True)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, 'Import STL failed', str(exc))
                return
            self._viewport_needs_reset = True
            self._populate_all()
            self._update_window_title()
            self.statusBar().showMessage(f"Imported STL: {summary.get('name', path)} | triangles={summary.get('triangle_count', '?')}")

        def _import_borehole_csv(self) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Import borehole CSV', self._document.file_path or '.', 'CSV files (*.csv);;All files (*.*)')
            if not path:
                return
            mode, ok = QtWidgets.QInputDialog.getItem(self, 'Borehole interval mode', 'Top/bottom values', ['depth', 'elevation'], 0, False)
            if not ok:
                return
            scale, ok = QtWidgets.QInputDialog.getDouble(self, 'CSV unit scale', 'Scale to project length unit (m). Use 1.0 for m.', 1.0, 1.0e-12, 1.0e12, 9)
            if not ok:
                return
            try:
                summary = self._service.import_borehole_csv_geology(self._document, path, unit_scale=float(scale), top_bottom_mode=str(mode))
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, 'Import borehole CSV failed', str(exc))
                return
            self._populate_all()
            self._update_window_title()
            metadata = dict(summary.get('metadata', {}) or {})
            self.statusBar().showMessage(
                f"Imported boreholes: {metadata.get('borehole_count', 0)} | layer surfaces={metadata.get('layer_surface_count', 0)}"
            )

        def _generate_layered_volume_mesh(self) -> None:
            nx, ok = QtWidgets.QInputDialog.getInt(self, 'Layered mesh grid', 'Grid points in X direction', 8, 2, 200, 1)
            if not ok:
                return
            ny, ok = QtWidgets.QInputDialog.getInt(self, 'Layered mesh grid', 'Grid points in Y direction', 8, 2, 200, 1)
            if not ok:
                return
            try:
                result = self._service.generate_layered_volume_mesh(self._document, nx=int(nx), ny=int(ny))
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, 'Generate layered mesh failed', str(exc))
                return
            if not result.ok:
                QtWidgets.QMessageBox.warning(self, 'Generate layered mesh failed', result.message)
                return
            self._viewport_needs_reset = True
            self._populate_all()
            self.right_tabs.setCurrentWidget(self.mesh_preview_table)
            self._update_window_title()
            self.statusBar().showMessage(result.message)

        def _load_demo_case(self) -> None:
            if not self._confirm_discard_if_dirty():
                return
            self._document = self._service.document_from_case(build_foundation_pit_showcase_case(), mode='geometry')
            self._document.messages.append('Loaded built-in foundation pit showcase demo into the next-generation workbench.')
            self._populate_all()
            self._update_window_title()
            self.statusBar().showMessage('Loaded demo case')

        def _save_case(self) -> None:
            if self._document.file_path:
                saved = self._service.save_document(self._document)
                self._append_message(f'Saved case to {saved}')
                self._populate_all()
                self._update_window_title()
                self.statusBar().showMessage(f'Saved {saved}')
            else:
                self._save_case_as()

        def _save_case_as(self) -> None:
            out_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save case as', self._document.file_path or f'{self._document.case.name}.json', 'Case files (*.json *.yaml *.yml)')
            if not out_path:
                return
            saved = self._service.save_document(self._document, out_path)
            self._append_message(f'Saved case to {saved}')
            self._populate_all()
            self._update_window_title()
            self.statusBar().showMessage(f'Saved {saved}')

        def _refresh_document(self) -> None:
            self._document = self._service.refresh_document(self._document, preserve_results=True)
            self._populate_all()
            self._update_window_title()
            self.statusBar().showMessage('Document refreshed')

        def _validate_document(self) -> None:
            validation = self._service.validate_document(self._document)
            self._populate_validation()
            self._populate_properties()
            self._populate_messages_only()
            self._populate_bottom_panel()
            self._populate_viewport()
            self._update_window_title()
            self.right_tabs.setCurrentWidget(self.validation_table)
            self.statusBar().showMessage(
                f'Validation updated: ok={validation.ok} errors={validation.error_count} warnings={validation.warning_count}'
            )

        def _selected_stage_name(self) -> str | None:
            item = self.stage_tree.currentItem()
            if item is None:
                return None
            return str(item.data(0, QtCore.Qt.ItemDataRole.UserRole) or item.text(0).split('|', 1)[0].strip())

        def _add_stage(self) -> None:
            text, ok = QtWidgets.QInputDialog.getText(self, 'Add stage', 'Stage name')
            if not ok or not text.strip():
                return
            try:
                self._service.add_stage(self._document, text.strip(), copy_from=self._document.browser.stage_rows[-1].name if self._document.browser.stage_rows else None)
                self._document = self._service.refresh_document(self._document, preserve_results=True)
                self._populate_all()
                self._update_window_title()
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, 'Add stage failed', str(exc))

        def _clone_selected_stage(self) -> None:
            stage_name = self._selected_stage_name()
            if stage_name is None:
                QtWidgets.QMessageBox.information(self, 'Clone stage', 'Select a stage first.')
                return
            text, ok = QtWidgets.QInputDialog.getText(self, 'Clone stage', 'New stage name')
            if not ok or not text.strip():
                return
            try:
                self._service.clone_stage(self._document, stage_name, text.strip())
                self._document = self._service.refresh_document(self._document, preserve_results=True)
                self._populate_all()
                self._update_window_title()
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, 'Clone stage failed', str(exc))

        def _remove_selected_stage(self) -> None:
            stage_name = self._selected_stage_name()
            if stage_name is None:
                QtWidgets.QMessageBox.information(self, 'Remove stage', 'Select a stage first.')
                return
            if len(self._document.browser.stage_rows) <= 1:
                QtWidgets.QMessageBox.information(self, 'Remove stage', 'At least one stage must remain in the case.')
                return
            result = QtWidgets.QMessageBox.question(
                self,
                'Remove stage',
                f'Remove stage {stage_name}?',
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if result != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            try:
                self._service.remove_stage(self._document, stage_name)
                self._document = self._service.refresh_document(self._document, preserve_results=True)
                self._populate_all()
                self._update_window_title()
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, 'Remove stage failed', str(exc))

        def _set_selected_stage_predecessor(self) -> None:
            stage_name = self._selected_stage_name()
            if stage_name is None:
                QtWidgets.QMessageBox.information(self, 'Set predecessor', 'Select a stage first.')
                return
            choices = ['<root>'] + [row.name for row in self._document.browser.stage_rows if row.name != stage_name]
            current_row = next((row for row in self._document.browser.stage_rows if row.name == stage_name), None)
            current_pred = current_row.predecessor if current_row is not None else None
            current_index = choices.index(current_pred) if current_pred in choices else 0
            text, ok = QtWidgets.QInputDialog.getItem(self, 'Set predecessor', f'Predecessor for {stage_name}', choices, current_index, False)
            if not ok:
                return
            predecessor = None if text == '<root>' else str(text)
            try:
                self._service.set_stage_predecessor(self._document, stage_name, predecessor)
                self._document = self._service.refresh_document(self._document, preserve_results=True)
                self._populate_all()
                self._update_window_title()
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, 'Set predecessor failed', str(exc))

        def _plan_job(self) -> None:
            plan = self._service.plan_document(self._document, execution_profile='cpu-robust', device='cpu')
            self._append_message(f'Planned job: profile={plan.profile} device={plan.device} threads={plan.thread_count}')
            self._populate_jobs()
            self._populate_bottom_panel()
            self.statusBar().showMessage('Job plan updated')

        def _run_job(self) -> None:
            out_dir = Path('exports_nextgen_gui')
            try:
                run = self._service.run_document(self._document, out_dir, execution_profile='cpu-robust', device='cpu', export_stage_series=False)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, 'Run failed', str(exc))
                return
            self._append_message(f'Job completed: {run.out_path}')
            self._populate_results_tree()
            self._populate_jobs()
            self._populate_properties()
            self._populate_bottom_panel()
            self._populate_viewport()
            self._update_window_title()
            self.statusBar().showMessage(f'Job completed -> {run.out_path}')

        def _apply_mesh_size(self, value: float) -> None:
            if self._ignore_table_events:
                return
            self._service.set_mesh_global_size(self._document, value)
            self._populate_messages_only()
            self._populate_properties()
            self._update_window_title()

        def _on_block_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
            if self._ignore_table_events:
                return
            row = item.row()
            block_name_item = self.block_table.item(row, 0)
            if block_name_item is None:
                return
            block_name = block_name_item.text()
            col = item.column()
            if col == 1:
                self._service.set_block_material(self._document, block_name, item.text().strip())
            elif col == 2:
                self._service.set_block_flags(self._document, block_name, visible=item.checkState() == QtCore.Qt.CheckState.Checked)
            elif col == 3:
                self._service.set_block_flags(self._document, block_name, locked=item.checkState() == QtCore.Qt.CheckState.Checked)
            self._document = self._service.refresh_document(self._document, preserve_results=True)
            self._populate_all()
            self._update_window_title()

        def _on_stage_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
            if self._ignore_table_events:
                return
            stage_name = self.stage_matrix.verticalHeaderItem(item.row()).text()
            region_name = self.stage_matrix.horizontalHeaderItem(item.column()).text()
            active = item.checkState() == QtCore.Qt.CheckState.Checked
            self._service.set_stage_region_state(self._document, stage_name, region_name, active)
            self._document = self._service.refresh_document(self._document, preserve_results=True)
            self._populate_all()
            self._update_window_title()

        def _sync_selection_from_model_tree(self) -> None:
            item = self.model_tree.currentItem()
            if item is None:
                return
            payload = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if not payload or payload[0] != 'block':
                return
            block_name = str(payload[1])
            self._select_block_row(block_name)
            self.right_tabs.setCurrentWidget(self.block_table)
            self._populate_viewport()

        def _sync_selection_from_block_table(self) -> None:
            if self._ignore_table_events:
                return
            row = self.block_table.currentRow()
            if row < 0:
                return
            item = self.block_table.item(row, 0)
            if item is None:
                return
            block_name = item.text()
            self._select_model_tree_block(block_name)
            self.statusBar().showMessage(f'Selected block: {block_name}')
            self._populate_viewport()

        def _select_block_row(self, block_name: str) -> None:
            for row in range(self.block_table.rowCount()):
                item = self.block_table.item(row, 0)
                if item is not None and item.text() == block_name:
                    self.block_table.setCurrentCell(row, 0)
                    return

        def _select_model_tree_block(self, block_name: str) -> None:
            root = self.model_tree.topLevelItem(0)
            if root is None:
                return
            for idx in range(root.childCount()):
                group = root.child(idx)
                if group is None or group.text(0) != 'Blocks':
                    continue
                for j in range(group.childCount()):
                    child = group.child(j)
                    payload = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                    if payload and payload[0] == 'block' and str(payload[1]) == block_name:
                        self.model_tree.setCurrentItem(child)
                        return

        def _populate_all(self) -> None:
            self._ignore_table_events = True
            try:
                self._populate_model_tree()
                self._populate_stage_tree()
                self._populate_results_tree()
                self._populate_properties()
                self._populate_block_table()
                self._populate_stage_matrix()
                self._populate_validation()
                self._populate_mesh_preview()
                self._populate_jobs()
                self.mesh_size_spin.setValue(float(self._document.case.mesh.global_size))
                self._populate_messages_only()
                self._populate_view_controls()
                self._populate_viewport()
                self._populate_bottom_panel()
                current_mode = self._document.mode
                if current_mode in self._mode_actions:
                    self._mode_actions[current_mode].setChecked(True)
            finally:
                self._ignore_table_events = False

        def _populate_messages_only(self) -> None:
            self.messages.setPlainText('\n'.join(self._document.messages or ['Object viewer has been removed. Use the fixed browser, properties, validation and stage matrix workflow.']))

        def _populate_model_tree(self) -> None:
            self.model_tree.clear()
            root = QtWidgets.QTreeWidgetItem([self._document.browser.model_name])
            self.model_tree.addTopLevelItem(root)
            blocks_item = QtWidgets.QTreeWidgetItem(['Blocks'])
            root.addChild(blocks_item)
            for block in self._document.browser.blocks:
                display_name = str((block.metadata or {}).get('display_name') or block.name)
                label = f"{display_name} ({block.material_name or 'unassigned'})"
                child = QtWidgets.QTreeWidgetItem([label])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, ('block', block.name))
                blocks_item.addChild(child)
            objects_item = QtWidgets.QTreeWidgetItem([f"Objects ({self._document.browser.object_count})"])
            root.addChild(objects_item)
            self.model_tree.expandAll()

        def _populate_stage_tree(self) -> None:
            self.stage_tree.clear()
            for row in self._document.browser.stage_rows:
                pred = row.predecessor or '<root>'
                text = f"{row.name} | prev={pred} | +{len(row.activate_regions)} / -{len(row.deactivate_regions)} | BC={row.boundary_condition_count} | L={row.load_count}"
                item = QtWidgets.QTreeWidgetItem([text])
                item.setData(0, QtCore.Qt.ItemDataRole.UserRole, row.name)
                self.stage_tree.addTopLevelItem(item)

        def _populate_results_tree(self) -> None:
            self.results_tree.clear()
            if self._document.results is None:
                self.results_tree.addTopLevelItem(QtWidgets.QTreeWidgetItem(['No results loaded']))
                return
            for stage_name in self._document.results.stages:
                stage_item = QtWidgets.QTreeWidgetItem([stage_name])
                self.results_tree.addTopLevelItem(stage_item)
            self.results_tree.expandAll()

        def _populate_properties(self) -> None:
            rows = [
                ('Mode', self._document.mode),
                ('Dirty', str(self._document.dirty)),
                ('File', self._document.file_path or '<unsaved>'),
                ('Geometry state', self._document.browser.geometry_state),
                ('Blocks', str(len(self._document.browser.blocks))),
                ('Stages', str(len(self._document.browser.stage_rows))),
                ('Stage roots', str(sum(1 for row in self._document.browser.stage_rows if row.predecessor in {None, ''}))),
                ('Interfaces', str(self._document.browser.interface_count)),
                ('Interface elements', str(self._document.browser.interface_element_count)),
                ('Structures', str(self._document.browser.structure_count)),
            ]
            stl_summary = self._document.metadata.get('stl_geology') if isinstance(self._document.metadata, dict) else None
            if isinstance(stl_summary, dict):
                quality = dict(stl_summary.get('quality', {}) or {})
                rows.extend([
                    ('STL source', str(stl_summary.get('source_path', ''))),
                    ('STL triangles', str(stl_summary.get('triangle_count', 0))),
                    ('STL vertices', str(stl_summary.get('vertex_count', 0))),
                    ('STL closed', str(quality.get('is_closed', False))),
                    ('STL boundary edges', str(quality.get('boundary_edge_count', 0))),
                ])
            borehole_summary = self._document.metadata.get('borehole_csv_import') if isinstance(self._document.metadata, dict) else None
            if isinstance(borehole_summary, dict):
                metadata = dict(borehole_summary.get('metadata', {}) or {})
                rows.extend([
                    ('Borehole CSV source', str(borehole_summary.get('source_path', ''))),
                    ('Boreholes', str(metadata.get('borehole_count', 0))),
                    ('Layer surfaces', str(metadata.get('layer_surface_count', 0))),
                    ('Initial soil volumes', str(metadata.get('volume_count', 0))),
                ])
            mesh_summary = self._document.metadata.get('geoproject_mesh_summary') if isinstance(self._document.metadata, dict) else None
            if isinstance(mesh_summary, dict):
                rows.extend([
                    ('GeoProject mesher', str(mesh_summary.get('mesher', ''))),
                    ('GeoProject mesh cells', str(mesh_summary.get('cell_count', 0))),
                    ('GeoProject mesh nodes', str(mesh_summary.get('node_count', 0))),
                ])
            if self._document.preprocess is not None:
                rows.extend([
                    ('Boundary adjacencies', str(self._document.preprocess.n_boundary_adjacencies)),
                    ('Interface candidates', str(self._document.preprocess.n_interface_candidates)),
                    ('Node split plans', str(self._document.preprocess.n_node_split_plans)),
                    ('Preprocessor interface elements', str(self._document.preprocess.n_interface_elements)),
                ])
            if self._document.validation is not None:
                rows.extend([
                    ('Validation ok', str(self._document.validation.ok)),
                    ('Validation errors', str(self._document.validation.error_count)),
                    ('Validation warnings', str(self._document.validation.warning_count)),
                    ('Validation info', str(self._document.validation.info_count)),
                ])
            self.properties.setRowCount(0)
            for r, (k, v) in enumerate(rows):
                self.properties.insertRow(r)
                self.properties.setItem(r, 0, QtWidgets.QTableWidgetItem(str(k)))
                self.properties.setItem(r, 1, QtWidgets.QTableWidgetItem(str(v)))

        def _populate_block_table(self) -> None:
            blocks = list(self._document.browser.blocks)
            self.block_table.setRowCount(0)
            for r, block in enumerate(blocks):
                self.block_table.insertRow(r)
                name_item = QtWidgets.QTableWidgetItem(block.name)
                name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                mat_item = QtWidgets.QTableWidgetItem(block.material_name or '')
                vis_item = QtWidgets.QTableWidgetItem('')
                vis_item.setFlags(vis_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                vis_item.setCheckState(QtCore.Qt.CheckState.Checked if block.visible else QtCore.Qt.CheckState.Unchecked)
                lock_item = QtWidgets.QTableWidgetItem('')
                lock_item.setFlags(lock_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                lock_item.setCheckState(QtCore.Qt.CheckState.Checked if block.locked else QtCore.Qt.CheckState.Unchecked)
                self.block_table.setItem(r, 0, name_item)
                self.block_table.setItem(r, 1, mat_item)
                self.block_table.setItem(r, 2, vis_item)
                self.block_table.setItem(r, 3, lock_item)
            self.block_table.resizeColumnsToContents()

        def _populate_stage_matrix(self) -> None:
            stages = [row.name for row in self._document.browser.stage_rows]
            blocks = [block.name for block in self._document.browser.blocks]
            self.stage_matrix.setRowCount(len(stages))
            self.stage_matrix.setColumnCount(len(blocks))
            self.stage_matrix.setVerticalHeaderLabels(stages)
            self.stage_matrix.setHorizontalHeaderLabels(blocks)
            for row_idx, stage_name in enumerate(stages):
                for col_idx, block_name in enumerate(blocks):
                    state = self._service.stage_region_state(self._document, stage_name, block_name)
                    item = QtWidgets.QTableWidgetItem('')
                    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(QtCore.Qt.CheckState.Checked if state is not False else QtCore.Qt.CheckState.Unchecked)
                    self.stage_matrix.setItem(row_idx, col_idx, item)
            self.stage_matrix.resizeColumnsToContents()

        def _populate_validation(self) -> None:
            validation = self._document.validation
            self.validation_table.setRowCount(0)
            if validation is None:
                self.validation_badge.setText('Validation: unavailable')
                return
            badge = f'Validation: ok={validation.ok} | E={validation.error_count} W={validation.warning_count} I={validation.info_count}'
            self.validation_badge.setText(badge)
            for r, issue in enumerate(validation.issues):
                self.validation_table.insertRow(r)
                self.validation_table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(issue.get('level', ''))))
                self.validation_table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(issue.get('code', ''))))
                self.validation_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(issue.get('message', ''))))
                self.validation_table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(issue.get('hint', ''))))
            self.validation_table.resizeColumnsToContents()

        def _populate_mesh_preview(self) -> None:
            payload = self._service.layered_mesh_preview_payload(self._document)
            rows = [
                {
                    'layer_id': '<summary>',
                    'block_id': str(payload.get('mesher') or '<not generated>'),
                    'cell_count': int(payload.get('cell_count', 0) or 0),
                    'material_id': ', '.join(payload.get('material_tags', []) or []),
                    'min_thickness': payload.get('min_thickness'),
                    'max_thickness_ratio': payload.get('max_thickness_ratio'),
                    'degenerate_cell_count': payload.get('degenerate_cell_count', 0),
                    'needs_remesh': bool(payload.get('needs_remesh', True)),
                    'warnings': list(payload.get('warnings', []) or []),
                }
            ]
            rows.extend(list(payload.get('layers', []) or []))
            self.mesh_preview_table.setRowCount(0)
            for r, row in enumerate(rows):
                self.mesh_preview_table.insertRow(r)
                values = [
                    row.get('layer_id', ''),
                    row.get('block_id', ''),
                    row.get('cell_count', 0),
                    row.get('material_id', ''),
                    '' if row.get('min_thickness') is None else f"{float(row.get('min_thickness')):.6g}",
                    '' if row.get('max_thickness_ratio') is None else f"{float(row.get('max_thickness_ratio')):.6g}",
                    row.get('degenerate_cell_count', 0),
                    'yes' if bool(row.get('needs_remesh', True)) else 'no',
                    '; '.join(str(item) for item in list(row.get('warnings', []) or [])),
                ]
                for c, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                    self.mesh_preview_table.setItem(r, c, item)
            self.mesh_preview_table.resizeColumnsToContents()

        def _populate_jobs(self) -> None:
            rows = []
            if self._document.job_plan is not None:
                rows.extend([
                    ('Planned profile', self._document.job_plan.profile),
                    ('Planned device', self._document.job_plan.device),
                    ('Threads', str(self._document.job_plan.thread_count)),
                    ('CUDA available', str(self._document.job_plan.has_cuda)),
                    ('Plan note', self._document.job_plan.note),
                ])
            if self._document.results is not None:
                rows.extend([
                    ('Result stages', str(self._document.results.stage_count)),
                    ('Result fields', str(self._document.results.field_count)),
                ])
            self.jobs_table.setRowCount(0)
            for r, (k, v) in enumerate(rows):
                self.jobs_table.insertRow(r)
                self.jobs_table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(k)))
                self.jobs_table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(v)))


        def _populate_view_controls(self) -> None:
            current = self.view_stage_combo.currentText() if self.view_stage_combo.count() else '<model>'
            stage_names = ['<model>'] + [row.name for row in self._document.browser.stage_rows]
            self.view_stage_combo.blockSignals(True)
            self.view_stage_combo.clear()
            self.view_stage_combo.addItems(stage_names)
            target = current if current in stage_names else ('<model>' if self._document.results is None else stage_names[-1])
            self.view_stage_combo.setCurrentText(target)
            self.view_stage_combo.blockSignals(False)
            if self._document.case.metadata.get('showcase') and self.view_mode_combo.currentText() == 'normal':
                self.view_mode_combo.setCurrentText(str(self._document.metadata.get('default_view_mode', 'stage_activity')))

        def _selected_block_names(self) -> list[str]:
            names: list[str] = []
            row = self.block_table.currentRow()
            if row >= 0:
                item = self.block_table.item(row, 0)
                if item is not None and item.text():
                    names.append(item.text())
            item = self.model_tree.currentItem()
            if item is not None:
                payload = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if payload and payload[0] == 'block':
                    name = str(payload[1])
                    if name and name not in names:
                        names.append(name)
            return names

        def _build_stage_activation_map(self, stage_name: str | None) -> dict[str, bool]:
            if not stage_name or stage_name == '<model>':
                return {}
            out: dict[str, bool] = {}
            for block in self._document.browser.blocks:
                state = self._service.stage_region_state(self._document, stage_name, block.name)
                out[block.name] = True if state is None else bool(state)
            return out

        def _configure_viewport_scene(self, title: str, subtitle: str) -> None:
            try:
                self.viewport.set_background('#0f172a', top='#1e293b')
            except TypeError:
                self.viewport.set_background('#0f172a')
            except Exception:
                pass
            try:
                self.viewport.add_text(title, position='upper_left', font_size=12, color='white', name='scene-title')
                self.viewport.add_text(subtitle, position='upper_edge', font_size=9, color='#cbd5e1', name='scene-subtitle')
            except Exception:
                pass

        def _reset_view_camera(self) -> None:
            self._viewport_needs_reset = True
            self._populate_viewport()

        def _populate_viewport(self) -> None:
            if getattr(self, 'viewport', None) is None:
                return
            try:
                self.viewport.clear()
            except Exception:
                return
            model = self._document.model
            if getattr(model, 'mesh', None) is None:
                self._configure_viewport_scene('Model preview unavailable', 'The current document does not contain a prepared mesh yet.')
                try:
                    self.viewport.add_text('No prepared mesh to display.', position='lower_left', font_size=11, color='#fbbf24', name='scene-empty')
                except Exception:
                    pass
                return
            stage_name = self.view_stage_combo.currentText().strip() or '<model>'
            view_mode = self.view_mode_combo.currentText().strip() or 'normal'
            selected_blocks = self._selected_block_names()
            selected_regions = list(selected_blocks)
            unassigned_regions = [block.name for block in self._document.browser.blocks if not (block.material_name or '').strip()]
            conflict_regions: list[str] = []
            stage_activation = self._build_stage_activation_map(None if stage_name == '<model>' else stage_name)
            visual_options = {
                'opacity': 0.96,
                'show_scalar_bar': False,
                'clip_axis': self.view_clip_combo.currentText().strip().lower(),
                'clip_ratio': 0.5,
            }
            title = str(self._document.case.metadata.get('display_title') or self._document.case.name)
            subtitle = str(self._document.case.metadata.get('display_subtitle') or f"Mode={self._document.mode} | View={view_mode} | Stage={stage_name}")
            self._configure_viewport_scene(title, subtitle)
            try:
                self._viewport_actor_map = self._preview_builder.add_model(
                    self.viewport,
                    model,
                    stage=None if stage_name == '<model>' else stage_name,
                    selected_regions=selected_regions,
                    selected_blocks=selected_blocks,
                    view_mode=view_mode,
                    stage_activation=stage_activation,
                    unassigned_regions=unassigned_regions,
                    conflict_regions=conflict_regions,
                    show_edges=bool(self.view_edges_check.isChecked()),
                    visual_options=visual_options,
                )
            except Exception as exc:
                self._viewport_actor_map = {}
                self._configure_viewport_scene('Model preview failed', 'The viewport could not render the current model.')
                try:
                    self.viewport.add_text(str(exc), position='lower_left', font_size=10, color='#fda4af', name='scene-error')
                except Exception:
                    pass
                self.statusBar().showMessage(f'Viewport render failed: {exc}')
                self._fill_key_value_table(self.scene_summary_table, build_scene_summary_rows(self._document, actor_map={}, view_mode=view_mode, stage_name=stage_name))
                return
            try:
                if self._viewport_needs_reset:
                    self.viewport.reset_camera()
                    try:
                        self.viewport.view_isometric()
                    except Exception:
                        pass
                    self._viewport_needs_reset = False
                self.viewport.render()
            except Exception:
                pass
            self._fill_key_value_table(self.scene_summary_table, build_scene_summary_rows(self._document, actor_map=self._viewport_actor_map, view_mode=view_mode, stage_name=stage_name))

        def _fill_key_value_table(self, table, rows: list[tuple[str, str]]) -> None:
            table.setRowCount(0)
            for row_index, (key, value) in enumerate(rows):
                table.insertRow(row_index)
                table.setItem(row_index, 0, QtWidgets.QTableWidgetItem(str(key)))
                table.setItem(row_index, 1, QtWidgets.QTableWidgetItem(str(value)))
            table.resizeColumnsToContents()

        def _fill_alert_table(self, rows: list[dict[str, str]]) -> None:
            self.alert_table.setRowCount(0)
            for row_index, row in enumerate(rows):
                self.alert_table.insertRow(row_index)
                self.alert_table.setItem(row_index, 0, QtWidgets.QTableWidgetItem(str(row.get('severity', ''))))
                self.alert_table.setItem(row_index, 1, QtWidgets.QTableWidgetItem(str(row.get('source', ''))))
                self.alert_table.setItem(row_index, 2, QtWidgets.QTableWidgetItem(str(row.get('message', ''))))
                self.alert_table.setItem(row_index, 3, QtWidgets.QTableWidgetItem(str(row.get('hint', ''))))
            self.alert_table.resizeColumnsToContents()

        def _fill_process_table(self, rows: list[dict[str, str]]) -> None:
            self.process_table.setRowCount(0)
            for row_index, row in enumerate(rows):
                self.process_table.insertRow(row_index)
                self.process_table.setItem(row_index, 0, QtWidgets.QTableWidgetItem(str(row.get('item', ''))))
                self.process_table.setItem(row_index, 1, QtWidgets.QTableWidgetItem(str(row.get('state', ''))))
                self.process_table.setItem(row_index, 2, QtWidgets.QTableWidgetItem(str(row.get('detail', ''))))
            self.process_table.resizeColumnsToContents()

        def _fill_blueprint_progress_table(self, rows: list[dict[str, str]]) -> None:
            self.blueprint_progress_table.setRowCount(0)
            for row_index, row in enumerate(rows):
                self.blueprint_progress_table.insertRow(row_index)
                self.blueprint_progress_table.setItem(row_index, 0, QtWidgets.QTableWidgetItem(str(row.get('plane', ''))))
                self.blueprint_progress_table.setItem(row_index, 1, QtWidgets.QTableWidgetItem(str(row.get('module', ''))))
                self.blueprint_progress_table.setItem(row_index, 2, QtWidgets.QTableWidgetItem(str(row.get('section', ''))))
                self.blueprint_progress_table.setItem(row_index, 3, QtWidgets.QTableWidgetItem(str(row.get('progress', ''))))
                self.blueprint_progress_table.setItem(row_index, 4, QtWidgets.QTableWidgetItem(str(row.get('status', ''))))
                self.blueprint_progress_table.setItem(row_index, 5, QtWidgets.QTableWidgetItem(str(row.get('summary', ''))))
                self.blueprint_progress_table.setItem(row_index, 6, QtWidgets.QTableWidgetItem(str(row.get('next_steps', '') or row.get('blockers', ''))))
            self.blueprint_progress_table.resizeColumnsToContents()

        def _populate_bottom_panel(self) -> None:
            current_stage = self.view_stage_combo.currentText().strip() if getattr(self, 'view_stage_combo', None) is not None else '<model>'
            current_mode = self.view_mode_combo.currentText().strip() if getattr(self, 'view_mode_combo', None) is not None else 'normal'
            self.runtime_log.setPlainText('\n'.join(build_runtime_log_lines(self._document)))
            self._fill_alert_table(build_alert_rows(self._document))
            self._fill_key_value_table(self.workflow_metrics_table, build_workflow_metric_rows(self._document))
            self._fill_process_table(build_key_process_rows(self._document))
            self._fill_key_value_table(self.scene_summary_table, build_scene_summary_rows(self._document, actor_map=self._viewport_actor_map, view_mode=current_mode, stage_name=current_stage))
            self._fill_blueprint_progress_table(build_blueprint_progress_rows(self._document))

        def _sync_stage_selection_to_view(self) -> None:
            item = self.stage_tree.currentItem()
            if item is None:
                return
            stage_name = str(item.data(0, QtCore.Qt.ItemDataRole.UserRole) or '')
            if not stage_name:
                return
            self.view_stage_combo.setCurrentText(stage_name)
            if self.view_mode_combo.currentText() == 'normal':
                self.view_mode_combo.setCurrentText('stage_activity')
            self._populate_viewport()

        def _sync_results_selection_to_view(self) -> None:
            item = self.results_tree.currentItem()
            if item is None:
                return
            stage_name = item.text(0).strip()
            if stage_name and self.view_stage_combo.findText(stage_name) >= 0:
                self.view_stage_combo.setCurrentText(stage_name)
                self._populate_viewport()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = NextGenWorkbenchWindow()
    window.show()
    app.exec()


__all__ = ['launch_nextgen_workbench']
