#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application settings page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.i18n import tr
from core.startup import set_windows_autostart
from core.zapret_manager import ZapretManager
from ui.widgets.common import Card, PageHeader, SettingRow, divider, section_label


class SettingsPage(QWidget):
    path_changed = Signal(str)
    theme_changed = Signal(str)
    language_changed = Signal(str)
    bridge_settings_changed = Signal(bool, int)
    maintenance_requested = Signal()
    notification = Signal(str, str)

    THEME_KEYS = ("light", "light_accent", "dark", "dark_accent")
    LANGUAGE_KEYS = ("ru", "en")

    def __init__(self, config: Config, zapret_manager: ZapretManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.zapret_manager = zapret_manager
        self._loading = False
        self._setup_ui()
        self._load_settings()
        self.retranslate_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(30, 24, 30, 30)
        root.setSpacing(18)
        self.header = PageHeader("", "")
        root.addWidget(self.header)

        self.path_section = section_label("")
        root.addWidget(self.path_section)
        path_card = Card()
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(20, 18, 20, 18)
        path_layout.setSpacing(10)
        path_row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.browse_button = QPushButton()
        self.browse_button.setProperty("role", "ghost")
        self.apply_path_button = QPushButton()
        self.apply_path_button.setProperty("role", "primary")
        path_row.addWidget(self.path_input, 1)
        path_row.addWidget(self.browse_button)
        path_row.addWidget(self.apply_path_button)
        self.path_status = QLabel("")
        self.path_status.setProperty("muted", True)
        path_layout.addLayout(path_row)
        path_layout.addWidget(self.path_status)
        root.addWidget(path_card)

        self.appearance_section = section_label("")
        root.addWidget(self.appearance_section)
        appearance_card = Card(variant="accent")
        appearance_layout = QVBoxLayout(appearance_card)
        appearance_layout.setContentsMargins(20, 14, 20, 14)
        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumWidth(210)
        self.theme_row = SettingRow("", "", self.theme_combo)
        appearance_layout.addWidget(self.theme_row)
        appearance_layout.addWidget(divider())
        self.language_combo = QComboBox()
        self.language_combo.setMinimumWidth(210)
        self.language_row = SettingRow("", "", self.language_combo)
        appearance_layout.addWidget(self.language_row)
        appearance_layout.addWidget(divider())
        self.start_minimized = QCheckBox()
        self.start_row = SettingRow("", "", self.start_minimized)
        appearance_layout.addWidget(self.start_row)
        appearance_layout.addWidget(divider())
        self.close_to_tray = QCheckBox()
        self.close_row = SettingRow("", "", self.close_to_tray)
        appearance_layout.addWidget(self.close_row)
        root.addWidget(appearance_card)

        self.startup_section = section_label("")
        root.addWidget(self.startup_section)
        startup_card = Card()
        startup_layout = QVBoxLayout(startup_card)
        startup_layout.setContentsMargins(20, 14, 20, 14)
        self.autostart_gui = QCheckBox()
        self.autostart_gui_row = SettingRow("", "", self.autostart_gui)
        startup_layout.addWidget(self.autostart_gui_row)
        startup_layout.addWidget(divider())
        self.autostart_zapret = QCheckBox()
        self.autostart_zapret_row = SettingRow("", "", self.autostart_zapret)
        startup_layout.addWidget(self.autostart_zapret_row)
        root.addWidget(startup_card)

        self.maintenance_section = section_label("")
        root.addWidget(self.maintenance_section)
        maintenance_card = Card()
        maintenance_layout = QVBoxLayout(maintenance_card)
        maintenance_layout.setContentsMargins(20, 14, 20, 14)
        self.auto_check_zapret = QCheckBox()
        self.auto_check_zapret_row = SettingRow("", "", self.auto_check_zapret)
        maintenance_layout.addWidget(self.auto_check_zapret_row)
        maintenance_layout.addWidget(divider())
        self.auto_install_zapret = QCheckBox()
        self.auto_install_zapret_row = SettingRow("", "", self.auto_install_zapret)
        maintenance_layout.addWidget(self.auto_install_zapret_row)
        maintenance_layout.addWidget(divider())
        self.auto_update_zapret = QCheckBox()
        self.auto_update_zapret_row = SettingRow("", "", self.auto_update_zapret)
        maintenance_layout.addWidget(self.auto_update_zapret_row)
        maintenance_layout.addWidget(divider())
        maintenance_footer = QHBoxLayout()
        self.maintenance_status = QLabel()
        self.maintenance_status.setProperty("muted", True)
        self.maintenance_status.setWordWrap(True)
        self.check_zapret_button = QPushButton()
        self.check_zapret_button.setProperty("role", "ghost")
        maintenance_footer.addWidget(self.maintenance_status, 1)
        maintenance_footer.addWidget(self.check_zapret_button)
        maintenance_layout.addLayout(maintenance_footer)
        root.addWidget(maintenance_card)

        self.bridge_section = section_label("")
        root.addWidget(self.bridge_section)
        bridge_card = Card()
        bridge_layout = QVBoxLayout(bridge_card)
        bridge_layout.setContentsMargins(20, 14, 20, 14)
        self.bridge_enabled = QCheckBox()
        self.bridge_enabled_row = SettingRow("", "", self.bridge_enabled)
        bridge_layout.addWidget(self.bridge_enabled_row)
        bridge_layout.addWidget(divider())
        self.bridge_port = QSpinBox()
        self.bridge_port.setRange(1024, 65535)
        self.bridge_port.setFixedWidth(130)
        self.bridge_port_row = SettingRow("", "", self.bridge_port)
        bridge_layout.addWidget(self.bridge_port_row)
        root.addWidget(bridge_card)

        self.config_hint = QLabel()
        self.config_hint.setProperty("faint", True)
        self.config_hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.config_hint)
        root.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

        self.browse_button.clicked.connect(self._browse_path)
        self.apply_path_button.clicked.connect(self._apply_path)
        self.path_input.returnPressed.connect(self._apply_path)
        self.theme_combo.currentIndexChanged.connect(self._save_theme)
        self.language_combo.currentIndexChanged.connect(self._save_language)
        self.start_minimized.toggled.connect(self._set_start_minimized)
        self.close_to_tray.toggled.connect(lambda value: self._set_bool("close_to_tray", value))
        self.autostart_zapret.toggled.connect(lambda value: self._set_bool("autostart_zapret", value))
        self.autostart_gui.toggled.connect(self._set_autostart_gui)
        self.auto_check_zapret.toggled.connect(lambda value: self._set_bool("auto_check_zapret", value))
        self.auto_install_zapret.toggled.connect(lambda value: self._set_bool("auto_install_zapret", value))
        self.auto_update_zapret.toggled.connect(lambda value: self._set_bool("auto_update_zapret", value))
        self.check_zapret_button.clicked.connect(self.maintenance_requested)
        self.bridge_enabled.toggled.connect(self._save_bridge)
        self.bridge_port.editingFinished.connect(self._save_bridge)

    def set_bridge_enabled(self, enabled: bool) -> None:
        self._loading = True
        self.bridge_enabled.setChecked(bool(enabled))
        self._loading = False

    def _load_settings(self) -> None:
        self._loading = True
        self.path_input.setText(self.config.zapret_path)
        self.start_minimized.setChecked(self.config.get("start_minimized", False))
        self.close_to_tray.setChecked(self.config.get("close_to_tray", True))
        self.autostart_zapret.setChecked(self.config.get("autostart_zapret", False))
        self.autostart_gui.setChecked(self.config.get("autostart_windows", False))
        self.auto_check_zapret.setChecked(self.config.get("auto_check_zapret", True))
        self.auto_install_zapret.setChecked(self.config.get("auto_install_zapret", False))
        self.auto_update_zapret.setChecked(self.config.get("auto_update_zapret", False))
        self.bridge_enabled.setChecked(self.config.get("bridge_enabled", True))
        self.bridge_port.setValue(self.config.get("bridge_port", 8765))
        self._populate_theme_combo(self.config.get("theme", "dark_accent"))
        self._populate_language_combo(self.config.get("language", "ru"))
        self._loading = False
        self._update_path_status()

    def _populate_theme_combo(self, selected: str) -> None:
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        labels = {
            "light": tr("settings.theme_light"),
            "light_accent": tr("settings.theme_light_accent"),
            "dark": tr("settings.theme_dark"),
            "dark_accent": tr("settings.theme_dark_accent"),
        }
        for key in self.THEME_KEYS:
            self.theme_combo.addItem(labels[key], key)
        index = self.theme_combo.findData(selected)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 3)
        self.theme_combo.blockSignals(False)

    def _populate_language_combo(self, selected: str) -> None:
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        self.language_combo.addItem(tr("settings.language_ru"), "ru")
        self.language_combo.addItem(tr("settings.language_en"), "en")
        index = self.language_combo.findData(selected)
        self.language_combo.setCurrentIndex(index if index >= 0 else 0)
        self.language_combo.blockSignals(False)

    def _set_bool(self, key: str, value: bool) -> None:
        if not self._loading:
            self.config.set(key, bool(value))

    def _set_start_minimized(self, enabled: bool) -> None:
        if self._loading:
            return
        self.config.set("start_minimized", bool(enabled))
        if self.config.get("autostart_windows", False):
            ok, message = set_windows_autostart(True, bool(enabled))
            if not ok:
                self.notification.emit(message, "warning")

    def _save_theme(self) -> None:
        if self._loading:
            return
        theme = str(self.theme_combo.currentData() or "dark_accent")
        self.config.set("theme", theme)
        self.theme_changed.emit(theme)

    def _save_language(self) -> None:
        if self._loading:
            return
        language = str(self.language_combo.currentData() or "ru")
        self.config.set("language", language)
        self.language_changed.emit(language)

    def _set_autostart_gui(self, enabled: bool) -> None:
        if self._loading:
            return
        ok, message = set_windows_autostart(enabled, self.start_minimized.isChecked())
        if ok:
            self.config.set("autostart_windows", enabled)
            self.notification.emit(message, "success")
        else:
            self._loading = True
            self.autostart_gui.setChecked(not enabled)
            self._loading = False
            self.notification.emit(message, "warning")

    def _save_bridge(self, *_args) -> None:
        if self._loading:
            return
        enabled = self.bridge_enabled.isChecked()
        port = self.bridge_port.value()
        self.config.update({"bridge_enabled": enabled, "bridge_port": port})
        self.bridge_settings_changed.emit(enabled, port)

    def _browse_path(self) -> None:
        initial = self.path_input.text().strip() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, tr("settings.choose_folder"), initial)
        if path:
            self.path_input.setText(path)
            self._apply_path()

    def _apply_path(self) -> None:
        path = self.path_input.text().strip().strip('"')
        candidate = Path(path).expanduser()
        if not candidate.is_dir():
            self.notification.emit(tr("settings.path_missing"), "error")
            self._update_path_status(False)
            return
        resolved = str(candidate.resolve())
        self.config.set("zapret_path", resolved)
        self.path_input.setText(resolved)
        self.path_changed.emit(resolved)
        valid, message = self.zapret_manager.validate_path()
        self._update_path_status(valid)
        if valid:
            self.notification.emit(tr("settings.path_applied"), "success")
        else:
            self.notification.emit(message or tr("settings.path_no_bat"), "warning")

    def _update_path_status(self, valid: bool | None = None) -> None:
        raw = self.path_input.text().strip()
        path = Path(raw) if raw else None
        if valid is None:
            valid = bool(path and path.is_dir() and list(path.glob("general*.bat")))
        self.path_status.setText(tr("settings.path_ok") if valid else tr("settings.path_bad"))

    def set_maintenance_status(self, text: str, status: str = "info") -> None:
        self.maintenance_status.setText(text)
        self.maintenance_status.setProperty("maintenanceStatus", status)
        self.maintenance_status.style().unpolish(self.maintenance_status)
        self.maintenance_status.style().polish(self.maintenance_status)

    def retranslate_ui(self) -> None:
        selected_theme = str(self.theme_combo.currentData() or self.config.get("theme", "dark_accent"))
        selected_language = str(self.language_combo.currentData() or self.config.get("language", "ru"))
        self.header.set_text(tr("settings.title"), tr("settings.subtitle"))
        self.path_section.setText(tr("settings.path_section").upper())
        self.path_input.setPlaceholderText(tr("settings.path_placeholder"))
        self.browse_button.setText(tr("common.browse"))
        self.apply_path_button.setText(tr("common.apply"))
        self.appearance_section.setText(tr("settings.appearance_section").upper())
        self.theme_row.set_text(tr("settings.theme"), tr("settings.theme_desc"))
        self.language_row.set_text(tr("settings.language"), tr("settings.language_desc"))
        self.start_row.set_text(tr("settings.start_tray"), tr("settings.start_tray_desc"))
        self.start_minimized.setText(tr("settings.start_minimized"))
        self.close_row.set_text(tr("settings.close_behavior"), tr("settings.close_behavior_desc"))
        self.close_to_tray.setText(tr("settings.close_to_tray"))
        self.startup_section.setText(tr("settings.startup_section").upper())
        self.autostart_gui_row.set_text(tr("settings.autostart_gui"), tr("settings.autostart_gui_desc"))
        self.autostart_gui.setText(tr("settings.autostart_gui_check"))
        self.autostart_zapret_row.set_text(tr("settings.autostart_zapret"), tr("settings.autostart_zapret_desc"))
        self.autostart_zapret.setText(tr("settings.autostart_zapret_check"))
        self.maintenance_section.setText(tr("settings.maintenance_section").upper())
        self.auto_check_zapret_row.set_text(tr("settings.auto_check_zapret"), tr("settings.auto_check_zapret_desc"))
        self.auto_check_zapret.setText(tr("settings.auto_check_zapret_check"))
        self.auto_install_zapret_row.set_text(tr("settings.auto_install_zapret"), tr("settings.auto_install_zapret_desc"))
        self.auto_install_zapret.setText(tr("settings.auto_install_zapret_check"))
        self.auto_update_zapret_row.set_text(tr("settings.auto_update_zapret"), tr("settings.auto_update_zapret_desc"))
        self.auto_update_zapret.setText(tr("settings.auto_update_zapret_check"))
        self.check_zapret_button.setText(tr("settings.check_zapret"))
        self.bridge_section.setText(tr("settings.bridge_section").upper())
        self.bridge_enabled_row.set_text(tr("settings.bridge_api"), tr("settings.bridge_api_desc"))
        self.bridge_enabled.setText(tr("settings.bridge_enable"))
        self.bridge_port_row.set_text(tr("settings.bridge_port"), tr("settings.bridge_port_desc"))
        self.config_hint.setText(tr("settings.config_path", path=self.config.path))
        self._populate_theme_combo(selected_theme)
        self._populate_language_combo(selected_language)
        self._update_path_status()
