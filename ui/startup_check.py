#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A compact launch window that explains local readiness checks."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.config import Config
from core.i18n import tr
from core.paths import resource_path
from core.preflight import StartupCheck, collect_startup_checks


class _CheckRow(QFrame):
    def __init__(self, check: StartupCheck, parent=None):
        super().__init__(parent)
        self.setObjectName("StartupCheckRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        icon = QLabel({"ok": "✓", "warning": "!", "error": "×"}.get(check.status, "•"))
        icon.setObjectName("StartupCheckIcon")
        icon.setText({"ok": "OK", "warning": "!", "error": "X"}.get(check.status, "i"))
        icon.setProperty("status", check.status)
        icon.setFixedSize(22, 22)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(check.title)
        title.setObjectName("StartupCheckTitle")
        detail = QLabel(check.detail)
        detail.setObjectName("StartupCheckDetail")
        detail.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(detail)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)


class StartupCheckDialog(QDialog):
    """Shows the checks briefly, then continues to the main window."""

    def __init__(self, config: Config, auto_continue_ms: int = 1200, parent=None):
        super().__init__(parent)
        self.config = config
        self.auto_continue_ms = max(0, int(auto_continue_ms))
        self._checks: tuple[StartupCheck, ...] = ()
        self.setObjectName("StartupCheckDialog")
        self.setWindowTitle("Integra")
        self.setModal(True)
        self.setMinimumWidth(510)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._setup_ui()
        QTimer.singleShot(0, self._run_checks)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        mark = QLabel()
        mark.setObjectName("StartupMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(44, 44)
        avatar = QPixmap(str(resource_path("assets/integra-avatar.png")))
        if not avatar.isNull():
            mark.setPixmap(avatar.scaled(44, 44, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        heading = QVBoxLayout()
        heading.setSpacing(2)
        title = QLabel(tr("preflight.title"))
        title.setObjectName("StartupTitle")
        subtitle = QLabel(tr("preflight.subtitle"))
        subtitle.setObjectName("StartupSubtitle")
        subtitle.setWordWrap(True)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addWidget(mark)
        header.addLayout(heading, 1)
        root.addLayout(header)

        self.checks_host = QWidget()
        self.checks_layout = QVBoxLayout(self.checks_host)
        self.checks_layout.setContentsMargins(0, 0, 0, 0)
        self.checks_layout.setSpacing(7)
        root.addWidget(self.checks_host)

        self.summary = QLabel(tr("preflight.checking"))
        self.summary.setObjectName("StartupSummary")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        self.launch_button = QPushButton(tr("preflight.launch"))
        self.launch_button.setObjectName("StartupLaunchButton")
        self.launch_button.clicked.connect(self.accept)
        root.addWidget(self.launch_button, 0, Qt.AlignmentFlag.AlignRight)

        self.setStyleSheet(
            "QDialog#StartupCheckDialog { background: #101720; color: #edf2f7; }"
            "QLabel#StartupMark { background: #4f86f7; color: white; border-radius: 8px; font-size: 20px; font-weight: 800; }"
            "QLabel#StartupTitle { font-size: 18px; font-weight: 700; }"
            "QLabel#StartupSubtitle, QLabel#StartupCheckDetail, QLabel#StartupSummary { color: #aebdce; }"
            "QFrame#StartupCheckRow { background: #172231; border: 1px solid #293a50; border-radius: 7px; }"
            "QLabel#StartupCheckTitle { font-weight: 650; }"
            "QLabel#StartupCheckIcon[status='ok'] { color: #48c78e; background: #153a31; border-radius: 11px; font-weight: 800; }"
            "QLabel#StartupCheckIcon[status='warning'] { color: #f5bd4f; background: #40351b; border-radius: 11px; font-weight: 800; }"
            "QLabel#StartupCheckIcon[status='error'] { color: #ff7189; background: #421f2a; border-radius: 11px; font-weight: 800; }"
            "QPushButton#StartupLaunchButton { background: #4f86f7; border: 1px solid #4f86f7; border-radius: 6px; color: white; font-weight: 700; padding: 8px 16px; }"
            "QPushButton#StartupLaunchButton:hover { background: #6595f8; }"
        )

    def _run_checks(self) -> None:
        self._checks = collect_startup_checks(self.config.zapret_path)
        for check in self._checks:
            self.checks_layout.addWidget(_CheckRow(check, self.checks_host))
        if any(check.status == "error" for check in self._checks):
            self.summary.setText(tr("preflight.needs_attention"))
        elif any(check.status == "warning" for check in self._checks):
            self.summary.setText(tr("preflight.ready_with_notes"))
        else:
            self.summary.setText(tr("preflight.ready"))
        if self.auto_continue_ms:
            QTimer.singleShot(self.auto_continue_ms, self.accept)


def show_startup_check(config: Config, auto_continue_ms: int = 1200) -> bool:
    """Run the launch check window and return whether the user continued."""
    dialog = StartupCheckDialog(config, auto_continue_ms=auto_continue_ms)
    return dialog.exec() == QDialog.DialogCode.Accepted
