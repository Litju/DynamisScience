"""Run DynamisScience as a native Qt Widgets application."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from ..data_root import DataRootConfigurationError, data_root, ensure_layout
from .main_window import MainWindow
from .services import DynamisAppService


def _settings_path() -> Path:
    override = os.environ.get("DYNAMISSCIENCE_SETTINGS_FILE", "").strip()
    if override:
        return Path(override).expanduser().resolve()
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


def _configure_logging(root: Path) -> logging.Logger:
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("dynamis_science.desktop")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(
            logs / "dynamis_desktop.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dynamis-science")
    parser.add_argument("--data-root", help="private research data directory")
    parser.add_argument("--benchmark-ready-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--benchmark-exit-after-ready", action="store_true", help=argparse.SUPPRESS)
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
    ensure_layout(validated)
    logger = _configure_logging(validated)

    def log_uncaught(exception_type, exception, traceback) -> None:
        logger.critical(
            "Unhandled application error (%s)",
            exception_type.__name__,
            exc_info=(exception_type, exception, traceback),
        )
        QMessageBox.critical(
            None,
            "DynamisScience error",
            "The application encountered an unexpected error. Details were saved in the private data-root logs folder.",
        )

    sys.excepthook = log_uncaught
    settings_path = _settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps({"data_root": str(validated)}, indent=2), encoding="utf-8"
    )
    window = MainWindow(DynamisAppService())
    if args.benchmark_exit_after_ready and not args.benchmark_ready_file:
        parser.error("--benchmark-exit-after-ready requires --benchmark-ready-file")
    if args.benchmark_ready_file:
        ready_file = args.benchmark_ready_file.expanduser().resolve()

        def write_ready_file() -> None:
            ready_file.parent.mkdir(parents=True, exist_ok=True)
            ready_file.write_text(str(time.perf_counter_ns()), encoding="utf-8")

        window.catalogue_loaded.connect(write_ready_file)
        if args.benchmark_exit_after_ready:
            window.catalogue_loaded.connect(lambda: QTimer.singleShot(1000, app.quit))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
