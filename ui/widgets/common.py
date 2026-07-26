#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable widgets for the redesigned interface."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("PageSubtitle")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        self.subtitle_label.setVisible(bool(subtitle))

    def set_text(self, title: str, subtitle: str = "") -> None:
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))


class Card(QFrame):
    def __init__(self, parent=None, hero: bool = False, variant: str = "default"):
        super().__init__(parent)
        if hero:
            variant = "hero"
        names = {"hero": "HeroCard", "accent": "AccentCard", "inset": "InsetCard"}
        self.setObjectName(names.get(variant, "Card"))


class MetricCard(Card):
    def __init__(self, label: str, value: str = "—", hint: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)
        self.label_widget = QLabel(label)
        self.label_widget.setProperty("muted", True)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        self.hint_widget = QLabel(hint)
        self.hint_widget.setProperty("faint", True)
        self.hint_widget.setWordWrap(True)
        layout.addWidget(self.label_widget)
        layout.addWidget(self.value_label)
        layout.addWidget(self.hint_widget)
        self.hint_widget.setVisible(bool(hint))

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)

    def set_content(self, label: str, hint: str = "") -> None:
        self.label_widget.setText(label)
        self.hint_widget.setText(hint)
        self.hint_widget.setVisible(bool(hint))


class SettingRow(QWidget):
    def __init__(self, title: str, description: str = "", control: QWidget | None = None, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 9, 0, 9)
        layout.setSpacing(18)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        self.title_label = QLabel(title)
        self.title_label.setWordWrap(True)
        self.description_label = QLabel(description)
        self.description_label.setProperty("muted", True)
        self.description_label.setWordWrap(True)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.description_label)
        self.description_label.setVisible(bool(description))
        layout.addLayout(text_layout, 1)
        if control is not None:
            layout.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)

    def set_text(self, title: str, description: str = "") -> None:
        self.title_label.setText(title)
        self.description_label.setText(description)
        self.description_label.setVisible(bool(description))


class StatusPill(QLabel):
    def __init__(self, text: str = "", running: bool = False, parent=None):
        super().__init__(text, parent)
        self.setObjectName("StatusPill")
        self.setProperty("running", bool(running))

    def set_status(self, text: str, running: bool) -> None:
        self.setText(text)
        self.setProperty("running", bool(running))
        self.style().unpolish(self)
        self.style().polish(self)


def section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("SectionTitle")
    return label


def divider() -> QFrame:
    frame = QFrame()
    frame.setObjectName("Divider")
    return frame
