#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Theme-aware logs with filtering, pausing and saving."""

from __future__ import annotations

import html
from collections import deque
from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget

from core.i18n import tr
from ui.styles import theme_colors
from ui.widgets.common import Card, PageHeader


class LogsPage(QWidget):
    notification = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: deque[tuple[str, str, str]] = deque(maxlen=5000)
        self._paused = False
        self._colors = theme_colors("dark_accent")
        self._setup_ui()
        self.retranslate_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 30)
        root.setSpacing(16)
        self.header = PageHeader("", "")
        root.addWidget(self.header)

        toolbar_card = Card(variant="accent")
        toolbar = QHBoxLayout(toolbar_card)
        toolbar.setContentsMargins(14, 12, 14, 12)
        self.filter_combo = QComboBox()
        self.pause_button = QPushButton()
        self.save_button = QPushButton()
        self.clear_button = QPushButton()
        self.clear_button.setProperty("role", "danger")
        toolbar.addWidget(self.filter_combo)
        toolbar.addStretch()
        toolbar.addWidget(self.pause_button)
        toolbar.addWidget(self.save_button)
        toolbar.addWidget(self.clear_button)
        root.addWidget(toolbar_card)

        log_card = Card()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(10, 10, 10, 10)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setProperty("logView", True)
        self.log_area.setAcceptRichText(True)
        self.log_area.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        log_layout.addWidget(self.log_area)
        root.addWidget(log_card, 1)

        self.filter_combo.currentIndexChanged.connect(lambda _index: self._render())
        self.pause_button.clicked.connect(self._toggle_pause)
        self.save_button.clicked.connect(self._save)
        self.clear_button.clicked.connect(self._clear)

    def _populate_filter(self) -> None:
        selected = str(self.filter_combo.currentData() or "ALL")
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        for label, value in (
            (tr("logs.all"), "ALL"), ("INFO", "INFO"), ("SUCCESS", "SUCCESS"),
            ("WARNING", "WARNING"), ("ERROR", "ERROR"),
        ):
            self.filter_combo.addItem(label, value)
        index = self.filter_combo.findData(selected)
        self.filter_combo.setCurrentIndex(index if index >= 0 else 0)
        self.filter_combo.blockSignals(False)

    def _record_html(self, timestamp: str, level: str, message: str) -> str:
        colors = {
            "INFO": self._colors["log_info"], "SUCCESS": self._colors["log_success"],
            "WARNING": self._colors["log_warning"], "ERROR": self._colors["log_error"],
        }
        color = colors.get(level, self._colors["muted"])
        return (
            f'<span style="color:{self._colors["log_time"]}">[{html.escape(timestamp)}]</span> '
            f'<span style="color:{color};font-weight:600">[{html.escape(level)}]</span> '
            f'<span style="color:{self._colors["text"]}">{html.escape(message)}</span>'
        )

    def add_log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        normalized_level = level.upper()
        was_full = len(self._records) == self._records.maxlen
        self._records.append((timestamp, normalized_level, str(message)))
        if self._paused:
            return
        selected = str(self.filter_combo.currentData() or "ALL")
        if was_full:
            self._render()
        elif selected == "ALL" or normalized_level == selected:
            self._append_html(self._record_html(timestamp, normalized_level, str(message)))

    def _append_html(self, record_html: str) -> None:
        cursor = self.log_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self.log_area.document().isEmpty():
            cursor.insertHtml("<br>")
        cursor.insertHtml(record_html)
        self.log_area.setTextCursor(cursor)
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

    def _render(self) -> None:
        if self._paused:
            return
        selected = str(self.filter_combo.currentData() or "ALL")
        chunks = [
            self._record_html(timestamp, level, message)
            for timestamp, level, message in self._records
            if selected == "ALL" or level == selected
        ]
        self.log_area.setHtml("<br>".join(chunks))
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_button.setText(tr("logs.resume") if self._paused else tr("logs.pause"))
        if not self._paused:
            self._render()

    def _clear(self) -> None:
        self._records.clear()
        self.log_area.clear()

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, tr("logs.save_title"), "integra.log", tr("logs.file_filter")
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                for timestamp, level, message in self._records:
                    handle.write(f"[{timestamp}] [{level}] {message}\n")
        except OSError as exc:
            self.notification.emit(tr("logs.save_error", error=exc), "error")
            return
        self.notification.emit(tr("logs.saved"), "success")

    def apply_theme(self, theme: str) -> None:
        self._colors = theme_colors(theme)
        self._render()

    def retranslate_ui(self) -> None:
        self.header.set_text(tr("logs.title"), tr("logs.subtitle"))
        self._populate_filter()
        self.pause_button.setText(tr("logs.resume") if self._paused else tr("logs.pause"))
        self.save_button.setText(tr("logs.save"))
        self.clear_button.setText(tr("logs.clear"))
