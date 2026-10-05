# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

a = Analysis(
    ["run.pyw"],
    pathex=["src"],
    binaries=[],
    datas=[("src/centercross/assets", "centercross/assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
# Qt on supported Windows versions uses the system ICU DLL. A different ICU
# on the build machine's PATH (for example Poppler's versioned ICU) may be
# collected by PyInstaller and shadow the compatible Windows DLL at runtime.
a.binaries = [entry for entry in a.binaries
              if Path(entry[1]).name.lower() not in {"icuuc.dll", "icudt78.dll"}]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CenterCross",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
