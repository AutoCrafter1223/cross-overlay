from __future__ import annotations

import copy
import sys
from dataclasses import fields
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QFileInfo, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPen, QPixmap, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QFileDialog, QFileIconProvider,
    QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QStyle, QSystemTrayIcon, QVBoxLayout,
    QWidget,
)

from .controller import OverlayController
from .editor_history import EditHistory
from .editor_widgets import scroll_page
from .i18n import tr
from .models import (
    AppSettings, CrosshairSettings, MotionAssistSettings, PointerSettings, Profile,
    ShapeLayer, body_reference_preset,
)
from .overlays import MotionAssistOverlay
from .shape_renderer import SHAPE_LABELS, FILLED_SHAPES, draw_layers
from .storage import SettingsStore
from .winapi import WindowInfo, list_top_level_windows, set_start_with_windows


DISCLAIMER = (
    "게임 프로세스에 접근하지 않는 외부 접근성 오버레이입니다. 모든 게임이나 안티치트와의 "
    "호환성을 보장할 수 없으므로 사용하려는 게임의 운영 정책을 확인하세요."
)

APP_STYLE = """
QMainWindow, QWidget#appRoot { background: #f4f7fb; color: #17233c; }
QWidget#editorPage { background: #f4f7fb; }
QWidget#editorProperties { background: #ffffff; border-radius: 12px; }
QScrollArea#propertyScroll { background: #ffffff; border: 1px solid #dce5f1; border-radius: 12px; }
QScrollArea#propertyScroll QWidget#qt_scrollarea_viewport { background: #ffffff; border-radius: 11px; }
QScrollArea#propertyScroll QScrollBar:vertical { background: #f3f7fc; width: 12px; border: 0; border-radius: 6px; margin: 10px 2px; }
QScrollArea#propertyScroll QScrollBar::handle:vertical { background: #b9c7d9; border-radius: 5px; min-height: 36px; }
QScrollArea#propertyScroll QScrollBar::add-line:vertical, QScrollArea#propertyScroll QScrollBar::sub-line:vertical { height: 0; }
QScrollArea#propertyScroll QScrollBar::add-page:vertical, QScrollArea#propertyScroll QScrollBar::sub-page:vertical { background: transparent; }
QScrollArea#motionSettingsScroll, QScrollArea#motionSettingsScroll QWidget#qt_scrollarea_viewport { background: #ffffff; border: 0; border-radius: 12px; }
QTabWidget::pane { background: #ffffff; border: 1px solid #dce5f1; border-radius: 8px; }
QTabBar::tab { background: #edf3fc; color: #334155; padding: 8px 14px; border: 0; }
QTabBar::tab:selected { background: #ffffff; color: #1257c5; font-weight: 600; }
QWidget { font-family: "Segoe UI", "Malgun Gothic"; font-size: 10pt; }
QFrame#header, QFrame#card { background: #ffffff; border: 1px solid #dce5f1; border-radius: 12px; }
QLabel#title { font-size: 18pt; font-weight: 700; color: #1257c5; }
QLabel#activeProfile { background: #e8f1ff; color: #0b5bd3; border: 1px solid #bfd7ff; border-radius: 8px; padding: 6px 10px; font-weight: 700; }
QLabel#sectionTitle { font-size: 13pt; font-weight: 700; color: #17233c; }
QLabel#muted { color: #64748b; }
QLabel#notice { background: #fff8df; border: 1px solid #f0d77b; border-radius: 8px; padding: 8px 12px; color: #674f00; }
QListWidget#navigation { background: #eef4fc; border: 0; border-radius: 12px; padding: 8px; outline: 0; }
QListWidget#navigation::item { height: 45px; padding: 0 12px; margin: 2px; border-radius: 8px; color: #334155; }
QListWidget#navigation::item:selected { background: #dceaff; color: #0b5bd3; font-weight: 700; }
QListWidget#layerList { background: #ffffff; border: 1px solid #dce5f1; border-radius: 9px; padding: 4px; outline: 0; }
QListWidget#layerList::item { min-height: 38px; margin: 2px; padding: 2px 7px; border-radius: 7px; }
QListWidget#layerList::item:selected { background: #e3efff; color: #0b5bd3; }
QPushButton, QToolButton { background: #ffffff; border: 1px solid #cbd7e6; border-radius: 7px; min-height: 36px; padding: 2px 14px; }
QPushButton:hover { border-color: #1677ff; color: #0b5bd3; }
QPushButton:pressed { background: #edf4ff; }
QPushButton#primary { background: #1677ff; color: white; border-color: #1677ff; font-weight: 700; }
QPushButton#danger:hover { border-color: #e5484d; color: #c62f35; }
QComboBox, QLineEdit, QSpinBox { background: #ffffff; border: 1px solid #cbd7e6; border-radius: 7px; min-height: 30px; padding: 1px 8px; }
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border: 1px solid #1677ff; }
QComboBox::drop-down { border: 0; width: 24px; }
QCheckBox { spacing: 7px; min-height: 25px; }
QScrollArea { border: 0; background: transparent; }
QToolTip { background: #17233c; color: white; border: 0; padding: 5px; }
"""


class FocusWheelSpinBox(QSpinBox):
    """Scroll the page unless this value editor has keyboard focus."""

    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class FocusWheelComboBox(QComboBox):
    """Keep a passing mouse wheel from changing an unselected option."""

    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


def _spin(minimum: int, maximum: int, value: int, suffix: str = "") -> QSpinBox:
    widget = FocusWheelSpinBox()
    widget.setRange(minimum, maximum)
    widget.setValue(value)
    widget.setSuffix(suffix)
    widget.setKeyboardTracking(False)
    return widget


def _title(text: str) -> QLabel:
    label = QLabel(text); label.setObjectName("sectionTitle"); return label


class Card(QFrame):
    def __init__(self, layout: QVBoxLayout | QFormLayout | None = None) -> None:
        super().__init__(); self.setObjectName("card")
        if layout is not None: self.setLayout(layout)


class ColorButton(QPushButton):
    def __init__(self, color: str, changed) -> None:
        super().__init__(); self.color = color; self.changed = changed; self.setObjectName("colorSwatch")
        self.clicked.connect(self.choose); self.refresh()

    def refresh(self) -> None:
        foreground = "#111827" if QColor(self.color).lightness() > 145 else "#ffffff"
        self.setText(self.color.upper())
        self.setStyleSheet(f"QPushButton#colorSwatch {{ background-color:{self.color}; color:{foreground}; border:1px solid #9aa9bc; border-radius:7px; font-weight:600; }}")

    def choose(self) -> None:
        window = self.window(); title = window.t("색상 선택") if hasattr(window, "t") else "색상 선택"
        value = QColorDialog.getColor(QColor(self.color), window, title, QColorDialog.ShowAlphaChannel)
        if value.isValid(): self.color = value.name(); self.refresh(); self.changed(self.color)


class ToggleSwitch(QCheckBox):
    def __init__(self, label: str = "") -> None:
        super().__init__();self.label=label;self.setText("");self.setCursor(Qt.PointingHandCursor);self.setMinimumHeight(28)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(56+self.fontMetrics().horizontalAdvance(self.label),28)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing,True)
        track=QRectF(1,(self.height()-22)/2,42,22);painter.setPen(Qt.NoPen);painter.setBrush(QColor("#1677ff") if self.isChecked() else QColor("#cbd5e1"));painter.drawRoundedRect(track,11,11)
        knob_x=22 if self.isChecked() else 3;painter.setBrush(QColor("#ffffff"));painter.drawEllipse(QRectF(knob_x,(self.height()-18)/2,18,18))
        if self.hasFocus():painter.setPen(QPen(QColor("#8bbcff"),1));painter.setBrush(Qt.NoBrush);painter.drawRoundedRect(track.adjusted(-1,-1,1,1),12,12)
        painter.setPen(QColor("#17233c") if self.isEnabled() else QColor("#94a3b8"));painter.drawText(QRectF(54,0,max(0,self.width()-54),self.height()),Qt.AlignVCenter|Qt.AlignLeft,self.label)

    def hitButton(self, position) -> bool:  # noqa: N802
        return self.rect().contains(position)


class ReticlePreview(QWidget):
    layer_moved = Signal(int, int)
    drag_started = Signal()
    drag_finished = Signal()

    def __init__(self) -> None:
        super().__init__(); self.settings = CrosshairSettings(); self.selected_id: str | None = None
        self._drag_origin: tuple[int, int] | None = None; self._drag_start = QPointF(); self._scale = 1.0
        self.language = "ko"
        self.setMinimumSize(280, 280); self.setCursor(Qt.CrossCursor);self.setFocusPolicy(Qt.StrongFocus)
        self.snap_to_grid = False

    def set_language(self, language: str) -> None:
        self.language = language; self.update()

    def set_model(self, settings: CrosshairSettings, selected_id: str | None) -> None:
        self.settings = settings; self.selected_id = selected_id; self.update()

    def _selected(self) -> ShapeLayer | None:
        return next((item for item in self.settings.layers if item.layer_id == self.selected_id), None)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing, self.settings.antialiasing); painter.setRenderHint(QPainter.SmoothPixmapTransform, True); painter.fillRect(self.rect(), QColor("#f8fafc"))
        self._scale = min(self.width()/1920, self.height()/1080)
        spacing=max(1,24*self._scale)
        painter.setPen(QPen(QColor("#e5ebf3"), 1))
        for index in range(int(self.width()/spacing)+2):
            x=round(((self.width()/2+self.settings.offset_x*self._scale)%spacing)+index*spacing)
            if x<self.width():painter.drawLine(x,0,x,self.height())
        for index in range(int(self.height()/spacing)+2):
            y=round(((self.height()/2+self.settings.offset_y*self._scale)%spacing)+index*spacing)
            if y<self.height():painter.drawLine(0,y,self.width(),y)
        center = QPointF(self.width() / 2, self.height() / 2); painter.setPen(QPen(QColor("#9fb9df"), 1, Qt.DashLine))
        painter.drawLine(QPointF(center.x(), 0), QPointF(center.x(), self.height())); painter.drawLine(QPointF(0, center.y()), QPointF(self.width(), center.y()))
        display_center = QPointF(center.x()+self.settings.offset_x*self._scale, center.y()+self.settings.offset_y*self._scale)
        if display_center != center:
            painter.setPen(QPen(QColor("#1677ff"), 1, Qt.DashLine)); painter.drawLine(center, display_center)
        draw_layers(painter, self.settings.layers, display_center, self._scale, self.selected_id)
        painter.setBrush(QColor("#1677ff")); painter.setPen(Qt.NoPen); painter.drawEllipse(center, 3, 3)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.setFocus()
        layer = self._selected()
        if event.button() != Qt.LeftButton or layer is None: return
        self._scale = min(self.width()/1920,self.height()/1080)
        center = QPointF(self.width() / 2 + self.settings.offset_x*self._scale, self.height() / 2 + self.settings.offset_y*self._scale); target = QPointF(center.x() + layer.x * self._scale, center.y() + layer.y * self._scale)
        radius = max(18.0, max(layer.width, layer.height) * self._scale / 2 + 8)
        if (event.position() - target).manhattanLength() <= radius * 2:
            self._drag_origin = (layer.x, layer.y); self._drag_start = event.position();self.drag_started.emit()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is None or not (event.buttons() & Qt.LeftButton): return
        delta = event.position() - self._drag_start
        x=self._drag_origin[0]+round(delta.x()/self._scale);y=self._drag_origin[1]+round(delta.y()/self._scale)
        if self.snap_to_grid:x=round(x/24)*24;y=round(y/24)*24
        self.layer_moved.emit(max(-1000,min(1000,x)),max(-1000,min(1000,y)))

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802
        if self._drag_origin is not None:self.drag_finished.emit()
        self._drag_origin = None

    def keyPressEvent(self,event):
        layer=self._selected()
        direction={Qt.Key_Left:(-1,0),Qt.Key_Right:(1,0),Qt.Key_Up:(0,-1),Qt.Key_Down:(0,1)}.get(event.key())
        if layer and direction:
            step=10 if event.modifiers() & Qt.ShiftModifier else 1
            self.layer_moved.emit(max(-1000,min(1000,layer.x+direction[0]*step)),max(-1000,min(1000,layer.y+direction[1]*step)));event.accept()
        else:super().keyPressEvent(event)


class PointerPreview(ReticlePreview):
    def __init__(self) -> None:
        super().__init__();self.settings=PointerSettings()


class MotionAssistPreview(QWidget):
    """Scaled 16:9 example scene for one motion-assist category."""

    def __init__(self) -> None:
        super().__init__();self.settings=MotionAssistSettings();self.section=0
        self.selected_id=None;self._drag_origin=None;self._drag_start=QPointF()
        self._vignette_key=None;self._vignette_preview=QPixmap()
        self.setMinimumWidth(390);policy=QSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed);policy.setHeightForWidth(True);self.setSizePolicy(policy)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return max(220,round(width*9/16))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(520,293)

    def set_model(self, settings: MotionAssistSettings) -> None:
        self.settings=settings;self.update()

    def set_section(self, section: int) -> None:
        self.section=section;self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing,True)
        painter.fillRect(self.rect(),QColor("#dbeafe"));w,h=self.width(),self.height()
        painter.fillRect(QRectF(0,h*.58,w,h*.42),QColor("#b8c7b0"))
        painter.setPen(Qt.NoPen);painter.setBrush(QColor("#8090a6"))
        painter.drawRect(QRectF(w*.08,h*.35,w*.18,h*.32));painter.drawRect(QRectF(w*.70,h*.26,w*.22,h*.41))
        painter.setBrush(QColor("#66778e"));painter.drawRect(QRectF(w*.38,h*.44,w*.22,h*.23))
        if self.section==0:self._draw_vignette(painter)
        elif self.section==1:
            painter.save();painter.scale(w/1920,h/1080);painter.setRenderHint(QPainter.Antialiasing,self.settings.body.antialiasing);painter.setRenderHint(QPainter.SmoothPixmapTransform,True)
            draw_layers(painter,self.settings.body.layers,QPointF(960,1080),selected_id=self.selected_id);painter.restore()
        elif self.section==2:self._draw_guides(painter)
        else:self._draw_grid(painter)
        painter.setPen(QPen(QColor("#cbd7e6"),1));painter.setBrush(Qt.NoBrush);painter.drawRect(self.rect().adjusted(0,0,-1,-1))

    layer_moved=Signal(int,int)
    drag_started=Signal()
    drag_finished=Signal()

    def mousePressEvent(self,event):  # noqa: N802
        if self.section!=1 or event.button()!=Qt.LeftButton:return
        layer=next((item for item in self.settings.body.layers if item.layer_id==self.selected_id),None)
        if layer is None:return
        scale=self.width()/1920
        target=QPointF(self.width()/2+layer.x*scale,self.height()+layer.y*scale)
        radius=max(18,max(layer.width,layer.height)*scale/2+8)
        if (event.position()-target).manhattanLength()<=radius*2:
            self._drag_origin=(layer.x,layer.y);self._drag_start=event.position();self.drag_started.emit()

    def mouseMoveEvent(self,event):  # noqa: N802
        if self._drag_origin is None or not (event.buttons() & Qt.LeftButton):return
        scale=self.width()/1920;delta=event.position()-self._drag_start
        self.layer_moved.emit(self._drag_origin[0]+round(delta.x()/scale),self._drag_origin[1]+round(delta.y()/scale))

    def mouseReleaseEvent(self,event):  # noqa: N802
        if self._drag_origin is not None:self.drag_finished.emit()
        self._drag_origin=None


    def _draw_vignette(self,painter:QPainter)->None:
        key=repr(self.settings.vignette)
        if key!=self._vignette_key:
            self._vignette_preview=MotionAssistOverlay.render_vignette(self.settings.vignette,1920,1080);self._vignette_key=key
        painter.save();painter.setRenderHint(QPainter.SmoothPixmapTransform,True)
        painter.drawPixmap(self.rect(),self._vignette_preview);painter.restore()

    def _draw_guides(self,painter:QPainter)->None:
        painter.save();painter.scale(self.width()/1920,self.height()/1080)
        MotionAssistOverlay.draw_guides(painter,self.settings.guides,1920,1080);painter.restore()

    def _draw_grid(self,painter:QPainter)->None:
        painter.save();painter.scale(self.width()/1920,self.height()/1080)
        MotionAssistOverlay.draw_grid(painter,self.settings.grid,1920,1080);painter.restore()


