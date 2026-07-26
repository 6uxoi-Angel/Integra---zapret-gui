#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Localized system tray icon."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from core.i18n import tr


class TrayIcon(QSystemTrayIcon):
    show_window = Signal()
    start_zapret = Signal()
    stop_zapret = Signal()
    quit_app = Signal()

    def __init__(self, icon: QIcon, parent=None):
        super().__init__(icon, parent)
        self._status = "stopped"
        self._pid = 0
        self.menu = QMenu()
        self.show_action = QAction(self.menu)
        self.show_action.triggered.connect(self.show_window.emit)
        self.menu.addAction(self.show_action)
        self.menu.addSeparator()
        self.start_action = QAction(self.menu)
        self.start_action.triggered.connect(self.start_zapret.emit)
        self.stop_action = QAction(self.menu)
        self.stop_action.triggered.connect(self.stop_zapret.emit)
        self.stop_action.setEnabled(False)
        self.menu.addAction(self.start_action)
        self.menu.addAction(self.stop_action)
        self.menu.addSeparator()
        self.quit_action = QAction(self.menu)
        self.quit_action.triggered.connect(self.quit_app.emit)
        self.menu.addAction(self.quit_action)
        self.setContextMenu(self.menu)
        self.activated.connect(self._activated)
        self.retranslate_ui()

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.show_window.emit()

    def update_status(self, status: str, pid: int = 0) -> None:
        self._status = status
        self._pid = pid
        running = status in {"running", "service"}
        if status == "service":
            self.setToolTip(tr("tray.tooltip_service"))
        elif running:
            self.setToolTip(tr("tray.tooltip_running", pid=f" · PID {pid}" if pid else ""))
        else:
            self.setToolTip(tr("tray.tooltip_stopped"))
        self.start_action.setEnabled(not running)
        self.stop_action.setEnabled(status == "running")

    def retranslate_ui(self) -> None:
        self.show_action.setText(tr("tray.open"))
        self.start_action.setText(tr("tray.start"))
        self.stop_action.setText(tr("tray.stop"))
        self.quit_action.setText(tr("tray.quit"))
        self.update_status(self._status, self._pid)
