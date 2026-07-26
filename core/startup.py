#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Управление автозапуском GUI в Windows."""

from __future__ import annotations

import os
import sys

from core.i18n import tr

APP_VALUE_NAME = "Integra"


def startup_command(minimized: bool = True) -> str:
    arguments = " --minimized" if minimized else " --show"
    if getattr(sys, "frozen", False):
        return f'"{os.path.abspath(sys.executable)}"{arguments}'

    # os.path is intentional here: this function is also used while checking
    # Windows startup settings from environments that emulate another platform.
    executable = os.path.abspath(sys.executable)
    pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe") if os.name == "nt" else executable
    if not os.path.isfile(pythonw):
        pythonw = executable
    main_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return f'"{pythonw}" "{main_path}"{arguments}'


def set_windows_autostart(enabled: bool, minimized: bool = True) -> tuple[bool, str]:
    if os.name != "nt":
        return False, tr("core.startup_windows_only")
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_VALUE_NAME, 0, winreg.REG_SZ, startup_command(minimized))
            else:
                try:
                    winreg.DeleteValue(key, APP_VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True, tr("core.startup_on") if enabled else tr("core.startup_off")
    except OSError as exc:
        return False, tr("core.startup_failed", error=exc)
