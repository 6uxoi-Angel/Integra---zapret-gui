#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostics page with persisted custom websites and live localization."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.diagnostic_sites import MAX_CUSTOM_SITES, all_sites, make_site, sanitize_custom_sites
from core.diagnostics import DiagnosticsManager, DiagnosticsWorker
from core.i18n import tr
from core.zapret_manager import ZapretManager
from ui.widgets.common import Card, PageHeader, divider, section_label


class ServiceCheckCard(Card):
    """A single website result card that can be retranslated without losing state."""

    remove_requested = Signal(str)

    def __init__(self, site: dict, parent=None):
        super().__init__(parent, variant="inset")
        self.site = dict(site)
        self._state = "idle"
        self._success = False
        self._latency = 0
        self.setMinimumWidth(210)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(5)

        top = QHBoxLayout()
        self.title = QLabel(str(site["name"]))
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setStyleSheet("font-weight:700;background:transparent;")
        self.badge = QLabel()
        self.badge.setObjectName("Badge")
        top.addWidget(self.title, 1)
        top.addWidget(self.badge)

        self.remove_button: QPushButton | None = None
        if not site.get("default", False):
            self.remove_button = QPushButton("×")
            self.remove_button.setProperty("role", "ghost")
            self.remove_button.setProperty("compact", True)
            self.remove_button.setFixedWidth(28)
            self.remove_button.clicked.connect(lambda: self.remove_requested.emit(str(self.site["id"])))
            top.addWidget(self.remove_button)
        layout.addLayout(top)

        self.host = QLabel(f"{site['host']}:{site['port']}")
        self.host.setTextFormat(Qt.TextFormat.PlainText)
        self.host.setProperty("muted", True)
        self.result = QLabel()
        self.result.setObjectName("MetricValue")
        layout.addWidget(self.host)
        layout.addSpacing(7)
        layout.addWidget(self.result)
        self.retranslate_ui()

    def set_editor_enabled(self, enabled: bool) -> None:
        if self.remove_button is not None:
            self.remove_button.setEnabled(enabled)

    def apply_state(self, state: str, success: bool = False, latency: int = 0) -> None:
        self._state = state if state in {"idle", "pending", "done"} else "idle"
        self._success = bool(success)
        self._latency = max(0, int(latency))
        self._render_result()

    def _render_result(self) -> None:
        self.result.setProperty("state", self._state)
        self.result.setProperty("success", self._success)
        if self._state == "pending":
            text = tr("common.checking")
        elif self._state == "done":
            text = tr("common.ms", value=self._latency) if self._success else tr("common.unavailable")
        else:
            text = tr("common.not_checked")
        self.result.setText(text)
        self.result.style().unpolish(self.result)
        self.result.style().polish(self.result)

    def retranslate_ui(self) -> None:
        self.badge.setText(tr("diag.default_badge") if self.site.get("default", False) else tr("diag.custom_badge"))
        if self.remove_button is not None:
            self.remove_button.setToolTip(tr("diag.remove_site_tooltip"))
        self._render_result()


