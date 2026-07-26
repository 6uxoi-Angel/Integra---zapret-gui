#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Domain and address normalization."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from core.i18n import tr

_HOST_RE = re.compile(
    r"^(?=.{1,253}\.?$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    re.IGNORECASE,
)


def normalize_host(value: str, allow_ip: bool = True) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError(tr("core.enter_domain"))
    parsed = urlparse(raw if "://" in raw else f"//{raw}", scheme="https")
    host = parsed.hostname
    if not host:
        raise ValueError(tr("core.cannot_parse_domain"))
    host = host.strip().rstrip(".").lower()
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if not allow_ip:
            raise ValueError(tr("core.ip_not_supported"))
        return ip.compressed
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(tr("core.invalid_domain")) from exc
    if ascii_host == "localhost" or _HOST_RE.fullmatch(ascii_host):
        return ascii_host
    raise ValueError(tr("core.invalid_domain"))
