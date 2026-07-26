#!/usr/bin/env python3
"""Локальная проверка проекта перед сборкой."""

from __future__ import annotations

import compileall
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def check_python() -> bool:
    targets = [ROOT / "main.py", ROOT / "core", ROOT / "ui", ROOT / "tests", ROOT / "scripts"]
    for target in targets:
        if target.is_file():
            if not compileall.compile_file(target, quiet=1):
                return False
        elif not compileall.compile_dir(target, quiet=1):
            return False
    return True


def check_launchers() -> bool:
    required = {
        "run.bat": ("install.bat", "run.vbs"),
        "install.bat": ("bootstrap_python.ps1", "requirements.txt"),
        "build.bat": ("build_app.py", "--arch x64"),
        "run.vbs": ("--show", "runas"),
        "test.bat": ("check_project.py", "install.bat"),
    }
    for filename, markers in required.items():
        path = ROOT / filename
        if not path.is_file():
            print(f"Ошибка: отсутствует {filename}")
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in markers:
            if marker not in text:
                print(f"Ошибка: в {filename} отсутствует обязательный маркер {marker!r}")
                return False
    if not (ROOT / "scripts" / "bootstrap_python.ps1").is_file():
        print("Ошибка: отсутствует scripts/bootstrap_python.ps1")
        return False
    if not (ROOT / "assets" / "version_info.txt").is_file():
        print("Ошибка: отсутствует assets/version_info.txt")
        return False
    if not (ROOT / "scripts" / "build_app.py").is_file():
        print("Ошибка: отсутствует scripts/build_app.py")
        return False
    return True


def check_ui_smoke() -> bool:
    try:
        import PySide6  # noqa: F401
    except ImportError:
        print("PySide6 не установлен — UI smoke-тест пропущен.")
        return True

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from core.config import Config
    from ui.main_window import MainWindow
    from ui.startup_check import StartupCheckDialog

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        config = Config(Path(tmp) / "config.json")
        config.update({"bridge_enabled": False, "zapret_path": ""})
        window = MainWindow(config)
        app.processEvents()
        window._status_timer.stop()
        window.bridge.stop()
        window.diagnostics.stop_all()
        window.deleteLater()
        startup = StartupCheckDialog(config, auto_continue_ms=0)
        app.processEvents()
        if not startup._checks:
            print("Ошибка: стартовая проверка не сформировала результаты.")
            return False
        startup.close()
        app.processEvents()
    return True


def main() -> int:
    print("[1/5] Компиляция Python...")
    if not check_python():
        return 1

    print("[2/5] Unit-тесты...")
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1

    print("[3/5] Проверка расширения...")
    manifest = json.loads((ROOT / "browser-extension" / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != 3:
        print("Ошибка: требуется Manifest V3")
        return 1
    try:
        node = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.SubprocessError):
        node = None
    if node and node.returncode == 0:
        for filename in ("popup.js", "background.js"):
            checked = subprocess.run(
                ["node", "--check", str(ROOT / "browser-extension" / filename)], timeout=15
            )
            if checked.returncode != 0:
                return checked.returncode
    else:
        print("Node.js не найден — синтаксис JS не проверен.")

    print("[4/5] Проверка Windows-лаунчеров...")
    if not check_launchers():
        return 1

    print("[5/5] UI smoke-тест...")
    if not check_ui_smoke():
        return 1

    print("Все проверки пройдены.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
