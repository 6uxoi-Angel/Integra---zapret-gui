#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application and bundled-resource paths for source and PyInstaller builds."""

from __future__ import annotations

import sys
from pathlib import Path


def application_root() -> Path:
    """Return the directory containing the source tree or built executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_path(relative: str | Path) -> Path:
    """Resolve a packaged resource without assuming PyInstaller's layout."""
    relative_path = Path(relative)
    candidates = [application_root() / relative_path]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / relative_path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
