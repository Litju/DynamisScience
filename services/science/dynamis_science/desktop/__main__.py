"""Run DynamisScience as a native Qt Widgets application."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from ..data_root import DataRootConfigurationError, data_root
from .main_window import MainWindow
from .services import DynamisAppService


def _settings_path() -> Path:
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppConfigLocation
    )
    return Path(location) / "settings.json"


def _configured_root() -> str | None:
    inherited = os.environ.get("DYNAMISSCIENCE_DATA_ROOT", "").strip()
    if inherited:
        return inherited
    path = _settings_path()
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("data_root")
            return str(value) if value else None
        except (OSError, ValueError):
            return None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dynamis-science")
    parser.add_argument("--data-root", help="private research data directory")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("DynamisScience")
    app.setOrganizationName("DynamisScience")

    root = args.data_root or _configured_root()
    if not root:
        root = QFileDialog.getExistingDirectory(
            None,
            "Choose the private DynamisScience data root",
            str(Path.home()),
        )
        if not root:
            return 0
    try:
        validated = data_root(root)
    except DataRootConfigurationError as error:
        QMessageBox.critical(None, "Invalid private data root", str(error))
        return 2

    os.environ["DYNAMISSCIENCE_DATA_ROOT"] = str(validated)
    settings_path = _settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps({"data_root": str(validated)}, indent=2), encoding="utf-8"
    )
    window = MainWindow(DynamisAppService())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
