#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure launch-mode decisions used by the GUI entry point and tests."""

from __future__ import annotations


def should_start_minimized(requested: bool, tray_visible: bool) -> bool:
    """Only explicit autostart requests may hide the initial main window."""
    return bool(requested and tray_visible)