class DiagnosticsPage(QWidget):
    notification = Signal(str, str)
    strategy_selected = Signal(str)

    def __init__(self, diagnostics: DiagnosticsManager, zapret_manager: ZapretManager, config: Config, parent=None):
        super().__init__(parent)
        self.diagnostics = diagnostics
        self.zapret_manager = zapret_manager
        self.config = config
        self._connectivity_worker: DiagnosticsWorker | None = None
        self._auto_worker: DiagnosticsWorker | None = None
        self._site_states: dict[str, tuple[str, bool, int]] = {}
        self._system_results_data: dict[str, bool | str] | None = None
        self._auto_phase = "ready"
        self._auto_strategy = ""
        self._auto_error = ""
        self.cards: dict[str, ServiceCheckCard] = {}
        self._setup_ui()
        self._rebuild_site_cards()
        self.retranslate_ui()
        self._update_control_states()

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

        self.sites_section = section_label("")
        root.addWidget(self.sites_section)
        sites_card = Card()
        sites_layout = QVBoxLayout(sites_card)
        sites_layout.setContentsMargins(18, 16, 18, 18)
        sites_layout.setSpacing(14)
        self.sites_hint = QLabel()
        self.sites_hint.setProperty("muted", True)
        self.sites_hint.setWordWrap(True)
        sites_layout.addWidget(self.sites_hint)

        add_row = QHBoxLayout()
        add_row.setSpacing(9)
        self.site_name_input = QLineEdit()
        self.site_name_input.setMaximumWidth(220)
        self.site_address_input = QLineEdit()
        self.site_port_input = QSpinBox()
        self.site_port_input.setRange(1, 65535)
        self.site_port_input.setValue(443)
        self.site_port_input.setFixedWidth(100)
        self.add_site_button = QPushButton()
        self.add_site_button.setProperty("role", "primary")
        add_row.addWidget(self.site_name_input)
        add_row.addWidget(self.site_address_input, 1)
        add_row.addWidget(self.site_port_input)
        add_row.addWidget(self.add_site_button)
        sites_layout.addLayout(add_row)
        sites_layout.addWidget(divider())

        self.cards_host = QWidget()
        self.cards_grid = QGridLayout(self.cards_host)
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        self.cards_grid.setSpacing(10)
        sites_layout.addWidget(self.cards_host)
        self.check_button = QPushButton()
        self.check_button.setProperty("role", "primary")
        sites_layout.addWidget(self.check_button, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(sites_card)

        self.auto_section = section_label("")
        root.addWidget(self.auto_section)
        auto_card = Card(variant="accent")
        auto_layout = QVBoxLayout(auto_card)
        auto_layout.setContentsMargins(20, 18, 20, 18)
        auto_layout.setSpacing(12)
        self.auto_hint = QLabel()
        self.auto_hint.setProperty("muted", True)
        self.auto_hint.setWordWrap(True)
        auto_layout.addWidget(self.auto_hint)
        auto_actions = QHBoxLayout()
        self.auto_button = QPushButton()
        self.auto_button.setProperty("role", "success")
        self.cancel_auto_button = QPushButton()
        self.cancel_auto_button.setProperty("role", "danger")
        auto_actions.addWidget(self.auto_button)
        auto_actions.addWidget(self.cancel_auto_button)
        auto_actions.addStretch()
        auto_layout.addLayout(auto_actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        auto_layout.addWidget(self.progress)
        self.progress_label = QLabel()
        self.progress_label.setProperty("muted", True)
        self.progress_label.setWordWrap(True)
        auto_layout.addWidget(self.progress_label)
        root.addWidget(auto_card)

        self.system_section = section_label("")
        root.addWidget(self.system_section)
        system_card = Card()
        system_layout = QVBoxLayout(system_card)
        system_layout.setContentsMargins(20, 18, 20, 18)
        system_layout.setSpacing(12)
        self.system_button = QPushButton()
        self.system_button.setProperty("role", "primary")
        self.system_results = QLabel()
        self.system_results.setWordWrap(True)
        self.system_results.setProperty("muted", True)
        self.system_results.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        system_layout.addWidget(self.system_button, 0, Qt.AlignmentFlag.AlignLeft)
        system_layout.addWidget(self.system_results)
        root.addWidget(system_card)
        root.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

        self.add_site_button.clicked.connect(self._add_custom_site)
        self.site_address_input.returnPressed.connect(self._add_custom_site)
        self.check_button.clicked.connect(self._start_connectivity)
        self.auto_button.clicked.connect(self._start_auto_find)
        self.cancel_auto_button.clicked.connect(self._cancel_auto_find)
        self.system_button.clicked.connect(self._run_system_diagnostics)

    def _sites(self) -> list[dict]:
        return all_sites(self.config.get("diagnostic_sites", []))

    def _custom_sites(self) -> list[dict]:
        return sanitize_custom_sites(self.config.get("diagnostic_sites", []))

    def _columns_for_width(self, width: int) -> int:
        return 3 if width >= 900 else (2 if width >= 620 else 1)

    def _rebuild_site_cards(self) -> None:
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.cards.clear()
        for column in range(3):
            self.cards_grid.setColumnStretch(column, 0)

        sites = self._sites()
        columns = self._columns_for_width(self.width())
        for index, site in enumerate(sites):
            site_id = str(site["id"])
            card = ServiceCheckCard(site)
            card.remove_requested.connect(self._remove_custom_site)
            state, success, latency = self._site_states.get(site_id, ("idle", False, 0))
            card.apply_state(state, success, latency)
            self.cards[site_id] = card
            self.cards_grid.addWidget(card, index // columns, index % columns)
        for column in range(columns):
            self.cards_grid.setColumnStretch(column, 1)
        self._update_control_states()

    def _add_custom_site(self) -> None:
        if len(self._custom_sites()) >= MAX_CUSTOM_SITES:
            self.notification.emit(tr("diag.site_limit"), "warning")
            return
        try:
            site = make_site(
                self.site_address_input.text(),
                self.site_name_input.text(),
                self.site_port_input.value(),
            )
        except (TypeError, ValueError) as exc:
            self.notification.emit(str(exc), "warning")
            return
        existing = {(item["host"], item["port"]) for item in self._sites()}
        if (site["host"], site["port"]) in existing:
            self.notification.emit(tr("diag.duplicate_site"), "warning")
            return
        custom = sanitize_custom_sites([*self._custom_sites(), site])
        self.config.set("diagnostic_sites", custom)
        self.site_name_input.clear()
        self.site_address_input.clear()
        self.site_port_input.setValue(443)
        self._site_states[str(site["id"])] = ("idle", False, 0)
        self._rebuild_site_cards()
        self.notification.emit(tr("diag.site_added", host=site["host"], port=site["port"]), "success")

    def _remove_custom_site(self, site_id: str) -> None:
        if self._diagnostics_busy():
            return
        custom = [site for site in self._custom_sites() if site["id"] != site_id]
        self.config.set("diagnostic_sites", custom)
        self._site_states.pop(site_id, None)
        self._rebuild_site_cards()
        self.notification.emit(tr("diag.site_removed"), "info")

    def _diagnostics_busy(self) -> bool:
        connectivity = bool(self._connectivity_worker and self._connectivity_worker.isRunning())
        auto = bool(self._auto_worker and self._auto_worker.isRunning())
        return connectivity or auto

    def _update_control_states(self) -> None:
        connectivity = bool(self._connectivity_worker and self._connectivity_worker.isRunning())
        auto = bool(self._auto_worker and self._auto_worker.isRunning())
        editor_enabled = not connectivity and not auto
        for widget in (self.site_name_input, self.site_address_input, self.site_port_input, self.add_site_button):
            widget.setEnabled(editor_enabled)
        for card in self.cards.values():
            card.set_editor_enabled(editor_enabled)
        self.check_button.setEnabled(not connectivity and not auto and bool(self._sites()))
        self.auto_button.setEnabled(not connectivity and not auto)
        self.cancel_auto_button.setEnabled(auto)
        self.system_button.setEnabled(not auto)

    def _start_connectivity(self) -> None:
        if self._diagnostics_busy():
            return
        sites = self._sites()
        if not sites:
            self.notification.emit(tr("diag.no_sites"), "warning")
            return
        for site in sites:
            site_id = str(site["id"])
            self._site_states[site_id] = ("pending", False, 0)
            card = self.cards.get(site_id)
            if card:
                card.apply_state("pending")
        self._connectivity_worker = self.diagnostics.test_connectivity(self._on_ping_result, sites)
        self._connectivity_worker.completed.connect(self._connectivity_done)
        self._update_control_states()
        self.retranslate_ui()

    def _on_ping_result(self, site_id: str, success: bool, latency: int) -> None:
        self._site_states[site_id] = ("done", bool(success), int(latency))
        card = self.cards.get(site_id)
        if card:
            card.apply_state("done", success, latency)

    def _connectivity_done(self, ok: bool, message: str) -> None:
        self._connectivity_worker = None
        self._update_control_states()
        self.retranslate_ui()
        self.notification.emit(message, "success" if ok else "warning")

    def _start_auto_find(self) -> None:
        if self._diagnostics_busy():
            return
        if self.zapret_manager.get_status() == ZapretManager.STATUS_SERVICE:
            self.notification.emit(tr("diag.stop_service"), "warning")
            return
        strategies = self.zapret_manager.get_strategies()
        if not strategies:
            self.notification.emit(tr("diag.no_strategies"), "warning")
            return
        sites = self._sites()
        if not sites:
            self.notification.emit(tr("diag.no_sites"), "warning")
            return
        self._auto_phase = "prepare"
        self._auto_strategy = ""
        self._auto_error = ""
        self.progress.setValue(0)
        self._auto_worker = self.diagnostics.auto_find_strategy(
            strategies, self._on_auto_progress, self._on_strategy_result, sites
        )
        self._auto_worker.completed.connect(self._auto_done)
        self._update_control_states()
        self._render_auto_status()

    def _on_auto_progress(self, percent: int, strategy: str) -> None:
        self.progress.setValue(percent)
        self._auto_strategy = strategy
        self._auto_phase = "testing" if strategy else "finishing"
        self._render_auto_status()

    def _on_strategy_result(self, strategy: str, success: bool) -> None:
        if success:
            self._auto_strategy = strategy
            self._auto_phase = "found"
            self._render_auto_status()

    def _auto_done(self, ok: bool, message: str) -> None:
        was_cancelled = self._auto_phase == "cancelled"
        self._auto_worker = None
        if ok:
            self.progress.setValue(100)
            self._auto_strategy = message
            self._auto_phase = "working"
            self.strategy_selected.emit(message)
            self.notification.emit(tr("diag.auto_found", strategy=message), "success")
        elif was_cancelled:
            self._auto_phase = "cancelled"
            self.notification.emit(tr("diag.selection_cancelled"), "warning")
        else:
            self._auto_phase = "not_found" if message in {tr("diag.not_found"), tr("diag.selection_cancelled")} else "error"
            self._auto_error = message
            self.notification.emit(message, "warning")
        self._update_control_states()
        self._render_auto_status()

    def _cancel_auto_find(self) -> None:
        if self._auto_worker and self._auto_worker.isRunning():
            self._auto_phase = "cancelled"
            self._auto_worker.stop()
            self._update_control_states()
            self._render_auto_status()

    def _render_auto_status(self) -> None:
        phase = self._auto_phase
        if phase == "prepare":
            text = tr("diag.auto_prepare")
        elif phase == "testing":
            text = tr("diag.auto_testing", strategy=self._auto_strategy)
        elif phase == "finishing":
            text = tr("diag.auto_finishing")
        elif phase == "found":
            text = tr("diag.auto_found", strategy=self._auto_strategy)
        elif phase == "working":
            text = tr("diag.auto_working", strategy=self._auto_strategy)
        elif phase == "cancelled":
            text = tr("diag.selection_cancelled")
        elif phase == "not_found":
            text = tr("diag.not_found")
        elif phase == "error":
            text = self._auto_error or tr("diag.not_found")
        else:
            text = tr("diag.auto_ready")
        self.progress_label.setText(text)

    def _run_system_diagnostics(self) -> None:
        self._system_results_data = self.diagnostics.run_system_diagnostics()
        self._render_system_results()

    def _render_system_results(self) -> None:
        if self._system_results_data is None:
            self.system_results.setText(tr("diag.system_idle"))
            return
        labels = {
            "platform_windows": tr("diag.system.windows"),
            "zapret_path": tr("diag.system.path"),
            "winws_present": tr("diag.system.winws"),
            "winws_running": tr("diag.system.process"),
            "service_installed": tr("diag.system.service"),
            "windivert_present": tr("diag.system.windivert"),
            "admin_rights": tr("diag.system.admin"),
        }
        self.system_results.setText(
            "\n".join(
                f"{'✓' if bool(self._system_results_data.get(key)) else '✕'}  {label}"
                for key, label in labels.items()
            )
        )

    def retranslate_ui(self) -> None:
        self.header.set_text(tr("diag.title"), tr("diag.subtitle"))
        self.sites_section.setText(tr("diag.sites_section").upper())
        self.sites_hint.setText(tr("diag.sites_hint"))
        self.site_name_input.setPlaceholderText(tr("diag.site_name"))
        self.site_address_input.setPlaceholderText(tr("diag.site_address"))
        self.site_port_input.setToolTip(tr("diag.site_port"))
        self.add_site_button.setText(tr("diag.add_site"))
        connectivity = bool(self._connectivity_worker and self._connectivity_worker.isRunning())
        self.check_button.setText(tr("diag.checking_sites") if connectivity else tr("diag.check_sites"))
        self.auto_section.setText(tr("diag.auto_section").upper())
        self.auto_hint.setText(tr("diag.auto_hint"))
        self.auto_button.setText(tr("diag.auto_start"))
        self.cancel_auto_button.setText(tr("diag.auto_cancel"))
        self.system_section.setText(tr("diag.system_section").upper())
        self.system_button.setText(tr("diag.system_run"))
        self._render_auto_status()
        self._render_system_results()
        for card in self.cards.values():
            card.retranslate_ui()

    def resizeEvent(self, event) -> None:
        old_columns = self._columns_for_width(event.oldSize().width())
        new_columns = self._columns_for_width(event.size().width())
        if old_columns != new_columns:
            self._rebuild_site_cards()
        super().resizeEvent(event)
