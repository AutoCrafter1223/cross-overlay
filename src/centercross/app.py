from __future__ import annotations

import sys
from pathlib import Path

# Allow both package execution and VS Code/debugpy's "Run Python File" action.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from centercross.controller import OverlayController
from centercross.storage import SettingsStore
from centercross.ui import MainWindow
from centercross.winapi import enable_dpi_awareness


def main() -> int:
    enable_dpi_awareness()
    app = QApplication(sys.argv)
    app.setApplicationName("CenterCross")
    app.setOrganizationName("CenterCross")
    # Packaging verification mode: importing this module and constructing the
    # QApplication exercises the Qt DLLs without opening the user interface.
    if "--packaging-smoke-test" in sys.argv:
        return 0
    app.setQuitOnLastWindowClosed(False)
    store = SettingsStore()
    settings = store.load()
    controller = OverlayController(settings, store, app)
    window = MainWindow(settings, store, controller)
    app.aboutToQuit.connect(window.shutdown)
    window.load_profile()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
