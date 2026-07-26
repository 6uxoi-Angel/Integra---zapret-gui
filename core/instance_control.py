#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small file-based activation channel for an already running GUI instance."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path


def activation_request_path(config_path: Path) -> Path:
    return config_path.parent / "integra.show-request"


def write_activation_request(path: Path) -> int:
    """Atomically request that the running instance shows its main window."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.time_ns()
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as handle:
            handle.write(f"{stamp}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return stamp


def read_activation_request(path: Path) -> int:
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return 0
