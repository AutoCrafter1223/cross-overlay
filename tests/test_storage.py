import json
import tempfile
import unittest
from pathlib import Path

from centercross.models import AppSettings, CrosshairSettings, PointerSettings, Profile
from centercross.storage import SettingsStore


class StorageTests(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory))
            settings = AppSettings(profiles=[Profile(name="테스트")])
            store.save(settings)
            self.assertEqual(store.load().profiles[0].name, "테스트")

    def test_bundled_body_images_render_and_export_with_profile(self):
        from PySide6.QtWidgets import QApplication
        from centercross.image_utils import load_processed_pixmap
        from centercross.models import body_reference_preset

        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        layers = body_reference_preset("body")
        self.assertEqual([(load_processed_pixmap(layer.image_path).width(),
                           load_processed_pixmap(layer.image_path).height()) for layer in layers],
                         [(210, 210), (620, 300), (620, 300)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "body.json"
            profile = Profile()
            profile.motion_assist.body.layers = layers
            SettingsStore.export_profile(profile, path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(raw["_assets"]), 3)
            restored = SettingsStore.import_profile(path, Path(directory) / "images")
            self.assertTrue(all(Path(layer.image_path).is_file()
                                for layer in restored.motion_assist.body.layers))

    def test_corrupt_file_is_backed_up(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory))
            store.path.write_text("not json", encoding="utf-8")
            recovered = store.load()
            self.assertEqual(recovered.profiles[0].name, "기본 프로필")
            self.assertIsNotNone(store.last_recovery)
            self.assertTrue(store.last_recovery.exists())

    def test_import_rejects_blank_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps({"name": " "}), encoding="utf-8")
            with self.assertRaises(ValueError):
                SettingsStore.import_profile(path)

    def test_legacy_profile_import_and_new_export_preserve_per_edge_guide_length(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"profile.json"
            path.write_text(json.dumps({"name":"Old","motion_assist":{"guides":{
                "horizontal_length":500,"vertical_length":200,"center_gap":100
            }}}),encoding="utf-8")
            profile=SettingsStore.import_profile(path)
            self.assertEqual((profile.motion_assist.guides.horizontal_length,profile.motion_assist.guides.vertical_length),(500,200))
            SettingsStore.export_profile(profile,path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"],14)
            restored=SettingsStore.import_profile(path,Path(directory)/"images")
            self.assertEqual((restored.motion_assist.guides.horizontal_length,restored.motion_assist.guides.vertical_length),(500,200))

    def test_reticle_preset_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reticle.ccshape.json"
            settings = CrosshairSettings()
            settings.layers[0].x = 73
            SettingsStore.export_reticle(settings, path)
            restored = SettingsStore.import_reticle(path)
            self.assertEqual(restored.layers[0].x, 73)

    def test_pointer_preset_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pointer.ccpointer.json"
            settings = PointerSettings()
            settings.layers[0].x = -45
            SettingsStore.export_pointer_preset(settings, path)
            restored = SettingsStore.import_pointer_preset(path)
            self.assertEqual(restored.layers[0].x, -45)


if __name__ == "__main__":
    unittest.main()
