#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Non-blocking execution of short application operations."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

from core.zapret_maintenance import MaintenanceResult, ZapretMaintenance


class FunctionWorker(QThread):
    completed = Signal(bool, str)

    def __init__(
        self,
        function: Callable[[], bool],
        success_message: str = "",
        failure_message: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.function = function
        self.success_message = success_message
        self.failure_message = failure_message

    def run(self) -> None:
        try:
            result = bool(self.function())
            self.completed.emit(result, self.success_message if result else self.failure_message)
        except Exception as exc:
            self.completed.emit(False, str(exc))


class ZapretMaintenanceWorker(QThread):
    """Runs release checks and archive work without blocking the Qt event loop."""

    completed = Signal(object)

    def __init__(
        self,
        maintenance: ZapretMaintenance,
        configured_path: str,
        *,
        auto_install: bool,
        auto_update: bool,
        check_remote: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.maintenance = maintenance
        self.configured_path = configured_path
        self.auto_install = auto_install
        self.auto_update = auto_update
        self.check_remote = check_remote

    def run(self) -> None:
        try:
            result = self.maintenance.maintain(
                self.configured_path,
                auto_install=self.auto_install,
                auto_update=self.auto_update,
                check_remote=self.check_remote,
            )
        except Exception as exc:
            result = MaintenanceResult("error", self.configured_path, detail=str(exc))
        self.completed.emit(result)
