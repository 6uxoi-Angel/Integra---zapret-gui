from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from core.bridge_server import BridgeServer
from core.config import Config
from core.diagnostic_sites import MAX_CUSTOM_SITES, all_sites, make_site, sanitize_custom_sites
from core.domain_utils import normalize_host
from core.i18n import _TRANSLATIONS, set_language, tr
from core.instance_control import activation_request_path, read_activation_request, write_activation_request
from core.launch_policy import should_start_minimized
from core.paths import application_root, resource_path
from core.preflight import inspect_zapret_installation
from core.startup import startup_command
from core.zapret_maintenance import ZapretMaintenance, ZapretRelease
from core.lists_manager import ListsManager
from core.windows_process import build_hidden_runtime_batch
from core.zapret_manager import ZapretManager
from ui.main_window import MainWindow
from ui.styles import PALETTES, build_stylesheet, resolved_theme


class DomainUtilsTests(unittest.TestCase):
    def test_normalizes_url_and_idna(self):
        self.assertEqual(normalize_host("https://Example.COM/path?q=1"), "example.com")
        self.assertEqual(normalize_host("https://пример.рф"), "xn--e1afmkfd.xn--p1ai")

    def test_rejects_invalid_host(self):
        with self.assertRaises(ValueError):
            normalize_host("not a domain")


class ConfigTests(unittest.TestCase):
    def test_round_trip_and_generated_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = Config(path)
            self.assertTrue(config.get("bridge_token"))
            config.update({"theme": "light", "bridge_port": 99999})
            loaded = Config(path)
            self.assertEqual(loaded.get("theme"), "light")
            self.assertEqual(loaded.get("bridge_port"), 65535)

    def test_recovers_broken_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{broken", encoding="utf-8")
            config = Config(path)
            self.assertEqual(config.get("theme"), "dark_accent")
            self.assertTrue(path.with_suffix(".broken.json").exists())

    def test_sanitizes_theme_language_and_custom_sites(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({
                "theme": "system",
                "language": "DE",
                "diagnostic_sites": [
                    {"host": "https://Example.com/path", "name": "Example", "port": 443},
                    {"host": "example.com", "name": "Duplicate", "port": 443},
                    {"host": "bad host", "port": 443},
                ],
            }), encoding="utf-8")
            config = Config(path)
            self.assertEqual(config.get("theme"), "dark_accent")
            self.assertEqual(config.get("language"), "ru")
            self.assertEqual(len(config.get("diagnostic_sites")), 1)
            self.assertEqual(config.get("diagnostic_sites")[0]["host"], "example.com")


class DiagnosticSitesTests(unittest.TestCase):
    def setUp(self):
        set_language("ru")

    def test_make_site_from_url_and_custom_name(self):
        site = make_site("https://Example.com/a", "My site", 8443)
        self.assertEqual(site["host"], "example.com")
        self.assertEqual(site["name"], "My site")
        self.assertEqual(site["port"], 8443)
        self.assertFalse(site["default"])

    def test_sanitize_deduplicates_defaults_and_limits_count(self):
        # Build a list that includes a default-site duplicate and exceeds the limit.
        raw = [{"host": "discord.com", "port": 443}] + [
            {"host": f"site-{index}.example", "port": 443}
            for index in range(MAX_CUSTOM_SITES + 5)
        ]
        sanitized = sanitize_custom_sites(raw)
        self.assertEqual(len(sanitized), MAX_CUSTOM_SITES)
        self.assertNotIn("discord.com", {site["host"] for site in sanitized})
        self.assertEqual(len(all_sites(sanitized)), MAX_CUSTOM_SITES + 3)

    def test_port_error_is_localized(self):
        set_language("en")
        with self.assertRaisesRegex(ValueError, "Port must"):
            make_site("example.com", port=0)
        set_language("ru")


class LocalizationAndThemeTests(unittest.TestCase):
    def tearDown(self):
        set_language("ru")

    def test_translation_catalogs_have_identical_keys(self):
        self.assertEqual(set(_TRANSLATIONS["ru"]), set(_TRANSLATIONS["en"]))
        set_language("ru")
        self.assertEqual(tr("settings.theme_light_accent"), "Светлая с выделениями")
        set_language("en")
        self.assertEqual(tr("settings.theme_light_accent"), "Light with accents")

    def test_all_four_themes_are_complete(self):
        expected = {"light", "light_accent", "dark", "dark_accent"}
        self.assertEqual(set(PALETTES), expected)
        required = set(PALETTES["dark_accent"])
        for name, palette in PALETTES.items():
            self.assertEqual(set(palette), required, name)
            stylesheet = build_stylesheet(name)
            self.assertIn("QMainWindow", stylesheet)
            self.assertNotIn("{p[", stylesheet)
        self.assertEqual(resolved_theme("unknown"), "dark_accent")


class ListsManagerTests(unittest.TestCase):
    def setUp(self):
        set_language("ru")
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "lists").mkdir()
        self.manager = ListsManager(str(self.root))

    def tearDown(self):
        self.temp.cleanup()

    def test_add_duplicate_remove_and_preserve_comment(self):
        target = self.root / "lists" / "list-general.txt"
        target.write_text("# keep this\nexisting.example\n", encoding="utf-8")
        ok, value = self.manager.add_domain("list-general", "https://Example.com/page")
        self.assertTrue(ok)
        self.assertEqual(value, "example.com")
        ok, message = self.manager.add_domain("list-general", "example.com")
        self.assertFalse(ok)
        self.assertIn("уже есть", message)
        ok, _ = self.manager.remove_domain("list-general", "existing.example")
        self.assertTrue(ok)
        self.assertIn("# keep this", target.read_text(encoding="utf-8"))

    def test_moves_between_modes(self):
        self.manager.add_domain("list-general", "example.com")
        self.manager.remove_domain("list-general", "example.com")
        self.manager.add_domain("list-exclude", "example.com")
        self.assertFalse(self.manager.contains("list-general", "example.com"))
        self.assertTrue(self.manager.contains("list-exclude", "example.com"))


class BridgeServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "lists").mkdir()
        self.manager = ListsManager(str(root))
        self.bridge = BridgeServer(self.manager, token="test-token", port=0)
        ok, message = self.bridge.start()
        self.assertTrue(ok, message)
        self.base = f"http://127.0.0.1:{self.bridge.port}"

    def tearDown(self):
        self.bridge.stop()
        self.temp.cleanup()

    def request(self, path: str, method: str = "GET", payload=None, token: str | None = None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Origin": "chrome-extension://unit-test"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_pair_and_domain_workflow(self):
        status, paired = self.request("/pair", "POST", {"code": self.bridge.pairing_code})
        self.assertEqual(status, 200)
        self.assertEqual(paired["token"], "test-token")

        status, added = self.request(
            "/api/domain", "POST", {"domain": "https://Example.com/path", "mode": "bypass"}, "test-token"
        )
        self.assertEqual(status, 200)
        self.assertTrue(added["ok"])
        _, membership = self.request("/api/domain?domain=example.com", token="test-token")
        self.assertTrue(membership["bypass"])

        _, deleted = self.request("/api/domain?domain=example.com", "DELETE", token="test-token")
        self.assertEqual(deleted["removed_from"], 1)

    def test_rejects_missing_token(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request("/api/status")
        self.assertEqual(context.exception.code, 401)


class WindowsProcessTests(unittest.TestCase):
    def test_runtime_batch_removes_start_and_has_no_unwanted_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "general (ALT).bat"
            runtime = Path(tmp) / "runtime.bat"
            source.write_text(
                '@echo off\r\n'
                'chcp 65001 > nul\r\n'
                'start "zapret: %~n0" /min "%BIN%winws.exe" --wf-tcp=80,443 ^\r\n'
                '--filter-tcp=443\r\n',
                encoding="utf-8",
                newline="",
            )
            build_hidden_runtime_batch(source, runtime)
            raw = runtime.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            text = raw.decode("utf-8")
            self.assertIn('@set "NO_UPDATE_CHECK=1"', text)
            self.assertIn('"%BIN%winws.exe" --wf-tcp=80,443', text)
            self.assertNotIn('start "zapret:', text.casefold())


class PreflightTests(unittest.TestCase):
    def test_zapret_readiness_requires_both_strategy_and_winws(self):
        missing = inspect_zapret_installation("")
        self.assertEqual(missing.status, "warning")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "general.bat").write_text("@echo off\n", encoding="utf-8")
            incomplete = inspect_zapret_installation(str(root))
            self.assertEqual(incomplete.status, "warning")

            (root / "bin").mkdir()
            (root / "bin" / "winws.exe").write_bytes(b"")
            ready = inspect_zapret_installation(str(root))
            self.assertEqual(ready.status, "ok")


class ZapretMaintenanceTests(unittest.TestCase):
    def _make_installation(self, root: Path) -> None:
        (root / "bin").mkdir(parents=True)
        (root / "lists").mkdir()
        (root / "general.bat").write_text("@echo off\n", encoding="utf-8")
        (root / "bin" / "winws.exe").write_bytes(b"winws")

    def test_compares_release_versions_numerically(self):
        self.assertTrue(ZapretMaintenance.is_newer("1.9.9", "1.10.0"))
        self.assertFalse(ZapretMaintenance.is_newer("1.10.0", "1.9.9"))
        self.assertFalse(ZapretMaintenance.is_newer("unknown", "1.10.0"))

    def test_check_reports_available_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "zapret"
            self._make_installation(root)
            (root / ".integra-zapret.json").write_text('{"version":"1.9.9"}', encoding="utf-8")
            maintenance = ZapretMaintenance()
            with patch.object(maintenance, "fetch_latest_release", return_value=ZapretRelease("1.10.0", "https://example.test/zapret.zip")):
                result = maintenance.check(str(root), check_remote=True)
            self.assertEqual(result.state, "update_available")
            self.assertEqual(result.installed_version, "1.9.9")
            self.assertEqual(result.latest_version, "1.10.0")

    def test_install_replaces_release_and_preserves_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "zapret"
            self._make_installation(target)
            (target / "lists" / "list-general.txt").write_text("custom.example\n", encoding="utf-8")
            archive = base / "release.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("zapret-discord-youtube-1.10.0/general.bat", "@echo off\n")
                bundle.writestr("zapret-discord-youtube-1.10.0/bin/winws.exe", b"new-winws")
                bundle.writestr("zapret-discord-youtube-1.10.0/lists/list-general.txt", "default.example\n")

            maintenance = ZapretMaintenance()
            release = ZapretRelease("1.10.0", "https://example.test/zapret.zip")
            with patch.object(maintenance, "_download_archive", side_effect=lambda _release, destination: shutil.copyfile(archive, destination)):
                maintenance._install_release(release, target)

            self.assertTrue(maintenance.is_valid_installation(target))
            self.assertEqual(maintenance.installed_version(target), "1.10.0")
            self.assertEqual((target / "lists" / "list-general.txt").read_text(encoding="utf-8"), "custom.example\n")

    def test_disabled_auto_update_reports_availability_without_installing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "zapret"
            self._make_installation(root)
            (root / ".integra-zapret.json").write_text('{"version":"1.9.9"}', encoding="utf-8")
            maintenance = ZapretMaintenance()
            release = ZapretRelease("1.10.0", "https://example.test/zapret.zip")
            with patch.object(maintenance, "fetch_latest_release", return_value=release), patch.object(maintenance, "_install_release") as install:
                result = maintenance.maintain(
                    str(root), auto_install=False, auto_update=False, check_remote=True
                )
            self.assertEqual(result.state, "update_available")
            self.assertEqual((result.installed_version, result.latest_version), ("1.9.9", "1.10.0"))
            install.assert_not_called()


class MaintenanceUiPolicyTests(unittest.TestCase):
    def test_running_zapret_allows_check_but_disables_automatic_update(self):
        captured: dict[str, object] = {}

        class Signal:
            def connect(self, callback):
                captured["callback"] = callback

        class Worker:
            def __init__(self, maintenance, configured_path, **kwargs):
                captured["maintenance"] = maintenance
                captured["path"] = configured_path
                captured.update(kwargs)
                self.completed = Signal()

            def isRunning(self):
                return False

            def start(self):
                captured["started"] = True

        class ConfigStub:
            zapret_path = "C:/managed-zapret"

            @staticmethod
            def get(key, default=None):
                return {"auto_check_zapret": True, "auto_install_zapret": False, "auto_update_zapret": True}.get(key, default)

        class ManagerStub:
            @staticmethod
            def get_status():
                return ZapretManager.STATUS_RUNNING

            @staticmethod
            def is_service_installed():
                return False

        class SettingsStub:
            @staticmethod
            def set_maintenance_status(*_args):
                return None

        window = MainWindow.__new__(MainWindow)
        window._maintenance_worker = None
        window.config = ConfigStub()
        window.zapret_manager = ManagerStub()
        window.zapret_maintenance = object()
        window.pages = {"settings": SettingsStub()}
        with patch("ui.main_window.ZapretMaintenanceWorker", Worker):
            window._run_zapret_maintenance()

        self.assertTrue(captured["started"])
        self.assertTrue(captured["check_remote"])
        self.assertFalse(captured["auto_update"])


class LaunchAndPackagingTests(unittest.TestCase):
    def test_activation_request_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            request_path = activation_request_path(config_path)
            self.assertEqual(read_activation_request(request_path), 0)
            stamp = int(write_activation_request(request_path))
            self.assertEqual(read_activation_request(request_path), stamp)

    def test_source_resource_paths(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(application_root(), root)
        self.assertEqual(resource_path("browser-extension"), root / "browser-extension")

    def test_manual_launch_is_never_hidden(self):
        self.assertFalse(should_start_minimized(False, True))
        self.assertFalse(should_start_minimized(True, False))
        self.assertTrue(should_start_minimized(True, True))

    def test_startup_command_has_explicit_visibility_mode(self):
        with patch("core.startup.os.name", "posix"):
            self.assertIn("--minimized", startup_command(True))
            self.assertIn("--show", startup_command(False))

    def test_windows_launchers_and_build_layout(self):
        root = Path(__file__).resolve().parents[1]
        run_bat = (root / "run.bat").read_text(encoding="utf-8")
        install_bat = (root / "install.bat").read_text(encoding="utf-8")
        run_vbs = (root / "run.vbs").read_text(encoding="utf-8")
        build_bat = (root / "build.bat").read_text(encoding="utf-8")
        test_bat = (root / "test.bat").read_text(encoding="utf-8")
        bootstrap = (root / "scripts" / "bootstrap_python.ps1").read_text(encoding="utf-8")
        self.assertIn('install.bat" --quiet', run_bat)
        self.assertIn("from PySide6.QtWidgets import QApplication; import psutil", run_bat)
        self.assertIn("sys.version_info[1] in range(10, 15)", install_bat)
        self.assertIn("from PySide6.QtWidgets import QApplication; import psutil", install_bat)
        self.assertIn("import PyInstaller; from PySide6.QtWidgets import QApplication; import psutil", build_bat)
        self.assertNotIn("^<", install_bat)
        self.assertIn("--show", run_vbs)
        self.assertIn("scripts\\build_app.py --arch x64", build_bat)
        app_builder = (root / "scripts" / "build_app.py").read_text(encoding="utf-8")
        self.assertIn("--contents-directory", app_builder)
        self.assertIn("browser-extension", app_builder)
        self.assertIn('APP_ROOT = REPOSITORY_ROOT / "app"', app_builder)
        self.assertIn("PySide6 does not publish a win32 wheel", app_builder)
        self.assertTrue((root.parent / "app" / "Integra" / "Integra.exe").is_file())
        extension_page = (root / "ui" / "pages" / "extension_page.py").read_text(encoding="utf-8")
        stylesheet = (root / "ui" / "styles.py").read_text(encoding="utf-8")
        self.assertIn("self.status_dot = QFrame()", extension_page)
        self.assertIn("self.status_dot.setFixedSize(12, 12)", extension_page)
        self.assertIn("QFrame#BridgeStatusDot", stylesheet)
        self.assertIn("check_project.py", test_bat)
        self.assertIn("Get-Command $name", bootstrap)
        self.assertIn("Python.Python.3.13", bootstrap)
        self.assertIn("python.org", bootstrap)


class ExtensionFilesTests(unittest.TestCase):
    def test_manifest_and_assets(self):
        root = Path(__file__).resolve().parents[1] / "browser-extension"
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["manifest_version"], 3)
        self.assertTrue((root / manifest["background"]["service_worker"]).exists())
        self.assertTrue((root / manifest["action"]["default_popup"]).exists())
        for path in manifest["icons"].values():
            self.assertTrue((root / path).exists())

        ru = json.loads((root / "_locales" / "ru" / "messages.json").read_text(encoding="utf-8"))
        en = json.loads((root / "_locales" / "en" / "messages.json").read_text(encoding="utf-8"))
        self.assertEqual(set(ru), set(en))
        self.assertEqual(manifest["action"]["default_title"], "__MSG_extName__")


if __name__ == "__main__":
    unittest.main()
