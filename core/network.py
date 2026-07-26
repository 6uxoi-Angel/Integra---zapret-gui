#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Network checks independent from the UI."""

from __future__ import annotations

import socket
import time

from core.i18n import tr


def measure_tcp_latency(host: str, port: int = 443, timeout: float = 4.0) -> tuple[bool, int, str]:
    """Measures DNS + TCP handshake latency without ICMP or elevation."""
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency = max(1, round((time.perf_counter() - started) * 1000))
            return True, latency, ""
    except socket.gaierror:
        return False, 0, tr("network.dns_failed")
    except TimeoutError:
        return False, 0, tr("network.timeout")
    except OSError as exc:
        return False, 0, str(exc)
