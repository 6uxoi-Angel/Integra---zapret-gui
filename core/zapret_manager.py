#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Управление процессом и службой zapret на Windows."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import IO, Optional

import psutil
from PySide6.QtCore import QObject, Signal

from core.i18n import tr
from core.windows_process import (
    build_hidden_runtime_batch,
    hidden_subprocess_options,
    is_windows_admin,
)


class ZapretManager(QObject):
    status_changed = Signal(str, int)
    log_message = Signal(str, str)
    strategy_changed = Signal(str)
    error_occurred = Signal(str)

    STATUS_STOPPED = "stopped"
    STATUS_RUNNING = "running"
    STATUS_SERVICE = "service"

    def __init__(self, zapret_path: str = ""):
        super().__init__()
        self.zapret_path = Path(zapret_path).expanduser() if zapret_path else Path.cwd()
        self._launcher: Optional[subprocess.Popen] = None
        self._launcher_log: Optional[IO[bytes]] = None
        self._launcher_log_path = Path(tempfile.gettempdir()) / "Integra" / "zapret-launch.log"
        self._runtime_batch: Optional[Path] = None
        self._current_strategy = ""
        self._status = self.STATUS_STOPPED
        self._service_cache_at = 0.0
        self._service_cache = (False, False)

    @property
    def current_strategy(self) -> str:
        return self._current_strategy

    def set_zapret_path(self, path: str) -> None:
        new_path = Path(path).expanduser() if path else Path.cwd()
        try:
            unchanged = new_path.resolve() == self.zapret_path.resolve()
        except OSError:
            unchanged = new_path == self.zapret_path
        self.zapret_path = new_path
        if not unchanged:
            self.log_message.emit("INFO", tr("zapret.path_changed", path=self.zapret_path))

    def _winws_path(self) -> Optional[Path]:
        candidates = (
            self.zapret_path / "bin" / "winws.exe",
            self.zapret_path / "winws.exe",
        )
        return next((path for path in candidates if path.is_file()), None)

    def validate_path(self) -> tuple[bool, str]:
        if os.name != "nt":
            return False, tr("zapret.windows_only")
        if not self.zapret_path.is_dir():
            return False, tr("zapret.path_missing")
        if not any(self.zapret_path.glob("general*.bat")):
            return False, tr("zapret.no_bat")
        if self._winws_path() is None:
            return False, tr("zapret.no_winws")
        return True, ""

    @staticmethod
    def _iter_winws():
        try:
            for proc in psutil.process_iter(["pid", "name", "exe"]):
                if (proc.info.get("name") or "").casefold() == "winws.exe":
                    yield proc
        except (psutil.Error, OSError):
            return

    def get_status(self) -> str:
        process = next(iter(self._iter_winws()), None)
        if process is not None:
            self._status = self.STATUS_SERVICE if self.is_service_running() else self.STATUS_RUNNING
        elif self.is_service_running():
            self._status = self.STATUS_SERVICE
        else:
            self._status = self.STATUS_STOPPED
        return self._status

    def get_pid(self) -> int:
        process = next(iter(self._iter_winws()), None)
        return int(process.info.get("pid", 0)) if process else 0

    def refresh_status(self) -> tuple[str, int]:
        status = self.get_status()
        pid = self.get_pid()
        self.status_changed.emit(status, pid)
        return status, pid

    def get_strategies(self) -> list[dict[str, str]]:
        if not self.zapret_path.is_dir():
            return []
        strategies: list[dict[str, str]] = []
        for bat_file in sorted(self.zapret_path.glob("general*.bat"), key=lambda p: p.name.casefold()):
            stem = bat_file.stem
            upper = stem.upper()
            if "FAKE TLS" in upper or "FAKE_TLS" in upper:
                category, label = "tls", "TLS"
            elif "SIMPLE" in upper:
                category, label = "simple", tr("home.category_simple")
            elif any(marker in upper for marker in ("ALT", "ADV", "FAKE")):
                category, label = "advanced", tr("home.category_advanced")
            else:
                category, label = "basic", tr("home.category_basic")
            strategies.append({
                "file": bat_file.name,
                "name": stem,
                "category": category,
                "category_label": label,
                "path": str(bat_file),
            })
        return strategies

    def _close_launcher_log(self) -> None:
        if self._launcher_log is not None:
            try:
                self._launcher_log.close()
            except OSError:
                pass
            self._launcher_log = None

    def _read_launcher_log_tail(self, limit: int = 1800) -> str:
        try:
            if self._launcher_log is not None:
                self._launcher_log.flush()
            raw = self._launcher_log_path.read_bytes()[-limit:]
        except OSError:
            return ""
        for encoding in ("utf-8", "cp866", "cp1251"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="replace")
        lines = [line.strip() for line in text.replace("\x00", "").splitlines() if line.strip()]
        return " | ".join(lines[-8:])

    def _prepare_runtime_strategy(self, bat_path: Path) -> Path:
        runtime = self.zapret_path / ".integra-runtime.bat"
        try:
            runtime.unlink()
        except FileNotFoundError:
            pass
        build_hidden_runtime_batch(bat_path, runtime)
        self._runtime_batch = runtime
        return runtime

    def _cleanup_runtime_strategy(self) -> None:
        runtime = self._runtime_batch
        self._runtime_batch = None
        if runtime is not None:
            try:
                runtime.unlink()
            except OSError:
                pass

    def start(self, strategy_file: str) -> bool:
        valid, message = self.validate_path()
        if not valid:
            self.error_occurred.emit(message)
            return False
        if not is_windows_admin():
            self.error_occurred.emit(tr("zapret.admin_start"))
            return False
        if self.is_service_installed(force=True):
            self.error_occurred.emit(tr("zapret.service_conflict"))
            return False

        strategy_name = Path(strategy_file).name
        bat_path = self.zapret_path / strategy_name
        if bat_path.suffix.casefold() != ".bat" or not bat_path.is_file():
            self.error_occurred.emit(tr("zapret.strategy_missing", strategy=strategy_name))
            return False

        try:
            self.stop(emit_when_already_stopped=False)
            runtime_batch = self._prepare_runtime_strategy(bat_path)
            self._launcher_log_path.parent.mkdir(parents=True, exist_ok=True)
            self._close_launcher_log()
            self._launcher_log = self._launcher_log_path.open("w+b")
            env = os.environ.copy()
            env["NO_UPDATE_CHECK"] = "1"
            command = ["cmd.exe", "/d", "/q", "/c", "call", str(runtime_batch)]
            self._launcher = subprocess.Popen(
                command,
                cwd=str(self.zapret_path),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=self._launcher_log,
                stderr=subprocess.STDOUT,
                close_fds=True,
                **hidden_subprocess_options(),
            )

            deadline = time.monotonic() + 7.0
            while time.monotonic() < deadline:
                if self.get_pid():
                    break
                code = self._launcher.poll()
                if code is not None:
                    details = self._read_launcher_log_tail()
                    self._launcher = None
                    self._close_launcher_log()
                    self._cleanup_runtime_strategy()
                    suffix = tr("zapret.output", details=details) if details else tr("zapret.launch_hint")
                    self.error_occurred.emit(tr("zapret.exit_code", code=code, suffix=suffix))
                    return False
                time.sleep(0.15)

            pid = self.get_pid()
            if not pid:
                details = self._read_launcher_log_tail()
                self.stop(emit_when_already_stopped=False)
                suffix = " " + tr("zapret.output", details=details).lstrip(". ") if details else ""
                self.error_occurred.emit(tr("zapret.timeout", suffix=suffix))
                return False

            self._current_strategy = strategy_name
            self.strategy_changed.emit(strategy_name)
            self._status = self.STATUS_RUNNING
            self.status_changed.emit(self.STATUS_RUNNING, pid)
            self.log_message.emit("SUCCESS", tr("zapret.started", strategy=strategy_name, pid=pid))
            return True
        except (OSError, ValueError) as exc:
            self._launcher = None
            self._close_launcher_log()
            self._cleanup_runtime_strategy()
            self.error_occurred.emit(tr("zapret.start_failed", error=exc))
            return False

    def stop(self, emit_when_already_stopped: bool = True) -> bool:
        killed = 0
        errors: list[str] = []
        for proc in list(self._iter_winws()):
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
                killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired) as exc:
                errors.append(str(exc))

        if self._launcher is not None:
            try:
                if self._launcher.poll() is None:
                    self._launcher.terminate()
                    self._launcher.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self._launcher.kill()
                except OSError:
                    pass
            self._launcher = None

        self._close_launcher_log()
        self._cleanup_runtime_strategy()
        self._status = self.STATUS_STOPPED
        self.status_changed.emit(self.STATUS_STOPPED, 0)
        if killed:
            self.log_message.emit("INFO", tr("zapret.stopped_count", count=killed))
        elif emit_when_already_stopped:
            self.log_message.emit("INFO", tr("zapret.already_stopped"))
        if errors:
            self.error_occurred.emit(tr("zapret.stop_partial", errors="; ".join(errors)))
            return False
        return True

    def _run_batch(
        self,
        filename: str,
        extra_args: Optional[list[str]] = None,
        *,
        input_text: Optional[str] = None,
        timeout: int = 90,
    ) -> subprocess.CompletedProcess:
        path = self.zapret_path / filename
        if not path.is_file():
            raise FileNotFoundError(filename)
        command = ["cmd.exe", "/d", "/q", "/c", "call", str(path)]
        if extra_args:
            command.extend(extra_args)
        env = os.environ.copy()
        env["NO_UPDATE_CHECK"] = "1"
        return subprocess.run(
            command,
            cwd=str(self.zapret_path),
            input=input_text,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            env=env,
            **hidden_subprocess_options(),
        )

    @staticmethod
    def _natural_key(name: str):
        return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", name)]

    def install_service(self, strategy_file: str) -> bool:
        valid, message = self.validate_path()
        if not valid:
            self.error_occurred.emit(message)
            return False
        if not is_windows_admin():
            self.error_occurred.emit(tr("zapret.admin_install"))
            return False

        strategy_name = Path(strategy_file).name
        try:
            # Runtime-файл после аварийного завершения не должен попадать в меню service.bat.
            try:
                (self.zapret_path / ".integra-runtime.bat").unlink()
            except FileNotFoundError:
                pass
            if (self.zapret_path / "service_install.bat").is_file():
                result = self._run_batch("service_install.bat", [strategy_name], timeout=150)
            elif (self.zapret_path / "service.bat").is_file():
                candidates = sorted(
                    [
                        p.name
                        for p in self.zapret_path.glob("*.bat")
                        if not p.name.casefold().startswith("service")
                        and not p.name.casefold().startswith(".integra-")
                    ],
                    key=self._natural_key,
                )
                if strategy_name not in candidates:
                    raise FileNotFoundError(strategy_name)
                index = candidates.index(strategy_name) + 1
                # 1 — установка, затем индекс стратегии, Enter для pause и 0 — выход.
                scripted_input = f"1\r\n{index}\r\n\r\n0\r\n"
                result = self._run_batch("service.bat", ["admin"], input_text=scripted_input, timeout=180)
            else:
                raise FileNotFoundError("service.bat")
        except (OSError, subprocess.SubprocessError) as exc:
            self.error_occurred.emit(tr("zapret.install_failed", error=exc))
            return False

        self._service_cache_at = 0.0
        installed, running = self._query_service(force=True)
        if not installed:
            details = (result.stderr or result.stdout or tr("zapret.unknown_error")).strip()[-1200:]
            self.error_occurred.emit(tr("zapret.install_error", details=details))
            return False
        self._current_strategy = strategy_name
        self._status = self.STATUS_SERVICE if running else self.STATUS_STOPPED
        self.status_changed.emit(self._status, self.get_pid())
        self.log_message.emit("SUCCESS", tr("zapret.service_installed", running=tr("zapret.and_started") if running else ""))
        return True

    def _run_system_command(self, command: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            **hidden_subprocess_options(),
        )

    def remove_service(self) -> bool:
        if os.name != "nt":
            self.error_occurred.emit(tr("zapret.service_windows_only"))
            return False
        if not is_windows_admin():
            self.error_occurred.emit(tr("zapret.admin_remove"))
            return False
        try:
            self._run_system_command(["sc", "stop", "zapret"])
            self._run_system_command(["taskkill", "/IM", "winws.exe", "/F"])
            self._run_system_command(["sc", "delete", "zapret"])
            for service in ("WinDivert", "WinDivert14"):
                self._run_system_command(["sc", "stop", service])
                self._run_system_command(["sc", "delete", service])
        except (OSError, subprocess.SubprocessError) as exc:
            self.error_occurred.emit(tr("zapret.remove_failed", error=exc))
            return False

        self._service_cache_at = 0.0
        installed = True
        for _ in range(10):
            installed, _ = self._query_service(force=True)
            if not installed:
                break
            time.sleep(0.3)
        if installed:
            self.error_occurred.emit(tr("zapret.remove_retry"))
            return False
        self._status = self.STATUS_STOPPED
        self.status_changed.emit(self.STATUS_STOPPED, 0)
        self.log_message.emit("INFO", tr("zapret.service_removed"))
        return True

    def is_service_installed(self, force: bool = False) -> bool:
        return self._query_service(force=force)[0]

    def is_service_running(self, force: bool = False) -> bool:
        installed, running = self._query_service(force=force)
        return installed and running

    def _query_service(self, force: bool = False) -> tuple[bool, bool]:
        if os.name != "nt":
            return False, False
        now = time.monotonic()
        if not force and now - self._service_cache_at < 5.0:
            return self._service_cache
        try:
            result = subprocess.run(
                ["sc", "query", "zapret"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=4,
                **hidden_subprocess_options(),
            )
        except (OSError, subprocess.SubprocessError):
            self._service_cache_at = now
            self._service_cache = (False, False)
            return self._service_cache
        output = result.stdout.upper()
        installed = result.returncode == 0 and "SERVICE_NAME" in output
        running = installed and re.search(r"STATE\s*:\s*4\s+RUNNING", output) is not None
        self._service_cache_at = now
        self._service_cache = (installed, running)
        return self._service_cache
