#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Startup readiness checks shared by the launch window and tests."""

from __future__ import annotations

import importlib.util
import os
import struct
from dataclasses import dataclass
from pathlib import Path

from core.i18n import tr
from core.windows_process import is_windows_admin


@dataclass(frozen=True)
class StartupCheck:
    """One non-destructive application readiness check."""

    identifier: str
    title: str
    detail: str
    status: str


def inspect_zapret_installation(zapret_path: str) -> StartupCheck:
    """Describe whether a configured Zapret folder is ready for use."""
    value = (zapret_path or "").strip()
    if not value:
        return StartupCheck("zapret", tr("preflight.zapret"), tr("preflight.zapret_not_configured"), "warning")

    root = Path(value).expanduser()
    if not root.is_dir():
        return StartupCheck("zapret", tr("preflight.zapret"), tr("preflight.zapret_folder_missing"), "warning")

    has_strategies = any(root.glob("general*.bat"))
    has_winws = any((root / relative).is_file() for relative in ("winws.exe", "bin/winws.exe"))
    if has_strategies and has_winws:
        return StartupCheck("zapret", tr("preflight.zapret"), tr("preflight.zapret_ready"), "ok")
    if not has_strategies:
        return StartupCheck("zapret", tr("preflight.zapret"), tr("preflight.zapret_strategies_missing"), "warning")
    return StartupCheck("zapret", tr("preflight.zapret"), tr("preflight.zapret_winws_missing"), "warning")


def collect_startup_checks(zapret_path: str) -> tuple[StartupCheck, ...]:
    """Collect local checks without downloading, modifying, or starting Zapret."""
    runtime_ready = all(importlib.util.find_spec(module) is not None for module in ("PySide6", "psutil"))
    platform_ready = os.name == "nt" and struct.calcsize("P") * 8 == 64
    admin_ready = is_windows_admin() if os.name == "nt" else False
    return (
        StartupCheck(
            "runtime",
            tr("preflight.runtime"),
            tr("preflight.runtime_ok") if runtime_ready else tr("preflight.runtime_missing"),
            "ok" if runtime_ready else "error",
        ),
        StartupCheck(
            "platform",
            tr("preflight.platform"),
            tr("preflight.platform_ok") if platform_ready else tr("preflight.platform_bad"),
            "ok" if platform_ready else "error",
        ),
        StartupCheck(
            "admin",
            tr("preflight.admin"),
            tr("preflight.admin_ok") if admin_ready else tr("preflight.admin_missing"),
            "ok" if admin_ready else "warning",
        ),
        inspect_zapret_installation(zapret_path),
    )
