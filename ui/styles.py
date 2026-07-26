#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Four complete application themes."""

from __future__ import annotations

PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#F5F6F8", "sidebar": "#FFFFFF", "surface": "#FFFFFF", "surface_alt": "#F8F9FB",
        "surface_hover": "#EEF1F5", "raised": "#FFFFFF", "border": "#DDE2E8", "border_strong": "#C7CED8",
        "text": "#171B23", "muted": "#667085", "faint": "#98A2B3", "primary": "#3F4857",
        "primary_hover": "#2C3440", "primary_soft": "#EDF0F3", "accent": "#5B6472", "accent_soft": "#F0F2F5",
        "success": "#17875B", "success_soft": "#E8F5EF", "danger": "#C53E55", "danger_soft": "#FCECEF",
        "warning": "#A96612", "warning_soft": "#FFF5E5", "info": "#3478B8", "info_soft": "#EAF3FB",
        "input": "#FFFFFF", "selection": "#DDE3EA", "scroll": "#C9D0D9", "shadow": "rgba(25,35,50,0.08)",
        "log_bg": "#FCFCFD", "log_time": "#98A2B3", "log_info": "#3478B8", "log_success": "#17875B",
        "log_warning": "#A96612", "log_error": "#C53E55",
    },
    "light_accent": {
        "bg": "#F3F5FB", "sidebar": "#FFFFFF", "surface": "#FFFFFF", "surface_alt": "#F7F8FE",
        "surface_hover": "#EEF0FC", "raised": "#FFFFFF", "border": "#DDE1F0", "border_strong": "#C9CFE8",
        "text": "#17182A", "muted": "#656B82", "faint": "#969DB4", "primary": "#5B5CE2",
        "primary_hover": "#4849C7", "primary_soft": "#ECECFF", "accent": "#7A5AF8", "accent_soft": "#F0EBFF",
        "success": "#148A60", "success_soft": "#E7F7F0", "danger": "#D0445C", "danger_soft": "#FDECEF",
        "warning": "#B36C0D", "warning_soft": "#FFF4DF", "info": "#2F74C0", "info_soft": "#E9F2FC",
        "input": "#FFFFFF", "selection": "#DDDDFB", "scroll": "#C7CCE3", "shadow": "rgba(57,45,120,0.10)",
        "log_bg": "#FCFCFF", "log_time": "#969DB4", "log_info": "#2F74C0", "log_success": "#148A60",
        "log_warning": "#B36C0D", "log_error": "#D0445C",
    },
    "dark": {
        "bg": "#111317", "sidebar": "#17191E", "surface": "#191C22", "surface_alt": "#1D2027",
        "surface_hover": "#252932", "raised": "#20242B", "border": "#2A2F38", "border_strong": "#3A414D",
        "text": "#F4F5F7", "muted": "#A1A7B0", "faint": "#737A85", "primary": "#D5D8DE",
        "primary_hover": "#FFFFFF", "primary_soft": "#2B3038", "accent": "#AEB4BD", "accent_soft": "#252A31",
        "success": "#4FD19B", "success_soft": "#17372C", "danger": "#FF7188", "danger_soft": "#3C1F28",
        "warning": "#F4BD62", "warning_soft": "#3B301D", "info": "#78B8E9", "info_soft": "#1D3040",
        "input": "#15181D", "selection": "#343A44", "scroll": "#414852", "shadow": "rgba(0,0,0,0.30)",
        "log_bg": "#14171B", "log_time": "#737A85", "log_info": "#78B8E9", "log_success": "#4FD19B",
        "log_warning": "#F4BD62", "log_error": "#FF7188",
    },
    "dark_accent": {
        "bg": "#0D1020", "sidebar": "#11152A", "surface": "#151A31", "surface_alt": "#181E38",
        "surface_hover": "#222A4A", "raised": "#1A203B", "border": "#293253", "border_strong": "#3A4773",
        "text": "#F5F7FF", "muted": "#A7B0CD", "faint": "#737F9F", "primary": "#7C7EF6",
        "primary_hover": "#9395FF", "primary_soft": "#252A57", "accent": "#A875FF", "accent_soft": "#2D2453",
        "success": "#4ED7A0", "success_soft": "#173A31", "danger": "#FF718D", "danger_soft": "#43202D",
        "warning": "#FFC46B", "warning_soft": "#40321E", "info": "#6DBEFF", "info_soft": "#1B334B",
        "input": "#101529", "selection": "#343A72", "scroll": "#3B456C", "shadow": "rgba(0,0,0,0.35)",
        "log_bg": "#101426", "log_time": "#737F9F", "log_info": "#6DBEFF", "log_success": "#4ED7A0",
        "log_warning": "#FFC46B", "log_error": "#FF718D",
    },
}


