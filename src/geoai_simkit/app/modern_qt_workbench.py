"""PySide-only integrated workbench for visual FEM modeling.

The workbench now includes a first-generation interactive geometry editor:
click-to-create points, continuous line drawing, surface closure, block box
creation, point dragging, rubber-band selection, multi-selection, endpoint/grid snapping,
support-axis creation, layer/excavation partitioning and interface review actions.  It still avoids mandatory PyVista/VTK dependencies so a fresh
Windows Python environment can launch the editor reliably.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def _safe_json(data: Any, limit: int = 40000) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)[:limit]


def launch_modern_qt_workbench() -> None:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QAction, QBrush, QColor, QFont, QPainter, QPen, QPolygonF
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QGridLayout,
        QGraphicsEllipseItem,
        QGraphicsLineItem,
        QGraphicsPolygonItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsTextItem,
        QGraphicsView,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QPlainTextEdit,
        QPushButton,
        QSplitter,
        QTabWidget,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    from geoai_simkit.app.geometry_mouse_interaction import GeometryMouseController
    from geoai_simkit.app.visual_modeling_system import VisualModelingSystem

    app = QApplication.instance() or QApplication(sys.argv)
    splash = QLabel("GeoAI SimKit\nLoading interactive geometry editor...")
    splash.setAlignment(Qt.AlignCenter)
    splash.setFont(QFont("Arial", 14, QFont.Bold))
    splash.resize(460, 190)
    splash.show()
    app.processEvents()

    system = VisualModelingSystem.create_default({"dimension": "3d"})
    system.run_results()
    controller = GeometryMouseController(system)

    window = QMainWindow()
    window.setWindowTitle("GeoAI SimKit — Interactive Visual Modeling Workbench")
    window.resize(1540, 920)

    root = QWidget()
    main_layout = QVBoxLayout(root)

    title_row = QHBoxLayout()
    title = QLabel("GeoAI SimKit Interactive Geometry Editor")
    title.setFont(QFont("Arial", 15, QFont.Bold))
    title_row.addWidget(title)
    title_row.addStretch(1)
    tool_mode_label = QLabel("Tool: select")
    tool_mode_label.setFont(QFont("Arial", 10, QFont.Bold))
    title_row.addWidget(tool_mode_label)
    active_stage_combo = QComboBox()
    title_row.addWidget(QLabel("Stage:"))
    title_row.addWidget(active_stage_combo)
    main_layout.addLayout(title_row)

    toolbar = QHBoxLayout()
    btn_select = QPushButton("Select")
    btn_create_point = QPushButton("Point")
    btn_create_line = QPushButton("Line")
    btn_create_surface = QPushButton("Surface")
    btn_create_block = QPushButton("Box block")
    btn_move_point = QPushButton("Move point")
    btn_soil_layer = QPushButton("Soil layer split")
    btn_excavation = QPushButton("Excavation polygon")
    btn_wall = QPushButton("Wall")
    btn_strut = QPushButton("Strut")
    btn_anchor = QPushButton("Anchor")
    btn_rebuild_interfaces = QPushButton("Review contacts")
    btn_accept_interface = QPushButton("Accept interface")
    btn_close_surface = QPushButton("Close surface")
    btn_finish_line = QPushButton("Finish line")
    btn_deactivate = QPushButton("Deactivate selected")
    btn_activate = QPushButton("Activate selected")
    btn_mesh = QPushButton("Generate mesh")
    btn_run = QPushButton("Run preview results")
    btn_undo = QPushButton("Undo")
    btn_redo = QPushButton("Redo")
    for button in (
        btn_select,
        btn_create_point,
        btn_create_line,
        btn_create_surface,
        btn_create_block,
        btn_move_point,
        btn_soil_layer,
        btn_excavation,
        btn_wall,
        btn_strut,
        btn_anchor,
        btn_rebuild_interfaces,
        btn_accept_interface,
        btn_close_surface,
        btn_finish_line,
        btn_deactivate,
        btn_activate,
        btn_mesh,
        btn_run,
        btn_undo,
        btn_redo,
    ):
        toolbar.addWidget(button)
    toolbar.addStretch(1)
    main_layout.addLayout(toolbar)

    hint = QLabel(
        "Mouse editor: Point=click with grid/endpoint snap; Line=continuous; Surface/Excavation=click vertices then close; "
        "Soil layer=drag/click horizontal split; Wall/Strut/Anchor=two clicks; Select=click, Ctrl/Shift multi-select, box select; right-click for context menu."
    )
    hint.setStyleSheet("color: #4d5965;")
    main_layout.addWidget(hint)

    editor_box = QWidget()
    editor_layout = QGridLayout(editor_box)
    editor_layout.setContentsMargins(0, 0, 0, 0)
    x_edit = QLineEdit("0"); y_edit = QLineEdit("0"); z_edit = QLineEdit("0")
    x2_edit = QLineEdit("5"); y2_edit = QLineEdit("0"); z2_edit = QLineEdit("-5")
    block_bounds_edit = QLineEdit("-5,5,-0.5,0.5,-5,0")
    surface_coords_edit = QLineEdit("-5,0,0; 5,0,0; 5,0,-5; -5,0,-5")
    btn_field_point = QPushButton("Point from fields")
    btn_field_line = QPushButton("Line from fields")
    btn_field_surface = QPushButton("Surface from fields")
    btn_field_block = QPushButton("Block from fields")
    feature_z_edit = QLineEdit("-8")
    support_type_edit = QLineEdit("strut")
    support_material_edit = QLineEdit("support_material")
    btn_update_soil_feature = QPushButton("Update selected layer z")
    btn_update_excavation_feature = QPushButton("Update selected excavation")
    btn_update_support = QPushButton("Update selected support")
    editor_layout.addWidget(QLabel("P1 x/y/z"), 0, 0)
    editor_layout.addWidget(x_edit, 0, 1); editor_layout.addWidget(y_edit, 0, 2); editor_layout.addWidget(z_edit, 0, 3)
    editor_layout.addWidget(QLabel("P2 x/y/z"), 0, 4)
    editor_layout.addWidget(x2_edit, 0, 5); editor_layout.addWidget(y2_edit, 0, 6); editor_layout.addWidget(z2_edit, 0, 7)
    editor_layout.addWidget(btn_field_point, 0, 8); editor_layout.addWidget(btn_field_line, 0, 9)
    editor_layout.addWidget(QLabel("Block bounds xmin,xmax,ymin,ymax,zmin,zmax"), 1, 0, 1, 3)
    editor_layout.addWidget(block_bounds_edit, 1, 3, 1, 3)
    editor_layout.addWidget(btn_field_block, 1, 6)
    editor_layout.addWidget(QLabel("Surface coords x,y,z; ..."), 2, 0, 1, 2)
    editor_layout.addWidget(surface_coords_edit, 2, 2, 1, 6)
    editor_layout.addWidget(btn_field_surface, 2, 8, 1, 2)
    editor_layout.addWidget(QLabel("Parametric edit z / support type / material"), 3, 0, 1, 2)
    editor_layout.addWidget(feature_z_edit, 3, 2)
    editor_layout.addWidget(support_type_edit, 3, 3)
    editor_layout.addWidget(support_material_edit, 3, 4)
    editor_layout.addWidget(btn_update_soil_feature, 3, 5)
    editor_layout.addWidget(btn_update_excavation_feature, 3, 6)
    editor_layout.addWidget(btn_update_support, 3, 7, 1, 2)
    main_layout.addWidget(editor_box)

    splitter = QSplitter(Qt.Horizontal)
    object_tree = QTreeWidget()
    object_tree.setHeaderLabels(["Object", "Type"])
    splitter.addWidget(object_tree)

    center_tabs = QTabWidget()
    scene = QGraphicsScene()

    scale = 7.5
    rubber_rect: dict[str, Any] = {"item": None, "start": None}

    def _project(x: float, z: float, current_scale: float = scale) -> QPointF:
        return QPointF(float(x) * current_scale, -float(z) * current_scale)

    def _scene_to_model(pos: QPointF) -> tuple[float, float]:
        return (float(pos.x()) / scale, -float(pos.y()) / scale)

    def _selection_modifier(event) -> str:
        modifiers = event.modifiers()
        if modifiers & Qt.ControlModifier:
            return "toggle"
        if modifiers & Qt.ShiftModifier:
            return "add"
        return "replace"

    def _picked_item_at(view: QGraphicsView, pos) -> Any | None:
        item = scene.itemAt(view.mapToScene(pos), view.transform())
        # Ignore transient rubber-band and labels when possible.
        if item is not None and item.data(0) is None and hasattr(item, "parentItem"):
            return None
        return item

    class InteractiveView(QGraphicsView):
        def mousePressEvent(self, event):  # type: ignore[override]
            scene_pos = self.mapToScene(event.pos())
            x, z = _scene_to_model(scene_pos)
            item = _picked_item_at(self, event.pos())
            entity_id = None if item is None else item.data(0)
            entity_type = None if item is None else item.data(1)

            if event.button() == Qt.RightButton:
                if entity_id and entity_type:
                    ref = system.make_selection_ref(str(entity_id), str(entity_type))
                    if ref is not None and not any(sel.key == ref.key for sel in system.document.selection.items):
                        system.apply_selection(ref, modifier="replace")
                        refresh_all()
                menu = QMenu(self)
                actions = controller.context_actions(entity_id=None if entity_id is None else str(entity_id), entity_type=None if entity_type is None else str(entity_type))
                for row in actions:
                    action = QAction(str(row.get("label", row.get("id"))), menu)
                    action.setEnabled(bool(row.get("enabled", True)))
                    action_id = str(row.get("id"))
                    action.triggered.connect(lambda _checked=False, aid=action_id: safe_action(lambda: controller.invoke_context_action(aid, stage_id=active_stage_id())))
                    menu.addAction(action)
                menu.exec(event.globalPosition().toPoint())
                return

            if event.button() != Qt.LeftButton:
                super().mousePressEvent(event)
                return

            if controller.mode == "select" and item is None:
                rubber_rect["start"] = scene_pos
                rb = QGraphicsRectItem(QRectF(scene_pos, scene_pos))
                rb.setPen(QPen(QColor(40, 110, 190), 1.2, Qt.DashLine))
                rb.setBrush(QBrush(QColor(80, 140, 220, 35)))
                rb.setZValue(9999)
                scene.addItem(rb)
                rubber_rect["item"] = rb
                event.accept()
                return

            if controller.mode in {"select", "move_point"} and entity_type == "point" and entity_id:
                controller.start_drag(str(entity_id), "point")
                super().mousePressEvent(event)
                return

            if controller.mode == "select":
                if entity_id and entity_type:
                    controller.click(x, z, entity_id=str(entity_id), entity_type=str(entity_type), selection_modifier=_selection_modifier(event))
                else:
                    controller.click(x, z, selection_modifier="replace")
                refresh_all()
                event.accept()
                return

            result = controller.click(x, z, entity_id=None if entity_id is None else str(entity_id), entity_type=None if entity_type is None else str(entity_type))
            status.setText(result.message or f"Mouse action: {result.action}")
            refresh_all()
            event.accept()

        def mouseMoveEvent(self, event):  # type: ignore[override]
            scene_pos = self.mapToScene(event.pos())
            if rubber_rect.get("item") is not None and rubber_rect.get("start") is not None:
                start = rubber_rect["start"]
                rubber_rect["item"].setRect(QRectF(start, scene_pos).normalized())
                event.accept()
                return
            if controller.drag_entity_id and controller.mode in {"select", "move_point"}:
                x, z = _scene_to_model(scene_pos)
                controller.drag_to(x, z)
                super().mouseMoveEvent(event)
                return
            if controller.mode in {"line", "surface", "block"} and (controller.line_anchor or controller.surface_vertices or controller.block_anchor):
                x, z = _scene_to_model(scene_pos)
                controller.preview_point = (x, controller.default_y, z)
                draw_viewport(system.to_payload())
                event.accept()
                return
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):  # type: ignore[override]
            scene_pos = self.mapToScene(event.pos())
            if rubber_rect.get("item") is not None and rubber_rect.get("start") is not None:
                start = rubber_rect["start"]
                rb = rubber_rect["item"]
                rect = rb.rect().normalized()
                scene.removeItem(rb)
                rubber_rect["item"] = None
                rubber_rect["start"] = None
                if rect.width() > 3 or rect.height() > 3:
                    x1, z1 = _scene_to_model(start)
                    x2, z2 = _scene_to_model(scene_pos)
                    controller.box_select(x1, z1, x2, z2, modifier=_selection_modifier(event))
                    refresh_all()
                else:
                    system.clear_selection()
                    refresh_all()
                event.accept()
                return
            if controller.layer_anchor is not None and controller.mode == "soil_layer" and event.button() == Qt.LeftButton:
                x, z = _scene_to_model(scene_pos)
                controller.end_soil_layer_drag(x, z)
                refresh_all()
                event.accept()
                return
            if controller.drag_entity_id and event.button() == Qt.LeftButton:
                x, z = _scene_to_model(scene_pos)
                controller.end_drag(x, z)
                refresh_all()
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def keyPressEvent(self, event):  # type: ignore[override]
            if event.key() == Qt.Key_Escape:
                controller.cancel()
                refresh_all()
                event.accept()
                return
            if event.key() in {Qt.Key_Return, Qt.Key_Enter} and controller.mode == "surface":
                controller.close_surface()
                refresh_all()
                event.accept()
                return
            if event.key() in {Qt.Key_Return, Qt.Key_Enter} and controller.mode == "excavation":
                controller.close_excavation_polygon()
                refresh_all()
                event.accept()
                return
            if event.key() == Qt.Key_Delete:
                system.delete_selected_geometry_entities()
                refresh_all()
                event.accept()
                return
            super().keyPressEvent(event)

    view = InteractiveView(scene)
    view.setRenderHint(QPainter.Antialiasing, True)
    view.setDragMode(QGraphicsView.NoDrag)
    center_tabs.addTab(view, "Viewport")
    mesh_text = QPlainTextEdit(); mesh_text.setReadOnly(True)
    solve_text = QPlainTextEdit(); solve_text.setReadOnly(True)
    result_text = QPlainTextEdit(); result_text.setReadOnly(True)
    benchmark_text = QPlainTextEdit(); benchmark_text.setReadOnly(True)
    advanced_text = QPlainTextEdit(); advanced_text.setReadOnly(True)
    center_tabs.addTab(mesh_text, "Mesh")
    center_tabs.addTab(solve_text, "Solve")
    center_tabs.addTab(result_text, "Results")
    center_tabs.addTab(benchmark_text, "Benchmark")
    center_tabs.addTab(advanced_text, "Advanced")
    splitter.addWidget(center_tabs)

    right_tabs = QTabWidget()
    property_text = QPlainTextEdit(); property_text.setReadOnly(True)
    stage_text = QPlainTextEdit(); stage_text.setReadOnly(True)
    contact_text = QPlainTextEdit(); contact_text.setReadOnly(True)
    log_text = QPlainTextEdit(); log_text.setReadOnly(True)
    right_tabs.addTab(property_text, "Properties")
    right_tabs.addTab(stage_text, "Stages")
    right_tabs.addTab(contact_text, "Contacts")
    right_tabs.addTab(log_text, "Log")
    splitter.addWidget(right_tabs)
    splitter.setSizes([300, 880, 360])
    main_layout.addWidget(splitter, 1)

    status = QLabel("Ready — interactive PySide section viewport is active; PyVista/VTK remains optional.")
    main_layout.addWidget(status)

    def add_tree_node(parent: QTreeWidgetItem | QTreeWidget, node: dict[str, Any]) -> None:
        item = QTreeWidgetItem([str(node.get("label", node.get("id", ""))), str(node.get("type", ""))])
        item.setData(0, Qt.UserRole, {"entity_id": node.get("entity_id"), "type": node.get("type"), "source": node.get("source")})
        if isinstance(parent, QTreeWidget):
            parent.addTopLevelItem(item)
        else:
            parent.addChild(item)
        for child in list(node.get("children", []) or []):
            add_tree_node(item, child)

    def color_for_role(role: str, active: bool) -> QColor:
        if role == "excavation":
            return QColor(239, 245, 255, 180 if active else 70)
        if role == "wall":
            return QColor(72, 111, 167, 220 if active else 80)
        if role == "support":
            return QColor(230, 145, 56, 220 if active else 90)
        if role == "soil":
            return QColor(90, 176, 170, 150 if active else 60)
        return QColor(190, 190, 190, 130 if active else 60)

    def _points_from_metadata(primitive: dict[str, Any]) -> list[tuple[float, float, float]]:
        pts = primitive.get("metadata", {}).get("points", [])
        out = []
        for item in pts:
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                out.append((float(item[0]), float(item[1]), float(item[2])))
        return out

    def _is_selected(entity_id: str) -> bool:
        return any(item.entity_id == entity_id for item in system.document.selection.items)

    def draw_interaction_preview() -> None:
        preview = controller.preview_state()
        mode = preview.get("mode")
        preview_point = preview.get("preview_point")
        if not preview_point:
            return
        px, _py, pz = [float(v) for v in preview_point]
        if mode == "line" and preview.get("line_anchor"):
            ax, _ay, az = [float(v) for v in preview["line_anchor"]]
            line = QGraphicsLineItem(ax * scale, -az * scale, px * scale, -pz * scale)
            line.setPen(QPen(QColor(245, 130, 32), 1.8, Qt.DashLine))
            line.setZValue(9000)
            scene.addItem(line)
        if mode == "surface" and preview.get("surface_vertices"):
            pts = [tuple(float(v) for v in p) for p in preview["surface_vertices"]]
            pts.append((px, float(controller.default_y), pz))
            for a, b in zip(pts[:-1], pts[1:]):
                line = QGraphicsLineItem(a[0] * scale, -a[2] * scale, b[0] * scale, -b[2] * scale)
                line.setPen(QPen(QColor(245, 130, 32), 1.6, Qt.DashLine))
                line.setZValue(9000)
                scene.addItem(line)
            if len(pts) >= 3:
                close = QGraphicsLineItem(pts[-1][0] * scale, -pts[-1][2] * scale, pts[0][0] * scale, -pts[0][2] * scale)
                close.setPen(QPen(QColor(245, 130, 32), 1.0, Qt.DotLine))
                close.setZValue(9000)
                scene.addItem(close)
        if mode in {"wall", "strut", "anchor"} and preview.get("support_anchor"):
            ax, _ay, az = [float(v) for v in preview["support_anchor"]]
            line = QGraphicsLineItem(ax * scale, -az * scale, px * scale, -pz * scale)
            line.setPen(QPen(QColor(210, 100, 30), 2.2, Qt.DashLine))
            line.setZValue(9000)
            scene.addItem(line)
        if mode == "soil_layer" and preview.get("layer_anchor"):
            line = QGraphicsLineItem(-1000, -pz * scale, 1000, -pz * scale)
            line.setPen(QPen(QColor(70, 170, 160), 2.0, Qt.DashLine))
            line.setZValue(9000)
            scene.addItem(line)
        if mode == "excavation" and preview.get("excavation_vertices"):
            pts = [tuple(float(v) for v in p) for p in preview["excavation_vertices"]]
            pts.append((px, float(controller.default_y), pz))
            for a, b in zip(pts[:-1], pts[1:]):
                line = QGraphicsLineItem(a[0] * scale, -a[2] * scale, b[0] * scale, -b[2] * scale)
                line.setPen(QPen(QColor(220, 95, 40), 1.8, Qt.DashLine))
                line.setZValue(9000)
                scene.addItem(line)
            if len(pts) >= 3:
                close = QGraphicsLineItem(pts[-1][0] * scale, -pts[-1][2] * scale, pts[0][0] * scale, -pts[0][2] * scale)
                close.setPen(QPen(QColor(220, 95, 40), 1.0, Qt.DotLine))
                close.setZValue(9000)
                scene.addItem(close)
        if mode == "block" and preview.get("block_anchor"):
            ax, _ay, az = [float(v) for v in preview["block_anchor"]]
            rect = QRectF(QPointF(ax * scale, -az * scale), QPointF(px * scale, -pz * scale)).normalized()
            item = QGraphicsRectItem(rect)
            item.setPen(QPen(QColor(245, 130, 32), 1.8, Qt.DashLine))
            item.setBrush(QBrush(QColor(245, 130, 32, 28)))
            item.setZValue(9000)
            scene.addItem(item)

    def draw_viewport(payload: dict[str, Any]) -> None:
        scene.clear()
        viewport_payload = payload.get("viewport", {})
        primitives = viewport_payload.get("primitives", [])
        overlays = viewport_payload.get("overlays", [])
        for overlay in overlays:
            if overlay.get("kind") == "grid_line":
                pts = overlay.get("points", [])
                if len(pts) >= 2:
                    a, b = pts[0], pts[1]
                    line = QGraphicsLineItem(float(a[0]) * scale, -float(a[2]) * scale, float(b[0]) * scale, -float(b[2]) * scale)
                    line.setPen(QPen(QColor(205, 215, 225), 0.7 if not overlay.get("major") else 1.1, Qt.SolidLine if overlay.get("major") else Qt.DotLine))
                    line.setZValue(-100)
                    scene.addItem(line)
            elif overlay.get("kind") == "snap_endpoint":
                p = overlay.get("point", [0, 0, 0])
                r = 2.2
                snap_item = QGraphicsEllipseItem(float(p[0]) * scale - r, -float(p[2]) * scale - r, 2 * r, 2 * r)
                snap_item.setPen(QPen(QColor(20, 110, 210), 0.8))
                snap_item.setBrush(QBrush(QColor(20, 110, 210, 80)))
                snap_item.setZValue(18)
                scene.addItem(snap_item)
        # Surfaces first, then blocks, supports, contacts, edges and points.
        for primitive in primitives:
            if primitive.get("kind") != "surface" or not primitive.get("visible", True):
                continue
            pts = _points_from_metadata(primitive)
            if len(pts) < 3:
                continue
            entity_id = str(primitive.get("entity_id"))
            poly = QGraphicsPolygonItem(QPolygonF([_project(x, z) for x, _y, z in pts]))
            poly.setPen(QPen(QColor(245, 130, 32) if _is_selected(entity_id) else QColor(80, 150, 180), 2.0 if _is_selected(entity_id) else 1.2))
            poly.setBrush(QBrush(QColor(80, 150, 180, 60 if _is_selected(entity_id) else 45)))
            poly.setToolTip(entity_id)
            poly.setData(0, entity_id); poly.setData(1, "surface")
            scene.addItem(poly)
        for primitive in primitives:
            if primitive.get("kind") != "block" or not primitive.get("bounds") or not primitive.get("visible", True):
                continue
            xmin, xmax, _ymin, _ymax, zmin, zmax = [float(v) for v in primitive["bounds"]]
            width = max((xmax - xmin) * scale, 1.0)
            height = max((zmax - zmin) * scale, 1.0)
            rect = QGraphicsRectItem(xmin * scale, -zmax * scale, width, height)
            style = dict(primitive.get("style", {}) or {})
            role = str(style.get("role", "unknown"))
            active = bool(style.get("active", True))
            entity_id = str(primitive.get("entity_id"))
            selected = _is_selected(entity_id)
            rect.setPen(QPen(QColor(245, 130, 32) if selected else QColor(120, 130, 140), 2.2 if selected else 0.8))
            rect.setBrush(QBrush(color_for_role(role, active)))
            rect.setToolTip(f"{entity_id}\nrole={role}\nactive={active}")
            rect.setData(0, entity_id); rect.setData(1, "block")
            scene.addItem(rect)
            if role in {"wall", "excavation"} or selected:
                label = QGraphicsTextItem(entity_id[:28])
                label.setDefaultTextColor(QColor(40, 40, 40))
                label.setPos(xmin * scale + 2, -zmax * scale + 2)
                label.setZValue(10)
                scene.addItem(label)
        for primitive in primitives:
            if primitive.get("kind") != "support" or not primitive.get("visible", True):
                continue
            pts = _points_from_metadata(primitive)
            if len(pts) < 2:
                continue
            entity_id = str(primitive.get("entity_id"))
            role = str((primitive.get("style", {}) or {}).get("role", "support"))
            color = QColor(180, 95, 30) if role in {"strut", "anchor"} else QColor(70, 85, 140)
            for a, b in zip(pts[:-1], pts[1:]):
                line = QGraphicsLineItem(a[0] * scale, -a[2] * scale, b[0] * scale, -b[2] * scale)
                line.setPen(QPen(QColor(245, 130, 32) if _is_selected(entity_id) else color, 4.0 if _is_selected(entity_id) else 3.0))
                line.setToolTip(f"{entity_id}\n{role}")
                line.setData(0, entity_id); line.setData(1, "support")
                line.setZValue(30)
                scene.addItem(line)
        for primitive in primitives:
            if primitive.get("kind") != "partition_feature" or not primitive.get("visible", True):
                continue
            pts = _points_from_metadata(primitive)
            if len(pts) < 2:
                continue
            entity_id = str(primitive.get("entity_id"))
            role = str((primitive.get("style", {}) or {}).get("role", "partition_feature"))
            pen = QPen(QColor(245, 130, 32) if _is_selected(entity_id) else QColor(40, 155, 140), 2.6 if _is_selected(entity_id) else 1.8, Qt.DashLine)
            if role == "horizontal_layer":
                a, b = pts[0], pts[-1]
                item = QGraphicsLineItem(a[0] * scale, -a[2] * scale, b[0] * scale, -b[2] * scale)
                item.setPen(pen); item.setData(0, entity_id); item.setData(1, "partition_feature"); item.setZValue(28); item.setToolTip(entity_id); scene.addItem(item)
            else:
                for a, b in zip(pts, pts[1:] + pts[:1]):
                    item = QGraphicsLineItem(a[0] * scale, -a[2] * scale, b[0] * scale, -b[2] * scale)
                    item.setPen(pen); item.setData(0, entity_id); item.setData(1, "partition_feature"); item.setZValue(28); item.setToolTip(entity_id); scene.addItem(item)
        for primitive in primitives:
            if primitive.get("kind") != "contact_pair" or not primitive.get("visible", True):
                continue
            pts = _points_from_metadata(primitive)
            if len(pts) < 2:
                continue
            entity_id = str(primitive.get("entity_id"))
            style = primitive.get("style", {}) or {}
            status = str(style.get("status", "candidate"))
            pen_color = QColor(210, 115, 35) if status == "accepted" else QColor(145, 145, 145)
            line = QGraphicsLineItem(pts[0][0] * scale, -pts[0][2] * scale, pts[1][0] * scale, -pts[1][2] * scale)
            line.setPen(QPen(pen_color, 1.2, Qt.DashLine))
            line.setToolTip(f"{entity_id}\n{style.get('role')}\n{status}")
            line.setData(0, entity_id); line.setData(1, "contact_pair")
            line.setZValue(25)
            scene.addItem(line)
        for primitive in primitives:
            if primitive.get("kind") != "edge" or not primitive.get("visible", True):
                continue
            pts = _points_from_metadata(primitive)
            if len(pts) < 2:
                continue
            entity_id = str(primitive.get("entity_id"))
            for a, b in zip(pts[:-1], pts[1:]):
                line = QGraphicsLineItem(a[0] * scale, -a[2] * scale, b[0] * scale, -b[2] * scale)
                line.setPen(QPen(QColor(245, 130, 32) if _is_selected(entity_id) else QColor(34, 90, 180), 2.6 if _is_selected(entity_id) else 2.0))
                line.setToolTip(entity_id)
                line.setData(0, entity_id); line.setData(1, "edge")
                scene.addItem(line)
        for primitive in primitives:
            if primitive.get("kind") != "point" or not primitive.get("visible", True):
                continue
            meta = primitive.get("metadata", {}) or {}
            x = float(meta.get("x", 0.0)); z = float(meta.get("z", 0.0))
            entity_id = str(primitive.get("entity_id"))
            selected = _is_selected(entity_id)
            r = 5.0 if selected else 3.5
            item = QGraphicsEllipseItem(x * scale - r, -z * scale - r, 2 * r, 2 * r)
            item.setFlag(QGraphicsEllipseItem.ItemIsMovable, True)
            item.setPen(QPen(QColor(245, 130, 32) if selected else QColor(30, 80, 160), 2.0))
            item.setBrush(QBrush(QColor(255, 255, 255)))
            item.setToolTip(entity_id)
            item.setData(0, entity_id); item.setData(1, "point")
            item.setZValue(20)
            scene.addItem(item)
        draw_interaction_preview()
        if scene.items():
            scene.setSceneRect(scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))
        else:
            scene.setSceneRect(QRectF(-200, -200, 400, 400))

    def refresh_all() -> None:
        payload = system.to_payload()
        object_tree.blockSignals(True)
        object_tree.clear()
        add_tree_node(object_tree, payload["object_tree"]["tree"])
        object_tree.expandToDepth(1)
        object_tree.blockSignals(False)
        active_stage_combo.blockSignals(True)
        active_stage_combo.clear()
        for item in payload["stage_timeline"]["items"]:
            active_stage_combo.addItem(item["name"], item["id"])
            if item.get("active"):
                active_stage_combo.setCurrentIndex(active_stage_combo.count() - 1)
        active_stage_combo.blockSignals(False)
        draw_viewport(payload)
        property_text.setPlainText(_safe_json(payload.get("property_panel", {})))
        stage_text.setPlainText(_safe_json(payload.get("stage_timeline", {})))
        contact_text.setPlainText(_safe_json({"interfaces": payload.get("interface_review", {}), "parametric_editing": payload.get("parametric_editing", {})}))
        pages = payload.get("operation_pages", {})
        mesh_text.setPlainText(_safe_json(pages.get("mesh", {})))
        solve_text.setPlainText(_safe_json(pages.get("solve", {})))
        result_text.setPlainText(_safe_json(pages.get("results", {})))
        benchmark_text.setPlainText(_safe_json(pages.get("benchmark", {})))
        advanced_text.setPlainText(_safe_json(pages.get("advanced", {})))
        log_text.setPlainText(_safe_json({"mouse": controller.preview_state(), "command_stack": payload.get("command_stack", {}), "validation": payload.get("validation", []), "operation_log": payload.get("operation_log", [])}))
        tool_mode_label.setText(f"Tool: {controller.mode}")
        selection_label = system.document.selection.active.display_name if system.document.selection.active else "none"
        status.setText(f"Active stage: {system.document.stages.active_stage_id} | Selected: {len(system.document.selection.items)} | Active: {selection_label}")

    def on_tree_selection() -> None:
        item = object_tree.currentItem()
        if item is None:
            return
        data = item.data(0, Qt.UserRole) or {}
        entity_id = data.get("entity_id")
        entity_type = str(data.get("type") or "")
        if not entity_id:
            return
        if entity_type in {"point", "edge", "surface", "block", "face", "support", "contact_pair", "interface", "partition_feature", "stage", "result"}:
            ref = system.make_selection_ref(str(entity_id), entity_type=entity_type)
            system.apply_selection(ref, modifier="replace")
            refresh_all()

    def on_stage_changed(index: int) -> None:
        stage_id = active_stage_combo.itemData(index)
        if stage_id:
            system.set_active_stage(str(stage_id))
            refresh_all()

    def active_stage_id() -> str:
        return str(active_stage_combo.currentData() or system.document.stages.active_stage_id)

    def p1() -> tuple[float, float, float]:
        return (float(x_edit.text()), float(y_edit.text()), float(z_edit.text()))

    def p2() -> tuple[float, float, float]:
        return (float(x2_edit.text()), float(y2_edit.text()), float(z2_edit.text()))

    def bounds_from_text() -> tuple[float, float, float, float, float, float]:
        values = [float(v.strip()) for v in block_bounds_edit.text().split(",") if v.strip()]
        if len(values) != 6:
            raise ValueError("Block bounds require exactly six values.")
        return tuple(values)  # type: ignore[return-value]

    def surface_coords_from_text() -> list[tuple[float, float, float]]:
        coords = []
        for chunk in surface_coords_edit.text().split(";"):
            if not chunk.strip():
                continue
            values = [float(v.strip()) for v in chunk.split(",") if v.strip()]
            if len(values) != 3:
                raise ValueError("Each surface point must have x,y,z.")
            coords.append(tuple(values))  # type: ignore[arg-type]
        return coords

    def safe_action(fn) -> None:
        try:
            result = fn()
            refresh_all()
            if result is not None:
                status.setText(str(result if isinstance(result, str) else getattr(result, "message", result)))
        except Exception as exc:
            status.setText(f"Geometry editor error: {exc}")

    object_tree.currentItemChanged.connect(lambda _current, _previous: on_tree_selection())
    active_stage_combo.currentIndexChanged.connect(on_stage_changed)
    btn_select.clicked.connect(lambda: safe_action(lambda: controller.set_mode("select")))
    btn_create_point.clicked.connect(lambda: safe_action(lambda: controller.set_mode("point")))
    btn_create_line.clicked.connect(lambda: safe_action(lambda: controller.set_mode("line")))
    btn_create_surface.clicked.connect(lambda: safe_action(lambda: controller.set_mode("surface")))
    btn_create_block.clicked.connect(lambda: safe_action(lambda: controller.set_mode("block")))
    btn_move_point.clicked.connect(lambda: safe_action(lambda: controller.set_mode("move_point")))
    btn_soil_layer.clicked.connect(lambda: safe_action(lambda: controller.set_mode("soil_layer")))
    btn_excavation.clicked.connect(lambda: safe_action(lambda: controller.set_mode("excavation")))
    btn_wall.clicked.connect(lambda: safe_action(lambda: controller.set_mode("wall")))
    btn_strut.clicked.connect(lambda: safe_action(lambda: controller.set_mode("strut")))
    btn_anchor.clicked.connect(lambda: safe_action(lambda: controller.set_mode("anchor")))
    btn_rebuild_interfaces.clicked.connect(lambda: safe_action(lambda: system.rebuild_interface_candidates()))
    btn_accept_interface.clicked.connect(lambda: safe_action(lambda: system.accept_first_interface_candidate()))
    btn_close_surface.clicked.connect(lambda: safe_action(lambda: controller.close_surface() if controller.mode != "excavation" else controller.close_excavation_polygon()))
    btn_finish_line.clicked.connect(lambda: safe_action(lambda: controller.finish_line()))
    btn_field_point.clicked.connect(lambda: safe_action(lambda: system.create_point(*p1())))
    btn_field_line.clicked.connect(lambda: safe_action(lambda: system.create_line(p1(), p2())))
    btn_field_surface.clicked.connect(lambda: safe_action(lambda: system.create_surface(surface_coords_from_text())))
    btn_field_block.clicked.connect(lambda: safe_action(lambda: system.create_block(bounds_from_text(), role="structure")))
    btn_update_soil_feature.clicked.connect(lambda: safe_action(lambda: system.update_selected_soil_layer_z(float(feature_z_edit.text()))))
    btn_update_excavation_feature.clicked.connect(lambda: safe_action(lambda: system.update_selected_excavation_polygon(surface_coords_from_text())))
    btn_update_support.clicked.connect(lambda: safe_action(lambda: system.update_selected_support_parameters(start=p1(), end=p2(), support_type=support_type_edit.text().strip() or None, material_id=support_material_edit.text().strip() or None, stage_id=active_stage_id())))
    btn_mesh.clicked.connect(lambda: safe_action(lambda: system.generate_mesh()))
    btn_run.clicked.connect(lambda: safe_action(lambda: system.run_results()))
    btn_undo.clicked.connect(lambda: safe_action(lambda: system.undo()))
    btn_redo.clicked.connect(lambda: safe_action(lambda: system.redo()))
    btn_activate.clicked.connect(lambda: safe_action(lambda: system.set_selected_blocks_activation(active_stage_id(), True)))
    btn_deactivate.clicked.connect(lambda: safe_action(lambda: system.set_selected_blocks_activation(active_stage_id(), False)))

    refresh_all()
    window.setCentralWidget(root)
    window.show()
    splash.close()
    app.exec()


__all__ = ["launch_modern_qt_workbench"]
