#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zapret list editor."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.lists_manager import ListsManager
from ui.widgets.common import Card, PageHeader, divider


class ListsPage(QWidget):
    notification = Signal(str, str)
    external_update = Signal()

    LIST_KEYS = ("list-general", "list-exclude", "list-google", "ipset-all", "ipset-exclude")

    def __init__(self, lists_manager: ListsManager, parent=None):
        super().__init__(parent)
        self.lists_manager = lists_manager
        self._current_list = "list-general"
        self._all_entries: list[str] = []
        self._setup_ui()
        self.external_update.connect(self.refresh)
        self.lists_manager.on_updated(lambda *_: self.external_update.emit())
        self.retranslate_ui()
        self.refresh()

    @staticmethod
    def _list_label(key: str) -> str:
        return tr({
            "list-general": "lists.general",
            "list-exclude": "lists.exclude",
            "list-google": "lists.google",
            "ipset-all": "lists.ip_all",
            "ipset-exclude": "lists.ip_exclude",
        }[key])

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 30)
        root.setSpacing(18)
        self.header = PageHeader("", "")
        root.addWidget(self.header)

        toolbar_card = Card(variant="accent")
        toolbar = QVBoxLayout(toolbar_card)
        toolbar.setContentsMargins(18, 16, 18, 16)
        toolbar.setSpacing(12)
        top = QHBoxLayout()
        self.list_selector = QComboBox()
        self.list_selector.setMinimumWidth(250)
        self.search_input = QLineEdit()
        self.count_label = QLabel()
        self.count_label.setProperty("muted", True)
        top.addWidget(self.list_selector, 2)
        top.addWidget(self.search_input, 3)
        top.addWidget(self.count_label)
        toolbar.addLayout(top)
        toolbar.addWidget(divider())
        add_row = QHBoxLayout()
        self.domain_input = QLineEdit()
        self.add_button = QPushButton()
        self.add_button.setProperty("role", "primary")
        self.remove_button = QPushButton()
        self.remove_button.setProperty("role", "danger")
        self.remove_button.setEnabled(False)
        self.refresh_button = QPushButton()
        self.refresh_button.setProperty("role", "ghost")
        add_row.addWidget(self.domain_input, 1)
        add_row.addWidget(self.add_button)
        add_row.addWidget(self.remove_button)
        add_row.addWidget(self.refresh_button)
        toolbar.addLayout(add_row)
        root.addWidget(toolbar_card)

        list_card = Card()
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(12, 12, 12, 12)
        self.entries = QListWidget()
        self.entries.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.entries.setAlternatingRowColors(False)
        list_layout.addWidget(self.entries)
        root.addWidget(list_card, 1)
        self.hint = QLabel()
        self.hint.setProperty("muted", True)
        root.addWidget(self.hint)

        self.list_selector.currentIndexChanged.connect(self._switch_list)
        self.search_input.textChanged.connect(self._apply_filter)
        self.domain_input.returnPressed.connect(self._add_entry)
        self.add_button.clicked.connect(self._add_entry)
        self.remove_button.clicked.connect(self._remove_selected)
        self.refresh_button.clicked.connect(self.refresh)
        self.entries.itemSelectionChanged.connect(lambda: self.remove_button.setEnabled(bool(self.entries.selectedItems())))

    def _populate_selector(self) -> None:
        current = self._current_list
        self.list_selector.blockSignals(True)
        self.list_selector.clear()
        for key in self.LIST_KEYS:
            self.list_selector.addItem(self._list_label(key), key)
        index = self.list_selector.findData(current)
        self.list_selector.setCurrentIndex(index if index >= 0 else 0)
        self.list_selector.blockSignals(False)

    def set_manager_path(self, path: str) -> None:
        self.lists_manager.set_path(path)
        self.refresh()

    def _switch_list(self, index: int) -> None:
        self._current_list = str(self.list_selector.itemData(index) or "list-general")
        self._update_input_placeholder()
        self.refresh()

    def _update_input_placeholder(self) -> None:
        self.domain_input.setPlaceholderText(
            tr("lists.ip_placeholder") if self._current_list.startswith("ipset-") else tr("lists.domain_placeholder")
        )

    def refresh(self) -> None:
        self._all_entries = self.lists_manager.read_list(self._current_list)
        self.count_label.setText(tr("common.entries", count=len(self._all_entries)))
        self._apply_filter(self.search_input.text())

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().casefold()
        self.entries.clear()
        self.entries.addItems([entry for entry in self._all_entries if not needle or needle in entry.casefold()])
        self.remove_button.setEnabled(False)

    def _add_entry(self) -> None:
        value = self.domain_input.text().strip()
        if not value:
            return
        ok, message = self.lists_manager.add_domain(self._current_list, value)
        if ok:
            self.domain_input.clear()
            self.refresh()
            self.notification.emit(tr("lists.added", value=message), "success")
        else:
            self.notification.emit(message, "warning")

    def _remove_selected(self) -> None:
        selected = [item.text() for item in self.entries.selectedItems()]
        if not selected:
            return
        removed = 0
        errors: list[str] = []
        for entry in selected:
            ok, message = self.lists_manager.remove_domain(self._current_list, entry)
            removed += int(ok)
            if not ok:
                errors.append(message)
        self.refresh()
        if removed:
            self.notification.emit(tr("lists.removed", count=removed), "success")
        elif errors:
            self.notification.emit(errors[0], "error")

    def retranslate_ui(self) -> None:
        self.header.set_text(tr("lists.title"), tr("lists.subtitle"))
        self.search_input.setPlaceholderText(tr("lists.search"))
        self.add_button.setText(tr("common.add"))
        self.remove_button.setText(tr("lists.remove_selected"))
        self.refresh_button.setText(tr("common.refresh"))
        self.hint.setText(tr("lists.restart_hint"))
        self._populate_selector()
        self._update_input_placeholder()
        self.refresh()
