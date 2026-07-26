#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main window for Integra."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from core.bridge_server import BridgeServer
from core.config import Config
from core.diagnostics import DiagnosticsManager
from core.i18n import set_language, tr
from core.lists_manager import ListsManager
from core.paths import resource_path
from core.zapret_maintenance import MaintenanceResult, ZapretMaintenance
from core.zapret_manager import ZapretManager
from ui.pages.diagnostics_page import DiagnosticsPage
from ui.pages.extension_page import ExtensionPage
from ui.pages.home_page import HomePage
from ui.pages.lists_page import ListsPage
from ui.pages.logs_page import LogsPage
from ui.pages.settings_page import SettingsPage
from ui.styles import build_stylesheet, resolved_theme
from ui.tray_icon import TrayIcon
from ui.widgets.common import StatusPill
from ui.widgets.toast_notification import ToastNotification
from ui.workers import ZapretMaintenanceWorker


class MainWindow(QMainWindow):
    bridge_log = Signal(str, str)

    VERSION = "2.2.0"
    NAVIGATION = (
        ("home", "", "nav.home", "topbar.home_caption"),
        ("lists", "", "nav.lists", "topbar.lists_caption"),
        ("diagnostics", "", "nav.diagnostics", "topbar.diagnostics_caption"),
        ("extension", "", "nav.extension", "topbar.extension_caption"),
        ("logs", "", "nav.logs", "topbar.logs_caption"),
        ("settings", "", "nav.settings", "topbar.settings_caption"),
    )

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        set_language(self.config.get("language", "ru"))
        self._quitting = False
        self._sidebar_collapsed = False
        self._sidebar_manual_override: bool | None = None
        self._current_page_id = "home"
        self._maintenance_worker: ZapretMaintenanceWorker | None = None
        self._pending_zapret_autostart = bool(self.config.get("autostart_zapret", False))
        self.zapret_manager = ZapretManager(config.zapret_path)
        self.lists_manager = ListsManager(config.zapret_path)
        self.zapret_maintenance = ZapretMaintenance()
        self.diagnostics = DiagnosticsManager(self.zapret_manager)
        self.bridge = BridgeServer(
            self.lists_manager,
            token=self.config.get("bridge_token"),
            port=self.config.get("bridge_port", 8765),
            status_provider=self._bridge_status,
            log_callback=lambda level, message: self.bridge_log.emit(level, message),
        )
        self.bridge_log.connect(self._on_log_message)
        self._setup_window()
        self._setup_ui()
        self._setup_tray()
        self._connect_signals()
        self.apply_theme(self.config.get("theme", "dark_accent"))
        self.retranslate_ui()
        self._restore_geometry()

        if self.config.get("bridge_enabled", True):
            ok, message = self.bridge.start()
            if not ok:
                QTimer.singleShot(0, lambda: self.show_toast(message, "error"))

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(2500)
        self._refresh_status()

        needs_maintenance = any(
            self.config.get(key, False)
            for key in ("auto_check_zapret", "auto_install_zapret", "auto_update_zapret")
        )
        if needs_maintenance:
            QTimer.singleShot(900, self._run_zapret_maintenance)
        elif self._pending_zapret_autostart:
            QTimer.singleShot(900, self._start_zapret_after_maintenance)

    def _setup_window(self) -> None:
        self.setWindowTitle("Integra")
        self.setMinimumSize(820, 620)
        self.resize(1220, 800)
        self.app_icon = self._create_app_icon()
        self.setWindowIcon(self.app_icon)

    @staticmethod
    def _create_app_icon() -> QIcon:
        icon_path = resource_path("assets/integra.ico")
        if icon_path.is_file():
            return QIcon(str(icon_path))
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#686BF2"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 4, 56, 56, 16, 16)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(16, 16, 32, 32)
        painter.setBrush(QColor("#686BF2"))
        painter.drawEllipse(25, 25, 14, 14)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _avatar_pixmap(size: int) -> QPixmap:
        source = QPixmap(str(resource_path("assets/integra-avatar.png")))
        if source.isNull():
            return QPixmap()
        return source.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _setup_ui(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("NavigationRail")
        self.sidebar.setFixedWidth(240)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(14, 18, 14, 14)
        side.setSpacing(7)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        self.brand_mark = QLabel()
        self.brand_mark.setObjectName("BrandMark")
        self.brand_mark.setAlignment(Qt.AlignCenter)
        self.brand_mark.setFixedSize(40, 40)
        self.brand_mark.setPixmap(self._avatar_pixmap(40))
        self.brand_text_widget = QWidget()
        brand_text = QVBoxLayout(self.brand_text_widget)
        brand_text.setContentsMargins(0, 0, 0, 0)
        brand_text.setSpacing(0)
        self.brand_label = QLabel("Integra")
        self.brand_label.setObjectName("Brand")
        self.version_label = QLabel()
        self.version_label.setObjectName("BrandVersion")
        brand_text.addWidget(self.brand_label)
        brand_text.addWidget(self.version_label)
        brand_row.addWidget(self.brand_mark)
        brand_row.addWidget(self.brand_text_widget, 1)
        side.addLayout(brand_row)
        side.addSpacing(14)

        self.nav_buttons: dict[str, QPushButton] = {}
        self.nav_icons: dict[str, str] = {}
        self.nav_label_keys: dict[str, str] = {}
        for page_id, icon, label_key, _caption_key in self.NAVIGATION:
            button = QPushButton()
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setProperty("nav", True)
            button.clicked.connect(lambda _checked=False, pid=page_id: self.switch_page(pid))
            self.nav_buttons[page_id] = button
            self.nav_icons[page_id] = icon
            self.nav_label_keys[page_id] = label_key
            side.addWidget(button)
        side.addStretch()
        self.sidebar_status = StatusPill()
        side.addWidget(self.sidebar_status)
        shell.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("ContentRoot")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        topbar = QFrame()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(72)
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(24, 0, 26, 0)
        top_layout.setSpacing(14)
        self.collapse_button = QPushButton("=")
        self.collapse_button.setProperty("role", "ghost")
        self.collapse_button.setText("=")
        self.collapse_button.setProperty("compact", True)
        self.collapse_button.setFixedSize(38, 38)
        self.collapse_button.setToolTip(tr("app.sidebar_toggle"))
        self.collapse_button.clicked.connect(lambda: self._set_sidebar_collapsed(not self._sidebar_collapsed, manual=True))
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        self.top_title = QLabel()
        self.top_title.setObjectName("TopTitle")
        self.top_caption = QLabel()
        self.top_caption.setObjectName("TopCaption")
        title_box.addWidget(self.top_title)
        title_box.addWidget(self.top_caption)
        self.top_status = StatusPill()
        top_layout.addWidget(self.collapse_button)
        top_layout.addLayout(title_box, 1)
        top_layout.addWidget(self.top_status)
        content_layout.addWidget(topbar)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("PageStack")
        extension_path = resource_path("browser-extension")
        self.pages = {
            "home": HomePage(self.zapret_manager, self.config),
            "lists": ListsPage(self.lists_manager),
            "diagnostics": DiagnosticsPage(self.diagnostics, self.zapret_manager, self.config),
            "extension": ExtensionPage(self.bridge, extension_path),
            "logs": LogsPage(),
            "settings": SettingsPage(self.config, self.zapret_manager),
        }
        for page in self.pages.values():
            self.page_stack.addWidget(page)
        content_layout.addWidget(self.page_stack, 1)

        status_strip = QFrame()
        status_strip.setObjectName("StatusStrip")
        status_strip.setFixedHeight(38)
        status_layout = QHBoxLayout(status_strip)
        status_layout.setContentsMargins(24, 0, 24, 0)
        self.status_label = QLabel()
        self.status_label.setProperty("muted", True)
        self.strategy_label = QLabel()
        self.strategy_label.setProperty("muted", True)
        self.bridge_label = QLabel()
        self.bridge_label.setProperty("muted", True)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.strategy_label)
        status_layout.addStretch()
        status_layout.addWidget(self.bridge_label)
        content_layout.addWidget(status_strip)
        shell.addWidget(content, 1)
        self.switch_page("home")

    def _setup_tray(self) -> None:
        self.tray_icon = TrayIcon(self.app_icon, self)
        self.tray_icon.show_window.connect(self._show_window)
        self.tray_icon.start_zapret.connect(self.pages["home"].start_selected)
        self.tray_icon.stop_zapret.connect(self.pages["home"].stop_zapret)
        self.tray_icon.quit_app.connect(self.quit_application)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()

    def _connect_signals(self) -> None:
        self.zapret_manager.status_changed.connect(self._update_status)
        self.zapret_manager.log_message.connect(self._on_log_message)
        self.zapret_manager.error_occurred.connect(self._on_error)
        self.zapret_manager.strategy_changed.connect(lambda _strategy: self._update_status(self.zapret_manager.get_status(), self.zapret_manager.get_pid()))
        home: HomePage = self.pages["home"]
        home.operation_finished.connect(self._on_operation_finished)
        self.pages["lists"].notification.connect(self.show_toast)
        self.pages["logs"].notification.connect(self.show_toast)
        diagnostics: DiagnosticsPage = self.pages["diagnostics"]
        diagnostics.notification.connect(self.show_toast)
        diagnostics.strategy_selected.connect(self._select_strategy)
        self.pages["extension"].notification.connect(self.show_toast)
        self.pages["extension"].bridge_toggled.connect(self._on_extension_bridge_toggled)
        settings: SettingsPage = self.pages["settings"]
        settings.notification.connect(self.show_toast)
        settings.path_changed.connect(self._on_path_changed)
        settings.theme_changed.connect(self.apply_theme)
        settings.language_changed.connect(self.apply_language)
        settings.bridge_settings_changed.connect(self._on_bridge_settings_changed)
        settings.maintenance_requested.connect(lambda: self._run_zapret_maintenance(manual=True))

    def switch_page(self, page_id: str) -> None:
        page = self.pages.get(page_id)
        if page is None:
            return
        self._current_page_id = page_id
        self.page_stack.setCurrentWidget(page)
        self.nav_buttons[page_id].setChecked(True)
        self._update_topbar_text()

    def _update_topbar_text(self) -> None:
        for page_id, _icon, label_key, caption_key in self.NAVIGATION:
            if page_id == self._current_page_id:
                self.top_title.setText(tr(label_key))
                self.top_caption.setText(tr(caption_key))
                break

    def _set_sidebar_collapsed(self, collapsed: bool, manual: bool = False) -> None:
        self._sidebar_collapsed = bool(collapsed)
        if manual:
            self._sidebar_manual_override = self._sidebar_collapsed
        self.sidebar.setFixedWidth(76 if collapsed else 240)
        self.brand_text_widget.setVisible(not collapsed)
        self.sidebar_status.setVisible(not collapsed)
        for page_id, button in self.nav_buttons.items():
            button.setProperty("navCollapsed", collapsed)
            label = tr(self.nav_label_keys[page_id])
            button.setText(label[:1].upper() if collapsed else label)
            button.setToolTip(label if collapsed else "")
            button.style().unpolish(button)
            button.style().polish(button)

    def apply_theme(self, theme: str) -> None:
        normalized = resolved_theme(theme)
        app = QApplication.instance()
        self.setUpdatesEnabled(False)
        try:
            if app:
                app.setStyleSheet(build_stylesheet(normalized))
            self.setProperty("theme", normalized)
            logs: LogsPage = self.pages.get("logs")
            if logs:
                logs.apply_theme(normalized)
        finally:
            self.setUpdatesEnabled(True)
            QTimer.singleShot(0, self.update)

    def apply_language(self, language: str) -> None:
        set_language(language)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.version_label.setText(tr("app.version", version=self.VERSION))
        for page in self.pages.values():
            retranslate = getattr(page, "retranslate_ui", None)
            if callable(retranslate):
                retranslate()
        if hasattr(self, "tray_icon"):
            self.tray_icon.retranslate_ui()
        self.collapse_button.setToolTip(tr("app.sidebar_toggle"))
        self._set_sidebar_collapsed(self._sidebar_collapsed)
        self._update_topbar_text()
        self._refresh_status()

    def _restore_geometry(self) -> None:
        encoded = self.config.get("window_geometry")
        if encoded:
            try:
                self.restoreGeometry(QByteArray.fromBase64(encoded.encode("ascii")))
            except (TypeError, ValueError):
                pass
        self._ensure_visible_geometry()

    def _ensure_visible_geometry(self) -> None:
        screens = QGuiApplication.screens()
        frame = self.frameGeometry()
        if screens and not any(screen.availableGeometry().intersects(frame) for screen in screens):
            screen_geometry = QGuiApplication.primaryScreen().availableGeometry()
            self.resize(min(1220, screen_geometry.width()), min(800, screen_geometry.height()))
            self.move(screen_geometry.center() - self.rect().center())

    def _on_path_changed(self, path: str) -> None:
        self.zapret_manager.set_zapret_path(path)
        self.lists_manager.set_path(path)
        self.pages["home"].reload_strategies()
        self.pages["lists"].refresh()
        self._refresh_status()

    def _start_zapret_after_maintenance(self) -> None:
        self._pending_zapret_autostart = False
        self.pages["home"].start_selected()

    def _run_zapret_maintenance(self, manual: bool = False) -> None:
        if self._maintenance_worker and self._maintenance_worker.isRunning():
            return
        auto_check = bool(self.config.get("auto_check_zapret", True))
        auto_install = bool(self.config.get("auto_install_zapret", False))
        auto_update = bool(self.config.get("auto_update_zapret", False))
        if not manual and not any((auto_check, auto_install, auto_update)):
            return
        update_blocked = auto_update and (
            self.zapret_manager.get_status() != ZapretManager.STATUS_STOPPED
            or self.zapret_manager.is_service_installed()
        )
        settings: SettingsPage = self.pages["settings"]
        settings.set_maintenance_status(tr("maintenance.checking"), "info")
        self._maintenance_worker = ZapretMaintenanceWorker(
            self.zapret_maintenance,
            self.config.zapret_path,
            auto_install=auto_install,
            # A running process or installed service only prevents the file swap.
            # The release check still runs and exposes installed/latest versions.
            auto_update=auto_update and not update_blocked,
            check_remote=manual or auto_check or auto_install or auto_update,
            parent=self,
        )
        self._maintenance_worker.completed.connect(self._on_maintenance_done)
        self._maintenance_worker.start()

    @staticmethod
    def _maintenance_message(result: MaintenanceResult) -> str:
        values = {
            "path": result.path,
            "installed": result.installed_version or tr("maintenance.version_unknown"),
            "latest": result.latest_version or tr("maintenance.version_unknown"),
            "error": result.detail or tr("common.operation_failed"),
        }
        keys = {
            "missing": "maintenance.missing",
            "invalid": "maintenance.invalid",
            "local": "maintenance.local",
            "unknown_version": "maintenance.unknown_version",
            "up_to_date": "maintenance.up_to_date",
            "update_available": "maintenance.update_available",
            "installed": "maintenance.installed",
            "updated": "maintenance.updated",
            "blocked": "maintenance.blocked",
            "error": "maintenance.error",
        }
        return tr(keys.get(result.state, "maintenance.error"), **values)

    def _on_maintenance_done(self, result: MaintenanceResult) -> None:
        worker = self._maintenance_worker
        self._maintenance_worker = None
        message = self._maintenance_message(result)
        self._on_log_message("ERROR" if not result.ok else "INFO", message)
        status = "error" if not result.ok else ("success" if result.state in {"installed", "updated", "up_to_date"} else "info")
        settings: SettingsPage = self.pages["settings"]
        settings.set_maintenance_status(message, status)
        if result.state in {"installed", "updated"} and result.path:
            self.config.set("zapret_path", result.path)
            settings.path_input.setText(result.path)
            self._on_path_changed(result.path)
            self.show_toast(message, "success")
        elif result.state == "error":
            self.show_toast(message, "error")
        if self._pending_zapret_autostart:
            if self.zapret_maintenance.is_valid_installation(Path(self.config.zapret_path)):
                QTimer.singleShot(0, self._start_zapret_after_maintenance)
            else:
                self._pending_zapret_autostart = False
        if worker:
            worker.deleteLater()

    def _on_extension_bridge_toggled(self, enabled: bool) -> None:
        self.config.set("bridge_enabled", bool(enabled))
        settings: SettingsPage = self.pages["settings"]
        settings.set_bridge_enabled(enabled)
        self._update_bridge_label()

    def _on_bridge_settings_changed(self, enabled: bool, port: int) -> None:
        self.bridge.stop()
        self.bridge.port = int(port)
        if enabled:
            ok, message = self.bridge.start()
            self.show_toast(message, "success" if ok else "error")
        self.pages["extension"].refresh_status()
        self._update_bridge_label()

    def _select_strategy(self, strategy: str) -> None:
        self.config.set("selected_strategy", strategy)
        self.pages["home"].reload_strategies()

    def _bridge_status(self) -> dict:
        return {
            "zapret_status": self.zapret_manager.get_status(),
            "pid": self.zapret_manager.get_pid(),
            "strategy": self.zapret_manager.current_strategy or self.config.get("selected_strategy", ""),
            "version": self.VERSION,
        }

    def _refresh_status(self) -> None:
        self._update_status(self.zapret_manager.get_status(), self.zapret_manager.get_pid())
        self._update_bridge_label()

    def _update_bridge_label(self) -> None:
        self.bridge_label.setText(tr("status.bridge_on", port=self.bridge.port) if self.bridge.is_running else tr("status.bridge_off"))

    def _update_status(self, status: str, pid: int) -> None:
        self.pages["home"].update_status(status, pid)
        if hasattr(self, "tray_icon"):
            self.tray_icon.update_status(status, pid)
        if status == ZapretManager.STATUS_RUNNING:
            text = tr("status.running") + (f" · PID {pid}" if pid else "")
            self.status_label.setText(text)
            self.sidebar_status.set_status(tr("status.running"), True)
            self.top_status.set_status(tr("status.running"), True)
        elif status == ZapretManager.STATUS_SERVICE:
            self.status_label.setText(tr("status.service"))
            self.sidebar_status.set_status(tr("status.service"), True)
            self.top_status.set_status(tr("status.service"), True)
        else:
            self.status_label.setText(tr("status.stopped"))
            self.sidebar_status.set_status(tr("status.stopped"), False)
            self.top_status.set_status(tr("status.stopped"), False)
        strategy = self.zapret_manager.current_strategy or self.config.get("selected_strategy", "")
        self.strategy_label.setText(tr("status.strategy", strategy=strategy) if strategy else "")

    def _on_operation_finished(self, ok: bool, message: str) -> None:
        if message:
            self.show_toast(message, "success" if ok else "error")

    def _on_log_message(self, level: str, message: str) -> None:
        self.pages["logs"].add_log(level, message)

    def _on_error(self, message: str) -> None:
        self._on_log_message("ERROR", message)
        self.show_toast(message, "error")

    def show_toast(self, message: str, toast_type: str = "info") -> None:
        toast = ToastNotification(message, toast_type, self)
        toast.adjustSize()
        active = [item for item in self.findChildren(ToastNotification) if item.isVisible()]
        y = self.height() - 64 - toast.height() - len(active) * (toast.height() + 10)
        toast.move(self.width() - toast.width() - 24, max(24, y))
        toast.show()
        toast.raise_()

    def _activate_window(self) -> None:
        state = self.windowState()
        was_maximized = bool(state & Qt.WindowMaximized)
        self.setWindowState((state & ~Qt.WindowMinimized) | Qt.WindowActive)
        if was_maximized:
            self.showMaximized()
        else:
            self.showNormal()
        self.raise_()
        self.activateWindow()
        if os.name == "nt":
            try:
                hwnd = int(self.winId())
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except (AttributeError, OSError, ValueError):
                pass

    def show_window(self) -> None:
        self._activate_window()
        QTimer.singleShot(120, self._activate_window)

    def _show_window(self) -> None:
        self.show_window()

    def _save_geometry(self) -> None:
        if not self.isMinimized():
            encoded = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.config.set("window_geometry", encoded)

    def quit_application(self) -> None:
        self._quitting = True
        self._save_geometry()
        self._status_timer.stop()
        self.diagnostics.stop_all()
        self.bridge.stop()
        self.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        self._save_geometry()
        can_tray = self.tray_icon.isVisible() and QSystemTrayIcon.isSystemTrayAvailable()
        if not self._quitting and self.config.get("close_to_tray", True) and can_tray:
            self.hide()
            self.tray_icon.showMessage("Integra", tr("app.tray_running"), QSystemTrayIcon.Information, 2500)
            event.ignore()
            return
        self.bridge.stop()
        self.diagnostics.stop_all()
        event.accept()
        QTimer.singleShot(0, QApplication.quit)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width = event.size().width()
        if self._sidebar_manual_override is None:
            if width < 980 and not self._sidebar_collapsed:
                self._set_sidebar_collapsed(True)
            elif width >= 1080 and self._sidebar_collapsed:
                self._set_sidebar_collapsed(False)
        self.top_caption.setVisible(width >= 930)
        for index, toast in enumerate([item for item in self.findChildren(ToastNotification) if item.isVisible()]):
            y = self.height() - 64 - toast.height() - index * (toast.height() + 10)
            toast.move(self.width() - toast.width() - 24, max(24, y))
