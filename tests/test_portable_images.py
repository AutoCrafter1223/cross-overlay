import base64
import json
import tempfile
import unittest
from pathlib import Path

from centercross.models import Profile, ShapeLayer
from centercross.storage import SettingsStore

PNG=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a8d8AAAAASUVORK5CYII=")


class PortableImageTests(unittest.TestCase):
    def test_managed_copy_survives_original_move(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/"original.png";source.write_bytes(PNG)
            store=SettingsStore(root/"app")
            copied=Path(store.import_image(source))
            source.rename(root/"moved.png")
            self.assertEqual(copied.read_bytes(),PNG)

    def test_profile_shares_all_image_groups_without_local_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/"original.png";source.write_bytes(PNG)
            profile=Profile()
            for settings in (profile.crosshair,profile.pointer,profile.motion_assist.body):
                settings.layers=[ShapeLayer(shape="image",image_path=str(source),color_key_enabled=True)]
            shared=root/"shared.json";SettingsStore.export_profile(profile,shared)
            payload=json.loads(shared.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["_assets"]),1)
            self.assertNotIn(str(source),shared.read_text(encoding="utf-8"))
            source.rename(root/"moved.png")
            received=SettingsStore.import_profile(shared,root/"recipient"/"images")
            for settings in (received.crosshair,received.pointer,received.motion_assist.body):
                self.assertEqual(Path(settings.layers[0].image_path).read_bytes(),PNG)
                self.assertTrue(settings.layers[0].color_key_enabled)

    def test_reticle_and_pointer_presets_include_images(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/"original.png";source.write_bytes(PNG)
            profile=Profile()
            for name,settings,exporter,importer in (("reticle",profile.crosshair,SettingsStore.export_reticle,SettingsStore.import_reticle),("pointer",profile.pointer,SettingsStore.export_pointer_preset,SettingsStore.import_pointer_preset)):
                settings.layers=[ShapeLayer(shape="image",image_path=str(source))]
                path=root/(name+".json");exporter(settings,path)
                received=importer(path,root/"recipient")
                self.assertEqual(Path(received.layers[0].image_path).read_bytes(),PNG)

    def test_broken_asset_rejected_before_importing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);shared=root/"bad.json";destination=root/"images"
            shared.write_text(json.dumps({"layers":[{"image_path":"asset://../../outside"}],"_assets":{"../../outside":base64.b64encode(PNG).decode()}}))
            with self.assertRaises(ValueError):SettingsStore.import_reticle(shared,destination)
            self.assertFalse(destination.exists())
