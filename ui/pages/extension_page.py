#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Browser extension setup page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.bridge_server import BridgeServer
from core.i18n import tr
from ui.widgets.common import Card, PageHeader, divider, section_label


class ExtensionPage(QWidget):
    notification = Signal(str, str)
    bridge_toggled = Signal(bool)

    def __init__(self, bridge: BridgeServer, extension_path: Path, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.extension_path = extension_path
        self._setup_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_status)
        self._timer.start(1000)
        self.retranslate_ui()
        self.refresh_status()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 30)
        root.setSpacing(18)
        self.header = PageHeader("", "")
        root.addWidget(self.header)

        self.bridge_section = section_label("")
        root.addWidget(self.bridge_section)
        status_card = Card(hero=True)
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(22, 20, 22, 20)
        self.status_dot = QFrame()
        self.status_dot.setObjectName("BridgeStatusDot")
        self.status_dot.setProperty("running", False)
        self.status_dot.setFixedSize(12, 12)
        self.status_text = QLabel()
        self.status_text.setObjectName("HeroTitle")
        self.endpoint_label = QLabel()
        self.endpoint_label.setProperty("muted", True)
        status_text_layout = QVBoxLayout()
        status_text_layout.addWidget(self.status_text)
        status_text_layout.addWidget(self.endpoint_label)
        self.start_button = QPushButton()
        self.start_button.setProperty("role", "primary")
        status_layout.addWidget(self.status_dot)
        status_layout.addLayout(status_text_layout, 1)
        status_layout.addWidget(self.start_button)
        root.addWidget(status_card)

        self.pair_section = section_label("")
        root.addWidget(self.pair_section)
        pair_card = Card(variant="accent")
        pair_layout = QVBoxLayout(pair_card)
        pair_layout.setContentsMargins(20, 18, 20, 18)
        pair_layout.setSpacing(12)
        self.pair_hint = QLabel()
        self.pair_hint.setProperty("muted", True)
        self.pair_hint.setWordWrap(True)
        self.code_label = QLabel("000000")
        self.code_label.setObjectName("MetricValue")
        self.code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.expires_label = QLabel()
        self.expires_label.setProperty("muted", True)
        pair_actions = QHBoxLayout()
        self.copy_button = QPushButton()
        self.copy_button.setProperty("role", "primary")
        self.regenerate_button = QPushButton()
        pair_actions.addWidget(self.copy_button)
        pair_actions.addWidget(self.regenerate_button)
        pair_actions.addStretch()
        pair_layout.addWidget(self.pair_hint)
        pair_layout.addWidget(self.code_label)
        pair_layout.addWidget(self.expires_label)
        pair_layout.addLayout(pair_actions)
        root.addWidget(pair_card)

        self.install_section = section_label("")
        root.addWidget(self.install_section)
        install_card = Card()
        install_layout = QVBoxLayout(install_card)
        install_layout.setContentsMargins(20, 18, 20, 18)
        install_layout.setSpacing(12)
        self.instructions = QLabel()
        self.instructions.setWordWrap(True)
        install_layout.addWidget(self.instructions)
        install_layout.addWidget(divider())
        self.path_label = QLabel(str(self.extension_path))
        self.path_label.setProperty("muted", True)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        install_layout.addWidget(self.path_label)
        self.open_folder_button = QPushButton()
        self.open_folder_button.setProperty("role", "primary")
        install_layout.addWidget(self.open_folder_button, 0, Qt.AlignLeft)
        root.addWidget(install_card)
        root.addStretch()

        self.start_button.clicked.connect(self._toggle_bridge)
        self.copy_button.clicked.connect(self._copy_code)
        self.regenerate_button.clicked.connect(self._regenerate)
        self.open_folder_button.clicked.connect(self._open_folder)

    def set_bridge(self, bridge: BridgeServer) -> None:
        self.bridge = bridge
        self.refresh_status()

    def refresh_status(self) -> None:
        running = self.bridge.is_running
        self.status_dot.setProperty("running", running)
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)
        self.status_text.setText(tr("extension.bridge_running") if running else tr("extension.bridge_stopped"))
        self.endpoint_label.setText(f"http://127.0.0.1:{self.bridge.port}" if running else tr("extension.endpoint_off"))
        self.start_button.setText(tr("extension.stop") if running else tr("extension.start"))
        self.start_button.setProperty("role", "danger" if running else "primary")
        self.start_button.style().unpolish(self.start_button)
        self.start_button.style().polish(self.start_button)
        self.code_label.setText(self.bridge.pairing_code)
        seconds = self.bridge.pairing_expires_in
        self.expires_label.setText(tr("extension.expires", time=f"{seconds // 60:02d}:{seconds % 60:02d}"))

    def _toggle_bridge(self) -> None:
        if self.bridge.is_running:
            self.bridge.stop()
            self.bridge_toggled.emit(False)
            self.notification.emit(tr("extension.stopped_notice"), "info")
        else:
            ok, message = self.bridge.start()
            if ok:
                self.bridge_toggled.emit(True)
            self.notification.emit(message, "success" if ok else "error")
        self.refresh_status()

    def _copy_code(self) -> None:
        QApplication.clipboard().setText(self.bridge.pairing_code)
        self.notification.emit(tr("extension.code_copied"), "success")

    def _regenerate(self) -> None:
        self.bridge.regenerate_pairing_code()
        self.refresh_status()
        self.notification.emit(tr("extension.code_created"), "info")

    def _open_folder(self) -> None:
        if self.extension_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.extension_path.resolve())))
        else:
            self.notification.emit(tr("extension.folder_missing"), "error")

    def retranslate_ui(self) -> None:
        self.header.set_text(tr("extension.title"), tr("extension.subtitle"))
        self.bridge_section.setText(tr("extension.bridge_section").upper())
        self.pair_section.setText(tr("extension.pair_section").upper())
        self.pair_hint.setText(tr("extension.pair_hint"))
        self.copy_button.setText(tr("extension.copy_code"))
        self.regenerate_button.setText(tr("extension.new_code"))
        self.install_section.setText(tr("extension.install_section").upper())
        self.instructions.setText(tr("extension.instructions"))
        self.open_folder_button.setText(tr("extension.open_folder"))
        self.refresh_status()