def resolved_theme(theme: str) -> str:
    return theme if theme in PALETTES else "dark_accent"


def theme_colors(theme: str) -> dict[str, str]:
    return dict(PALETTES[resolved_theme(theme)])


def build_stylesheet(theme: str) -> str:
    theme = resolved_theme(theme)
    p = PALETTES[theme]
    primary_text = "#0D1020" if theme == "dark_accent" else ("#111317" if theme == "dark" else "#FFFFFF")
    return f"""
    * {{ font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif; font-size: 13px; outline: none; }}
    QMainWindow, QDialog, QMessageBox, QWidget#AppRoot, QWidget#ContentRoot, QStackedWidget#PageStack {{ background: {p['bg']}; color: {p['text']}; }}
    QWidget {{ color: {p['text']}; }}
    QToolTip {{ background: {p['raised']}; color: {p['text']}; border: 1px solid {p['border_strong']}; padding: 6px 8px; border-radius: 7px; }}

    QFrame#NavigationRail {{ background: {p['sidebar']}; border-right: 1px solid {p['border']}; }}
    QFrame#TopBar {{ background: {p['bg']}; border-bottom: 1px solid {p['border']}; }}
    QFrame#StatusStrip {{ background: {p['sidebar']}; border-top: 1px solid {p['border']}; }}
    QLabel#BrandMark {{ background: {p['primary']}; color: {primary_text}; border-radius: 12px; font-size: 18px; font-weight: 800; }}
    QLabel#Brand {{ font-size: 17px; font-weight: 760; }}
    QLabel#BrandVersion, QLabel[muted="true"] {{ color: {p['muted']}; }}
    QLabel[faint="true"] {{ color: {p['faint']}; }}
    QLabel#TopTitle {{ font-size: 18px; font-weight: 760; }}
    QLabel#TopCaption {{ color: {p['muted']}; }}
    QLabel#PageTitle {{ font-size: 28px; font-weight: 780; }}
    QLabel#PageSubtitle {{ color: {p['muted']}; font-size: 14px; }}
    QLabel#SectionTitle {{ font-size: 13px; font-weight: 720; color: {p['muted']}; letter-spacing: 0.5px; }}
    QLabel#MetricValue {{ font-size: 22px; font-weight: 780; }}
    QLabel#MetricValue[state="idle"], QLabel#MetricValue[state="pending"] {{ color: {p['muted']}; }}
    QLabel#MetricValue[state="done"][success="true"] {{ color: {p['success']}; }}
    QLabel#MetricValue[state="done"][success="false"] {{ color: {p['danger']}; }}
    QLabel#HeroTitle {{ font-size: 22px; font-weight: 780; }}
    QLabel#StatusDot[running="true"] {{ background: {p['success']}; border-radius: 9px; }}
    QLabel#StatusDot[running="false"] {{ background: {p['faint']}; border-radius: 9px; }}
    QFrame#BridgeStatusDot[running="true"] {{ background: {p['success']}; border: none; border-radius: 6px; }}
    QFrame#BridgeStatusDot[running="false"] {{ background: {p['faint']}; border: none; border-radius: 6px; }}
    QLabel#StatusPill {{ background: {p['success_soft']}; color: {p['success']}; border: 1px solid {p['success']}; border-radius: 10px; padding: 4px 9px; font-weight: 650; }}
    QLabel#StatusPill[running="false"] {{ background: {p['surface_alt']}; color: {p['muted']}; border-color: {p['border']}; }}
    QLabel#Badge {{ background: {p['primary_soft']}; color: {p['primary']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 2px 7px; font-size: 11px; font-weight: 650; }}

    QFrame#Card, QFrame#HeroCard, QFrame#AccentCard, QFrame#InsetCard {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 16px; }}
    QFrame#HeroCard {{ background: {p['raised']}; border-color: {p['border_strong']}; }}
    QFrame#AccentCard {{ background: {p['primary_soft']}; border-color: {p['border_strong']}; }}
    QFrame#InsetCard {{ background: {p['surface_alt']}; border-radius: 12px; }}
    QFrame#Divider {{ background: {p['border']}; min-height: 1px; max-height: 1px; border: none; }}

    QPushButton {{ background: {p['surface_alt']}; color: {p['text']}; border: 1px solid {p['border']}; border-radius: 10px; padding: 9px 14px; font-weight: 650; min-height: 18px; }}
    QPushButton:hover {{ background: {p['surface_hover']}; border-color: {p['border_strong']}; }}
    QPushButton:pressed {{ background: {p['selection']}; }}
    QPushButton:disabled {{ color: {p['faint']}; background: {p['surface_alt']}; border-color: {p['border']}; }}
    QPushButton[role="primary"] {{ background: {p['primary']}; color: {primary_text}; border-color: {p['primary']}; }}
    QPushButton[role="primary"]:hover {{ background: {p['primary_hover']}; border-color: {p['primary_hover']}; }}
    QPushButton[role="success"] {{ background: {p['success']}; color: #081A12; border-color: {p['success']}; }}
    QPushButton[role="success"]:hover {{ background: {p['success']}; border-color: {p['success']}; }}
    QPushButton[role="danger"] {{ background: {p['danger_soft']}; color: {p['danger']}; border-color: {p['danger']}; }}
    QPushButton[role="danger"]:hover {{ background: {p['danger']}; color: #FFFFFF; }}
    QPushButton[role="ghost"] {{ background: transparent; border-color: transparent; color: {p['muted']}; }}
    QPushButton[role="ghost"]:hover {{ background: {p['surface_hover']}; color: {p['text']}; }}
    QPushButton[nav="true"] {{ text-align: left; background: transparent; border: none; color: {p['muted']}; padding: 10px 12px; border-radius: 10px; font-weight: 650; }}
    QPushButton[nav="true"]:hover {{ background: {p['surface_hover']}; color: {p['text']}; }}
    QPushButton[nav="true"]:checked {{ background: {p['primary_soft']}; color: {p['primary']}; }}
    QPushButton[navCollapsed="true"] {{ text-align: center; padding: 10px 0; font-size: 17px; }}
    QPushButton[compact="true"] {{ padding: 5px 8px; min-width: 24px; border-radius: 8px; }}

    QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit, QListWidget {{ background: {p['input']}; color: {p['text']}; border: 1px solid {p['border']}; border-radius: 10px; padding: 8px 10px; selection-background-color: {p['selection']}; selection-color: {p['text']}; }}
    QTextEdit[logView="true"], QPlainTextEdit[logView="true"] {{ background: {p['log_bg']}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus, QListWidget:focus {{ border-color: {p['primary']}; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QListWidget:disabled {{ color: {p['faint']}; background: {p['surface_alt']}; }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox QAbstractItemView {{ background: {p['raised']}; color: {p['text']}; border: 1px solid {p['border_strong']}; selection-background-color: {p['primary_soft']}; selection-color: {p['text']}; padding: 4px; }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; border: none; background: transparent; }}
    QListWidget::item {{ border-radius: 7px; padding: 7px 8px; margin: 1px 0; }}
    QListWidget::item:hover {{ background: {p['surface_hover']}; }}
    QListWidget::item:selected {{ background: {p['primary_soft']}; color: {p['text']}; }}

    QCheckBox {{ spacing: 9px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {p['border_strong']}; border-radius: 5px; background: {p['input']}; }}
    QCheckBox::indicator:hover {{ border-color: {p['primary']}; }}
    QCheckBox::indicator:checked {{ background: {p['primary']}; border-color: {p['primary']}; }}

    QProgressBar {{ background: {p['surface_alt']}; border: 1px solid {p['border']}; border-radius: 8px; text-align: center; color: {p['text']}; min-height: 14px; }}
    QProgressBar::chunk {{ background: {p['primary']}; border-radius: 7px; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {p['scroll']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {p['scroll']}; border-radius: 4px; min-width: 30px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QMenu, QCalendarWidget, QAbstractItemView {{ background: {p['raised']}; color: {p['text']}; border: 1px solid {p['border_strong']}; }}
    QMenu {{ padding: 6px; }}
    QMenu::item {{ padding: 7px 24px 7px 10px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {p['primary_soft']}; }}
    QHeaderView::section {{ background: {p['surface_alt']}; color: {p['muted']}; border: none; border-bottom: 1px solid {p['border']}; padding: 7px; }}
    QStatusBar {{ background: {p['sidebar']}; color: {p['muted']}; }}

    ToastNotification {{ background: {p['raised']}; border: 1px solid {p['border_strong']}; border-radius: 12px; }}
    ToastNotification[type="success"] {{ border-left: 4px solid {p['success']}; }}
    ToastNotification[type="error"] {{ border-left: 4px solid {p['danger']}; }}
    ToastNotification[type="warning"] {{ border-left: 4px solid {p['warning']}; }}
    ToastNotification[type="info"] {{ border-left: 4px solid {p['info']}; }}
    QLabel#ToastIcon[type="success"] {{ color: {p['success']}; }}
    QLabel#ToastIcon[type="error"] {{ color: {p['danger']}; }}
    QLabel#ToastIcon[type="warning"] {{ color: {p['warning']}; }}
    QLabel#ToastIcon[type="info"] {{ color: {p['info']}; }}
    QLabel#ToastText {{ color: {p['text']}; }}
    QLabel[maintenanceStatus="success"] {{ color: {p['success']}; }}
    QLabel[maintenanceStatus="error"] {{ color: {p['danger']}; }}
    """
