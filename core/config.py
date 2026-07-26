#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Надёжное хранение конфигурации Integra."""

from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional


class Config:
    """Потокобезопасная JSON-конфигурация с атомарной записью."""

    APP_NAME = "Integra"
    CONFIG_FILE = "config.json"

    DEFAULTS = {
        "theme": "dark_accent",
        "language": "ru",
        "zapret_path": "",
        "auto_check_zapret": True,
        "auto_install_zapret": False,
        "auto_update_zapret": False,
        "selected_strategy": "general.bat",
        "start_minimized": False,
        "autostart_zapret": False,
        "autostart_windows": False,
        "close_to_tray": True,
        "log_level": "ALL",
        "window_geometry": None,
        "bridge_enabled": True,
        "bridge_port": 8765,
        "bridge_token": "",
        "diagnostic_sites": [],
    }

    def __init__(self, config_path: Optional[Path | str] = None):
        self._lock = threading.RLock()
        self._config_path = Path(config_path) if config_path else self._default_config_path()
        self._data: dict[str, Any] = {}
        self.load()

    @classmethod
    def _default_config_path(cls) -> Path:
        """Возвращает постоянный путь, не зависящий от текущей рабочей папки."""
        app_dir = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
        portable_root = app_dir if getattr(sys, "frozen", False) else app_dir.parent
        if (portable_root / "portable.flag").exists():
            return portable_root / cls.CONFIG_FILE

        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / cls.APP_NAME / cls.CONFIG_FILE

    @property
    def path(self) -> Path:
        return self._config_path

    def load(self) -> None:
        with self._lock:
            loaded: dict[str, Any] = {}
            source_path = self._config_path
            if not source_path.exists():
                legacy = Path(__file__).resolve().parents[1] / "zapret_gui_config.json"
                if legacy.exists():
                    source_path = legacy
            if source_path.exists():
                try:
                    loaded = json.loads(source_path.read_text(encoding="utf-8"))
                    if not isinstance(loaded, dict):
                        raise ValueError("Корень конфигурации должен быть объектом")
                except (OSError, ValueError, json.JSONDecodeError):
                    if source_path == self._config_path:
                        self._backup_broken_config()
                    loaded = {}

            self._data = {**self.DEFAULTS, **loaded}
            self._sanitize()
            if not self._data.get("bridge_token"):
                self._data["bridge_token"] = secrets.token_urlsafe(32)
            self.save()

    def _sanitize(self) -> None:
        theme = str(self._data.get("theme", "dark_accent"))
        legacy_theme_map = {"system": "dark_accent"}
        theme = legacy_theme_map.get(theme, theme)
        if theme not in {"light", "light_accent", "dark", "dark_accent"}:
            theme = "dark_accent"
        self._data["theme"] = theme
        language = str(self._data.get("language", "ru")).lower()
        self._data["language"] = language if language in {"ru", "en"} else "ru"
        from core.diagnostic_sites import sanitize_custom_sites
        self._data["diagnostic_sites"] = sanitize_custom_sites(self._data.get("diagnostic_sites", []))
        try:
            port = int(self._data.get("bridge_port", 8765))
        except (TypeError, ValueError):
            port = 8765
        self._data["bridge_port"] = min(65535, max(1024, port))
        for key in (
            "start_minimized",
            "autostart_zapret",
            "autostart_windows",
            "close_to_tray",
            "bridge_enabled",
            "auto_check_zapret",
            "auto_install_zapret",
            "auto_update_zapret",
        ):
            self._data[key] = bool(self._data.get(key, self.DEFAULTS[key]))

    def _backup_broken_config(self) -> None:
        try:
            broken = self._config_path.with_suffix(".broken.json")
            self._config_path.replace(broken)
        except OSError:
            pass

    def save(self) -> None:
        with self._lock:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{self._config_path.name}.", suffix=".tmp", dir=self._config_path.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                    json.dump(self._data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self._config_path)
            finally:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._sanitize()
            self.save()

    def update(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._data.update(values)
            self._sanitize()
            self.save()

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    @property
    def zapret_path(self) -> str:
        configured = str(self.get("zapret_path", "")).strip()
        if configured and self._looks_like_zapret(Path(configured)):
            return str(Path(configured).resolve())

        detected = self._auto_detect_zapret()
        if detected:
            self.set("zapret_path", detected)
            return detected
        return configured if configured and Path(configured).exists() else ""

    @staticmethod
    def _looks_like_zapret(path: Path) -> bool:
        return path.is_dir() and (
            (path / "winws.exe").exists()
            or any(path.glob("general*.bat"))
            or (path / "lists").is_dir()
        )

    def _auto_detect_zapret(self) -> Optional[str]:
        roots: list[Path] = []
        if getattr(sys, "frozen", False):
            roots.append(Path(sys.executable).resolve().parent)
        roots.extend([
            Path.cwd(),
            Path(__file__).resolve().parents[1],
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Integra" / "zapret",
            Path.home() / "zapret-discord-youtube",
            Path.home() / "Documents" / "zapret-discord-youtube",
            Path.home() / "Downloads" / "zapret-discord-youtube",
            Path("C:/zapret-discord-youtube"),
            Path("C:/Tools/zapret-discord-youtube"),
        ])
        for candidate in roots:
            if self._looks_like_zapret(candidate):
                return str(candidate.resolve())
        return None
