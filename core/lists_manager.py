#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Безопасное управление списками доменов и IP."""

from __future__ import annotations

import ipaddress
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

from core.domain_utils import normalize_host
from core.i18n import tr


class ListsManager:
    LIST_FILES = {
        "list-general": "list-general.txt",
        "list-exclude": "list-exclude.txt",
        "list-google": "list-google.txt",
        "ipset-all": "ipset-all.txt",
        "ipset-exclude": "ipset-exclude.txt",
    }

    def __init__(self, zapret_path: str = ""):
        self._lock = threading.RLock()
        self._callbacks: list[Callable[[str, int], None]] = []
        self.set_path(zapret_path)

    def on_updated(self, callback: Callable[[str, int], None]) -> None:
        self._callbacks.append(callback)

    def _emit_updated(self, list_name: str) -> None:
        count = self.get_count(list_name)
        for callback in tuple(self._callbacks):
            try:
                callback(list_name, count)
            except Exception:
                pass

    def set_path(self, path: str) -> None:
        with self._lock:
            self.zapret_path = Path(path).expanduser() if path else Path.cwd()
            self.lists_dir = self.zapret_path / "lists"

    def get_list_path(self, list_name: str, create: bool = False) -> Optional[Path]:
        filename = self.LIST_FILES.get(list_name)
        if not filename:
            return None
        path = self.lists_dir / filename
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        return path

    def read_list(self, list_name: str) -> list[str]:
        path = self.get_list_path(list_name)
        if not path or not path.exists():
            return []
        with self._lock:
            try:
                result: list[str] = []
                seen: set[str] = set()
                for raw_line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    key = line.casefold()
                    if key not in seen:
                        result.append(line)
                        seen.add(key)
                return result
            except OSError:
                return []


    @staticmethod
    def _normalize_entry(list_name: str, value: str) -> str:
        raw = (value or "").strip()
        if list_name.startswith("ipset-"):
            if not raw:
                raise ValueError(tr("core.enter_ip"))
            try:
                if "/" in raw:
                    return str(ipaddress.ip_network(raw, strict=False))
                return ipaddress.ip_address(raw).compressed
            except ValueError as exc:
                raise ValueError(tr("core.invalid_ip")) from exc
        return normalize_host(raw, allow_ip=True)

    def contains(self, list_name: str, value: str) -> bool:
        try:
            normalized = self._normalize_entry(list_name, value)
        except ValueError:
            normalized = value.strip().lower()
        return normalized.casefold() in {item.casefold() for item in self.read_list(list_name)}

    def add_domain(self, list_name: str, domain: str) -> tuple[bool, str]:
        try:
            normalized = self._normalize_entry(list_name, domain)
        except ValueError as exc:
            return False, str(exc)

        path = self.get_list_path(list_name, create=True)
        if path is None:
            return False, tr("core.unknown_list")

        with self._lock:
            if self.contains(list_name, normalized):
                return False, tr("core.duplicate_entry")
            try:
                needs_newline = False
                if path.stat().st_size > 0:
                    with path.open("rb") as source:
                        source.seek(-1, os.SEEK_END)
                        needs_newline = source.read(1) not in (b"\n", b"\r")
                with path.open("a", encoding="utf-8", newline="\n") as handle:
                    if needs_newline:
                        handle.write("\n")
                    handle.write(normalized + "\n")
            except OSError as exc:
                return False, tr("core.write_failed", error=exc)

        self._emit_updated(list_name)
        return True, normalized

    def remove_domain(self, list_name: str, domain: str) -> tuple[bool, str]:
        path = self.get_list_path(list_name)
        if not path or not path.exists():
            return False, tr("core.list_missing")
        target = domain.strip().casefold()

        with self._lock:
            try:
                source_lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
                output: list[str] = []
                removed = False
                for raw in source_lines:
                    stripped = raw.strip()
                    if stripped and not stripped.startswith("#") and stripped.casefold() == target:
                        removed = True
                        continue
                    output.append(raw)
                if not removed:
                    return False, tr("core.entry_missing")
                self._atomic_write(path, "\n".join(output).rstrip() + ("\n" if output else ""))
            except OSError as exc:
                return False, tr("core.edit_failed", error=exc)

        self._emit_updated(list_name)
        return True, domain

    def remove_from_all(self, domain: str) -> int:
        removed = 0
        for list_name in ("list-general", "list-exclude"):
            ok, _ = self.remove_domain(list_name, domain)
            removed += int(ok)
        return removed

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def get_count(self, list_name: str) -> int:
        return len(self.read_list(list_name))
