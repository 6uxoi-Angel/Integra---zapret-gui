#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integra entry point."""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLockFile, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import Config
from core.i18n import set_language, tr
from core.instance_control import activation_request_path, read_activation_request, write_activation_request
from core.launch_policy import should_start_minimized
from core.paths import application_root
from core.windows_process import is_windows_admin
from ui.main_window import MainWindow
from ui.startup_check import show_startup_check


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    launch_mode = parser.add_mutually_exclusive_group()
    launch_mode.add_argument("--minimized", action="store_true")
    launch_mode.add_argument("--show", action="store_true")
    parser.add_argument("--no-elevate", action="store_true")
    return parser.parse_known_args()[0]


def relaunch_as_admin() -> tuple[bool, str]:
    if os.name != "nt":
        return False, tr("core.elevation_windows_only")
    if getattr(sys, "frozen", False):
        executable = str(Path(sys.executable).resolve())
        parameters = subprocess.list2cmdline(sys.argv[1:])
        workdir = str(application_root())
    else:
        executable_path = Path(sys.executable).resolve()
        pythonw = executable_path.with_name("pythonw.exe")
        executable = str(pythonw if pythonw.exists() else executable_path)
        main_path = Path(__file__).resolve()
        parameters = subprocess.list2cmdline([str(main_path), *sys.argv[1:]])
        workdir = str(main_path.parent)
    try:
        result = int(ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, parameters, workdir, 1))
    except (AttributeError, OSError) as exc:
        return False, str(exc)
    if result <= 32:
        return False, tr("core.elevation_failed_code", code=result)
    return True, ""


def _crash_log_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "Integra" / "logs" / "crash.log"


def _write_crash_log(exc_type, exc_value, exc_traceback) -> Path:
    path = _crash_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    report = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"\n=== {datetime.now().isoformat(timespec='seconds')} ===\n")
        handle.write(report)
    return path


def install_exception_hook() -> None:
    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        try:
            path = _write_crash_log(exc_type, exc_value, exc_traceback)
        except OSError:
            path = None
        app = QApplication.instance()
        if app is not None:
            detail = f"\n\nCrash log: {path}" if path else ""
            QMessageBox.critical(None, "Integra", f"Unexpected application error:\n{exc_value}{detail}")
        else:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception


def main() -> int:
    install_exception_hook()
    args = parse_args()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Integra")
    app.setApplicationVersion(MainWindow.VERSION)
    app.setOrganizationName("Integra")
    app.setQuitOnLastWindowClosed(False)

    config = Config()
    set_language(config.get("language", "ru"))

    if os.name == "nt" and not args.no_elevate and not is_windows_admin():
        relaunched, error = relaunch_as_admin()
        if relaunched:
            return 0
        QMessageBox.critical(None, tr("app.admin_required_title"), tr("app.admin_required_body", error=error))
        return 1

    lock_path = config.path.parent / "integra.lock"
    request_path = activation_request_path(config.path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(150):
        try:
            write_activation_request(request_path)
        except OSError:
            QMessageBox.information(None, "Integra", tr("app.already_running"))
        return 0

    if not args.minimized and not show_startup_check(config):
        lock.unlock()
        return 0

    window = MainWindow(config)
    app.setWindowIcon(window.app_icon)

    last_activation_request = read_activation_request(request_path)

    def check_activation_request() -> None:
        nonlocal last_activation_request
        current = read_activation_request(request_path)
        if current > last_activation_request:
            last_activation_request = current
            window.show_window()

    activation_timer = QTimer(app)
    activation_timer.setInterval(400)
    activation_timer.timeout.connect(check_activation_request)
    activation_timer.start()

    minimized = should_start_minimized(args.minimized, window.tray_icon.isVisible())
    if minimized:
        window.hide()
    else:
        QTimer.singleShot(0, window.show_window)

    exit_code = app.exec()
    activation_timer.stop()
    lock.unlock()
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        try:
            path = _write_crash_log(exc_type, exc_value, exc_traceback)
            print(f"Integra failed. Crash log: {path}", file=sys.stderr)
        except OSError:
            traceback.print_exc()
        raise
