#!/usr/bin/env python3
"""Build a native Windows Integra application in the repository app directory."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import struct
import subprocess
import sys
from pathlib import Path


CODE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = CODE_ROOT.parent
APP_ROOT = REPOSITORY_ROOT / "app"
SUPPORTED_ARCHITECTURES = {"x64", "arm64"}


def interpreter_architecture() -> str:
    if struct.calcsize("P") * 8 == 32:
        return "x86"
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return "x64"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a native Windows Integra application.")
    parser.add_argument("--arch", choices=("x64", "arm64", "x86"), required=True)
    return parser.parse_args()


def verify_runtime(arch: str) -> None:
    if os.name != "nt":
        raise RuntimeError("Windows is required to build the Windows application.")
    if arch == "x86":
        raise RuntimeError(
            "Windows x86 is not supported: PySide6 does not publish a win32 wheel. "
            "Do not create a broken x86 application."
        )
    if arch not in SUPPORTED_ARCHITECTURES:
        raise RuntimeError(f"Unsupported architecture: {arch}")
    actual = interpreter_architecture()
    if actual != arch:
        raise RuntimeError(
            f"Requested {arch}, but {sys.executable} is a {actual} Python. "
            "PyInstaller must run under a Python native to the target architecture."
        )
    try:
        import PyInstaller  # noqa: F401
        import psutil  # noqa: F401
        from PySide6.QtWidgets import QApplication  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Install requirements-dev.txt before building the application.") from exc


def verify_package(package_dir: Path) -> None:
    required = (
        package_dir / "Integra.exe",
        package_dir / "PySide6" / "QtWidgets.pyd",
        package_dir / "browser-extension" / "manifest.json",
    )
    missing = [str(path.relative_to(package_dir)) for path in required if not path.is_file()]
    if not any(package_dir.glob("python*.dll")):
        missing.append("python*.dll")
    if missing:
        raise RuntimeError(f"Build finished but required files are missing: {', '.join(missing)}")


def build(arch: str) -> Path:
    package_dir = APP_ROOT / "Integra"
    build_root = REPOSITORY_ROOT / ".build" / "pyinstaller" / arch
    work_dir = build_root / "work"
    spec_dir = build_root / "spec"

    APP_ROOT.mkdir(parents=True, exist_ok=True)
    for target in (package_dir, work_dir, spec_dir):
        if target.exists():
            shutil.rmtree(target)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--contents-directory",
        ".",
        "--noupx",
        "--name",
        "Integra",
        "--icon",
        str(CODE_ROOT / "assets" / "integra.ico"),
        "--version-file",
        str(CODE_ROOT / "assets" / "version_info.txt"),
        "--add-data",
        f"{CODE_ROOT / 'browser-extension'};browser-extension",
        "--add-data",
        f"{CODE_ROOT / 'assets'};assets",
        "--distpath",
        str(APP_ROOT),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        str(CODE_ROOT / "main.py"),
    ]
    subprocess.run(command, cwd=CODE_ROOT, check=True)

    if not package_dir.is_dir():
        raise RuntimeError("PyInstaller did not create the Integra directory.")
    verify_package(package_dir)
    return package_dir


def main() -> int:
    args = parse_args()
    try:
        verify_runtime(args.arch)
        package_dir = build(args.arch)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    print(f"Application ready: {package_dir.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
