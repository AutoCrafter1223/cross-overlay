import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QWheelEvent
from PySide6.QtWidgets import QApplication, QFrame, QPushButton

from centercross.models import AppSettings, Profile, ShapeLayer
from centercross.storage import SettingsStore
from centercross.ui import MainWindow


class DummyController(QObject):
    hotkey_errors = Signal(list)
    profile_activated = Signal(int)
    settings_changed = Signal()

    def register_hotkeys(self):
        return []

    def refresh_visuals(self):
        pass

    def refresh_topmost(self):
        pass

    def preview_effect(self):
        pass

    def apply_profile(self):
        return []

    def _update(self, force_target=False):
        del force_target

    def close(self):
        pass


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_editor_cards_align_and_motion_switch_is_per_section(self):
        with tempfile.TemporaryDirectory() as directory:
            window=MainWindow(AppSettings(),SettingsStore(Path(directory)),DummyController())
            try:
                window.resize(1800,1000);window.show();window.load_profile();self.app.processEvents()
                for row,stack_index in ((0,0),(1,1),(2,2)):
                    window.navigation.setCurrentRow(row);self.app.processEvents()
                    cards=[card for card in window.stack.widget(stack_index).findChildren(QFrame)
                           if card.objectName()=="card" and card.isVisible()]
                    self.assertEqual(len(cards),3)
                    self.assertEqual(len({(card.mapTo(window,QPoint(0,0)).y(),card.height()) for card in cards}),1)
                self.assertLessEqual(window.motion_preview.pos().y(),1)
                self.assertFalse(window.profile.motion_assist.body.enabled)
                window.motion_header_enabled.click()
                self.assertTrue(window.profile.motion_assist.body.enabled)
                window.navigation.setCurrentRow(4);self.app.processEvents()
                self.assertFalse(window.motion_header_enabled.isChecked())
                self.assertFalse(window.profile.motion_assist.guides.enabled)
                self.assertTrue(window.guide_horizontal_length.isEnabled())
                self.assertTrue(all(not button.text().startswith("+") for button in window.findChildren(QPushButton)))
                self.assertEqual([button.text() for button in window.body_action_buttons],
                                 [window.t(label) for label in ("추가","복제","삭제","위로","아래로")])
                self.assertEqual(len({button.y() for button in window.body_action_buttons[:3]}),1)
                self.assertEqual(len({button.y() for button in window.body_action_buttons[3:]}),1)
                self.assertNotEqual(window.body_action_buttons[0].y(),window.body_action_buttons[3].y())
                for toggle in (window.cross_enabled,window.pointer_enabled,window.motion_header_enabled):
                    self.assertEqual(toggle.label,"")
                window.resize(1528,888);self.app.processEvents()
                preview_tops=[]
                for row,preview in ((0,window.reticle_preview),(1,window.pointer_preview),
                                    (2,window.motion_preview),(3,window.motion_preview),
                                    (4,window.motion_preview),(5,window.motion_preview)):
                    window.navigation.setCurrentRow(row);self.app.processEvents()
                    preview_tops.append(preview.mapTo(window,QPoint(0,0)).y())
                self.assertEqual(len(set(preview_tops)),1,preview_tops)
                for row in (3,4,5):
                    window.navigation.setCurrentRow(row);self.app.processEvents()
                    scroll=window.motion_settings_stack.currentWidget()
                    self.assertEqual(scroll.widget().objectName(),"card")
                    self.assertGreaterEqual(scroll.widget().height(),scroll.viewport().height())
                    self.assertEqual(scroll.horizontalScrollBar().maximum(),0)
                self.assertGreater(window.motion_settings_stack.currentWidget().verticalScrollBar().maximum(),0)
                card_origins=[]
                for row in range(7):
                    window.navigation.setCurrentRow(row);self.app.processEvents()
                    page=window.stack.currentWidget().widget()
                    cards=[card for card in page.findChildren(QFrame)
                           if card.objectName()=="card" and card.isVisible()]
                    self.assertTrue(cards)
                    card_origins.append(cards[0].mapTo(window,QPoint(0,0)))
                self.assertEqual(len({(point.x(),point.y()) for point in card_origins}),1,card_origins)
                self.assertTrue(window.effect_enabled.isChecked())
                window.effect_enabled.click()
                self.assertFalse(window.profile.find_effect.enabled)
                self.assertTrue(window.effect_type.isEnabled())
                window._flush_save()
                self.assertFalse(window.store.load().profiles[0].find_effect.enabled)
                self.assertEqual(window.body_layer_name.parent().objectName(),"editorProperties")
            finally:
                window._quitting=True;window.tray.hide();window.close()

    def test_hotkey_failure_survives_runtime_and_master_toggles(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = DummyController()
            window = MainWindow(AppSettings(), SettingsStore(Path(directory)), controller)
            try:
                window.load_profile()
                controller.last_hotkey_errors = ["Alt+R conflict"]
                window.show_hotkey_errors(controller.last_hotkey_errors)
                window._sync_runtime_state()
                self.assertIn("Alt+R conflict", window.hotkey_status.text())
                window.master_toggled(False)
                self.assertIn("Alt+R conflict", window.hotkey_status.text())
                controller.last_hotkey_errors = []
                window.show_hotkey_errors([])
                self.assertNotIn("conflict", window.hotkey_status.text())
            finally:
                window._quitting = True
                window.tray.hide()
                window.close()

    def test_new_controls_load_in_both_languages(self):
        with tempfile.TemporaryDirectory() as directory:
            png_path = Path(directory) / "key-test.png"
            image = QImage(4, 4, QImage.Format_RGBA8888)
            image.fill(QColor("white"))
            self.assertTrue(image.save(str(png_path)))

            settings = AppSettings()
            settings.profiles[0].pointer.layers = [ShapeLayer(
                name="Pointer PNG", shape="image", image_path=str(png_path),
                width=80, height=40, color_key_enabled=True,
            )]
            settings.profiles[0].crosshair.layers = [ShapeLayer(
                name="PNG", shape="image", image_path=str(png_path),
                mirror_horizontal=True, color_key_enabled=True,
            )]
            window = MainWindow(settings, SettingsStore(Path(directory)), DummyController())
            try:
                window.load_profile()
                self.assertTrue(window.pointer_layer_key_enabled.isEnabled())
                self.assertTrue(window.pointer_layer_key_color.isEnabled())
                self.assertTrue(window.layer_key_enabled.isEnabled())
                self.assertTrue(window.keep_topmost.isChecked())
                self.assertEqual(window.pointer_layer_controls["width"].value(), 80)
                self.assertEqual(window.pointer_layer_controls["height"].value(), 40)
                self.assertEqual(window.pointer_layer_shape.findData("arc") >= 0, True)
                self.assertEqual(window.pointer_rate.currentData(), 0)
                self.assertEqual(window.pointer_rate.count(), 6)
                self.assertEqual(window.tray_korean.text(), "한국어")
                self.assertEqual(window.tray_english.text(), "English")
                self.assertTrue(hasattr(window, "pattern_enabled"))
                self.assertTrue(hasattr(window, "pattern_angle"))
                self.assertTrue(hasattr(window, "pattern_copies"))
                self.assertEqual(window.layer_shape.findData("arc") >= 0, True)
                window.layer_shape.setCurrentIndex(window.layer_shape.findData("line"))
                self.assertFalse(window.layer_controls["height"].isEnabled())
                self.assertGreaterEqual(window.layer_cap.findData("triangle"), 0)
                window.layer_shape.setCurrentIndex(window.layer_shape.findData("arc"))
                self.assertTrue(window.layer_controls["arc_radius"].isEnabled())
                self.assertFalse(window.layer_controls["width"].isEnabled())
                self.assertFalse(window.layer_controls["height"].isEnabled())

                english_index = window.language_combo.findData("en")
                window.change_language(english_index)
                self.assertEqual(settings.language, "en")
                self.assertIn("CenterCross", window.windowTitle())
                self.assertEqual(window.navigation.item(0).text(), "Screen reference point")
                self.assertEqual(window.navigation.item(1).text(), "Mouse cursor tracking")
                self.assertEqual(window.navigation.item(2).text(), "Show virtual body")
                self.assertNotEqual(window.navigation.item(0).icon().cacheKey(), window.navigation.item(1).icon().cacheKey())
                self.assertEqual(window.body_preset.count(), 3)
                self.assertEqual(set(window.hotkey_widgets), {"find", "all_overlays"})
                self.assertFalse(window.guide_dash_length.isEnabled())
                self.assertFalse(window.grid_horizontal_dash_gap.isEnabled())
                self.assertFalse(window.grid_vertical_dash_gap.isEnabled())
                self.assertEqual(window.guide_thickness.maximum(), 300)
                self.assertEqual(window.guide_center_cap.count(), 3)
                self.assertEqual(window.motion_settings_stack.count(), 4)
                self.assertEqual(window.navigation.count(), 9)
                window.navigation.setCurrentRow(4)
                self.assertEqual(window.motion_settings_stack.currentIndex(), 2)
                self.assertEqual(window.stack.currentIndex(), 2)
                window.navigation.setCurrentRow(8)
                self.assertEqual(window.stack.currentIndex(), 5)
                self.assertEqual(window.profile_list.count(), 1)
                self.assertIn("Center of monitor", window.profile_list.item(0).text())
                self.assertEqual(window.effect_type.findData("spotlight"), -1)
                self.assertGreaterEqual(window.effect_type.findData("focus_lines"), 0)
                sample_key=next(iter(window.hotkey_widgets.values()))[1]
                self.assertEqual(sample_key.findData("F13"), -1)
                self.assertGreaterEqual(sample_key.findData("Mouse5"), 0)
            finally:
                window._quitting = True
                window.tray.hide()
                window.close()

    def test_general_overview_uses_target_modes_without_window_titles(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = AppSettings(profiles=[Profile(name="Monitor"), Profile(name="App")])
            settings.profiles[1].target.mode = "application"
            settings.profiles[1].target.executable = "Example.exe"
            settings.profiles[1].motion_assist.enabled = True
            settings.profiles[1].motion_assist.guides.enabled = True
            window = MainWindow(settings, SettingsStore(Path(directory)), DummyController())
            try:
                window.load_profile()
                self.assertEqual(window.navigation.item(8).text(), "일반")
                self.assertEqual(window.profile_list.count(), 2)
                self.assertIn("모니터 중앙", window.profile_list.item(0).text())
                self.assertIn("Example", window.profile_list.item(1).text())
                self.assertEqual(window.profile_status.text(), "표시 대기")
                window.profile_list.setCurrentRow(1)
                self.assertIn("수평선", window.profile_features.text())
                self.assertIn("켜짐", window.profile_features.text())
                self.assertEqual(window.profile_name_edit.text(), "App")
                self.assertEqual(window.target_combo.currentData(), ("application", "Example.exe"))
                window.duplicate_profile()
                self.assertEqual(window.profile_list.count(), 3)
                self.assertEqual(settings.profiles[2].target.executable, "Example.exe")
                self.assertTrue(settings.profiles[2].motion_assist.guides.enabled)
                self.assertEqual(window.profile_name_edit.text(), "App 복사본")
            finally:
                window._quitting = True
                window.tray.hide()
                window.close()

    def test_profile_list_and_shared_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = AppSettings(profiles=[Profile(name="One"), Profile(name="Two")])
            store = SettingsStore(Path(directory))
            window = MainWindow(settings, store, DummyController())
            try:
                window.resize(1500, 900)
                window.show()
                window.load_profile()
                self.app.processEvents()

                self.assertEqual(window.profile_list.count(), 2)
                self.assertEqual(window.language_combo.parentWidget().objectName(), "header")
                self.assertFalse(hasattr(window, "active_only"))
                self.assertFalse(hasattr(window, "pointer_active"))

                window.profile_list.item(1).setCheckState(Qt.Unchecked)
                self.assertFalse(settings.profiles[1].enabled)
                window._flush_save()
                self.assertFalse(store.load().profiles[1].enabled)

                window.navigation.setCurrentRow(4)
                self.app.processEvents()
                self.assertEqual(
                    window.guide_horizontal.mapTo(window, QPoint(0, 0)).y(),
                    window.guide_vertical.mapTo(window, QPoint(0, 0)).y(),
                )

                window.guide_thickness.setValue(10)
                window.guide_vertical.setFocus()
                wheel = QWheelEvent(
                    QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
                    Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
                )
                self.app.sendEvent(window.guide_thickness, wheel)
                self.assertEqual(window.guide_thickness.value(), 10)

                window.guide_thickness.setFocus()
                self.app.processEvents()
                focused_wheel = QWheelEvent(
                    QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
                    Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
                )
                self.app.sendEvent(window.guide_thickness, focused_wheel)
                self.assertEqual(window.guide_thickness.value(), 11)

                window.guide_vertical.setFocus()
                window.guide_center_cap.setCurrentIndex(0)
                combo_wheel = QWheelEvent(
                    QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                    Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
                )
                self.app.sendEvent(window.guide_center_cap, combo_wheel)
                self.assertEqual(window.guide_center_cap.currentIndex(), 0)
            finally:
                window._quitting = True
                window.tray.hide()
                window.close()


if __name__ == "__main__":
    unittest.main()
