#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Безопасный запуск системных процессов Windows без мигающих окон."""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from core.i18n import tr


def is_windows_admin() -> bool:
    """Проверяет, запущен ли текущий процесс с повышенными правами."""
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def hidden_subprocess_options() -> dict[str, Any]:
    """Параметры subprocess, не создающие консольное окно в Windows."""
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0  # SW_HIDE
    return {
        "creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        "startupinfo": startupinfo,
    }


def read_batch_text(path: Path) -> tuple[str, str]:
    """Читает BAT, сохраняя подходящую кодировку для обратной записи."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        # BOM удаляем намеренно: cmd.exe может воспринять его как часть @echo.
        return raw.decode("utf-8-sig"), "utf-8"
    for encoding in ("utf-8", "cp866", "cp1251"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "latin-1"


def build_hidden_runtime_batch(source: Path, destination: Path) -> None:
    """
    Создаёт копию стратегии, запускающую winws напрямую.

    Оригинальные стратегии Flowseal используют `start ... /min winws.exe`, что
    создаёт отдельное консольное окно. В runtime-копии `start` удаляется, поэтому
    winws наследует скрытый процесс cmd.exe и не мигает на экране.
    """
    text, encoding = read_batch_text(source)
    lines = text.splitlines(keepends=True)
    replaced = False

    start_pattern = re.compile(
        r'^(?P<indent>\s*)start\s+"[^"]*"\s+'
        r'(?:(?:/min|/b|/wait)\s+)*'
        r'(?P<exe>"[^"]*winws\.exe")(?P<rest>.*)$',
        re.IGNORECASE,
    )
    bare_pattern = re.compile(
        r'^(?P<indent>\s*)start\s+'
        r'(?:(?:/min|/b|/wait)\s+)*'
        r'(?P<exe>"?[^\s"]*winws\.exe"?)(?P<rest>.*)$',
        re.IGNORECASE,
    )

    output: list[str] = []
    inserted_no_update = False
    for line in lines:
        ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        body = line[:-len(ending)] if ending else line

        if not inserted_no_update and body.strip().casefold() == "@echo off":
            output.append(body + ending)
            output.append('@set "NO_UPDATE_CHECK=1"' + ending)
            inserted_no_update = True
            continue

        match = start_pattern.match(body) or bare_pattern.match(body)
        if not replaced and match and "winws.exe" in body.casefold():
            output.append(
                f"{match.group('indent')}{match.group('exe')}{match.group('rest')}{ending}"
            )
            replaced = True
        else:
            output.append(body + ending)

    if not replaced:
        raise ValueError(tr("windows.batch_no_winws"))

    destination.write_text("".join(output), encoding=encoding, newline="")
