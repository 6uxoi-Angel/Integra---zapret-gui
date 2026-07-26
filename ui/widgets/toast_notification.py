#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Theme-aware non-blocking toast notification."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


class ToastNotification(QFrame):
    def __init__(self, message: str, toast_type: str = "info", parent=None):
        super().__init__(parent)
        normalized = toast_type if toast_type in {"success", "error", "warning", "info"} else "info"
        self.setProperty("type", normalized)
        self.setMinimumWidth(310)
        self.setMaximumWidth(420)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 16, 11)
        layout.setSpacing(10)
        icons = {"success": "✓", "error": "✕", "warning": "!", "info": "i"}
        icons = {"success": "OK", "error": "X", "warning": "!", "info": "i"}
        icon_label = QLabel(icons[normalized])
        icon_label.setObjectName("ToastIcon")
        icon_label.setProperty("type", normalized)
        icon_label.setStyleSheet("font-weight:800;background:transparent;")
        text_label = QLabel(message)
        text_label.setObjectName("ToastText")
        text_label.setWordWrap(True)
        text_label.setStyleSheet("background:transparent;")
        layout.addWidget(icon_label)
        layout.addWidget(text_label, 1)
        QTimer.singleShot(4200, self._fade_out)

    def _fade_out(self) -> None:
        self._animation = QPropertyAnimation(self, b"windowOpacity", self)
        self._animation.setDuration(240)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)
        self._animation.finished.connect(self.deleteLater)
        self._animation.start()
