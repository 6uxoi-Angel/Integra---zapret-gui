#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Redesigned Zapret control center with live localization."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.i18n import tr
from core.zapret_manager import ZapretManager
from ui.widgets.common import Card, MetricCard, PageHeader, divider, section_label
from ui.workers import FunctionWorker


class HomePage(QWidget):
    operation_finished = Signal(bool, str)

    def __init__(self, zapret_manager: ZapretManager, config: Config, parent=None):
        super().__init__(parent)
        self.zapret_manager = zapret_manager
        self.config = config
        self._strategies: list[dict] = []
        self._worker: FunctionWorker | None = None
        self._operation_kind: str | None = None
        self._operation_success_key = ""
        self._operation_success_values: dict[str, str] = {}
        self._last_status = ZapretManager.STATUS_STOPPED
        self._last_pid = 0
        self._setup_ui()
        self._connect_signals()
        self.reload_strategies()
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

        hero = Card(hero=True)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_layout.setSpacing(18)
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setText("")
        self.status_dot.setProperty("running", False)
        self.status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_dot.setFixedSize(18, 18)
        status_text = QVBoxLayout()
        status_text.setSpacing(4)
        self.status_title = QLabel()
        self.status_title.setObjectName("HeroTitle")
        self.status_description = QLabel()
        self.status_description.setProperty("muted", True)
        self.status_description.setWordWrap(True)
        status_text.addWidget(self.status_title)
        status_text.addWidget(self.status_description)
        self.btn_start = QPushButton()
        self.btn_start.setProperty("role", "success")
        self.btn_stop = QPushButton()
        self.btn_stop.setProperty("role", "danger")
        hero_layout.addWidget(self.status_dot)
        hero_layout.addLayout(status_text, 1)
        hero_layout.addWidget(self.btn_start)
        hero_layout.addWidget(self.btn_stop)
        root.addWidget(hero)

        metrics = QGridLayout()
        metrics.setSpacing(12)
        self.metric_process = MetricCard("", "—", "winws.exe")
        self.metric_pid = MetricCard("PID", "—", "")
        self.metric_strategy = MetricCard("", "—", "")
        metrics.addWidget(self.metric_process, 0, 0)
        metrics.addWidget(self.metric_pid, 0, 1)
        metrics.addWidget(self.metric_strategy, 0, 2)
        for column in range(3):
            metrics.setColumnStretch(column, 1)
        root.addLayout(metrics)

        self.strategy_section = section_label("")
        root.addWidget(self.strategy_section)
        strategy_card = Card(variant="accent")
        strategy_layout = QVBoxLayout(strategy_card)
        strategy_layout.setContentsMargins(20, 18, 20, 18)
        strategy_layout.setSpacing(14)
        strategy_row = QHBoxLayout()
        strategy_row.setSpacing(10)
        self.strategy_combo = QComboBox()
        self.strategy_combo.setMinimumWidth(300)
        self.btn_reload = QPushButton()
        self.btn_reload.setProperty("role", "ghost")
        strategy_row.addWidget(self.strategy_combo, 1)
        strategy_row.addWidget(self.btn_reload)
        strategy_layout.addLayout(strategy_row)
        strategy_layout.addWidget(divider())
        self.strategy_category = QLabel()
        self.strategy_category.setStyleSheet("font-weight:700;background:transparent;")
        self.strategy_description = QLabel()
        self.strategy_description.setWordWrap(True)
        self.strategy_description.setProperty("muted", True)
        strategy_layout.addWidget(self.strategy_category)
        strategy_layout.addWidget(self.strategy_description)
        root.addWidget(strategy_card)

        self.service_section = section_label("")
        root.addWidget(self.service_section)
        service_card = Card()
        service_layout = QHBoxLayout(service_card)
        service_layout.setContentsMargins(20, 18, 20, 18)
        service_layout.setSpacing(12)
        service_text = QVBoxLayout()
        self.service_title = QLabel()
        self.service_title.setStyleSheet("font-weight:700;background:transparent;")
        self.service_hint = QLabel()
        self.service_hint.setProperty("muted", True)
        self.service_hint.setWordWrap(True)
        service_text.addWidget(self.service_title)
        service_text.addWidget(self.service_hint)
        self.btn_install_service = QPushButton()
        self.btn_install_service.setProperty("role", "primary")
        self.btn_remove_service = QPushButton()
        service_layout.addLayout(service_text, 1)
        service_layout.addWidget(self.btn_install_service)
        service_layout.addWidget(self.btn_remove_service)
        root.addWidget(service_card)
        root.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _connect_signals(self) -> None:
        self.btn_start.clicked.connect(self.start_selected)
        self.btn_stop.clicked.connect(self.stop_zapret)
        self.btn_reload.clicked.connect(self.reload_strategies)
        self.btn_install_service.clicked.connect(self.install_service)
        self.btn_remove_service.clicked.connect(self.remove_service)
        self.strategy_combo.currentIndexChanged.connect(self._on_strategy_changed)
        self.zapret_manager.status_changed.connect(self.update_status)
        self.zapret_manager.strategy_changed.connect(self._on_running_strategy_changed)

    @staticmethod
    def _category_label(category: str) -> str:
        return tr({
            "basic": "home.category_basic",
            "advanced": "home.category_advanced",
            "tls": "home.category_tls",
            "simple": "home.category_simple",
        }.get(category, "home.category_basic"))

    def reload_strategies(self) -> None:
        selected = self.config.get("selected_strategy", "general.bat")
        self._strategies = self.zapret_manager.get_strategies()
        self.strategy_combo.blockSignals(True)
        self.strategy_combo.clear()
        selected_index = -1
        for index, strategy in enumerate(self._strategies):
            self.strategy_combo.addItem(
                f"{strategy['name']} · {self._category_label(strategy['category'])}", strategy["file"]
            )
            if strategy["file"] == selected:
                selected_index = index
        if self._strategies:
            self.strategy_combo.setCurrentIndex(selected_index if selected_index >= 0 else 0)
        self.strategy_combo.blockSignals(False)
        self._on_strategy_changed(self.strategy_combo.currentIndex())
        self.update_status(self._last_status, self._last_pid)

    def selected_strategy(self) -> str:
        return str(self.strategy_combo.currentData() or "")

    def start_selected(self) -> None:
        strategy = self.selected_strategy()
        if not strategy:
            self.operation_finished.emit(False, tr("home.no_strategy"))
            return
        self.config.set("selected_strategy", strategy)
        self._run_operation(
            lambda: self.zapret_manager.start(strategy),
            kind="start",
            success_key="home.started_strategy",
            success_values={"strategy": strategy},
        )

    def stop_zapret(self) -> None:
        self._run_operation(
            self.zapret_manager.stop,
            kind="stop",
            success_key="status.stopped",
        )

    def install_service(self) -> None:
        strategy = self.selected_strategy()
        if not strategy:
            self.operation_finished.emit(False, tr("home.no_strategy"))
            return
        self.config.set("selected_strategy", strategy)
        self._run_operation(
            lambda: self.zapret_manager.install_service(strategy),
            kind="install",
            success_key="home.service_installed",
        )

    def remove_service(self) -> None:
        self._run_operation(
            self.zapret_manager.remove_service,
            kind="remove",
            success_key="home.service_removed",
        )

    def _run_operation(
        self,
        function,
        *,
        kind: str,
        success_key: str,
        success_values: dict[str, str] | None = None,
    ) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._operation_kind = kind
        self._operation_success_key = success_key
        self._operation_success_values = dict(success_values or {})
        self._worker = FunctionWorker(function, parent=self)
        self._worker.completed.connect(self._operation_done)
        self.update_status(self._last_status, self._last_pid)
        self._worker.start()

    def _operation_done(self, ok: bool, message: str) -> None:
        worker = self._worker
        success_key = self._operation_success_key
        success_values = dict(self._operation_success_values)
        self._worker = None
        self._operation_kind = None
        self._operation_success_key = ""
        self._operation_success_values = {}
        self.update_status(self.zapret_manager.get_status(), self.zapret_manager.get_pid())
        if ok:
            self.operation_finished.emit(True, tr(success_key, **success_values))
        elif message:
            self.operation_finished.emit(False, message)
        if worker:
            worker.deleteLater()

    def _on_strategy_changed(self, index: int) -> None:
        if not (0 <= index < len(self._strategies)):
            self.strategy_category.setText(tr("home.no_strategies"))
            self.strategy_description.setText(tr("home.path_hint"))
            return
        strategy = self._strategies[index]
        self.config.set("selected_strategy", strategy["file"])
        descriptions = {
            "basic": tr("home.strategy_basic"),
            "advanced": tr("home.strategy_advanced"),
            "tls": tr("home.strategy_tls"),
            "simple": tr("home.strategy_simple"),
        }
        self.strategy_category.setText(f"{self._category_label(strategy['category'])} · {strategy['file']}")
        self.strategy_description.setText(descriptions.get(strategy["category"], descriptions["basic"]))

    def _on_running_strategy_changed(self, strategy: str) -> None:
        self.metric_strategy.set_value(strategy)

    def _busy_text(self) -> str:
        return tr({
            "start": "home.starting",
            "stop": "home.stopping",
            "install": "home.installing",
            "remove": "home.removing",
        }.get(self._operation_kind or "", "common.ready"))

    def _update_action_texts(self) -> None:
        self.btn_start.setText(tr("home.start"))
        self.btn_stop.setText(tr("home.stop"))
        self.btn_install_service.setText(tr("home.install_service"))
        self.btn_remove_service.setText(tr("home.remove_service"))
        busy_buttons = {
            "start": self.btn_start,
            "stop": self.btn_stop,
            "install": self.btn_install_service,
            "remove": self.btn_remove_service,
        }
        if self._operation_kind in busy_buttons:
            busy_buttons[self._operation_kind].setText(self._busy_text())

    def update_status(self, status: str, pid: int) -> None:
        self._last_status, self._last_pid = status, pid
        running = status in {ZapretManager.STATUS_RUNNING, ZapretManager.STATUS_SERVICE}
        self.status_dot.setProperty("running", running)
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)
        if status == ZapretManager.STATUS_RUNNING:
            self.status_title.setText(tr("home.hero_running_title"))
            self.status_description.setText(tr("home.hero_running_desc"))
            self.metric_process.set_value(tr("home.process_active"))
            self.metric_pid.set_value(str(pid) if pid else "—")
            self.metric_strategy.set_value(self.zapret_manager.current_strategy or self.config.get("selected_strategy", "—"))
        elif status == ZapretManager.STATUS_SERVICE:
            self.status_title.setText(tr("home.hero_service_title"))
            self.status_description.setText(tr("home.hero_service_desc"))
            self.metric_process.set_value(tr("home.process_service"))
            self.metric_pid.set_value(str(pid) if pid else "—")
            self.metric_strategy.set_value(self.zapret_manager.current_strategy or self.config.get("selected_strategy", "—"))
        else:
            self.status_title.setText(tr("home.hero_stopped_title"))
            self.status_description.setText(tr("home.hero_stopped_desc"))
            self.metric_process.set_value(tr("home.process_stopped"))
            self.metric_pid.set_value("—")
            self.metric_strategy.set_value(self.config.get("selected_strategy", "—"))
        busy = bool(self._worker and self._worker.isRunning())
        self.btn_start.setEnabled(not running and bool(self._strategies) and not busy)
        self.btn_stop.setEnabled(status == ZapretManager.STATUS_RUNNING and not busy)
        self.btn_install_service.setEnabled(bool(self._strategies) and not busy)
        self.btn_remove_service.setEnabled(not busy)
        self.strategy_combo.setEnabled(not busy)
        self.btn_reload.setEnabled(not busy)
        self._update_action_texts()

    def retranslate_ui(self) -> None:
        self.header.set_text(tr("home.title"), tr("home.subtitle"))
        self.metric_process.set_content(tr("home.process"), "winws.exe")
        self.metric_pid.set_content("PID", tr("home.pid_hint"))
        self.metric_strategy.set_content(tr("home.strategy"), tr("home.strategy_hint"))
        self.strategy_section.setText(tr("home.strategy_section").upper())
        self.strategy_combo.setToolTip(tr("home.strategy_tooltip"))
        self.btn_reload.setText(tr("home.reload_strategies"))
        self.service_section.setText(tr("home.service_section").upper())
        self.service_title.setText(tr("home.service_title"))
        self.service_hint.setText(tr("home.service_hint"))
        self.reload_strategies()
        self._update_action_texts()
