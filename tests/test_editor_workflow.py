import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from PySide6.QtCore import Qt, QEvent, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from centercross.editor_widgets import ResponsivePanel
from centercross.models import AppSettings
from centercross.storage import SettingsStore
from centercross.ui import MainWindow
from test_ui_smoke import DummyController


class EditorWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=SettingsStore(Path(self.temp.name))
        self.tray_patch=patch.object(QSystemTrayIcon,"show")
        self.tray_patch.start()
        self.window=MainWindow(AppSettings(),self.store,DummyController())
        self.window.load_profile()

    def tearDown(self):
        self.window._quitting=True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.tray_patch.stop()
        self.temp.cleanup()

    def test_drag_is_one_undo_and_redo_step(self):
        w=self.window;layer=w.current_layer();original=(layer.x,layer.y)
        w._begin_drag()
        w.preview_layer_moved(40,50);w.preview_layer_moved(60,70)
        w._end_drag()
        w._restore_edit()
        self.assertEqual((w.current_layer().x,w.current_layer().y),original)
        w._restore_edit(True)
        self.assertEqual((w.current_layer().x,w.current_layer().y),(60,70))
        w.delete_layer();w._restore_edit()
        self.assertTrue(any(x.layer_id==layer.layer_id for x in w.profile.crosshair.layers))

    def test_keyboard_nudge_and_debounced_save(self):
        w=self.window;self.store.save=Mock(wraps=self.store.save)
        x=w.current_layer().x
        QTest.keyClick(w.reticle_preview,Qt.Key_Right)
        QTest.keyClick(w.reticle_preview,Qt.Key_Right,Qt.ShiftModifier)
        self.assertEqual(w.current_layer().x,x+11)
        self.store.save.assert_not_called()
        w._flush_save();self.store.save.assert_called_once()
        self.assertEqual(self.store.load().profiles[0].crosshair.layers[0].x,x+11)

    def test_ctrl_z_remains_available_without_visible_history_buttons(self):
        w=self.window;w.resize(1920,1080);w.show();self.app.processEvents();w._set_layer("x",w.current_layer().x+25)
        changed=w.current_layer().x
        QTest.keyClick(w.reticle_preview,Qt.Key_Z,Qt.ControlModifier)
        self.assertEqual(w.current_layer().x,changed-25)

    def test_independent_guide_lengths_survive_save_and_undo(self):
        w=self.window
        w.guide_horizontal_length.setValue(600);w.guide_vertical_length.setValue(220)
        w._flush_save()
        guides=self.store.load().profiles[0].motion_assist.guides
        self.assertEqual((guides.horizontal_length,guides.vertical_length),(600,220))
        w._restore_edit()
        self.assertEqual(w.profile.motion_assist.guides.horizontal_length,600)
        self.assertEqual(w.guide_vertical_length.value(),410)

    def test_three_previews_share_zoom_and_drag_uses_real_pixels(self):
        w=self.window;w.resize(1920,1080);w.show();self.app.processEvents()
        original=w.profile.to_dict()
        for nav,choice,preview in ((0,w.reticle_zoom,w.reticle_preview),(1,w.pointer_zoom,w.pointer_preview),(2,w.body_zoom,w.motion_preview)):
            w.navigation.setCurrentRow(nav);self.app.processEvents()
            self.assertEqual(choice.currentData(),"fit")
            choice.setCurrentIndex(choice.findData(.5));self.app.processEvents()
            self.assertEqual((preview.width(),preview.height()),(960,540))
            choice.setCurrentIndex(choice.findData(1.0));self.app.processEvents()
            self.assertEqual((preview.width(),preview.height()),(1920,1080))
            self.assertGreater(preview.parentWidget().parentWidget().horizontalScrollBar().maximum(),0)
        self.assertEqual(w.profile.to_dict(),original)
        w.reticle_zoom.setCurrentIndex(w.reticle_zoom.findData(.5))
        layer=w.current_layer();start=QPointF(480+(layer.x+w.profile.crosshair.offset_x)*.5,270+(layer.y+w.profile.crosshair.offset_y)*.5)
        end=start+QPointF(20,10)
        w.reticle_preview.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress,start,start,Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
        w.reticle_preview.mouseMoveEvent(QMouseEvent(QEvent.MouseMove,end,end,Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
        w.reticle_preview.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease,end,end,Qt.LeftButton,Qt.NoButton,Qt.NoModifier))
        self.assertEqual((w.current_layer().x-original["crosshair"]["layers"][0]["x"],w.current_layer().y-original["crosshair"]["layers"][0]["y"]),(40,20))

        w.pointer_zoom.setCurrentIndex(w.pointer_zoom.findData(.5))
        pointer=w.current_pointer_layer();old=(pointer.x,pointer.y)
        start=QPointF(480+(pointer.x+w.profile.pointer.offset_x)*.5,270+(pointer.y+w.profile.pointer.offset_y)*.5)
        end=start+QPointF(15,-10)
        w.pointer_preview.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress,start,start,Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
        w.pointer_preview.mouseMoveEvent(QMouseEvent(QEvent.MouseMove,end,end,Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
        w.pointer_preview.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease,end,end,Qt.LeftButton,Qt.NoButton,Qt.NoModifier))
        self.assertEqual((pointer.x-old[0],pointer.y-old[1]),(30,-20))

        w.navigation.setCurrentRow(2);w.body_zoom.setCurrentIndex(w.body_zoom.findData(.5))
        body=w.current_body_layer();old=(body.x,body.y)
        start=QPointF(480+body.x*.5,540+body.y*.5);end=start+QPointF(10,-15)
        w.motion_preview.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress,start,start,Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
        w.motion_preview.mouseMoveEvent(QMouseEvent(QEvent.MouseMove,end,end,Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
        w.motion_preview.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease,end,end,Qt.LeftButton,Qt.NoButton,Qt.NoModifier))
        self.assertEqual((body.x-old[0],body.y-old[1]),(20,-30))
        w.resize(800,600)
        for nav in (0,1,2):
            w.navigation.setCurrentRow(nav)
            for _ in range(12):self.app.processEvents()
            page=w.stack.currentWidget()
            self.assertLessEqual(page.widget().width(),page.viewport().width())

    def test_small_and_large_layouts_in_both_languages(self):
        w=self.window;w.show()
        for language in ("ko","en"):
            w._set_language_from_tray(language)
            for width,height in ((800,600),(1040,680),(1920,1080)):
                w.resize(width,height)
                for nav in (0,1,2,3,6,7,8):
                    with self.subTest(language=language,width=width,nav=nav):
                        w.navigation.setCurrentRow(nav)
                        for _ in range(12):self.app.processEvents()
                        scroll=w.stack.currentWidget()
                        self.assertLessEqual(scroll.widget().width(),scroll.viewport().width())
                        for panel in scroll.findChildren(ResponsivePanel):
                            for index in range(panel._tabs.count()):
                                panel._tabs.setCurrentIndex(index)
                                for _ in range(8):self.app.processEvents()
                                self.assertLessEqual(scroll.widget().width(),scroll.viewport().width())

    def test_irrelevant_properties_hidden(self):
        w=self.window
        w._set_layer("shape","line")
        self.assertFalse(w.layer_properties_form.isRowVisible(w.layer_controls["height"]))
        self.assertFalse(w.layer_properties_form.isRowVisible(w.layer_controls["arc_radius"]))
        w._set_layer("shape","arc")
        self.assertTrue(w.layer_properties_form.isRowVisible(w.layer_controls["arc_radius"]))
        self.assertFalse(w.layer_properties_form.isRowVisible(w.layer_controls["width"]))
