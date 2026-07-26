#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Background connectivity diagnostics and automatic strategy selection."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

import psutil
from PySide6.QtCore import QObject, QThread, Signal

from core.diagnostic_sites import all_sites
from core.i18n import tr
from core.network import measure_tcp_latency
from core.windows_process import hidden_subprocess_options, is_windows_admin


class DiagnosticsWorker(QThread):
    ping_result = Signal(str, bool, int)
    strategy_result = Signal(str, bool)
    progress = Signal(int, str)
    completed = Signal(bool, str)

    def __init__(
        self,
        mode: str,
        zapret_manager=None,
        strategies: Optional[list[dict]] = None,
        sites: Optional[list[dict]] = None,
    ):
        super().__init__()
        self.mode = mode
        self.zapret_manager = zapret_manager
        self.strategies = strategies or []
        self.sites = sites or all_sites([])
        self._running = True

    def run(self) -> None:
        try:
            if self.mode == "ping":
                self._run_ping_test()
            elif self.mode == "auto_find":
                self._run_auto_find()
            else:
                self.completed.emit(False, tr("diag.unknown_mode"))
        except Exception as exc:
            self.completed.emit(False, str(exc))

    def _run_ping_test(self) -> None:
        if not self.sites:
            self.completed.emit(False, tr("diag.no_sites"))
            return
        success_count = 0
        for site in self.sites:
            if not self._running:
                self.completed.emit(False, tr("diag.cancelled"))
                return
            success, latency, _ = measure_tcp_latency(str(site["host"]), int(site.get("port", 443)))
            success_count += int(success)
            self.ping_result.emit(str(site["id"]), success, latency)
        total = len(self.sites)
        self.completed.emit(
            success_count == total,
            tr("diag.completed_summary", ok=success_count, total=total),
        )

    def _run_auto_find(self) -> None:
        if not self.strategies or self.zapret_manager is None:
            self.completed.emit(False, tr("diag.no_strategies"))
            return
        if not self.sites:
            self.completed.emit(False, tr("diag.no_sites"))
            return

        previous_strategy = self.zapret_manager.current_strategy
        previous_status = self.zapret_manager.get_status()
        total = len(self.strategies)
        found = ""

        for index, strategy in enumerate(self.strategies, start=1):
            if not self._running:
                break
            filename = strategy["file"]
            self.progress.emit(round((index - 1) / total * 100), filename)
            self.zapret_manager.stop()
            if not self._running:
                break
            if not self.zapret_manager.start(filename):
                self.strategy_result.emit(filename, False)
                continue

            for _ in range(12):
                if not self._running:
                    break
                time.sleep(0.25)
            if not self._running:
                break

            success = True
            for site in self.sites:
                if not self._running:
                    success = False
                    break
                site_ok, _, _ = measure_tcp_latency(str(site["host"]), int(site.get("port", 443)))
                if not site_ok:
                    success = False
                    break
            self.strategy_result.emit(filename, success)
            if success:
                found = filename
                self.progress.emit(100, filename)
                break

        if found:
            self.completed.emit(True, found)
            return

        self.zapret_manager.stop()
        if previous_status == self.zapret_manager.STATUS_RUNNING and previous_strategy:
            self.zapret_manager.start(previous_strategy)
        self.progress.emit(100, "")
        self.completed.emit(False, tr("diag.not_found") if self._running else tr("diag.selection_cancelled"))

    def stop(self) -> None:
        self._running = False
        self.requestInterruption()


class DiagnosticsManager(QObject):
    def __init__(self, zapret_manager=None):
        super().__init__()
        self.zapret_manager = zapret_manager
        self._workers: set[DiagnosticsWorker] = set()

    def _track(self, worker: DiagnosticsWorker) -> DiagnosticsWorker:
        self._workers.add(worker)
        worker.finished.connect(lambda: self._workers.discard(worker))
        worker.start()
        return worker

    def test_connectivity(self, callback: Callable, sites: Optional[list[dict]] = None) -> DiagnosticsWorker:
        worker = DiagnosticsWorker("ping", sites=sites)
        worker.ping_result.connect(callback)
        return self._track(worker)

    def auto_find_strategy(
        self,
        strategies: list[dict],
        progress_callback: Callable,
        result_callback: Callable,
        sites: Optional[list[dict]] = None,
    ) -> DiagnosticsWorker:
        worker = DiagnosticsWorker("auto_find", self.zapret_manager, strategies, sites=sites)
        worker.progress.connect(progress_callback)
        worker.strategy_result.connect(result_callback)
        return self._track(worker)

    def stop_all(self) -> None:
        workers = tuple(self._workers)
        for worker in workers:
            worker.stop()
        for worker in workers:
            worker.wait(6000)
        self._workers = {worker for worker in self._workers if worker.isRunning()}

    def run_system_diagnostics(self) -> dict[str, bool | str]:
        zapret_path = Path(self.zapret_manager.zapret_path) if self.zapret_manager else Path.cwd()
        results: dict[str, bool | str] = {
            "platform_windows": os.name == "nt",
            "zapret_path": zapret_path.exists(),
            "winws_present": (zapret_path / "winws.exe").exists() or (zapret_path / "bin" / "winws.exe").exists(),
            "winws_running": False,
            "service_installed": False,
            "windivert_present": False,
            "admin_rights": False,
        }

        try:
            results["winws_running"] = any(
                (proc.info.get("name") or "").casefold() == "winws.exe"
                for proc in psutil.process_iter(["name"])
            )
        except (psutil.Error, OSError):
            pass

        results["windivert_present"] = any(
            p.exists()
            for p in (
                zapret_path / "WinDivert.dll",
                zapret_path / "WinDivert64.sys",
                zapret_path / "bin" / "WinDivert.dll",
                zapret_path / "bin" / "WinDivert64.sys",
            )
        )

        if os.name == "nt":
            try:
                query = subprocess.run(
                    ["sc", "query", "zapret"],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=8,
                    **hidden_subprocess_options(),
                )
                results["service_installed"] = query.returncode == 0 and "SERVICE_NAME" in query.stdout
            except (OSError, subprocess.SubprocessError):
                pass
            results["admin_rights"] = is_windows_admin()
        return results
