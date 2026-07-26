#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validation and persistence helpers for diagnostic websites."""

from __future__ import annotations

import hashlib
from typing import Any

from core.domain_utils import normalize_host
from core.i18n import tr

MAX_CUSTOM_SITES = 40

DEFAULT_SITES: tuple[dict[str, Any], ...] = (
    {"id": "default-discord", "name": "Discord", "host": "discord.com", "port": 443, "default": True},
    {"id": "default-youtube", "name": "YouTube", "host": "youtube.com", "port": 443, "default": True},
    {"id": "default-github", "name": "GitHub", "host": "github.com", "port": 443, "default": True},
)


def make_site(value: str, name: str = "", port: int = 443, *, default: bool = False) -> dict[str, Any]:
    host = normalize_host(value, allow_ip=True)
    normalized_port = int(port)
    if not 1 <= normalized_port <= 65535:
        raise ValueError(tr("common.port_invalid"))
    display_name = (name or "").strip() or host
    digest = hashlib.sha1(f"{host}:{normalized_port}".encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return {
        "id": f"site-{digest}",
        "name": display_name[:80],
        "host": host,
        "port": normalized_port,
        "default": bool(default),
    }


def sanitize_custom_sites(raw_sites: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_sites, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in raw_sites:
        if not isinstance(item, dict):
            continue
        try:
            site = make_site(
                str(item.get("host") or item.get("url") or ""),
                str(item.get("name") or ""),
                int(item.get("port", 443)),
                default=False,
            )
        except (TypeError, ValueError):
            continue
        key = (site["host"], site["port"])
        if key in seen or any(key == (default["host"], default["port"]) for default in DEFAULT_SITES):
            continue
        seen.add(key)
        result.append(site)
    return result[:MAX_CUSTOM_SITES]


def all_sites(custom_sites: Any) -> list[dict[str, Any]]:
    return [dict(site) for site in DEFAULT_SITES] + sanitize_custom_sites(custom_sites)
