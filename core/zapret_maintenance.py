#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safe checks, installation, and updates for the official Zapret release."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


RELEASES_API_URL = "https://api.github.com/repos/Flowseal/zapret-discord-youtube/releases/latest"
METADATA_FILENAME = ".integra-zapret.json"
MAX_ARCHIVE_BYTES = 600 * 1024 * 1024
MAX_UNPACKED_BYTES = 1_200 * 1024 * 1024
VERSION_RE = re.compile(r"\b(?:v(?:ersion)?\s*)?(\d+(?:\.\d+)+(?:[-+][A-Za-z0-9.-]+)?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ZapretRelease:
    version: str
    archive_url: str


@dataclass(frozen=True)
class MaintenanceResult:
    state: str
    path: str = ""
    installed_version: str = ""
    latest_version: str = ""
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.state not in {"error", "invalid", "blocked"}


class ZapretMaintenance:
    """Maintains only a verified archive from Flowseal's official GitHub release."""

    def __init__(self, releases_api_url: str = RELEASES_API_URL):
        self.releases_api_url = releases_api_url

    @staticmethod
    def default_install_path() -> Path:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Integra" / "zapret"

    @staticmethod
    def is_valid_installation(path: Path) -> bool:
        return path.is_dir() and any(path.glob("general*.bat")) and any(
            (path / candidate).is_file() for candidate in ("winws.exe", "bin/winws.exe")
        )

    @staticmethod
    def is_managed_installation(path: Path) -> bool:
        return (path / METADATA_FILENAME).is_file()

    @staticmethod
    def _normalize_version(value: str) -> str:
        return value.strip().lstrip("vV")

    @classmethod
    def _version_key(cls, value: str) -> tuple[int, ...] | None:
        match = VERSION_RE.search(cls._normalize_version(value))
        if not match:
            return None
        try:
            return tuple(int(item) for item in match.group(1).split("-", 1)[0].split("+", 1)[0].split("."))
        except ValueError:
            return None

    @classmethod
    def is_newer(cls, installed: str, latest: str) -> bool:
        installed_key = cls._version_key(installed)
        latest_key = cls._version_key(latest)
        if not installed_key or not latest_key:
            return False
        width = max(len(installed_key), len(latest_key))
        return latest_key + (0,) * (width - len(latest_key)) > installed_key + (0,) * (width - len(installed_key))

    def installed_version(self, path: Path) -> str:
        metadata = path / METADATA_FILENAME
        try:
            payload = json.loads(metadata.read_text(encoding="utf-8"))
            version = str(payload.get("version", "")).strip()
            if self._version_key(version):
                return self._normalize_version(version)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass

        for candidate in ("version.txt", "VERSION", "VERSION.txt", "README.md", "readme.md"):
            try:
                content = (path / candidate).read_text(encoding="utf-8", errors="ignore")[:4096]
            except OSError:
                continue
            match = VERSION_RE.search(content)
            if match:
                return self._normalize_version(match.group(1))

        for candidate in (path, path.parent):
            match = VERSION_RE.search(candidate.name)
            if match:
                return self._normalize_version(match.group(1))
        return ""

    def fetch_latest_release(self) -> ZapretRelease:
        request = urllib.request.Request(
            self.releases_api_url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Integra/2.2"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(str(exc)) from exc

        version = self._normalize_version(str(payload.get("tag_name", "")))
        if not self._version_key(version):
            raise RuntimeError("Release version is missing or invalid")
        assets = payload.get("assets", [])
        if not isinstance(assets, list):
            raise RuntimeError("Release archive is missing")
        for asset in assets:
            name = str(asset.get("name", "")).casefold()
            url = str(asset.get("browser_download_url", ""))
            if name.endswith(".zip") and "zapret" in name and url.startswith("https://"):
                return ZapretRelease(version, url)
        raise RuntimeError("Windows ZIP archive is missing")

    def check(self, path: str, *, check_remote: bool) -> MaintenanceResult:
        root = Path(path).expanduser() if path else self.default_install_path()
        if not self.is_valid_installation(root):
            return MaintenanceResult("missing", str(root))

        installed_version = self.installed_version(root)
        if not check_remote:
            return MaintenanceResult("local", str(root), installed_version)
        try:
            release = self.fetch_latest_release()
        except RuntimeError as exc:
            return MaintenanceResult("error", str(root), installed_version, detail=str(exc))
        if not installed_version:
            return MaintenanceResult("unknown_version", str(root), latest_version=release.version)
        if self.is_newer(installed_version, release.version):
            return MaintenanceResult("update_available", str(root), installed_version, release.version)
        return MaintenanceResult("up_to_date", str(root), installed_version, release.version)

    def maintain(
        self,
        configured_path: str,
        *,
        auto_install: bool,
        auto_update: bool,
        check_remote: bool,
    ) -> MaintenanceResult:
        root = Path(configured_path).expanduser() if configured_path else self.default_install_path()
        ready = self.is_valid_installation(root)
        if root.exists() and not ready:
            return MaintenanceResult("invalid", str(root))

        needs_release = check_remote or (auto_install and not ready) or (auto_update and ready)
        release: ZapretRelease | None = None
        if needs_release:
            try:
                release = self.fetch_latest_release()
            except RuntimeError as exc:
                return MaintenanceResult("error", str(root), detail=str(exc))

        if not ready:
            if not auto_install:
                return MaintenanceResult("missing", str(root), latest_version=release.version if release else "")
            assert release is not None
            try:
                self._install_release(release, root)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                return MaintenanceResult("error", str(root), latest_version=release.version, detail=str(exc))
            return MaintenanceResult("installed", str(root), release.version, release.version)

        installed_version = self.installed_version(root)
        assert release is not None or not needs_release
        if release is None:
            return MaintenanceResult("local", str(root), installed_version)
        if not installed_version:
            return MaintenanceResult("unknown_version", str(root), latest_version=release.version)
        if not self.is_newer(installed_version, release.version):
            return MaintenanceResult("up_to_date", str(root), installed_version, release.version)
        if not auto_update:
            return MaintenanceResult("update_available", str(root), installed_version, release.version)
        try:
            self._install_release(release, root)
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            return MaintenanceResult("error", str(root), installed_version, release.version, str(exc))
        return MaintenanceResult("updated", str(root), release.version, release.version)

    def _download_archive(self, release: ZapretRelease, destination: Path) -> None:
        request = urllib.request.Request(release.archive_url, headers={"User-Agent": "Integra/2.2"})
        total = 0
        try:
            with urllib.request.urlopen(request, timeout=45) as source, destination.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise RuntimeError("Release archive is too large")
                    target.write(chunk)
        except (OSError, urllib.error.URLError) as exc:
            raise RuntimeError(str(exc)) from exc

    @staticmethod
    def _safe_extract(archive: Path, destination: Path) -> None:
        with zipfile.ZipFile(archive) as source:
            total = 0
            for item in source.infolist():
                relative = PurePosixPath(item.filename)
                if relative.is_absolute() or ".." in relative.parts:
                    raise RuntimeError("Release archive contains an unsafe path")
                mode = item.external_attr >> 16
                if mode and (mode & 0o170000) == 0o120000:
                    raise RuntimeError("Release archive contains symbolic links")
                total += item.file_size
                if total > MAX_UNPACKED_BYTES:
                    raise RuntimeError("Release archive is too large after unpacking")
            source.extractall(destination)

    def _find_install_root(self, directory: Path) -> Path:
        if self.is_valid_installation(directory):
            return directory
        matches = [child for child in directory.iterdir() if child.is_dir() and self.is_valid_installation(child)]
        if len(matches) != 1:
            raise RuntimeError("Release archive has an unexpected structure")
        return matches[0]

    @staticmethod
    def _preserve_lists(source: Path, destination: Path) -> None:
        old_lists = source / "lists"
        if not old_lists.is_dir():
            return
        new_lists = destination / "lists"
        for item in old_lists.rglob("*"):
            if not item.is_file():
                continue
            relative = item.relative_to(old_lists)
            target = new_lists / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

    @staticmethod
    def _write_metadata(directory: Path, release: ZapretRelease) -> None:
        payload = {
            "version": release.version,
            "source": release.archive_url,
            "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        (directory / METADATA_FILENAME).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _install_release(self, release: ZapretRelease, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".integra-zapret-", dir=str(target.parent)) as temporary:
            temporary_root = Path(temporary)
            archive = temporary_root / "release.zip"
            unpacked = temporary_root / "unpacked"
            unpacked.mkdir()
            self._download_archive(release, archive)
            self._safe_extract(archive, unpacked)
            staged_root = self._find_install_root(unpacked)
            if target.exists():
                self._preserve_lists(target, staged_root)
            self._write_metadata(staged_root, release)

            backup = target.with_name(f"{target.name}.backup")
            if backup.exists():
                shutil.rmtree(backup)
            if target.exists():
                target.replace(backup)
            try:
                staged_root.replace(target)
            except OSError:
                if backup.exists():
                    backup.replace(target)
                raise
            shutil.rmtree(backup, ignore_errors=True)
