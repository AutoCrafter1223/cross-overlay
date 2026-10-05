from __future__ import annotations

import json
import os
import shutil
import base64
import binascii
import hashlib
import copy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .image_utils import resolve_image_path
from .models import AppSettings, CrosshairSettings, PointerSettings, Profile


APP_DIR_NAME = "CenterCross"
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_PACKAGE_BYTES = 128 * 1024 * 1024


def _image_nodes(value):
    if isinstance(value, dict):
        if value.get("image_path"):
            yield value
        for child in value.values():
            yield from _image_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _image_nodes(child)


def _read_png(path):
    path=resolve_image_path(path)
    if path.stat().st_size>MAX_IMAGE_BYTES:raise ValueError("PNG image exceeds 32 MB.")
    data=path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):raise ValueError("Invalid PNG image.")
    return data


def _store_png(data,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    target=directory/(hashlib.sha256(data).hexdigest()+".png")
    if not target.exists():
        temp=target.with_suffix(".tmp");temp.write_bytes(data);os.replace(temp,target)
    return str(target.resolve())


def _write_portable(raw,path):
    raw=copy.deepcopy(raw);assets={};total=0
    for node in _image_nodes(raw):
        data=_read_png(node["image_path"]);key=hashlib.sha256(data).hexdigest()
        if key not in assets:
            total+=len(data)
            if total>MAX_PACKAGE_BYTES:raise ValueError("Images exceed 128 MB in total.")
            assets[key]=base64.b64encode(data).decode("ascii")
        node["image_path"]="asset://"+key
    if assets:raw["_assets"]=assets
    path=Path(path);temp=path.with_suffix(path.suffix+".tmp")
    temp.write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding="utf-8");os.replace(temp,path)


def _read_portable(path,directory=None):
    path=Path(path)
    if path.stat().st_size>MAX_PACKAGE_BYTES*2:raise ValueError("Profile file is too large.")
    raw=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw,dict):raise ValueError("Invalid profile file.")
    assets=raw.pop("_assets",{})
    if not isinstance(assets,dict):raise ValueError("Invalid image package.")
    decoded={};total=0
    # Validate every referenced image before storing any files.
    for node in _image_nodes(raw):
        value=node["image_path"]
        if not isinstance(value,str):raise ValueError("Invalid image path.")
        if not value.startswith("asset://"):continue
        key=value[8:]
        if key in decoded:continue
        encoded=assets.get(key)
        if not isinstance(encoded,str) or len(encoded)>MAX_IMAGE_BYTES*4//3+4:raise ValueError("Missing or oversized image.")
        try:data=base64.b64decode(encoded,validate=True)
        except (ValueError,binascii.Error) as exc:raise ValueError("Invalid image data.") from exc
        if len(data)>MAX_IMAGE_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n") or hashlib.sha256(data).hexdigest()!=key:raise ValueError("Invalid PNG image or checksum.")
        total+=len(data)
        if total>MAX_PACKAGE_BYTES:raise ValueError("Image package is too large.")
        decoded[key]=data
    locations={key:_store_png(data,directory or default_config_dir()/"images") for key,data in decoded.items()}
    for node in _image_nodes(raw):
        if node["image_path"].startswith("asset://"):node["image_path"]=locations[node["image_path"][8:]]
        elif node["image_path"].startswith("builtin://"):continue
        else:
            legacy=Path(node["image_path"])
            if not legacy.is_absolute():legacy=path.parent/legacy
            if legacy.is_file():node["image_path"]=_store_png(_read_png(legacy),directory or default_config_dir()/"images")
    return raw


def default_config_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / APP_DIR_NAME


class SettingsStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_config_dir()
        self.path = self.directory / "settings.json"
        self.last_recovery: Path | None = None

    def import_image(self,path: Path) -> str:
        return _store_png(_read_png(path),self.directory/"images")

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            settings=AppSettings.from_dict(raw)
            for profile in settings.profiles:
                for group in (profile.crosshair,profile.pointer,profile.motion_assist.body):
                    for layer in group.layers:
                        if layer.image_path and Path(layer.image_path).is_file():
                            try:layer.image_path=self.import_image(Path(layer.image_path))
                            except (OSError,ValueError):pass
            return settings
        except (OSError, ValueError, TypeError):
            self.directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = self.directory / f"settings.corrupt-{stamp}.json"
            try:
                shutil.copy2(self.path, backup)
                self.last_recovery = backup
            except OSError:
                self.last_recovery = None
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    @staticmethod
    def export_profile(profile: Profile, path: Path) -> None:
        payload = profile.to_dict()
        payload["schema_version"] = 14
        _write_portable(payload, path)

    @staticmethod
    def import_profile(path: Path, image_directory: Path | None = None) -> Profile:
        raw = _read_portable(path,image_directory)
        if not isinstance(raw,dict):
            raise ValueError("올바른 프로필 파일이 아닙니다.")
        version=int(raw.get("schema_version",11))
        profile=AppSettings.from_dict({"schema_version":version,"profiles":[raw]}).profiles[0]
        if not profile.name.strip():
            raise ValueError("프로필 이름이 없습니다.")
        return profile

    @staticmethod
    def export_reticle(settings: CrosshairSettings, path: Path) -> None:
        _write_portable(asdict(settings),path)

    @staticmethod
    def import_reticle(path: Path, image_directory: Path | None = None) -> CrosshairSettings:
        raw = _read_portable(path,image_directory)
        if not isinstance(raw, dict) or not isinstance(raw.get("layers"), list):
            raise ValueError("도형 레이어가 없는 프리셋입니다.")
        return CrosshairSettings.from_dict(raw)

    @staticmethod
    def export_pointer_preset(settings: PointerSettings, path: Path) -> None:
        _write_portable(asdict(settings),path)

    @staticmethod
    def import_pointer_preset(path: Path, image_directory: Path | None = None) -> PointerSettings:
        raw = _read_portable(path,image_directory)
        if not isinstance(raw, dict) or not isinstance(raw.get("layers"), list):
            raise ValueError("도형 레이어가 없는 마우스 커서 추적 프리셋입니다.")
        return PointerSettings.from_dict(raw)