class PreviewScrollArea(QScrollArea):
    """Shared, view-only zoom state for the three shape previews."""

    def __init__(self,preview):
        super().__init__();self.preview=preview;self.mode="fit";preview.setMinimumSize(1,1)
        self.setWidgetResizable(False);self.setAlignment(Qt.AlignHCenter|Qt.AlignTop)
        self.setMinimumSize(280,280);self.setWidget(preview)
        self.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Expanding)
        self.setObjectName("previewScroll")
        QTimer.singleShot(0,self._update_zoom)

    def set_zoom(self,mode):
        self.mode=mode;self._update_zoom()

    def resizeEvent(self,event):  # noqa: N802
        super().resizeEvent(event)
        if self.mode=="fit":QTimer.singleShot(0,self._update_zoom)

    def _update_zoom(self):
        if self.mode=="fit":scale=min(max(1,self.viewport().width()-2)/1920,max(1,self.viewport().height()-2)/1080)
        else:scale=float(self.mode)
        width=max(1,round(1920*scale));height=max(1,round(1080*scale))
        if self.preview.size()!=QSize(width,height):self.preview.setFixedSize(width,height)
        self.preview.update()


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings, store: SettingsStore, controller: OverlayController) -> None:
        super().__init__(); self.settings, self.store, self.controller = settings, store, controller; self.windows: list[WindowInfo] = []; self._loading = False;self._quitting=False
        self.setWindowTitle(self.t("CenterCross 접근성 오버레이")); self.resize(1280, 820); self.setMinimumSize(800, 600); self.setStyleSheet(APP_STYLE)
        self._histories={id(self.profile):EditHistory(self.profile)};self._drag_group=False;self._drag_recorded=False
        self._save_timer=QTimer(self);self._save_timer.setSingleShot(True);self._save_timer.setInterval(350);self._save_timer.timeout.connect(self._flush_save)
        self.undo_action=QAction(self.t("실행 취소"),self);self.undo_action.setShortcut(QKeySequence.Undo);self.undo_action.triggered.connect(lambda:self._restore_edit(False));self.addAction(self.undo_action)
        self.redo_action=QAction(self.t("다시 실행"),self);self.redo_action.setShortcuts([QKeySequence.Redo,QKeySequence("Ctrl+Shift+Z")]);self.redo_action.triggered.connect(lambda:self._restore_edit(True));self.addAction(self.redo_action)
        self._build_ui()
        self._build_tray()
        self.controller.hotkey_errors.connect(self.show_hotkey_errors)
        self.controller.profile_activated.connect(self._external_profile_change)
        self.controller.settings_changed.connect(self._sync_runtime_state)
        self._overview_timer = QTimer(self)
        self._overview_timer.setInterval(500)
        self._overview_timer.timeout.connect(self._refresh_visible_overview)
        self._overview_timer.start()
        QTimer.singleShot(0, self.refresh_windows)

    @property
    def profile(self) -> Profile: return self.settings.profiles[self.settings.selected_profile]

    def _save_settings(self):
        history=self._histories.get(id(self.profile))
        if history is None:history=EditHistory(self.profile);self._histories[id(self.profile)]=history
        changed=history.record(self.profile,self._drag_group and self._drag_recorded)
        if changed and self._drag_group:self._drag_recorded=True
        self._save_timer.start()
        self._update_history_actions()

    def _flush_save(self):
        self._save_timer.stop()
        self.store.save(self.settings)

    def _keep_image(self,path):
        try:return self.store.import_image(Path(path))
        except (OSError,ValueError) as exc:
            QMessageBox.warning(self,self.t("이미지 오류"),str(exc));return None

    def _update_history_actions(self):
        history=self._histories.get(id(self.profile))
        self.undo_action.setEnabled(bool(history and history.past))
        self.redo_action.setEnabled(bool(history and history.future))

    def _restore_edit(self,redo=False):
        history=self._histories.get(id(self.profile))
        if not history:return
        restored=history.redo() if redo else history.undo()
        if restored is None:return
        for field in fields(Profile):setattr(self.profile,field.name,getattr(restored,field.name))
        self._refresh_profile_list()
        self.load_profile();self.controller.apply_profile();self._save_timer.start();self._update_history_actions()

    def _begin_drag(self):
        self._drag_group=True;self._drag_recorded=False

    def _end_drag(self):
        self._drag_group=False;self._drag_recorded=False

    def _preview_zoom(self,preview):
        row=QHBoxLayout();row.addWidget(QLabel(self.t("미리보기 배율")))
        choice=FocusWheelComboBox()
        for label,value in ((self.t("화면 맞춤"),"fit"),("25%",.25),("50%",.5),("75%",.75),("100%",1.0)):
            choice.addItem(label,value)
        area=PreviewScrollArea(preview)
        choice.currentIndexChanged.connect(lambda _index:area.set_zoom(choice.currentData()))
        row.addWidget(choice);row.addStretch()
        return row,area,choice

    def _configure_shape_editor(self,pointer=False):
        preview=self.pointer_preview if pointer else self.reticle_preview
        form=self.pointer_properties_form if pointer else self.layer_properties_form
        first=self.pointer_mirror_h if pointer else self.mirror_h
        advanced=QCheckBox(self.t("대칭·패턴 설정 펼치기"));form.insertRow(form.getWidgetPosition(first)[0],advanced)
        if pointer:self.pointer_advanced=advanced
        else:self.layer_advanced=advanced
        advanced.toggled.connect(lambda _checked,p=pointer:self._property_visibility(p))
        preview.drag_started.connect(self._begin_drag);preview.drag_finished.connect(self._end_drag)
        snap=QCheckBox(self.t("격자 맞춤 (24 px)"));snap.toggled.connect(lambda value,p=preview:setattr(p,"snap_to_grid",value))
        center=QPushButton(self.t("선택 도형 중심 맞춤"));center.clicked.connect(lambda _=False,p=preview:p.layer_moved.emit(0,0))
        return snap,center

    def _property_visibility(self,pointer=False):
        layer=self.current_pointer_layer() if pointer else self.current_layer()
        if not layer:return
        form=self.pointer_properties_form if pointer else self.layer_properties_form
        prefix="pointer_layer_" if pointer else "layer_"
        controls=self.pointer_layer_controls if pointer else self.layer_controls
        arc=layer.shape=="arc";line=layer.shape=="line";image=layer.shape=="image"
        for name in ("width","height"):
            form.setRowVisible(controls[name],not arc and (name!="height" or not line))
        for name in ("arc_radius","arc_start_angle","arc_span_angle"):form.setRowVisible(controls[name],arc)
        for name in ("thickness","outline_thickness"):form.setRowVisible(controls[name],not image)
        for name,visible in (("cap",line or arc),("cap_angle",line and layer.cap_style=="triangle"),("fill",layer.shape in FILLED_SHAPES),("stroke",not image),("outline",not image and layer.outline_thickness>0),("key_enabled",image),("key_color",image and layer.color_key_enabled),("key_tolerance",image and layer.color_key_enabled),("key_softness",image and layer.color_key_enabled)):
            form.setRowVisible(getattr(self,prefix+name),visible)
        advanced=getattr(self,"pointer_advanced" if pointer else "layer_advanced",None)
        if advanced is None:return
        prefix="pointer_" if pointer else ""
        for name in ("mirror_h","mirror_v","pattern_enabled"):
            form.setRowVisible(getattr(self,prefix+name),advanced.isChecked())
        for name in ("pattern_angle","pattern_copies"):
            form.setRowVisible(getattr(self,prefix+name),advanced.isChecked() and layer.circular_pattern)

    def t(self, text: str) -> str:
        return tr(self.settings.language, text)

    def shape_label(self, shape: str) -> str:
        return self.t(SHAPE_LABELS.get(shape, shape))

    def _build_ui(self, current_page: int = 0) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(10)

        notice = QLabel(self.t(DISCLAIMER))
        notice.setObjectName("notice")
        notice.setWordWrap(True)
        outer.addWidget(notice)
        outer.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(10)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(220)
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.navigation.setIconSize(QSize(16, 16))

        # Four motion-assist pages share one stacked page, so their navigation
        # order must stay in sync with _navigation_changed below.
        nav_items = [
            ("화면 기준점", QStyle.SP_DialogYesButton),
            ("마우스 커서 추적", QStyle.SP_ArrowRight),
        ]
        for label, icon in nav_items:
            self.navigation.addItem(QListWidgetItem(self.style().standardIcon(icon), self.t(label)))
        for label in ("가상 신체 표시", "가장자리 어둡게", "수평선 · 수직선", "격자선"):
            self.navigation.addItem(QListWidgetItem(self.t(label)))
        for label, icon in (
            ("마우스 찾기", QStyle.SP_FileDialogContentsView),
            ("단축키", QStyle.SP_DialogApplyButton),
            ("일반", QStyle.SP_FileDialogDetailedView),
        ):
            self.navigation.addItem(QListWidgetItem(self.style().standardIcon(icon), self.t(label)))

        self.stack = QStackedWidget()
        pages = [
            self._build_crosshair_page(), self._build_pointer_page(),
            self._build_motion_page(), self._build_effect_page(),
            self._build_hotkey_page(), self._build_general_page(),
        ]
        for page in pages:
            for form in page.findChildren(QFormLayout):
                form.setRowWrapPolicy(QFormLayout.WrapLongRows)
            for label in page.findChildren(QLabel):
                label.setWordWrap(True)
            self.stack.addWidget(scroll_page(page, self.settings.language))

        self.navigation.currentRowChanged.connect(self._navigation_changed)
        self.navigation.setCurrentRow(current_page if 0 <= current_page < self.navigation.count() else 0)
        body.addWidget(self.navigation)
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(root)

    def _navigation_changed(self, row: int) -> None:
        if row < 0:
            return
        self.stack.setCurrentIndex(0 if row == 0 else 1 if row == 1 else 2 if row <= 5 else row - 3)
        if 2 <= row <= 5:
            section = {2: 1, 3: 0, 4: 2, 5: 3}[row]
            self.motion_settings_stack.setCurrentIndex(section)
            self.motion_preview.set_section(section)
            title = {0: "가장자리 어둡게", 1: "가상 신체 표시", 2: "수평선 · 수직선", 3: "격자선"}[section]
            self.motion_page_title.setText(self.t(title))
            self.motion_header_enabled.setAccessibleName(self.motion_page_title.text() + " " + self.t("사용"))
            self.motion_header_enabled.blockSignals(True)
            section_key = ("vignette", "body", "guides", "grid")[section]
            self.motion_header_enabled.setChecked(getattr(self.profile.motion_assist, section_key).enabled)
            self.motion_header_enabled.blockSignals(False)

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("header")
        box = QVBoxLayout(frame)
        box.setContentsMargins(16, 10, 16, 10)
        box.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("CenterCross")
        title.setObjectName("title")
        top.addWidget(title)
        self.active_profile_label = QLabel()
        self.active_profile_label.setWordWrap(True)
        self.active_profile_label.setMinimumWidth(0)
        self.active_profile_label.setObjectName("activeProfile")
        top.addWidget(self.active_profile_label, 1)

        top.addWidget(QLabel(self.t("언어 / Language")))
        self.language_combo = FocusWheelComboBox()
        self.language_combo.addItem("한국어", "ko")
        self.language_combo.addItem("English", "en")
        self.language_combo.setCurrentIndex(self.language_combo.findData(self.settings.language))
        self.language_combo.currentIndexChanged.connect(self.change_language)
        top.addWidget(self.language_combo)
        box.addLayout(top)
        self._update_active_profile()
        return frame

    def _page(self,title:str,subtitle:str="")->tuple[QWidget,QVBoxLayout]:
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(4,4,4,4);layout.setSpacing(10);layout.addWidget(_title(title))
        if subtitle:text=QLabel(subtitle);text.setObjectName("muted");text.setWordWrap(True);layout.addWidget(text)
        return page,layout

    def _build_crosshair_page(self)->QWidget:
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(4,4,4,4);layout.setSpacing(10);heading=QHBoxLayout();self.cross_enabled=ToggleSwitch();self.cross_enabled.setAccessibleName(self.t("화면 기준점 사용"));self.cross_enabled.toggled.connect(lambda value:self._set_crosshair("enabled",value));heading.addWidget(self.cross_enabled);heading.addWidget(_title(self.t("화면 기준점 편집")));heading.addStretch();layout.addLayout(heading);subtitle=QLabel(self.t("CENTER (0, 0)을 기준으로 도형을 조합하고 대칭 프리셋을 만들 수 있습니다."));subtitle.setObjectName("muted");layout.addWidget(subtitle);columns=QHBoxLayout();columns.setContentsMargins(0,0,0,0);columns.setSpacing(10);settings_widget=QWidget();settings_box=QVBoxLayout(settings_widget);settings_box.setContentsMargins(0,0,0,0);settings_box.setSpacing(8);settings_columns=QHBoxLayout();settings_columns.setSpacing(8);settings_box.addLayout(settings_columns,1)
        left=QVBoxLayout();left.setContentsMargins(14,14,14,14);left.addWidget(_title(self.t("도형 레이어")))
        self.layer_list=QListWidget();self.layer_list.setObjectName("layerList");self.layer_list.currentRowChanged.connect(self.select_layer);self.layer_list.itemChanged.connect(self.layer_visibility_changed);left.addWidget(self.layer_list,1)
        buttons=QHBoxLayout()
        for label,slot in [("추가",self.add_layer),("복제",self.duplicate_layer),("삭제",self.delete_layer)]:button=QPushButton(self.t(label));button.clicked.connect(slot);buttons.addWidget(button)
        left.addLayout(buttons);order=QHBoxLayout();up=QPushButton(self.t("위로"));up.clicked.connect(lambda:self.move_layer(-1));down=QPushButton(self.t("아래로"));down.clicked.connect(lambda:self.move_layer(1));order.addWidget(up);order.addWidget(down);left.addLayout(order);layer_card=Card(left);layer_card.setMinimumWidth(230);layer_card.setMaximumWidth(280);settings_columns.addWidget(layer_card)
        props=QWidget();props.setObjectName("editorProperties");form=QFormLayout(props);self.layer_properties_form=form;form.setContentsMargins(14,14,14,14);form.setSpacing(9);form.setRowWrapPolicy(QFormLayout.WrapLongRows);form.addRow(_title(self.t("도형 속성")));self.layer_name=QLineEdit();self.layer_name.editingFinished.connect(lambda:self._set_layer("name",self.layer_name.text().strip() or self.t("도형")));form.addRow(self.t("이름"),self.layer_name)
        self.layer_shape=FocusWheelComboBox()
        for key in SHAPE_LABELS:self.layer_shape.addItem(self.shape_label(key),key)
        self.layer_shape.currentIndexChanged.connect(lambda:self._set_layer("shape",self.layer_shape.currentData()));form.addRow(self.t("도형 종류"),self.layer_shape);self.layer_controls:dict[str,QWidget]={}
        for field,label,minimum,maximum,suffix in [("x","X 위치",-1000,1000," px"),("y","Y 위치",-1000,1000," px"),("width","너비/크기",1,1000," px"),("height","높이",1,1000," px"),("rotation","회전",-360,360,"°"),("arc_radius","반지름",1,1000," px"),("arc_start_angle","호 시작 각도",-360,360,"°"),("arc_span_angle","호 각도",-360,360,"°"),("thickness","선 두께",1,50," px"),("outline_thickness","외곽선 두께",0,30," px"),("opacity","불투명도",0,255,"")]:
            control=_spin(minimum,maximum,0,suffix);control.valueChanged.connect(lambda value,name=field:self._set_layer(name,value));self.layer_controls[field]=control;form.addRow(self.t(label),control)
        self.layer_cap=FocusWheelComboBox();self.layer_cap.addItem(self.t("둥근 끝"),"round");self.layer_cap.addItem(self.t("각진 끝"),"flat");self.layer_cap.addItem(self.t("삼각형 끝"),"triangle");self.layer_cap.currentIndexChanged.connect(lambda:self._set_layer("cap_style",self.layer_cap.currentData()));form.addRow(self.t("선 끝 모양"),self.layer_cap)
        self.layer_cap_angle=_spin(15,75,45,"°");self.layer_cap_angle.valueChanged.connect(lambda value:self._set_layer("cap_angle",value));form.addRow(self.t("끝 경사 각도"),self.layer_cap_angle)
        self.layer_stroke=ColorButton("#ff3b30",lambda value:self._set_layer("stroke_color",value));form.addRow(self.t("선 색상"),self.layer_stroke);self.layer_outline=ColorButton("#000000",lambda value:self._set_layer("outline_color",value));form.addRow(self.t("외곽선 색상"),self.layer_outline);self.layer_fill=ColorButton("#ff3b30",lambda value:self._set_layer("fill_color",value));form.addRow(self.t("채우기 색상"),self.layer_fill)
        self.mirror_h=QCheckBox(self.t("좌우 대칭"));self.mirror_h.toggled.connect(lambda value:self._set_layer("mirror_horizontal",value));form.addRow(self.mirror_h);self.mirror_v=QCheckBox(self.t("상하 대칭"));self.mirror_v.toggled.connect(lambda value:self._set_layer("mirror_vertical",value));form.addRow(self.mirror_v);self.pattern_enabled=QCheckBox(self.t("원형 패턴"));self.pattern_enabled.toggled.connect(lambda value:self._set_layer("circular_pattern",value));form.addRow(self.pattern_enabled);self.pattern_angle=_spin(-360,360,30,"°");self.pattern_angle.valueChanged.connect(lambda value:self._set_layer("pattern_angle",value));form.addRow(self.t("회전 간격"),self.pattern_angle);self.pattern_copies=_spin(1,3,1);self.pattern_copies.valueChanged.connect(lambda value:self._set_layer("pattern_copies",value));form.addRow(self.t("복사 횟수 (최대 3회)"),self.pattern_copies)
        pngrow=QHBoxLayout();choose=QPushButton(self.t("PNG 선택"));choose.clicked.connect(self.choose_layer_png);clear=QPushButton(self.t("제거"));clear.clicked.connect(self.clear_layer_png);pngrow.addWidget(choose);pngrow.addWidget(clear);form.addRow(self.t("도형 PNG"),pngrow)
        self.layer_key_enabled=QCheckBox(self.t("특정 색상 투명 처리"));self.layer_key_enabled.toggled.connect(lambda value:self._set_layer("color_key_enabled",value));form.addRow(self.layer_key_enabled);self.layer_key_color=ColorButton("#ffffff",lambda value:self._set_layer("color_key",value));form.addRow(self.t("투명 처리 색상"),self.layer_key_color);self.layer_key_tolerance=_spin(0,255,0);self.layer_key_tolerance.valueChanged.connect(lambda value:self._set_layer("color_key_tolerance",value));form.addRow(self.t("색상 허용 범위"),self.layer_key_tolerance);self.layer_key_softness=_spin(0,255,8);self.layer_key_softness.valueChanged.connect(lambda value:self._set_layer("color_key_softness",value));form.addRow(self.t("가장자리 부드럽게"),self.layer_key_softness)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);scroll.setWidget(props);scroll.setMinimumWidth(340);scroll.setMaximumWidth(430);scroll.setObjectName("propertyScroll");holder=QVBoxLayout();holder.setContentsMargins(0,0,0,0);holder.addWidget(scroll);settings_columns.addWidget(Card(holder),1);columns.addWidget(settings_widget,1)
        right=QVBoxLayout();right.setContentsMargins(14,14,14,14);right.setSpacing(9);right.addWidget(_title(self.t("실시간 미리보기")));self.reticle_preview=ReticlePreview();self.reticle_preview.set_language(self.settings.language);self.reticle_preview.layer_moved.connect(self.preview_layer_moved);zoom_row,zoom_area,self.reticle_zoom=self._preview_zoom(self.reticle_preview);right.addLayout(zoom_row);right.addWidget(zoom_area,1);preview_help=QLabel(f"{self.t('CENTER (0, 0)')}  ·  {self.t('선택한 도형을 드래그해 이동')}");preview_help.setObjectName("muted");right.addWidget(preview_help)
        right.addWidget(_title(self.t("전체 도형 위치 보정(오프셋)")));offsets=QHBoxLayout();self.cross_x=_spin(-1000,1000,0," px");self.cross_x.valueChanged.connect(lambda v:self._set_crosshair("offset_x",v));self.cross_y=_spin(-1000,1000,0," px");self.cross_y.valueChanged.connect(lambda v:self._set_crosshair("offset_y",v));self.antialias=QCheckBox(self.t("안티앨리어싱"));self.antialias.toggled.connect(lambda v:self._set_crosshair("antialiasing",v));offsets.addWidget(QLabel(self.t("가로 X")));offsets.addWidget(self.cross_x);offsets.addWidget(QLabel(self.t("세로 Y")));offsets.addWidget(self.cross_y);offsets.addWidget(self.antialias);right.addLayout(offsets);offset_hint=QLabel(self.t("X+: 오른쪽 · X-: 왼쪽 · Y+: 아래 · Y-: 위"));offset_hint.setObjectName("muted");right.addWidget(offset_hint)
        snap,center=self._configure_shape_editor(False);actions=QHBoxLayout();reset=QPushButton(self.t("기본값 복원"));reset.clicked.connect(self.reset_crosshair);actions.addWidget(reset);actions.addWidget(snap);actions.addWidget(center);actions.addStretch();right.addLayout(actions);presets=QHBoxLayout();presets.addStretch();load=QPushButton(self.t("프리셋 불러오기"));load.clicked.connect(self.import_reticle);save=QPushButton(self.t("프리셋 저장"));save.setObjectName("primary");save.clicked.connect(self.export_reticle);presets.addWidget(load);presets.addWidget(save);right.addLayout(presets);hint=QLabel(self.t("미리보기 클릭 후 방향키: 1 px · Shift: 10 px · Ctrl+Z: 실행 취소"));hint.setObjectName("muted");right.addWidget(hint);settings_widget.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding);preview_card=Card(right);preview_card.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding);columns.addWidget(preview_card,1);layout.addLayout(columns,1);return page

    def _build_pointer_page(self)->QWidget:
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(4,4,4,4);layout.setSpacing(10);heading=QHBoxLayout();self.pointer_enabled=ToggleSwitch();self.pointer_enabled.setAccessibleName(self.t("마우스 커서 추적 사용"));self.pointer_enabled.toggled.connect(lambda value:self._set_group("pointer","enabled",value));heading.addWidget(self.pointer_enabled);heading.addWidget(_title(self.t("마우스 커서 추적")));heading.addStretch();layout.addLayout(heading);subtitle=QLabel(self.t("현재 마우스 위치를 CURSOR (0, 0)으로 삼아 도형을 조합합니다."));subtitle.setObjectName("muted");layout.addWidget(subtitle);columns=QHBoxLayout();columns.setContentsMargins(0,0,0,0);columns.setSpacing(10);settings_widget=QWidget();settings_box=QVBoxLayout(settings_widget);settings_box.setContentsMargins(0,0,0,0);settings_box.setSpacing(8);settings_columns=QHBoxLayout();settings_columns.setSpacing(8);settings_box.addLayout(settings_columns,1)
        left=QVBoxLayout();left.setContentsMargins(14,14,14,14);left.addWidget(_title(self.t("도형 레이어")))
        self.pointer_layer_list=QListWidget();self.pointer_layer_list.setObjectName("layerList");self.pointer_layer_list.currentRowChanged.connect(self.select_pointer_layer);self.pointer_layer_list.itemChanged.connect(self.pointer_layer_visibility_changed);left.addWidget(self.pointer_layer_list,1)
        buttons=QHBoxLayout()
        for label,slot in [("추가",self.add_pointer_layer),("복제",self.duplicate_pointer_layer),("삭제",self.delete_pointer_layer)]:button=QPushButton(self.t(label));button.clicked.connect(slot);buttons.addWidget(button)
        left.addLayout(buttons);order=QHBoxLayout();up=QPushButton(self.t("위로"));up.clicked.connect(lambda:self.move_pointer_layer(-1));down=QPushButton(self.t("아래로"));down.clicked.connect(lambda:self.move_pointer_layer(1));order.addWidget(up);order.addWidget(down);left.addLayout(order);layer_card=Card(left);layer_card.setMinimumWidth(230);layer_card.setMaximumWidth(280);settings_columns.addWidget(layer_card)
        props=QWidget();props.setObjectName("editorProperties");form=QFormLayout(props);self.pointer_properties_form=form;form.setContentsMargins(14,14,14,14);form.setSpacing(9);form.setRowWrapPolicy(QFormLayout.WrapLongRows);form.addRow(_title(self.t("도형 속성")));self.pointer_layer_name=QLineEdit();self.pointer_layer_name.editingFinished.connect(lambda:self._set_pointer_layer("name",self.pointer_layer_name.text().strip() or self.t("도형")));form.addRow(self.t("이름"),self.pointer_layer_name)
        self.pointer_layer_shape=FocusWheelComboBox()
        for key in SHAPE_LABELS:self.pointer_layer_shape.addItem(self.shape_label(key),key)
        self.pointer_layer_shape.currentIndexChanged.connect(lambda:self._set_pointer_layer("shape",self.pointer_layer_shape.currentData()));form.addRow(self.t("도형 종류"),self.pointer_layer_shape);self.pointer_layer_controls={}
        for field,label,minimum,maximum,suffix in [("x","X 위치",-1000,1000," px"),("y","Y 위치",-1000,1000," px"),("width","너비/크기",1,1000," px"),("height","높이",1,1000," px"),("rotation","회전",-360,360,"°"),("arc_radius","반지름",1,1000," px"),("arc_start_angle","호 시작 각도",-360,360,"°"),("arc_span_angle","호 각도",-360,360,"°"),("thickness","선 두께",1,50," px"),("outline_thickness","외곽선 두께",0,30," px"),("opacity","불투명도",0,255,"")]:control=_spin(minimum,maximum,0,suffix);control.valueChanged.connect(lambda value,name=field:self._set_pointer_layer(name,value));self.pointer_layer_controls[field]=control;form.addRow(self.t(label),control)
        self.pointer_layer_cap=FocusWheelComboBox();self.pointer_layer_cap.addItem(self.t("둥근 끝"),"round");self.pointer_layer_cap.addItem(self.t("각진 끝"),"flat");self.pointer_layer_cap.addItem(self.t("삼각형 끝"),"triangle");self.pointer_layer_cap.currentIndexChanged.connect(lambda:self._set_pointer_layer("cap_style",self.pointer_layer_cap.currentData()));form.addRow(self.t("선 끝 모양"),self.pointer_layer_cap);self.pointer_layer_stroke=ColorButton("#ffff00",lambda value:self._set_pointer_layer("stroke_color",value));form.addRow(self.t("선 색상"),self.pointer_layer_stroke);self.pointer_layer_outline=ColorButton("#000000",lambda value:self._set_pointer_layer("outline_color",value));form.addRow(self.t("외곽선 색상"),self.pointer_layer_outline);self.pointer_layer_fill=ColorButton("#ffff00",lambda value:self._set_pointer_layer("fill_color",value));form.addRow(self.t("채우기 색상"),self.pointer_layer_fill)
        self.pointer_layer_cap_angle=_spin(15,75,45,"°");self.pointer_layer_cap_angle.valueChanged.connect(lambda value:self._set_pointer_layer("cap_angle",value));form.addRow(self.t("끝 경사 각도"),self.pointer_layer_cap_angle)
        self.pointer_mirror_h=QCheckBox(self.t("좌우 대칭"));self.pointer_mirror_h.toggled.connect(lambda value:self._set_pointer_layer("mirror_horizontal",value));form.addRow(self.pointer_mirror_h);self.pointer_mirror_v=QCheckBox(self.t("상하 대칭"));self.pointer_mirror_v.toggled.connect(lambda value:self._set_pointer_layer("mirror_vertical",value));form.addRow(self.pointer_mirror_v);self.pointer_pattern_enabled=QCheckBox(self.t("원형 패턴"));self.pointer_pattern_enabled.toggled.connect(lambda value:self._set_pointer_layer("circular_pattern",value));form.addRow(self.pointer_pattern_enabled);self.pointer_pattern_angle=_spin(-360,360,30,"°");self.pointer_pattern_angle.valueChanged.connect(lambda value:self._set_pointer_layer("pattern_angle",value));form.addRow(self.t("회전 간격"),self.pointer_pattern_angle);self.pointer_pattern_copies=_spin(1,3,1);self.pointer_pattern_copies.valueChanged.connect(lambda value:self._set_pointer_layer("pattern_copies",value));form.addRow(self.t("복사 횟수 (최대 3회)"),self.pointer_pattern_copies)
        pngrow=QHBoxLayout();choose=QPushButton(self.t("PNG 선택"));choose.clicked.connect(self.choose_pointer_layer_png);clear=QPushButton(self.t("제거"));clear.clicked.connect(self.clear_pointer_layer_png);pngrow.addWidget(choose);pngrow.addWidget(clear);form.addRow(self.t("도형 PNG"),pngrow);self.pointer_layer_key_enabled=QCheckBox(self.t("특정 색상 투명 처리"));self.pointer_layer_key_enabled.toggled.connect(lambda value:self._set_pointer_layer("color_key_enabled",value));form.addRow(self.pointer_layer_key_enabled);self.pointer_layer_key_color=ColorButton("#ffffff",lambda value:self._set_pointer_layer("color_key",value));form.addRow(self.t("투명 처리 색상"),self.pointer_layer_key_color);self.pointer_layer_key_tolerance=_spin(0,255,0);self.pointer_layer_key_tolerance.valueChanged.connect(lambda value:self._set_pointer_layer("color_key_tolerance",value));form.addRow(self.t("색상 허용 범위"),self.pointer_layer_key_tolerance);self.pointer_layer_key_softness=_spin(0,255,8);self.pointer_layer_key_softness.valueChanged.connect(lambda value:self._set_pointer_layer("color_key_softness",value));form.addRow(self.t("가장자리 부드럽게"),self.pointer_layer_key_softness)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);scroll.setWidget(props);scroll.setMinimumWidth(340);scroll.setMaximumWidth(430);scroll.setObjectName("propertyScroll");holder=QVBoxLayout();holder.setContentsMargins(0,0,0,0);holder.addWidget(scroll);settings_columns.addWidget(Card(holder),1);columns.addWidget(settings_widget,1)
        right=QVBoxLayout();right.setContentsMargins(14,14,14,14);right.setSpacing(9);right.addWidget(_title(self.t("실시간 미리보기")));self.pointer_preview=PointerPreview();self.pointer_preview.set_language(self.settings.language);self.pointer_preview.layer_moved.connect(self.preview_pointer_layer_moved);zoom_row,zoom_area,self.pointer_zoom=self._preview_zoom(self.pointer_preview);right.addLayout(zoom_row);right.addWidget(zoom_area,1);help_label=QLabel(f"{self.t('CURSOR (0, 0)')}  ·  {self.t('선택한 도형을 드래그해 이동')}");help_label.setObjectName("muted");right.addWidget(help_label);right.addWidget(_title(self.t("전체 도형 위치 보정(오프셋)")));offsets=QHBoxLayout();self.pointer_x=_spin(-1000,1000,0," px");self.pointer_x.valueChanged.connect(lambda value:self._set_group("pointer","offset_x",value));self.pointer_y=_spin(-1000,1000,0," px");self.pointer_y.valueChanged.connect(lambda value:self._set_group("pointer","offset_y",value));self.pointer_antialias=QCheckBox(self.t("안티앨리어싱"));self.pointer_antialias.toggled.connect(lambda value:self._set_group("pointer","antialiasing",value));offsets.addWidget(QLabel(self.t("가로 X")));offsets.addWidget(self.pointer_x);offsets.addWidget(QLabel(self.t("세로 Y")));offsets.addWidget(self.pointer_y);offsets.addWidget(self.pointer_antialias);right.addLayout(offsets)
        rate=QHBoxLayout();rate.addWidget(QLabel(self.t("추적 속도")));self.pointer_rate=FocusWheelComboBox();self.pointer_rate.addItem(self.t("자동 (모니터 주사율)"),0)
        for hz in (60,120,144,165,240):self.pointer_rate.addItem(f"{hz} Hz",hz)
        self.pointer_rate.currentIndexChanged.connect(lambda:self._set_group("pointer","update_rate",self.pointer_rate.currentData()));rate.addWidget(self.pointer_rate);rate.addStretch();right.addLayout(rate);snap,center=self._configure_shape_editor(True);actions=QHBoxLayout();reset=QPushButton(self.t("기본값 복원"));reset.clicked.connect(self.reset_pointer);actions.addWidget(reset);actions.addWidget(snap);actions.addWidget(center);actions.addStretch();right.addLayout(actions);presets=QHBoxLayout();presets.addStretch();load=QPushButton(self.t("프리셋 불러오기"));load.clicked.connect(self.import_pointer_preset);save=QPushButton(self.t("프리셋 저장"));save.setObjectName("primary");save.clicked.connect(self.export_pointer_preset);presets.addWidget(load);presets.addWidget(save);right.addLayout(presets);hint=QLabel(self.t("미리보기 클릭 후 방향키: 1 px · Shift: 10 px · Ctrl+Z: 실행 취소"));hint.setObjectName("muted");right.addWidget(hint);settings_widget.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding);preview_card=Card(right);preview_card.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding);columns.addWidget(preview_card,1);layout.addLayout(columns,1);return page

    def _build_motion_page(self)->QWidget:
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(4,4,4,4);layout.setSpacing(10)
        heading=QHBoxLayout();self.motion_header_enabled=ToggleSwitch();self.motion_header_enabled.setAccessibleName(self.t("화면 보조 기능 사용"));self.motion_header_enabled.toggled.connect(self._set_current_motion_enabled);heading.addWidget(self.motion_header_enabled)
        self.motion_page_title=_title(self.t("가상 신체 표시"));heading.addWidget(self.motion_page_title);heading.addStretch();layout.addLayout(heading)
        subtitle = QLabel(self.t("화면에 고정된 정적 기준을 조합합니다. 켜 둔 기능은 전체 오버레이 단축키로 함께 표시하거나 숨길 수 있습니다."))
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        workspace=QHBoxLayout();workspace.setContentsMargins(0,0,0,0);workspace.setSpacing(10)
        self.motion_settings_stack=QStackedWidget()
        def add_motion_card(card:QWidget)->None:
            scroll=QScrollArea();scroll.setObjectName("motionSettingsScroll");scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setWidget(card);self.motion_settings_stack.addWidget(scroll)

        vignette=QFormLayout();vignette.setContentsMargins(16,14,16,14);vignette.setSpacing(9)
        self.vignette_shape=FocusWheelComboBox();self.vignette_shape.addItem(self.t("타원형"),"ellipse");self.vignette_shape.addItem(self.t("둥근 사각형"),"rounded_rect");self.vignette_shape.currentIndexChanged.connect(lambda:self._set_motion("vignette","shape",self.vignette_shape.currentData()));vignette.addRow(self.t("형태"),self.vignette_shape)
        self.vignette_opacity=self._motion_spin(vignette,self.t("강도"),0,255,"vignette","opacity")
        self.vignette_width=self._motion_spin(vignette,self.t("중앙 투명 영역 가로"),10,95,"vignette","center_width"," %")
        self.vignette_height=self._motion_spin(vignette,self.t("중앙 투명 영역 세로"),10,95,"vignette","center_height"," %")
        self.vignette_softness=self._motion_spin(vignette,self.t("전환 부드러움"),1,100,"vignette","softness"," %")
        self.vignette_x=self._motion_spin(vignette,self.t("X 위치 보정"),-1000,1000,"vignette","offset_x"," px")
        self.vignette_y=self._motion_spin(vignette,self.t("Y 위치 보정"),-1000,1000,"vignette","offset_y"," px")
        self.vignette_color=ColorButton("#000000",lambda v:self._set_motion("vignette","color",v));vignette.addRow(self.t("색상"),self.vignette_color);add_motion_card(Card(vignette))

        body_widget=QWidget();body_columns=QHBoxLayout(body_widget);body_columns.setContentsMargins(0,0,0,0);body_columns.setSpacing(8)
        body_left=QVBoxLayout();body_left.setContentsMargins(14,14,14,14);body_left.addWidget(_title(self.t("도형 레이어")))
        self.body_layer_list=QListWidget();self.body_layer_list.setObjectName("layerList");self.body_layer_list.setMinimumHeight(190);self.body_layer_list.currentRowChanged.connect(self.select_body_layer);self.body_layer_list.itemChanged.connect(self.body_layer_visibility_changed);body_left.addWidget(self.body_layer_list,1)
        body_props_widget=QWidget();body_props_widget.setObjectName("editorProperties");body_props=QFormLayout(body_props_widget);body_props.setContentsMargins(14,14,14,14);body_props.setSpacing(9);body_props.setRowWrapPolicy(QFormLayout.WrapLongRows);body_props.addRow(_title(self.t("도형 속성")))
        self.body_preset=FocusWheelComboBox();self.body_preset.addItem(self.t("코 기준점"),"nose");self.body_preset.addItem(self.t("양손 기준점"),"arms");self.body_preset.addItem(self.t("코+양손 기준점"),"body");self.body_apply_preset=QPushButton(self.t("프리셋 적용"));self.body_apply_preset.clicked.connect(self.apply_body_preset);body_preset_row=QHBoxLayout();body_preset_row.addWidget(self.body_preset);body_preset_row.addWidget(self.body_apply_preset);body_props.addRow(self.t("기본 도형"),body_preset_row)
        self.body_layer_name=QLineEdit();self.body_layer_name.editingFinished.connect(lambda:self._set_body_layer("name",self.body_layer_name.text().strip() or self.t("도형")));body_props.addRow(self.t("이름"),self.body_layer_name)
        self.body_layer_shape=FocusWheelComboBox()
        for key in ("nose","arm_left","arm_right","image"):self.body_layer_shape.addItem(self.shape_label(key),key)
        self.body_layer_shape.currentIndexChanged.connect(lambda:self._set_body_layer("shape",self.body_layer_shape.currentData()));body_props.addRow(self.t("도형 종류"),self.body_layer_shape);self.body_layer_controls={}
        for field,label,minimum,maximum,suffix in [("x","X 위치",-3000,3000," px"),("y","Y 위치",-2000,500," px"),("width","가로 크기 (X)",1,2000," px"),("height","세로 크기 (Y)",1,2000," px"),("rotation","회전",-360,360,"°"),("opacity","불투명도",0,255,"")]:
            control=_spin(minimum,maximum,0,suffix);control.valueChanged.connect(lambda value,name=field:self._set_body_layer(name,value));self.body_layer_controls[field]=control;body_props.addRow(self.t(label),control)
        self.body_layer_fill=ColorButton("#d8a184",lambda v:self._set_body_layer("fill_color",v));body_props.addRow(self.t("색상"),self.body_layer_fill)
        image_row=QHBoxLayout();self.body_choose_png=QPushButton(self.t("PNG 선택"));self.body_choose_png.clicked.connect(self.choose_body_png);self.body_clear_png=QPushButton(self.t("제거"));self.body_clear_png.clicked.connect(self.clear_body_png);image_row.addWidget(self.body_choose_png);image_row.addWidget(self.body_clear_png);body_props.addRow(self.t("사용자 이미지"),image_row);self.body_key_enabled=QCheckBox(self.t("특정 색상 투명 처리"));self.body_key_enabled.toggled.connect(lambda v:self._set_body_layer("color_key_enabled",v));body_props.addRow(self.body_key_enabled);self.body_key_color=ColorButton("#ffffff",lambda v:self._set_body_layer("color_key",v));body_props.addRow(self.t("투명 처리 색상"),self.body_key_color);self.body_key_tolerance=_spin(0,255,0);self.body_key_tolerance.valueChanged.connect(lambda v:self._set_body_layer("color_key_tolerance",v));body_props.addRow(self.t("색상 허용 범위"),self.body_key_tolerance);self.body_key_softness=_spin(0,255,8);self.body_key_softness.valueChanged.connect(lambda v:self._set_body_layer("color_key_softness",v));body_props.addRow(self.t("가장자리 부드럽게"),self.body_key_softness)
        body_actions=QHBoxLayout();body_order=QHBoxLayout();self.body_action_buttons=[]
        for label,slot in [("추가",self.add_body_layer),("복제",self.duplicate_body_layer),("삭제",self.delete_body_layer)]:
            button=QPushButton(self.t(label));button.clicked.connect(slot);body_actions.addWidget(button);self.body_action_buttons.append(button)
        for label,slot in [("위로",lambda:self.move_body_layer(-1)),("아래로",lambda:self.move_body_layer(1))]:
            button=QPushButton(self.t(label));button.clicked.connect(slot);body_order.addWidget(button);self.body_action_buttons.append(button)
        body_left.addLayout(body_actions);body_left.addLayout(body_order);body_layer_card=Card(body_left);body_layer_card.setMinimumWidth(230);body_layer_card.setMaximumWidth(280);body_columns.addWidget(body_layer_card)
        body_props_scroll=QScrollArea();body_props_scroll.setWidgetResizable(True);body_props_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);body_props_scroll.setWidget(body_props_widget);body_props_scroll.setMinimumWidth(340);body_props_scroll.setMaximumWidth(430);body_props_scroll.setObjectName("propertyScroll");body_props_layout=QVBoxLayout();body_props_layout.setContentsMargins(0,0,0,0);body_props_layout.addWidget(body_props_scroll);body_columns.addWidget(Card(body_props_layout),1);self.motion_settings_stack.addWidget(body_widget)

        # Guide controls are grouped in the same order as the renderer:
        # visibility, per-edge length, appearance, offsets, and end treatment.
        guides = QFormLayout()
        guides.setContentsMargins(16, 14, 16, 14)
        guides.setSpacing(9)
        self.guide_horizontal = QCheckBox(self.t("수평선"))
        self.guide_horizontal.toggled.connect(lambda v: self._set_motion("guides", "horizontal", v))
        self.guide_vertical = QCheckBox(self.t("수직선"))
        self.guide_vertical.toggled.connect(lambda v: self._set_motion("guides", "vertical", v))
        line_options = QHBoxLayout()
        line_options.addWidget(self.guide_horizontal)
        line_options.addWidget(self.guide_vertical)
        line_options.addStretch()
        guides.addRow(line_options)

        self.guide_horizontal_length = self._motion_spin(guides, self.t("가로선 각 선의 길이"), 1, 4000, "guides", "horizontal_length", " px")
        self.guide_vertical_length = self._motion_spin(guides, self.t("세로선 각 선의 길이"), 1, 4000, "guides", "vertical_length", " px")
        self.guide_thickness = self._motion_spin(guides, self.t("선 두께"), 1, 300, "guides", "thickness", " px")
        self.guide_opacity = self._motion_spin(guides, self.t("불투명도"), 0, 255, "guides", "opacity")
        self.guide_x = self._motion_spin(guides, self.t("X 위치 보정"), -1000, 1000, "guides", "offset_x", " px")
        self.guide_y = self._motion_spin(guides, self.t("Y 위치 보정"), -1000, 1000, "guides", "offset_y", " px")

        self.guide_center_cap = FocusWheelComboBox()
        for label, value in (("둥근 끝", "round"), ("각진 끝", "flat"), ("삼각형 끝", "triangle")):
            self.guide_center_cap.addItem(self.t(label), value)
        self.guide_center_cap.currentIndexChanged.connect(
            lambda: self._set_motion("guides", "center_cap", self.guide_center_cap.currentData())
        )
        guides.addRow(self.t("중앙 선 마무리"), self.guide_center_cap)
        self.guide_cap_angle = self._motion_spin(guides, self.t("끝 경사 각도"), 15, 75, "guides", "center_cap_angle", "°")
        self.guide_dashed = QCheckBox(self.t("점선"))
        self.guide_dashed.toggled.connect(lambda v: self._set_motion("guides", "dashed", v))
        guides.addRow(self.guide_dashed)
        self.guide_dash_length = self._motion_spin(guides, self.t("점선 길이"), 1, 200, "guides", "dash_length", " px")
        self.guide_dash_gap = self._motion_spin(guides, self.t("점선 간격"), 1, 200, "guides", "dash_gap", " px")
        self.guide_color = ColorButton("#ffffff", lambda v: self._set_motion("guides", "color", v))
        guides.addRow(self.t("색상"), self.guide_color)
        add_motion_card(Card(guides))

        grid=QFormLayout();grid.setContentsMargins(16,14,16,14);grid.setSpacing(9)
        self.grid_columns=self._motion_spin(grid,self.t("가로 분할 수"),2,16,"grid","columns");self.grid_rows=self._motion_spin(grid,self.t("세로 분할 수"),2,16,"grid","rows");self.grid_thickness=self._motion_spin(grid,self.t("선 두께"),1,10,"grid","thickness"," px");self.grid_opacity=self._motion_spin(grid,self.t("불투명도"),0,255,"grid","opacity");self.grid_margin=self._motion_spin(grid,self.t("바깥 여백"),0,500,"grid","margin"," px")
        grid.addRow(_title(self.t("가로선 설정")));self.grid_horizontal_dashed=QCheckBox(self.t("가로선 점선"));self.grid_horizontal_dashed.toggled.connect(lambda v:self._set_motion("grid","horizontal_dashed",v));grid.addRow(self.grid_horizontal_dashed);self.grid_horizontal_dash_length=self._motion_spin(grid,self.t("가로 점선 길이"),1,200,"grid","horizontal_dash_length"," px");self.grid_horizontal_dash_gap=self._motion_spin(grid,self.t("가로 점선 간격"),1,200,"grid","horizontal_dash_gap"," px");self.grid_horizontal_dash_offset=self._motion_spin(grid,self.t("가로 점선 시작 오프셋"),-400,400,"grid","horizontal_dash_offset"," px")
        grid.addRow(_title(self.t("세로선 설정")));self.grid_vertical_dashed=QCheckBox(self.t("세로선 점선"));self.grid_vertical_dashed.toggled.connect(lambda v:self._set_motion("grid","vertical_dashed",v));grid.addRow(self.grid_vertical_dashed);self.grid_vertical_dash_length=self._motion_spin(grid,self.t("세로 점선 길이"),1,200,"grid","vertical_dash_length"," px");self.grid_vertical_dash_gap=self._motion_spin(grid,self.t("세로 점선 간격"),1,200,"grid","vertical_dash_gap"," px");self.grid_vertical_dash_offset=self._motion_spin(grid,self.t("세로 점선 시작 오프셋"),-400,400,"grid","vertical_dash_offset"," px")
        self.grid_center=QCheckBox(self.t("중앙선 강조"));self.grid_center.toggled.connect(lambda v:self._set_motion("grid","emphasize_center",v));grid.addRow(self.grid_center);self.grid_color=ColorButton("#ffffff",lambda v:self._set_motion("grid","color",v));grid.addRow(self.t("색상"),self.grid_color);add_motion_card(Card(grid))
        self.motion_preview=MotionAssistPreview();self.motion_preview.set_model(self.profile.motion_assist);self.motion_preview.layer_moved.connect(self.preview_body_layer_moved);self.motion_preview.drag_started.connect(self._begin_drag);self.motion_preview.drag_finished.connect(self._end_drag)
        preview_box=QVBoxLayout();preview_box.setContentsMargins(14,14,14,14);preview_box.setSpacing(9);preview_box.addWidget(_title(self.t("예시 미리보기 · 16:9")));zoom_row,zoom_area,self.body_zoom=self._preview_zoom(self.motion_preview);preview_box.addLayout(zoom_row);preview_box.addWidget(zoom_area,1);preview_hint=QLabel(self.t("1920×1080 기준의 축소 예시입니다. 실제 게임 화면을 캡처하지 않습니다."));preview_hint.setObjectName("muted");preview_hint.setWordWrap(True);preview_box.addWidget(preview_hint)
        settings_side=QWidget();settings_box=QVBoxLayout(settings_side);settings_box.setContentsMargins(0,0,0,0);settings_box.setSpacing(8);settings_box.addWidget(self.motion_settings_stack,1);workspace.addWidget(settings_side,1);workspace.addWidget(Card(preview_box),1)
        layout.addLayout(workspace,1);return page

    def _build_effect_page(self)->QWidget:
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(4,4,4,4);layout.setSpacing(10)
        heading=QHBoxLayout();self.effect_enabled=ToggleSwitch();self.effect_enabled.setAccessibleName(self.t("마우스 찾기 사용"));self.effect_enabled.toggled.connect(lambda value:self._set_group("find_effect","enabled",value));heading.addWidget(self.effect_enabled);heading.addWidget(_title(self.t("마우스 찾기")));heading.addStretch();layout.addLayout(heading)
        subtitle=QLabel(self.t("현재 마우스 위치에 입력을 방해하지 않는 짧은 시각 효과를 표시합니다."));subtitle.setObjectName("muted");layout.addWidget(subtitle)
        form=QFormLayout();form.setContentsMargins(18,18,18,18);form.setSpacing(11);self.effect_type=FocusWheelComboBox();
        for key,label in [("expand","확대"),("contract","축소"),("flash","깜박임"),("lines","선 강조"),("focus_lines","중앙 집중"),("grow","커서 확대")]:self.effect_type.addItem(self.t(label),key)
        self.effect_type.currentIndexChanged.connect(lambda:self._set_group("find_effect","effect",self.effect_type.currentData()));form.addRow(self.t("효과"),self.effect_type);self.effect_color=ColorButton("#00e5ff",lambda v:self._set_group("find_effect","color",v));form.addRow(self.t("색상"),self.effect_color)
        self.effect_opacity=self._group_spin(form,self.t("불투명도"),0,255,"find_effect","opacity");self.effect_size=self._group_spin(form,self.t("최대 크기"),30,600,"find_effect","max_size");self.effect_thick=self._group_spin(form,self.t("선 두께"),1,30,"find_effect","thickness");self.effect_duration=self._group_spin(form,self.t("지속 시간"),100,5000,"find_effect","duration_ms");self.effect_duration.setSuffix(" ms");self.effect_repeats=self._group_spin(form,self.t("반복 횟수"),1,10,"find_effect","repeats");self.effect_speed=self._group_spin(form,self.t("속도"),10,300,"find_effect","speed");self.effect_speed.setSuffix(" %");button=QPushButton(self.t("현재 마우스 위치에서 미리보기"));button.setObjectName("primary");button.clicked.connect(self.controller.preview_effect);form.addRow(button);layout.addWidget(Card(form));layout.addStretch();return page

    def _build_hotkey_page(self)->QWidget:
        page,layout=self._page(self.t("전역 단축키"),self.t("텍스트를 입력하지 않고 보조 키와 실행 키를 목록에서 선택합니다."));form=QFormLayout();form.setContentsMargins(18,18,18,18);form.setSpacing(12);self.hotkey_widgets={};labels={"find":"찾기 효과 실행","all_overlays":"전체 오버레이 ON/OFF"};modifiers=[("없음",""),("Ctrl+Alt","Ctrl+Alt"),("Ctrl+Shift","Ctrl+Shift"),("Alt+Shift","Alt+Shift"),("Ctrl+Alt+Shift","Ctrl+Alt+Shift"),("Ctrl","Ctrl"),("Alt","Alt"),("Shift","Shift")];keys=[f"F{i}" for i in range(1,13)]+[chr(c) for c in range(65,91)]+[str(i) for i in range(10)]
        for field,label in labels.items():
            mods=FocusWheelComboBox()
            for text,data in modifiers:mods.addItem(self.t(text),data)
            key=FocusWheelComboBox()
            for value in keys:key.addItem(value,value)
            for text,data in [("Mouse 1 · "+self.t("왼쪽 버튼"),"Mouse1"),("Mouse 2 · "+self.t("오른쪽 버튼"),"Mouse2"),("Mouse 3 · "+self.t("휠 클릭"),"Mouse3"),("Mouse 4 · "+self.t("뒤로 버튼"),"Mouse4"),("Mouse 5 · "+self.t("앞으로 버튼"),"Mouse5")]:key.addItem(text,data)
            row=QHBoxLayout();row.addWidget(mods);row.addWidget(key);mods.currentIndexChanged.connect(self.update_hotkeys);key.currentIndexChanged.connect(self.update_hotkeys);self.hotkey_widgets[field]=(mods,key);form.addRow(self.t(label),row)
        warning=QLabel(self.t("보조 키 없이 문자 키나 Mouse 1·2를 지정하면 일반 입력 중에도 기능이 자주 실행될 수 있습니다."));warning.setObjectName("muted");warning.setWordWrap(True);form.addRow(warning);self.hotkey_status=QLabel();self.hotkey_status.setWordWrap(True);form.addRow(self.t("등록 상태"),self.hotkey_status);layout.addWidget(Card(form));layout.addStretch();return page

    def _build_general_page(self) -> QWidget:
        page, layout = self._page(self.t("일반 설정"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        cards = QVBoxLayout(content)
        cards.setContentsMargins(0, 0, 8, 0)
        cards.setSpacing(10)

        management = QVBoxLayout()
        management.setContentsMargins(18, 18, 18, 18)
        management.setSpacing(14)
        heading = QHBoxLayout()
        heading.addWidget(_title(self.t("프로필 관리")))
        heading.addStretch()
        for label, slot in (("새로 만들기", self.add_profile), ("가져오기", self.import_profile)):
            button = QPushButton(self.t(label))
            button.clicked.connect(slot)
            heading.addWidget(button)
        management.addLayout(heading)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.addWidget(_title(self.t("내 프로필")))
        self.profile_count = QLabel()
        self.profile_count.setObjectName("muted")
        left.addWidget(self.profile_count)

        # One list owns both profile selection and its independent enable state.
        self.profile_list = QListWidget()
        self.profile_list.setObjectName("layerList")
        self.profile_list.setMinimumHeight(330)
        for profile in self.settings.profiles:
            self.profile_list.addItem(self._new_profile_item(profile))
        self.profile_list.setCurrentRow(self.settings.selected_profile)
        self.profile_list.currentRowChanged.connect(self.change_profile)
        self.profile_list.itemChanged.connect(self._profile_enabled_changed)
        left.addWidget(self.profile_list, 1)
        profile_hint = QLabel(self.t("체크한 프로필만 자동 전환과 오버레이 표시에 사용합니다."))
        profile_hint.setObjectName("muted")
        profile_hint.setWordWrap(True)
        left.addWidget(profile_hint)
        columns.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(_title(self.t("선택한 프로필")))
        detail = QFormLayout()
        detail.setSpacing(10)
        self.profile_name_edit = QLineEdit(self.profile.name)
        self.profile_name_edit.editingFinished.connect(self.rename_profile)
        detail.addRow(self.t("이름"), self.profile_name_edit)
        self.target_combo = FocusWheelComboBox()
        self.target_combo.currentIndexChanged.connect(self.target_changed)
        refresh = QPushButton(self.t("새로 고침"))
        refresh.clicked.connect(self.refresh_windows)
        target_row = QHBoxLayout()
        target_row.addWidget(self.target_combo, 1)
        target_row.addWidget(refresh)
        detail.addRow(self.t("대상 위치"), target_row)
        self.profile_status = QLabel()
        detail.addRow(self.t("현재 상태"), self.profile_status)
        right.addLayout(detail)

        right.addWidget(_title(self.t("사용 기능")))
        self.profile_features = QLabel()
        self.profile_features.setWordWrap(True)
        self.profile_features.setMinimumHeight(68)
        right.addWidget(self.profile_features)
        self.profile_target_hint = QLabel()
        self.profile_target_hint.setObjectName("muted")
        self.profile_target_hint.setWordWrap(True)
        right.addWidget(self.profile_target_hint)
        right.addStretch()

        actions = QHBoxLayout()
        for label, slot in (
            ("복제", self.duplicate_profile),
            ("내보내기", self.export_profile),
            ("삭제", self.delete_profile),
        ):
            button = QPushButton(self.t(label))
            button.clicked.connect(slot)
            actions.addWidget(button)
        right.addLayout(actions)
        sharing = QLabel(self.t("프로필 내보내기에는 PNG가 포함됩니다. 원본 이미지는 앱에 복사하여 보관합니다."))
        sharing.setWordWrap(True)
        sharing.setObjectName("muted")
        right.addWidget(sharing)
        columns.addLayout(right, 3)
        management.addLayout(columns)
        note = QLabel(self.t("앱 이름만 표시합니다. 창 제목, 문서명, 이메일 주소는 표시하지 않습니다."))
        note.setObjectName("muted")
        management.addWidget(note)
        cards.addWidget(Card(management))
        form = QFormLayout()
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)
        form.addRow(_title(self.t("앱 설정")))
        self.master_enabled = QCheckBox(self.t("모든 오버레이 활성화"))
        self.master_enabled.toggled.connect(self.master_toggled)
        form.addRow(self.master_enabled)
        self.keep_topmost = QCheckBox(self.t("테두리 없는 창 모드에서 최상위 유지"))
        self.keep_topmost.toggled.connect(lambda value: self._set_app("keep_overlay_on_top", value))
        form.addRow(self.keep_topmost)
        top_hint = QLabel(self.t("독점 전체화면은 지원하지 않습니다."))
        top_hint.setObjectName("muted")
        form.addRow(top_hint)
        self.startup = QCheckBox(self.t("Windows 시작 시 자동 실행 (현재 사용자)"))
        self.startup.toggled.connect(self.startup_toggled)
        form.addRow(self.startup)
        self.to_tray = QCheckBox(self.t("창을 닫으면 트레이로 최소화"))
        self.to_tray.toggled.connect(lambda value: self._set_app("minimize_to_tray", value))
        form.addRow(self.to_tray)
        exit_button = QPushButton(self.t("프로그램 완전히 종료"))
        exit_button.clicked.connect(self.request_quit)
        form.addRow(exit_button)
        cards.addWidget(Card(form))
        cards.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page

    def _group_spin(self,form,label,minimum,maximum,group,field)->QSpinBox:
        widget=_spin(minimum,maximum,getattr(getattr(self.profile,group),field));widget.valueChanged.connect(lambda v:self._set_group(group,field,v));form.addRow(label,widget);return widget

    def _motion_spin(self,form,label,minimum,maximum,section,field,suffix="")->QSpinBox:
        widget=_spin(minimum,maximum,0,suffix);widget.valueChanged.connect(lambda v:self._set_motion(section,field,v));form.addRow(label,widget);return widget

    def _set_motion(self,section,field,value)->None:
        if self._loading:return
        setattr(getattr(self.profile.motion_assist,section),field,value);self._save_settings();self.controller.refresh_visuals();self.motion_preview.set_model(self.profile.motion_assist);self._refresh_nav_status();self._update_motion_enabled_controls()

    def _set_current_motion_enabled(self,value)->None:
        section={2:"body",3:"vignette",4:"guides",5:"grid"}.get(self.navigation.currentRow())
        if section:self._set_motion(section,"enabled",value)

    def _update_motion_enabled_controls(self)->None:
        motion=self.profile.motion_assist
        self.guide_cap_angle.setEnabled(motion.guides.center_cap=="triangle")
        self.guide_dash_length.setEnabled(motion.guides.dashed);self.guide_dash_gap.setEnabled(motion.guides.dashed)
        for widget in (self.grid_horizontal_dash_length,self.grid_horizontal_dash_gap,self.grid_horizontal_dash_offset):widget.setEnabled(motion.grid.horizontal_dashed)
        for widget in (self.grid_vertical_dash_length,self.grid_vertical_dash_gap,self.grid_vertical_dash_offset):widget.setEnabled(motion.grid.vertical_dashed)
        self._update_body_image_controls()

    def current_body_layer(self):
        item=self.body_layer_list.currentItem();layer_id=item.data(Qt.UserRole) if item else None
        return next((layer for layer in self.profile.motion_assist.body.layers if layer.layer_id==layer_id),None)

    def rebuild_body_layer_list(self,selected_id=None)->None:
        self.body_layer_list.blockSignals(True);self.body_layer_list.clear();selected_row=0
        for row,layer in enumerate(self.profile.motion_assist.body.layers):
            item=QListWidgetItem(f"{self.shape_label(layer.shape)}   {layer.name}");item.setData(Qt.UserRole,layer.layer_id);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if layer.visible else Qt.Unchecked);self.body_layer_list.addItem(item)
            if layer.layer_id==selected_id:selected_row=row
        self.body_layer_list.blockSignals(False)
        if self.body_layer_list.count():self.body_layer_list.setCurrentRow(selected_row)
        else:self.select_body_layer(-1)

    def select_body_layer(self,_row)->None:
        layer=self.current_body_layer();self.motion_preview.selected_id=layer.layer_id if layer else None;self.motion_preview.update();self._loading=True;enabled=layer is not None
        for widget in [self.body_layer_name,self.body_layer_shape,*self.body_layer_controls.values(),self.body_layer_fill,self.body_key_enabled,self.body_key_color,self.body_key_tolerance,self.body_key_softness]:widget.setEnabled(enabled)
        if layer:
            self.body_layer_name.setText(layer.name);self.body_layer_shape.setCurrentIndex(max(0,self.body_layer_shape.findData(layer.shape)))
            for field,widget in self.body_layer_controls.items():widget.setValue(getattr(layer,field))
            self.body_layer_fill.color=layer.fill_color;self.body_layer_fill.refresh()
            self.body_key_enabled.setChecked(layer.color_key_enabled);self.body_key_color.color=layer.color_key;self.body_key_color.refresh();self.body_key_tolerance.setValue(layer.color_key_tolerance);self.body_key_softness.setValue(layer.color_key_softness)
        self._loading=False;self._update_body_image_controls()

    def _update_body_image_controls(self)->None:
        layer=self.current_body_layer();image_mode=bool(layer and layer.shape=="image" and layer.image_path);self.body_key_enabled.setEnabled(image_mode);details=image_mode and self.body_key_enabled.isChecked()
        for widget in (self.body_key_color,self.body_key_tolerance,self.body_key_softness):widget.setEnabled(details)

    def _set_body_layer(self,field,value)->None:
        if self._loading:return
        layer=self.current_body_layer()
        if not layer:return
        setattr(layer,field,value)
        if field in {"name","shape"}:self.rebuild_body_layer_list(layer.layer_id)
        self._update_body_image_controls();self._body_changed()

    def _body_changed(self)->None:
        self._save_settings();self.controller.refresh_visuals();self.motion_preview.set_model(self.profile.motion_assist);self._refresh_nav_status()

    def preview_body_layer_moved(self,x,y)->None:
        layer=self.current_body_layer()
        if layer is None:return
        x=max(-3000,min(3000,x));y=max(-2000,min(500,y))
        if (x,y)==(layer.x,layer.y):return
        layer.x=x;layer.y=y
        self.body_layer_controls["x"].blockSignals(True);self.body_layer_controls["y"].blockSignals(True)
        self.body_layer_controls["x"].setValue(x);self.body_layer_controls["y"].setValue(y)
        self.body_layer_controls["x"].blockSignals(False);self.body_layer_controls["y"].blockSignals(False)
        self._body_changed()

    def add_body_layer(self)->None:
        layer=ShapeLayer(name=self.t("새 신체 이미지"),shape="image",x=0,y=-110,width=180,height=180,opacity=70)
        self.profile.motion_assist.body.layers.append(layer);self.rebuild_body_layer_list(layer.layer_id);self._body_changed()

    def duplicate_body_layer(self)->None:
        source=self.current_body_layer()
        if not source:return
        layer=copy.deepcopy(source);layer.layer_id=uuid4().hex;layer.name=f"{source.name} {self.t('복사본')}";layer.x+=20;self.profile.motion_assist.body.layers.append(layer);self.rebuild_body_layer_list(layer.layer_id);self._body_changed()

    def delete_body_layer(self)->None:
        layer=self.current_body_layer()
        if not layer:return
        self.profile.motion_assist.body.layers.remove(layer);self.rebuild_body_layer_list();self._body_changed()

    def move_body_layer(self,direction)->None:
        row=self.body_layer_list.currentRow();target=row+direction;layers=self.profile.motion_assist.body.layers
        if row<0 or target<0 or target>=len(layers):return
        layers[row],layers[target]=layers[target],layers[row];self.rebuild_body_layer_list(layers[target].layer_id);self._body_changed()

    def body_layer_visibility_changed(self,item)->None:
        layer=next((layer for layer in self.profile.motion_assist.body.layers if layer.layer_id==item.data(Qt.UserRole)),None)
        if layer:layer.visible=item.checkState()==Qt.Checked;self._body_changed()

    def apply_body_preset(self)->None:
        name=self.body_preset.currentData() or "nose";body=self.profile.motion_assist.body;body.preset=name;body.layers=body_reference_preset(name);self.rebuild_body_layer_list();self._body_changed()

    def choose_body_png(self)->None:
        layer=self.current_body_layer()
        if not layer:return
        path,_=QFileDialog.getOpenFileName(self,self.t("투명 PNG 선택"),"",self.t("PNG 이미지 (*.png)"))
        if not path:return
        pixmap=QPixmap(path)
        if pixmap.isNull():QMessageBox.warning(self,self.t("이미지 오류"),self.t("선택한 파일은 읽을 수 있는 PNG 이미지가 아닙니다."));return
        managed=self._keep_image(path)
        if not managed:return
        layer.shape="image";layer.image_path=managed;layer.width=max(1,pixmap.width());layer.height=max(1,pixmap.height());self.rebuild_body_layer_list(layer.layer_id);self.select_body_layer(self.body_layer_list.currentRow());self._body_changed()

    def clear_body_png(self)->None:
        layer=self.current_body_layer()
        if not layer:return
        layer.image_path=""
        if layer.shape=="image":layer.shape="nose"
        self.rebuild_body_layer_list(layer.layer_id);self._body_changed()

    def _set_group(self,group,field,value)->None:
        if self._loading:return
        setattr(getattr(self.profile,group),field,value);self._save_settings();self.controller.refresh_visuals()
        if group=="pointer":self.pointer_preview.set_model(self.profile.pointer,self.current_pointer_layer_id())
        self._refresh_nav_status()

    def _set_crosshair(self,field,value)->None:
        if self._loading:return
        setattr(self.profile.crosshair,field,value);self._crosshair_changed()

    def _crosshair_changed(self)->None:
        self._save_settings();self.controller.refresh_visuals();self.reticle_preview.set_model(self.profile.crosshair,self.current_layer_id())
        self._refresh_nav_status()

    def _set_app(self,field,value)->None:
        if self._loading:return
        setattr(self.settings,field,value);self._save_settings()
        if field=="keep_overlay_on_top":self.controller.refresh_topmost()

    def current_layer_id(self):
        item=self.layer_list.currentItem();return item.data(Qt.UserRole) if item else None

    def current_layer(self):
        layer_id=self.current_layer_id();return next((layer for layer in self.profile.crosshair.layers if layer.layer_id==layer_id),None)

    def rebuild_layer_list(self,selected_id=None)->None:
        self.layer_list.blockSignals(True);self.layer_list.clear();selected_row=0
        for row,layer in enumerate(self.profile.crosshair.layers):
            item=QListWidgetItem(f"{self.shape_label(layer.shape)}   {layer.name}");item.setData(Qt.UserRole,layer.layer_id);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if layer.visible else Qt.Unchecked);self.layer_list.addItem(item)
            if layer.layer_id==selected_id:selected_row=row
        self.layer_list.blockSignals(False)
        if self.layer_list.count():self.layer_list.setCurrentRow(selected_row)
        else:self.select_layer(-1)

    def select_layer(self,_row)->None:
        layer=self.current_layer();self._loading=True;enabled=layer is not None
        for widget in [self.layer_name,self.layer_shape,*self.layer_controls.values(),self.layer_cap,self.layer_cap_angle,self.layer_stroke,self.layer_outline,self.layer_fill,self.mirror_h,self.mirror_v,self.pattern_enabled,self.pattern_angle,self.pattern_copies,self.layer_key_enabled,self.layer_key_color,self.layer_key_tolerance,self.layer_key_softness]:widget.setEnabled(enabled)
        if layer:
            self.layer_name.setText(layer.name);self.layer_shape.setCurrentIndex(max(0,self.layer_shape.findData(layer.shape)))
            for field,widget in self.layer_controls.items():widget.setValue(getattr(layer,field))
            self.layer_cap.setCurrentIndex(max(0,self.layer_cap.findData(layer.cap_style)))
            self.layer_cap_angle.setValue(layer.cap_angle)
            for button,value in [(self.layer_stroke,layer.stroke_color),(self.layer_outline,layer.outline_color),(self.layer_fill,layer.fill_color)]:button.color=value;button.refresh()
            self.mirror_h.setChecked(layer.mirror_horizontal);self.mirror_v.setChecked(layer.mirror_vertical);self.pattern_enabled.setChecked(layer.circular_pattern);self.pattern_angle.setValue(layer.pattern_angle);self.pattern_copies.setValue(layer.pattern_copies)
            self.layer_key_enabled.setChecked(layer.color_key_enabled);self.layer_key_color.color=layer.color_key;self.layer_key_color.refresh();self.layer_key_tolerance.setValue(layer.color_key_tolerance);self.layer_key_softness.setValue(layer.color_key_softness)
        self._loading=False;self._update_layer_key_controls();self._update_layer_shape_controls();self.reticle_preview.set_model(self.profile.crosshair,self.current_layer_id())

    def _update_layer_key_controls(self)->None:
        layer=self.current_layer();image_mode=bool(layer and layer.shape=="image" and layer.image_path);self.layer_key_enabled.setEnabled(image_mode);details=image_mode and self.layer_key_enabled.isChecked()
        for widget in (self.layer_key_color,self.layer_key_tolerance,self.layer_key_softness):widget.setEnabled(details)

    def _update_layer_shape_controls(self)->None:
        layer=self.current_layer();enabled=layer is not None;arc_mode=bool(layer and layer.shape=="arc");line_mode=bool(layer and layer.shape=="line");pattern=bool(layer and layer.circular_pattern)
        self.layer_controls["width"].setEnabled(enabled and not arc_mode);self.layer_controls["height"].setEnabled(enabled and not arc_mode and not line_mode)
        label=self.layer_properties_form.labelForField(self.layer_controls["width"])
        if label:label.setText(self.t("선 길이") if line_mode else self.t("너비/크기"))
        for field in ("arc_radius","arc_start_angle","arc_span_angle"):self.layer_controls[field].setEnabled(arc_mode)
        self.layer_cap_angle.setEnabled(enabled and line_mode and layer.cap_style=="triangle")
        self.pattern_angle.setEnabled(enabled and pattern);self.pattern_copies.setEnabled(enabled and pattern)
        self._property_visibility()

    def _set_layer(self,field,value)->None:
        if self._loading:return
        layer=self.current_layer()
        if not layer:return
        setattr(layer,field,value)
        if field=="circular_pattern":layer.rotation_symmetry=False
        if field in {"name","shape"}:self.rebuild_layer_list(layer.layer_id)
        self._update_layer_key_controls();self._update_layer_shape_controls()
        self._crosshair_changed()

    def current_pointer_layer_id(self):
        item=self.pointer_layer_list.currentItem();return item.data(Qt.UserRole) if item else None

    def current_pointer_layer(self):
        layer_id=self.current_pointer_layer_id();return next((layer for layer in self.profile.pointer.layers if layer.layer_id==layer_id),None)

    def rebuild_pointer_layer_list(self,selected_id=None)->None:
        self.pointer_layer_list.blockSignals(True);self.pointer_layer_list.clear();selected_row=0
        for row,layer in enumerate(self.profile.pointer.layers):
            item=QListWidgetItem(f"{self.shape_label(layer.shape)}   {layer.name}");item.setData(Qt.UserRole,layer.layer_id);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if layer.visible else Qt.Unchecked);self.pointer_layer_list.addItem(item)
            if layer.layer_id==selected_id:selected_row=row
        self.pointer_layer_list.blockSignals(False)
        if self.pointer_layer_list.count():self.pointer_layer_list.setCurrentRow(selected_row)
        else:self.select_pointer_layer(-1)

    def select_pointer_layer(self,_row)->None:
        layer=self.current_pointer_layer();self._loading=True;enabled=layer is not None
        widgets=[self.pointer_layer_name,self.pointer_layer_shape,*self.pointer_layer_controls.values(),self.pointer_layer_cap,self.pointer_layer_cap_angle,self.pointer_layer_stroke,self.pointer_layer_outline,self.pointer_layer_fill,self.pointer_mirror_h,self.pointer_mirror_v,self.pointer_pattern_enabled,self.pointer_pattern_angle,self.pointer_pattern_copies,self.pointer_layer_key_enabled,self.pointer_layer_key_color,self.pointer_layer_key_tolerance,self.pointer_layer_key_softness]
        for widget in widgets:widget.setEnabled(enabled)
        if layer:
            self.pointer_layer_name.setText(layer.name);self.pointer_layer_shape.setCurrentIndex(max(0,self.pointer_layer_shape.findData(layer.shape)))
            for field,widget in self.pointer_layer_controls.items():widget.setValue(getattr(layer,field))
            self.pointer_layer_cap.setCurrentIndex(max(0,self.pointer_layer_cap.findData(layer.cap_style)))
            self.pointer_layer_cap_angle.setValue(layer.cap_angle)
            for button,value in [(self.pointer_layer_stroke,layer.stroke_color),(self.pointer_layer_outline,layer.outline_color),(self.pointer_layer_fill,layer.fill_color),(self.pointer_layer_key_color,layer.color_key)]:button.color=value;button.refresh()
            self.pointer_mirror_h.setChecked(layer.mirror_horizontal);self.pointer_mirror_v.setChecked(layer.mirror_vertical);self.pointer_pattern_enabled.setChecked(layer.circular_pattern);self.pointer_pattern_angle.setValue(layer.pattern_angle);self.pointer_pattern_copies.setValue(layer.pattern_copies);self.pointer_layer_key_enabled.setChecked(layer.color_key_enabled);self.pointer_layer_key_tolerance.setValue(layer.color_key_tolerance);self.pointer_layer_key_softness.setValue(layer.color_key_softness)
        self._loading=False;self._update_pointer_layer_controls();self.pointer_preview.set_model(self.profile.pointer,self.current_pointer_layer_id())

    def _update_pointer_layer_controls(self)->None:
        layer=self.current_pointer_layer();enabled=layer is not None;arc_mode=bool(layer and layer.shape=="arc");line_mode=bool(layer and layer.shape=="line");pattern=bool(layer and layer.circular_pattern);image_mode=bool(layer and layer.shape=="image" and layer.image_path)
        self.pointer_layer_controls["width"].setEnabled(enabled and not arc_mode);self.pointer_layer_controls["height"].setEnabled(enabled and not arc_mode and not line_mode)
        label=self.pointer_properties_form.labelForField(self.pointer_layer_controls["width"])
        if label:label.setText(self.t("선 길이") if line_mode else self.t("너비/크기"))
        for field in ("arc_radius","arc_start_angle","arc_span_angle"):self.pointer_layer_controls[field].setEnabled(arc_mode)
        self.pointer_layer_cap_angle.setEnabled(enabled and line_mode and layer.cap_style=="triangle")
        self.pointer_pattern_angle.setEnabled(enabled and pattern);self.pointer_pattern_copies.setEnabled(enabled and pattern);self.pointer_layer_key_enabled.setEnabled(image_mode)
        for widget in (self.pointer_layer_key_color,self.pointer_layer_key_tolerance,self.pointer_layer_key_softness):widget.setEnabled(image_mode and self.pointer_layer_key_enabled.isChecked())
        self._property_visibility(True)

    def _set_pointer_layer(self,field,value)->None:
        if self._loading:return
        layer=self.current_pointer_layer()
        if not layer:return
        setattr(layer,field,value)
        if field=="circular_pattern":layer.rotation_symmetry=False
        if field in {"name","shape"}:self.rebuild_pointer_layer_list(layer.layer_id)
        self._update_pointer_layer_controls();self._pointer_layers_changed()

    def _pointer_layers_changed(self)->None:
        self._save_settings();self.controller.refresh_visuals();self.pointer_preview.set_model(self.profile.pointer,self.current_pointer_layer_id())

    def add_pointer_layer(self)->None:
        labels=[self.shape_label(key) for key in SHAPE_LABELS];label,ok=QInputDialog.getItem(self,self.t("도형 추가"),self.t("도형 종류"),labels,0,False)
        if not ok:return
        shape=next(key for key in SHAPE_LABELS if self.shape_label(key)==label);layer=ShapeLayer(name=label,shape=shape,stroke_color="#ffff00",fill_color="#ffff00")
        if shape=="line":layer.height=1
        self.profile.pointer.layers.append(layer);self.rebuild_pointer_layer_list(layer.layer_id);self._pointer_layers_changed()

    def duplicate_pointer_layer(self)->None:
        source=self.current_pointer_layer()
        if not source:return
        layer=copy.deepcopy(source);layer.layer_id=uuid4().hex;layer.name=f"{source.name} {self.t('복사본')}";layer.x+=8;layer.y+=8;self.profile.pointer.layers.append(layer);self.rebuild_pointer_layer_list(layer.layer_id);self._pointer_layers_changed()

    def delete_pointer_layer(self)->None:
        layer=self.current_pointer_layer()
        if layer:self.profile.pointer.layers.remove(layer);self.rebuild_pointer_layer_list();self._pointer_layers_changed()

    def move_pointer_layer(self,direction)->None:
        row=self.pointer_layer_list.currentRow();target=row+direction
        if row<0 or target<0 or target>=len(self.profile.pointer.layers):return
        layers=self.profile.pointer.layers;layers[row],layers[target]=layers[target],layers[row];selected=layers[target].layer_id;self.rebuild_pointer_layer_list(selected);self._pointer_layers_changed()

    def pointer_layer_visibility_changed(self,item)->None:
        layer=next((layer for layer in self.profile.pointer.layers if layer.layer_id==item.data(Qt.UserRole)),None)
        if layer:layer.visible=item.checkState()==Qt.Checked;self._pointer_layers_changed()

    def preview_pointer_layer_moved(self,x,y)->None:
        layer=self.current_pointer_layer()
        if not layer:return
        self._loading=True;layer.x=x;layer.y=y;self.pointer_layer_controls["x"].setValue(x);self.pointer_layer_controls["y"].setValue(y);self._loading=False;self._pointer_layers_changed()

    def choose_pointer_layer_png(self)->None:
        layer=self.current_pointer_layer()
        if not layer:return
        path,_=QFileDialog.getOpenFileName(self,self.t("도형 PNG 선택"),"",self.t("PNG 이미지 (*.png)"))
        if not path:return
        if QPixmap(path).isNull():QMessageBox.warning(self,self.t("이미지 오류"),self.t("읽을 수 있는 PNG 이미지가 아닙니다."));return
        managed=self._keep_image(path)
        if not managed:return
        layer.shape="image";layer.image_path=managed;self.rebuild_pointer_layer_list(layer.layer_id);self._pointer_layers_changed()

    def clear_pointer_layer_png(self)->None:
        layer=self.current_pointer_layer()
        if not layer:return
        layer.image_path=""
        if layer.shape=="image":layer.shape="line";layer.name=self.t("선")
        self.rebuild_pointer_layer_list(layer.layer_id);self._pointer_layers_changed()

    def add_layer(self)->None:
        labels=[self.shape_label(key) for key in SHAPE_LABELS];label,ok=QInputDialog.getItem(self,self.t("도형 추가"),self.t("도형 종류"),labels,0,False)
        if not ok:return
        shape=next(key for key in SHAPE_LABELS if self.shape_label(key)==label);layer=ShapeLayer(name=label,shape=shape)
        if shape=="line":layer.height=1
        self.profile.crosshair.layers.append(layer);self.rebuild_layer_list(layer.layer_id);self._crosshair_changed()

    def duplicate_layer(self)->None:
        source=self.current_layer()
        if not source:return
        layer=copy.deepcopy(source);layer.layer_id=uuid4().hex;layer.name=f"{source.name} {self.t('복사본')}";layer.x+=8;layer.y+=8;self.profile.crosshair.layers.append(layer);self.rebuild_layer_list(layer.layer_id);self._crosshair_changed()

    def delete_layer(self)->None:
        layer=self.current_layer()
        if layer:self.profile.crosshair.layers.remove(layer);self.rebuild_layer_list();self._crosshair_changed()

    def move_layer(self,direction)->None:
        row=self.layer_list.currentRow();target=row+direction
        if row<0 or target<0 or target>=len(self.profile.crosshair.layers):return
        layers=self.profile.crosshair.layers;layers[row],layers[target]=layers[target],layers[row];selected=layers[target].layer_id;self.rebuild_layer_list(selected);self._crosshair_changed()

    def layer_visibility_changed(self,item)->None:
        layer=next((layer for layer in self.profile.crosshair.layers if layer.layer_id==item.data(Qt.UserRole)),None)
        if layer:layer.visible=item.checkState()==Qt.Checked;self._crosshair_changed()

    def preview_layer_moved(self,x,y)->None:
        layer=self.current_layer()
        if not layer:return
        self._loading=True;layer.x=x;layer.y=y;self.layer_controls["x"].setValue(x);self.layer_controls["y"].setValue(y);self._loading=False;self._crosshair_changed()

    def choose_layer_png(self)->None:
        layer=self.current_layer()
        if not layer:return
        path,_=QFileDialog.getOpenFileName(self,self.t("도형 PNG 선택"),"",self.t("PNG 이미지 (*.png)"))
        if not path:return
        if QPixmap(path).isNull():QMessageBox.warning(self,self.t("이미지 오류"),self.t("읽을 수 있는 PNG 이미지가 아닙니다."));return
        managed=self._keep_image(path)
        if not managed:return
        layer.shape="image";layer.image_path=managed;self.rebuild_layer_list(layer.layer_id);self._crosshair_changed()

    def clear_layer_png(self)->None:
        layer=self.current_layer()
        if not layer:return
        layer.image_path=""
        if layer.shape=="image":layer.shape="line";layer.name=self.t("선")
        self.rebuild_layer_list(layer.layer_id);self._crosshair_changed()

    def export_reticle(self)->None:
        path,_=QFileDialog.getSaveFileName(self,self.t("도형 프리셋 저장"),"reticle.ccshape.json",self.t("CenterCross 도형 (*.ccshape.json);;JSON (*.json)"))
        if path:
            try:self.store.export_reticle(self.profile.crosshair,Path(path))
            except (OSError,ValueError) as exc:QMessageBox.warning(self,self.t("저장 실패"),str(exc))

    def import_reticle(self)->None:
        path,_=QFileDialog.getOpenFileName(self,self.t("도형 프리셋 불러오기"),"",self.t("CenterCross 도형 (*.ccshape.json);;JSON (*.json)"))
        if not path:return
        try:self.profile.crosshair=self.store.import_reticle(Path(path),self.store.directory/"images")
        except (OSError,ValueError) as exc:QMessageBox.warning(self,self.t("불러오기 실패"),f"{self.t('올바른 도형 프리셋이 아닙니다.')}\n{exc}");return
        self._save_settings();self.load_profile();self.controller.refresh_visuals()

    def refresh_windows(self)->None:
        self.windows=list_top_level_windows();self.target_combo.blockSignals(True);self.target_combo.clear();self.target_combo.addItem(self.style().standardIcon(QStyle.SP_ArrowRight),self.t("현재 활성화된 프로그램"),("active",""));self.target_combo.addItem(self.style().standardIcon(QStyle.SP_DesktopIcon),self.t("모니터 중앙"),("monitor",""));provider=QFileIconProvider();selected=0;apps={}
        for item in self.windows:
            if item.executable:apps.setdefault(item.executable.casefold(),item)
        for item in sorted(apps.values(),key=lambda value:value.label.casefold()):
            icon=provider.icon(QFileInfo(item.executable_path)) if item.executable_path else self.style().standardIcon(QStyle.SP_ComputerIcon);self.target_combo.addItem(icon,item.label,("application",item.executable))
        for index in range(self.target_combo.count()):
            data=self.target_combo.itemData(index)
            if data and data[0]==self.profile.target.mode and (data[0]!="application" or data[1].casefold()==self.profile.target.executable.casefold()):selected=index;break
        if self.profile.target.mode=="application" and selected==0 and self.profile.target.executable:
            self.target_combo.addItem(self.profile.target.executable.removesuffix(".exe"),("application",self.profile.target.executable));selected=self.target_combo.count()-1
        self.target_combo.setCurrentIndex(selected);self.target_combo.blockSignals(False)

    def target_changed(self,index)->None:
        if self._loading or index<0:return
        data=self.target_combo.itemData(index)
        if not data:return
        self.profile.target.mode, self.profile.target.executable = data
        self._save_settings()
        self.controller.apply_profile()
        self._update_active_profile()
        self._refresh_profile_list()

    def change_profile(self, index) -> None:
        if index < 0 or index == self.settings.selected_profile:
            return
        self.settings.selected_profile = index
        self._save_settings()
        self.load_profile()
        self.controller.apply_profile()

    def _external_profile_change(self, index) -> None:
        self.profile_list.setCurrentRow(index)
        self.load_profile()

    def _target_summary(self)->str:
        return self._target_summary_for(self.profile)

    def _target_summary_for(self,profile:Profile)->str:
        target=profile.target
        if target.mode=="active":return self.t("현재 활성화된 프로그램")
        if target.mode=="monitor":return self.t("모니터 중앙")
        return target.executable.removesuffix(".exe") or self.t("특정 프로그램")

    def _new_profile_item(self, profile: Profile) -> QListWidgetItem:
        item = QListWidgetItem(self._profile_list_label(profile))
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if profile.enabled else Qt.Unchecked)
        item.setSizeHint(QSize(0, 58))
        return item

    def _profile_list_label(self, profile: Profile) -> str:
        return f"{profile.name}\n{self._target_summary_for(profile)}"

    def _refresh_profile_list(self) -> None:
        if not hasattr(self, "profile_list"):
            return
        self.profile_list.blockSignals(True)
        for index, profile in enumerate(self.settings.profiles):
            item = self.profile_list.item(index)
            if item is not None:
                item.setText(self._profile_list_label(profile))
                item.setCheckState(Qt.Checked if profile.enabled else Qt.Unchecked)
        self.profile_list.setCurrentRow(self.settings.selected_profile)
        self.profile_list.blockSignals(False)
        self._refresh_profile_details()

    def _profile_enabled_changed(self, item: QListWidgetItem) -> None:
        index = self.profile_list.row(item)
        if index < 0:
            return
        profile = self.settings.profiles[index]
        profile.enabled = item.checkState() == Qt.Checked
        self._save_timer.start()
        self.controller.apply_profile()
        self._update_active_profile()

    def _refresh_visible_overview(self) -> None:
        if self.navigation.currentRow() == 8 and self.isVisible():
            self._refresh_profile_details()

    def _current_display_status(self) -> str:
        profile = self.profile
        if not profile.enabled:
            return self.t("프로필 꺼짐")
        if not self.settings.overlays_enabled:
            return self.t("전체 꺼짐")
        overlays = (
            getattr(self.controller, "crosshair", None),
            getattr(self.controller, "pointer", None),
            getattr(self.controller, "motion", None),
            getattr(self.controller, "effect", None),
        )
        if any(overlay is not None and overlay.isVisible() for overlay in overlays):
            return self.t("표시 중")
        if profile.find_effect.enabled and not (
            profile.crosshair.enabled or profile.pointer.enabled
            or profile.motion_assist.vignette.enabled or profile.motion_assist.body.enabled
            or profile.motion_assist.guides.enabled or profile.motion_assist.grid.enabled
        ):
            return self.t("찾기 단축키 대기")
        return self.t("표시 대기")

    def _update_active_profile(self)->None:
        if not hasattr(self,"active_profile_label"):return
        text = f"{self.t('현재 선택')}: {self.profile.name}  ·  {self._target_summary()}"
        if not self.profile.enabled:
            text += f"  ·  {self.t('프로필 꺼짐')}"
        self.active_profile_label.setText(text)
        self.setWindowTitle(f"CenterCross — {self.profile.name}")
        if hasattr(self,"tray"):self.tray.setToolTip(text)
        self._refresh_profile_details()

    def _refresh_profile_details(self) -> None:
        if not hasattr(self, "profile_features"):
            return
        profile = self.profile
        motion = profile.motion_assist
        self.profile_count.setText(f"{len(self.settings.profiles)} {self.t('개 프로필')}")
        self.profile_status.setText(self._current_display_status())
        self.profile_status.setStyleSheet(
            "color: #0b5bd3; font-weight: 700" if profile.enabled else "color: #64748b"
        )
        features = (
            ("화면 기준점", profile.crosshair.enabled),
            ("마우스 커서 추적", profile.pointer.enabled),
            ("가상 신체 표시", motion.body.enabled),
            ("가장자리 어둡게", motion.vignette.enabled),
            ("수평선 · 수직선", motion.guides.enabled),
            ("격자선", motion.grid.enabled),
            ("마우스 찾기", profile.find_effect.enabled),
        )
        rows = []
        for label, enabled in features:
            color = "#0b5bd3" if enabled else "#94a3b8"
            state = self.t("켜짐") if enabled else self.t("꺼짐")
            rows.append(
                f'<tr><td style="padding: 3px 14px 3px 0">{self.t(label)}</td>'
                f'<td style="color: {color}; font-weight: 600">● {state}</td></tr>'
            )
        self.profile_features.setText("<table>" + "".join(rows) + "</table>")
        if profile.target.mode == "application":
            hint = self.t("선택한 프로그램이 활성화될 때 오버레이를 표시합니다.")
        elif profile.target.mode == "monitor":
            hint = self.t("모니터 중앙에 오버레이를 표시합니다.")
        else:
            hint = self.t("현재 활성화된 프로그램을 기준으로 표시합니다.")
        self.profile_target_hint.setText(hint)

    def _refresh_nav_status(self)->None:
        if not hasattr(self,"navigation") or self.navigation.count()<6:return
        motion=self.profile.motion_assist
        states=[
            (0,"화면 기준점",self.profile.crosshair.enabled),
            (1,"마우스 커서 추적",self.profile.pointer.enabled),
        ]
        for index,label,enabled in states:
            self.navigation.item(index).setText(self.t(label));self.navigation.item(index).setIcon(self._status_icon(enabled))
        for index,label,enabled in ((2,"가상 신체 표시",motion.body.enabled),(3,"가장자리 어둡게",motion.vignette.enabled),(4,"수평선 · 수직선",motion.guides.enabled),(5,"격자선",motion.grid.enabled),(6,"마우스 찾기",self.profile.find_effect.enabled)):
            self.navigation.item(index).setText(self.t(label));self.navigation.item(index).setIcon(self._status_icon(enabled))
        self._refresh_profile_details()

    @staticmethod
    def _status_icon(enabled:bool)->QIcon:
        pixmap=QPixmap(16,16);pixmap.fill(Qt.transparent);painter=QPainter(pixmap);painter.setRenderHint(QPainter.Antialiasing,True)
        if enabled:painter.setPen(QPen(QColor("#ffffff"),1));painter.setBrush(QColor("#1677ff"))
        else:painter.setPen(QPen(QColor("#94a3b8"),1.5));painter.setBrush(QColor("#f4f7fb"))
        painter.drawEllipse(3,3,10,10);painter.end();return QIcon(pixmap)

    def load_profile(self)->None:
        self._histories.setdefault(id(self.profile),EditHistory(self.profile))
        self._update_history_actions()
        self._loading=True
        p=self.profile
        self.profile_name_edit.setText(p.name)
        self.cross_enabled.setChecked(p.crosshair.enabled)
        self.cross_x.setValue(p.crosshair.offset_x)
        self.cross_y.setValue(p.crosshair.offset_y)
        self.antialias.setChecked(p.crosshair.antialiasing)
        self.pointer_enabled.setChecked(p.pointer.enabled)
        self.pointer_x.setValue(p.pointer.offset_x)
        self.pointer_y.setValue(p.pointer.offset_y)
        self.pointer_antialias.setChecked(p.pointer.antialiasing)
        self.pointer_rate.setCurrentIndex(max(0,self.pointer_rate.findData(p.pointer.update_rate)))
        m=p.motion_assist
        v=m.vignette
        self.vignette_shape.setCurrentIndex(max(0,self.vignette_shape.findData(v.shape)))
        self.vignette_opacity.setValue(v.opacity)
        self.vignette_width.setValue(v.center_width)
        self.vignette_height.setValue(v.center_height)
        self.vignette_softness.setValue(v.softness)
        self.vignette_x.setValue(v.offset_x)
        self.vignette_y.setValue(v.offset_y)
        self.vignette_color.color=v.color
        self.vignette_color.refresh()
        body=m.body
        self.body_preset.setCurrentIndex(max(0,self.body_preset.findData(body.preset)))
        g=m.guides
        self.guide_horizontal.setChecked(g.horizontal)
        self.guide_vertical.setChecked(g.vertical)
        self.guide_horizontal_length.setValue(g.horizontal_length or 730)
        self.guide_vertical_length.setValue(g.vertical_length or 410)
        self.guide_thickness.setValue(g.thickness)
        self.guide_opacity.setValue(g.opacity)
        self.guide_x.setValue(g.offset_x)
        self.guide_y.setValue(g.offset_y)
        self.guide_center_cap.setCurrentIndex(max(0,self.guide_center_cap.findData(g.center_cap)))
        self.guide_cap_angle.setValue(g.center_cap_angle)
        self.guide_dashed.setChecked(g.dashed)
        self.guide_dash_length.setValue(g.dash_length)
        self.guide_dash_gap.setValue(g.dash_gap)
        self.guide_color.color=g.color
        self.guide_color.refresh()
        grid=m.grid
        self.grid_columns.setValue(grid.columns)
        self.grid_rows.setValue(grid.rows)
        self.grid_thickness.setValue(grid.thickness)
        self.grid_opacity.setValue(grid.opacity)
        self.grid_margin.setValue(grid.margin)
        self.grid_horizontal_dashed.setChecked(grid.horizontal_dashed)
        self.grid_horizontal_dash_length.setValue(grid.horizontal_dash_length)
        self.grid_horizontal_dash_gap.setValue(grid.horizontal_dash_gap)
        self.grid_horizontal_dash_offset.setValue(grid.horizontal_dash_offset)
        self.grid_vertical_dashed.setChecked(grid.vertical_dashed)
        self.grid_vertical_dash_length.setValue(grid.vertical_dash_length)
        self.grid_vertical_dash_gap.setValue(grid.vertical_dash_gap)
        self.grid_vertical_dash_offset.setValue(grid.vertical_dash_offset)
        self.grid_center.setChecked(grid.emphasize_center)
        self.grid_color.color=grid.color
        self.grid_color.refresh()
        self.effect_enabled.setChecked(p.find_effect.enabled)
        self.effect_color.color=p.find_effect.color
        self.effect_color.refresh()
        self.effect_type.setCurrentIndex(max(0,self.effect_type.findData(p.find_effect.effect)))
        self.effect_opacity.setValue(p.find_effect.opacity)
        self.effect_size.setValue(p.find_effect.max_size)
        self.effect_thick.setValue(p.find_effect.thickness)
        self.effect_duration.setValue(p.find_effect.duration_ms)
        self.effect_repeats.setValue(p.find_effect.repeats)
        self.effect_speed.setValue(p.find_effect.speed)
        for field,(mods,key) in self.hotkey_widgets.items():
            sequence=getattr(p.hotkeys,field)
            parts=sequence.rsplit("+",1)
            modifier=parts[0] if len(parts)==2 else ""
            key_value=parts[-1]
            mods.setCurrentIndex(max(0,mods.findData(modifier)))
            key_index=key.findData(key_value)
            key.setCurrentIndex(key_index if key_index>=0 else max(0,key.findData("F12")))
        self.master_enabled.setChecked(self.settings.overlays_enabled)
        self.keep_topmost.setChecked(self.settings.keep_overlay_on_top)
        self.startup.setChecked(self.settings.start_with_windows)
        self.to_tray.setChecked(self.settings.minimize_to_tray)
        self.motion_preview.set_model(m)
        self._loading=False
        self.rebuild_layer_list(self.current_layer_id())
        self.rebuild_pointer_layer_list(self.current_pointer_layer_id())
        self.rebuild_body_layer_list()
        self._navigation_changed(self.navigation.currentRow())
        self._update_motion_enabled_controls()
        self.refresh_windows()
        self._set_hotkey_status(self.controller.register_hotkeys())
        self._update_active_profile()
        self._refresh_profile_list()
        self._refresh_nav_status()

    def add_profile(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile.name = f"{self.t('새 프로필')} {len(self.settings.profiles) + 1}"
        profile.enabled = True
        profile.target.mode = "monitor"
        profile.target.executable = ""
        self.settings.profiles.append(profile)
        self.profile_list.addItem(self._new_profile_item(profile))
        self.profile_list.setCurrentRow(len(self.settings.profiles) - 1)

    def duplicate_profile(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile.name = f"{profile.name} {self.t('복사본')}"
        self.settings.profiles.append(profile)
        self.profile_list.addItem(self._new_profile_item(profile))
        self.profile_list.setCurrentRow(len(self.settings.profiles) - 1)

    def rename_profile(self)->None:
        name=self.profile_name_edit.text().strip()
        if not name:self.profile_name_edit.setText(self.profile.name);return
        self.profile.name = name
        self._refresh_profile_list()
        self._save_settings()
        self._update_active_profile()

    def delete_profile(self)->None:
        if len(self.settings.profiles)==1:QMessageBox.information(self,self.t("삭제 불가"),self.t("최소 한 개의 프로필이 필요합니다."));return
        index = self.settings.selected_profile
        self.profile_list.blockSignals(True)
        self.profile_list.takeItem(index)
        self.profile_list.blockSignals(False)
        self.settings.profiles.pop(index)
        self.settings.selected_profile = 0
        self.profile_list.setCurrentRow(0)
        self._save_settings()
        self.load_profile()
        self.controller.apply_profile()

    def import_profile(self)->None:
        path,_=QFileDialog.getOpenFileName(self,self.t("프로필 가져오기"),"","JSON (*.json)")
        if not path:return
        try:profile=self.store.import_profile(Path(path),self.store.directory/"images")
        except (OSError,ValueError) as exc:QMessageBox.warning(self,self.t("불러오기 실패"),f"{self.t('올바른 프로필 파일이 아닙니다.')}\n{exc}");return
        self.settings.profiles.append(profile)
        self.profile_list.addItem(self._new_profile_item(profile))
        self.profile_list.setCurrentRow(len(self.settings.profiles) - 1)

    def export_profile(self)->None:
        path,_=QFileDialog.getSaveFileName(self,self.t("프로필 내보내기"),f"{self.profile.name}.json","JSON (*.json)")
        if path:
            try:self.store.export_profile(self.profile,Path(path))
            except (OSError,ValueError) as exc:QMessageBox.warning(self,self.t("저장 실패"),str(exc))

    def reset_crosshair(self)->None:
        self.profile.crosshair=CrosshairSettings();self._save_settings();self.load_profile();self.controller.refresh_visuals()

    def reset_pointer(self)->None:
        enabled=self.profile.pointer.enabled;active_only=self.profile.pointer.active_only;self.profile.pointer=PointerSettings(enabled=enabled,active_only=active_only);self._save_settings();self.load_profile();self.controller.refresh_visuals()

    def export_pointer_preset(self)->None:
        path,_=QFileDialog.getSaveFileName(self,self.t("마우스 커서 추적 프리셋 저장"),"pointer.ccpointer.json",self.t("CenterCross 커서 도형 (*.ccpointer.json);;JSON (*.json)"))
        if path:
            try:self.store.export_pointer_preset(self.profile.pointer,Path(path))
            except (OSError,ValueError) as exc:QMessageBox.warning(self,self.t("저장 실패"),str(exc))

    def import_pointer_preset(self)->None:
        path,_=QFileDialog.getOpenFileName(self,self.t("마우스 커서 추적 프리셋 불러오기"),"",self.t("CenterCross 커서 도형 (*.ccpointer.json);;JSON (*.json)"))
        if not path:return
        try:self.profile.pointer=self.store.import_pointer_preset(Path(path),self.store.directory/"images")
        except (OSError,ValueError) as exc:QMessageBox.warning(self,self.t("불러오기 실패"),f"{self.t('올바른 마우스 커서 추적 프리셋이 아닙니다.')}\n{exc}");return
        self._save_settings();self.load_profile();self.controller.refresh_visuals()

    def update_hotkeys(self)->None:
        if self._loading:return
        for field,(mods,key) in self.hotkey_widgets.items():
            modifier=mods.currentData() or "";action=key.currentData() or key.currentText();setattr(self.profile.hotkeys,field,f"{modifier}+{action}" if modifier else str(action))
        self._save_settings();self._set_hotkey_status(self.controller.register_hotkeys())

    def _set_hotkey_status(self,errors=None)->None:
        if errors is None:errors=getattr(self.controller,"last_hotkey_errors",[])
        if errors:self.hotkey_status.setText("⚠ "+"  ·  ".join(errors));self.hotkey_status.setStyleSheet("color:#b42318")
        else:self.hotkey_status.setText(f"● {self.t('단축키 2개 등록됨')}" + ("" if self.settings.overlays_enabled else f"  ·  {self.t('전체 오버레이 꺼짐')}"));self.hotkey_status.setStyleSheet("color:#16803c;font-weight:600")

    def _sync_runtime_state(self)->None:
        for widget,value in [(self.cross_enabled,self.profile.crosshair.enabled),(self.pointer_enabled,self.profile.pointer.enabled),(self.master_enabled,self.settings.overlays_enabled)]:
            widget.blockSignals(True);widget.setChecked(value);widget.blockSignals(False)
        self.tray_toggle.setText(self.t("전체 비활성화") if self.settings.overlays_enabled else self.t("전체 활성화"));self._set_hotkey_status();self._update_active_profile();self._refresh_nav_status()

    def master_toggled(self,value)->None:
        if self._loading:return
        self.settings.overlays_enabled=value;self._save_settings();self.controller._update(force_target=True);self.tray_toggle.setText(self.t("전체 비활성화") if value else self.t("전체 활성화"));self._set_hotkey_status();self._refresh_nav_status()

    def change_language(self,index)->None:
        language=self.language_combo.itemData(index)
        if self._loading or language not in {"ko","en"} or language==self.settings.language:return
        page=self.navigation.currentRow();self.settings.language=language;self._save_settings();self._build_ui(page);self.load_profile();self._retranslate_tray()

    def _set_language_from_tray(self,language:str)->None:
        index=self.language_combo.findData(language)
        if index>=0:self.change_language(index)

    def startup_toggled(self,value)->None:
        if self._loading:return
        command=f'"{sys.executable}" "{Path(sys.argv[0]).resolve()}"'
        try:set_start_with_windows(value,command);self._set_app("start_with_windows",value)
        except OSError as exc:self.startup.blockSignals(True);self.startup.setChecked(not value);self.startup.blockSignals(False);QMessageBox.warning(self,self.t("자동 실행 설정 실패"),str(exc))

    def show_hotkey_errors(self,errors)->None:
        if hasattr(self,"hotkey_status"):self._set_hotkey_status(errors)

    def _build_tray(self)->None:
        icon=QPixmap(32,32);icon.fill(Qt.transparent);painter=QPainter(icon);painter.setPen(QPen(QColor("#1677ff"),3));painter.drawEllipse(5,5,22,22);painter.drawLine(4,16,28,16);painter.drawLine(16,4,16,28);painter.end();self.tray=QSystemTrayIcon(QIcon(icon),self);menu=QMenu();self.tray_show=QAction(self);self.tray_show.triggered.connect(self.showNormal);menu.addAction(self.tray_show);self.tray_toggle=QAction(self);self.tray_toggle.triggered.connect(lambda:self.master_toggled(not self.settings.overlays_enabled));menu.addAction(self.tray_toggle);self.tray_language_menu=menu.addMenu("언어 / Language");self.tray_language_group=QActionGroup(self);self.tray_language_group.setExclusive(True);self.tray_korean=QAction("한국어",self,checkable=True);self.tray_english=QAction("English",self,checkable=True);self.tray_language_group.addAction(self.tray_korean);self.tray_language_group.addAction(self.tray_english);self.tray_language_menu.addActions(self.tray_language_group.actions());self.tray_korean.triggered.connect(lambda:self._set_language_from_tray("ko"));self.tray_english.triggered.connect(lambda:self._set_language_from_tray("en"));menu.addSeparator();self.tray_quit=QAction(self);self.tray_quit.triggered.connect(self.request_quit);menu.addAction(self.tray_quit);self.tray.setContextMenu(menu);self.tray.activated.connect(lambda reason:self.showNormal() if reason==QSystemTrayIcon.Trigger else None);self._retranslate_tray();self.tray.show()

    def _retranslate_tray(self)->None:
        self.tray_show.setText(self.t("설정 열기"));self.tray_toggle.setText(self.t("전체 비활성화") if self.settings.overlays_enabled else self.t("전체 활성화"));self.tray_quit.setText(self.t("완전히 종료"));self.tray_korean.setChecked(self.settings.language=="ko");self.tray_english.setChecked(self.settings.language=="en");self._update_active_profile()

    def request_quit(self)->None:
        self._flush_save();self._quitting=True;self.tray.hide();QApplication.instance().quit()

    def closeEvent(self,event)->None:  # noqa: N802
        if self._save_timer.isActive():self._flush_save()
        if self._quitting:event.accept();return
        if self.settings.minimize_to_tray and self.tray.isVisible():event.ignore();self.hide();self.tray.showMessage("CenterCross",self.t("트레이에서 계속 실행 중입니다."),QSystemTrayIcon.Information,1800)
        else:self._quitting=True;event.accept();QApplication.instance().quit()

    def shutdown(self)->None:
        self._quitting=True;self.tray.hide();self.controller.close();self._flush_save()
