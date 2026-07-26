#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Локальный HTTP-мост между Integra и браузерным расширением."""

from __future__ import annotations

import hmac
import json
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

from core.network import measure_tcp_latency
from core.domain_utils import normalize_host
from core.lists_manager import ListsManager
from core.i18n import tr


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class BridgeServer:
    """Минимальный loopback API. Изменяющие запросы требуют bearer-токен."""

    API_VERSION = 1

    def __init__(
        self,
        lists_manager: ListsManager,
        token: str,
        port: int = 8765,
        status_provider: Optional[Callable[[], dict]] = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.lists_manager = lists_manager
        self.token = token
        self.port = int(port)
        self.status_provider = status_provider or (lambda: {})
        self.log_callback = log_callback or (lambda level, message: None)
        self._server: Optional[_ReusableThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._pairing_code = ""
        self._pairing_expires_at = 0.0
        self.regenerate_pairing_code()

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._server)

    @property
    def pairing_code(self) -> str:
        if time.monotonic() >= self._pairing_expires_at:
            self.regenerate_pairing_code()
        return self._pairing_code

    @property
    def pairing_expires_in(self) -> int:
        return max(0, int(self._pairing_expires_at - time.monotonic()))

    def regenerate_pairing_code(self) -> str:
        with self._lock:
            self._pairing_code = f"{secrets.randbelow(1_000_000):06d}"
            self._pairing_expires_at = time.monotonic() + 15 * 60
            return self._pairing_code

    def update_token(self, token: str) -> None:
        with self._lock:
            self.token = token

    def start(self) -> tuple[bool, str]:
        with self._lock:
            if self.is_running:
                return True, tr("bridge.already_running", port=self.port)
            handler = self._make_handler()
            try:
                self._server = _ReusableThreadingHTTPServer(("127.0.0.1", self.port), handler)
                self.port = int(self._server.server_address[1])
            except OSError as exc:
                self._server = None
                return False, tr("bridge.start_failed", error=exc)
            self._thread = threading.Thread(target=self._server.serve_forever, name="IntegraBridge", daemon=True)
            self._thread.start()
            self.log_callback("SUCCESS", tr("bridge.log_started", port=self.port))
            return True, tr("bridge.started", port=self.port)

    def stop(self) -> None:
        with self._lock:
            server, thread = self._server, self._thread
            self._server = None
            self._thread = None
        if not server and not thread:
            return
        if server:
            server.shutdown()
            server.server_close()
        if thread and thread.is_alive():
            thread.join(timeout=2)
        self.log_callback("INFO", tr("bridge.log_stopped"))

    def _make_handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "IntegraBridge/2.2"

            def log_message(self, _format: str, *args) -> None:
                return

            def end_headers(self) -> None:
                origin = self.headers.get("Origin", "")
                if origin.startswith(("chrome-extension://", "moz-extension://")):
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                super().end_headers()

            def do_OPTIONS(self) -> None:
                if not self._valid_origin():
                    self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": tr("bridge.invalid_origin")})
                    return
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._json(HTTPStatus.OK, {
                        "ok": True,
                        "service": "integra-bridge",
                        "api_version": bridge.API_VERSION,
                        "paired": False,
                    })
                    return
                if not self._authorized():
                    return

                query = parse_qs(parsed.query)
                if parsed.path == "/api/status":
                    data = dict(bridge.status_provider() or {})
                    data.update({
                        "ok": True,
                        "api_version": bridge.API_VERSION,
                        "bridge_port": bridge.port,
                        "counts": {
                            "bypass": bridge.lists_manager.get_count("list-general"),
                            "exclude": bridge.lists_manager.get_count("list-exclude"),
                        },
                    })
                    self._json(HTTPStatus.OK, data)
                    return

                if parsed.path == "/api/ping":
                    try:
                        host = normalize_host((query.get("host") or [""])[0], allow_ip=False)
                    except ValueError as exc:
                        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                        return
                    success, latency, error = measure_tcp_latency(host)
                    self._json(HTTPStatus.OK, {
                        "ok": success,
                        "host": host,
                        "latency_ms": latency if success else None,
                        "error": error or None,
                    })
                    return

                if parsed.path == "/api/domain":
                    try:
                        domain = normalize_host((query.get("domain") or [""])[0], allow_ip=True)
                    except ValueError as exc:
                        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                        return
                    self._json(HTTPStatus.OK, {
                        "ok": True,
                        "domain": domain,
                        "bypass": bridge.lists_manager.contains("list-general", domain),
                        "exclude": bridge.lists_manager.contains("list-exclude", domain),
                    })
                    return

                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": tr("bridge.route_missing")})

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/pair":
                    if not self._valid_origin():
                        self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": tr("bridge.invalid_origin")})
                        return
                    payload = self._read_json()
                    if payload is None:
                        return
                    code = str(payload.get("code", "")).strip()
                    valid = time.monotonic() < bridge._pairing_expires_at and hmac.compare_digest(code, bridge._pairing_code)
                    if not valid:
                        self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": tr("bridge.bad_pair_code")})
                        return
                    self._json(HTTPStatus.OK, {
                        "ok": True,
                        "token": bridge.token,
                        "port": bridge.port,
                        "api_version": bridge.API_VERSION,
                    })
                    bridge.log_callback("INFO", tr("bridge.connected"))
                    return

                if not self._authorized():
                    return
                payload = self._read_json()
                if payload is None:
                    return

                if parsed.path == "/api/domain":
                    try:
                        domain = normalize_host(str(payload.get("domain", "")), allow_ip=True)
                    except ValueError as exc:
                        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                        return
                    mode = str(payload.get("mode", "")).lower()
                    list_name = {"bypass": "list-general", "exclude": "list-exclude"}.get(mode)
                    if not list_name:
                        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": tr("bridge.bad_mode")})
                        return
                    # Один домен не должен одновременно находиться в противоположных списках.
                    opposite = "list-exclude" if list_name == "list-general" else "list-general"
                    bridge.lists_manager.remove_domain(opposite, domain)
                    added, message = bridge.lists_manager.add_domain(list_name, domain)
                    if not added and not bridge.lists_manager.contains(list_name, domain):
                        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": message})
                        return
                    bridge.log_callback("INFO", tr("bridge.domain_log", domain=domain, mode=mode))
                    self._json(HTTPStatus.OK, {
                        "ok": True,
                        "domain": domain,
                        "mode": mode,
                        "changed": added,
                        "restart_required": True,
                    })
                    return

                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": tr("bridge.route_missing")})

            def do_DELETE(self) -> None:
                parsed = urlparse(self.path)
                if not self._authorized():
                    return
                if parsed.path != "/api/domain":
                    self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": tr("bridge.route_missing")})
                    return
                query = parse_qs(parsed.query)
                try:
                    domain = normalize_host((query.get("domain") or [""])[0], allow_ip=True)
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                    return
                removed = bridge.lists_manager.remove_from_all(domain)
                bridge.log_callback("INFO", tr("bridge.domain_removed_log", domain=domain))
                self._json(HTTPStatus.OK, {"ok": True, "domain": domain, "removed_from": removed, "restart_required": bool(removed)})

            def _valid_origin(self) -> bool:
                origin = self.headers.get("Origin", "")
                return not origin or origin.startswith(("chrome-extension://", "moz-extension://"))

            def _authorized(self) -> bool:
                if not self._valid_origin():
                    self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": tr("bridge.invalid_origin")})
                    return False
                header = self.headers.get("Authorization", "")
                provided = header[7:].strip() if header.startswith("Bearer ") else ""
                if not provided or not hmac.compare_digest(provided, bridge.token):
                    self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": tr("bridge.auth_required")})
                    return False
                return True

            def _read_json(self) -> Optional[dict]:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length <= 0 or length > 16_384:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": tr("bridge.bad_length")})
                    return None
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": tr("bridge.bad_json")})
                    return None
                if not isinstance(payload, dict):
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": tr("bridge.json_object")})
                    return None
                return payload

            def _json(self, status: HTTPStatus | int, payload: dict) -> None:
                body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(int(status))
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler
