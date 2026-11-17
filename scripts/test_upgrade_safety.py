"""Tests for private upgrade snapshots and runtime selection."""

import importlib.util
import base64
import http.server
import json
import os
import socketserver
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app/qwenpaw"))
import fnos_api

spec = importlib.util.spec_from_file_location(
    "qwenpaw_fnos_snapshot", ROOT / "app/qwenpaw/snapshot.py"
)
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class FnosPathTests(unittest.TestCase):
    def test_conversion_uses_unix_socket(self):
        received = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                received["path"] = self.path
                received["authorization"] = self.headers.get("Authorization")
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received["body"] = body
                payload = json.dumps({
                    "code": 0,
                    "data": {"status": 0, "result": [{
                        "path": body["data"]["path"],
                        "semanticPath": "存储空间1/应用文件/.qwenpaw",
                    }]},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory(dir="/tmp", prefix="qpf-") as directory:
            socket_path = str(Path(directory) / "api.sock")
            with socketserver.UnixStreamServer(socket_path, Handler) as server:
                thread = threading.Thread(target=server.handle_request)
                thread.start()
                try:
                    with patch.object(fnos_api, "SOCKET_PATH", socket_path), \
                         patch.dict(os.environ, {"TRIM_API_TOKEN": "test-token"}):
                        result = fnos_api.convert_path("/vol1/example")
                finally:
                    thread.join(timeout=3)
            self.assertEqual(result, "存储空间1/应用文件/.qwenpaw")
            self.assertEqual(received["path"], "/api/v1/trimapp")
            self.assertEqual(received["authorization"], "Bearer test-token")
            self.assertEqual(received["body"]["req"], "trim.file.convertPath")

    def test_converts_resolved_path_with_server_side_token(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "storage"
            target.mkdir()
            alias = root / "share"
            alias.symlink_to(target)
            resolved = os.path.realpath(alias / ".qwenpaw")
            payload = {
                "code": 0,
                "data": {"status": 0, "result": [
                    {"path": resolved, "semanticPath": "存储空间1/应用文件/.qwenpaw"}
                ]},
            }
            with patch.dict(os.environ, {"TRIM_API_TOKEN": "test-token"}), \
                 patch.object(fnos_api, "UnixHTTPConnection") as connection:
                response = connection.return_value.getresponse.return_value
                response.status = 200
                response.read.return_value = json.dumps(payload).encode()
                self.assertEqual(
                    fnos_api.convert_path(str(alias / ".qwenpaw")),
                    "存储空间1/应用文件/.qwenpaw",
                )
                args, kwargs = connection.return_value.request.call_args
                self.assertEqual(args, ("POST", "/api/v1/trimapp"))
                self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")
                self.assertEqual(json.loads(kwargs["body"]), {
                    "reqId": "qwenpaw-status",
                    "req": "trim.file.convertPath",
                    "appName": "com.dustinky.qwenpaw",
                    "data": {"path": resolved, "language": "zh-CN"},
                })

    def test_conversion_fails_closed_without_token_or_on_invalid_response(self):
        with patch.dict(os.environ, {"TRIM_API_TOKEN": ""}), \
             patch.object(fnos_api, "UnixHTTPConnection") as connection:
            self.assertIsNone(fnos_api.convert_path("/vol1/data"))
            connection.assert_not_called()
        with patch.dict(os.environ, {"TRIM_API_TOKEN": "test-token"}), \
             patch.object(fnos_api, "UnixHTTPConnection") as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            for payload in (
                {"code": 1},
                {"code": 0, "data": {"status": 1}},
                {"code": 0, "data": {"status": 0, "result": [
                    {"path": "/wrong", "semanticPath": "wrong"}
                ]}},
            ):
                response.read.return_value = json.dumps(payload).encode()
                self.assertIsNone(fnos_api.convert_path("/vol1/data"))
            connection.return_value.request.side_effect = OSError("socket unavailable")
            self.assertIsNone(fnos_api.convert_path("/vol1/data"))


class SnapshotTests(unittest.TestCase):
    def test_backup_contains_workdir_and_secrets_with_private_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workdir = root / "share with spaces" / ".qwenpaw"
            secret = root / "custom-secret"
            workdir.mkdir(parents=True)
            secret.mkdir()
            (workdir / "config.json").write_text("config", encoding="utf-8")
            (secret / ".master_key").write_text("key", encoding="utf-8")
            result = snapshot.snapshot(workdir, secret, root / "backups")
            self.assertEqual(result.stat().st_mode & 0o777, 0o600)
            with tarfile.open(result) as archive:
                self.assertEqual(
                    archive.extractfile(str(workdir / "config.json").lstrip("/")).read(),
                    b"config",
                )
                self.assertEqual(
                    archive.extractfile(str(secret / ".master_key").lstrip("/")).read(),
                    b"key",
                )

    def test_resolves_old_secret_variable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workdir = root / "work"
            workdir.mkdir()
            (workdir / ".env").write_text(
                f"COPAW_SECRET_DIR='{root / 'old secret'}'\n", encoding="utf-8"
            )
            _, secret = snapshot.data_paths(
                {"QWENPAW_WORKING_DIR": str(workdir)}, root / "missing"
            )
            self.assertEqual(secret, (root / "old secret").resolve())

    def test_refuses_backup_inside_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                snapshot.snapshot(root, root / "secret", root / "backups")

    def test_verifies_encrypted_values_before_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workdir = root / "work"
            secret = root / "secret"
            workdir.mkdir()
            secret.mkdir()
            raw_key = os.urandom(32)
            token = Fernet(base64.urlsafe_b64encode(raw_key)).encrypt(b"secret")
            (secret / "envs.json").write_text(
                json.dumps({"TOKEN": "ENC:" + token.decode()}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "密钥文件不存在"):
                snapshot.verify_file_key(workdir, secret)
            (secret / ".master_key").write_text(raw_key.hex(), encoding="utf-8")
            snapshot.verify_file_key(workdir, secret)
            (secret / ".master_key").write_text(os.urandom(32).hex(), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "无法使用"):
                snapshot.verify_file_key(workdir, secret)


class RuntimeTests(unittest.TestCase):
    def test_runtime_pointer_cannot_escape_through_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "qwenpaw-runtimes"
            runtime_root.mkdir()
            outside = root / "outside"
            (outside / "bin").mkdir(parents=True)
            (outside / "bin/python3").symlink_to(sys.executable)
            escape = runtime_root / "escape"
            escape.symlink_to(outside)
            (root / "qwenpaw-active-runtime").write_text(str(escape) + "\n")
            result = subprocess.run(
                ["bash", "-c", 'source "$1"; qwenpaw_setup', "bash",
                 str(ROOT / "app/qwenpaw/runtime.sh")],
                env=dict(os.environ, TRIM_PKGHOME=str(root)),
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid active runtime path", result.stderr)

    def test_cgi_accepts_runtime_pointer_through_home_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "actual-home"
            runtime = home / "qwenpaw-runtimes" / "runtime.test"
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin/python3").symlink_to(sys.executable)
            alias = root / "home"
            alias.symlink_to(home)
            (home / "qwenpaw-active-runtime").write_text(str(runtime) + "\n")
            env = dict(
                os.environ,
                TRIM_APPDEST=str(ROOT / "app"),
                TRIM_PKGHOME=str(alias),
                TRIM_PKGETC=str(root / "etc"),
                TRIM_PKGVAR=str(root / "var"),
                QUERY_STRING="action=status",
                REQUEST_METHOD="GET",
            )
            result = subprocess.run(
                ["bash", str(ROOT / "app/ui/api.cgi")],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout.split("\n\n", 1)[1])["success"])

    def test_cgi_initialization_failure_returns_json_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "qwenpaw-active-runtime").write_text("/tmp/other\n")
            env = dict(
                os.environ,
                TRIM_APPDEST=str(ROOT / "app"),
                TRIM_PKGHOME=str(root),
                TRIM_PKGETC=str(root / "etc"),
                TRIM_PKGVAR=str(root / "var"),
                QUERY_STRING="action=status",
                REQUEST_METHOD="GET",
            )
            result = subprocess.run(
                ["bash", str(ROOT / "app/ui/api.cgi")],
                env=env, capture_output=True, text=True,
            )
            self.assertIn("Status: 503 Service Unavailable", result.stdout)
            self.assertFalse(json.loads(result.stdout.split("\n\n", 1)[1])["success"])

    def test_log_endpoints_read_bounded_lines_and_handle_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / 'home "quoted"'
            var = root / 'var "quoted"'
            home.mkdir()
            var.mkdir()
            (home / "venv").symlink_to(Path(sys.executable).parent.parent)
            (var / "qwenpaw.log").write_bytes(
                b"".join(f"line {i}\n".encode() for i in range(501))
                + b"\x1b[31mERROR\x1b[0m invalid \xff\n"
            )
            (var / "qwenpaw-upgrade.log").write_text("upgrade complete\n", encoding="utf-8")
            env = dict(
                os.environ,
                TRIM_APPDEST=str(ROOT / "app"),
                TRIM_PKGHOME=str(home),
                TRIM_PKGETC=str(root / "etc"),
                TRIM_PKGVAR=str(var),
                REQUEST_METHOD="GET",
            )

            def request(action):
                result = subprocess.run(
                    ["bash", str(ROOT / "app/ui/api.cgi")],
                    env=dict(env, QUERY_STRING=f"action={action}"),
                    capture_output=True, text=True, check=True,
                )
                return json.loads(result.stdout.split("\n\n", 1)[1])

            runtime = request("logs")
            self.assertTrue(runtime["success"])
            self.assertEqual(len(runtime["logs"]), 500)
            self.assertEqual(runtime["logs"][0]["message"], "line 2")
            self.assertEqual(runtime["logs"][-1]["message"], "ERROR invalid \ufffd")
            self.assertEqual(request("upgrade_logs")["logs"][0]["message"], "upgrade complete")
            (var / "qwenpaw-upgrade.log").unlink()
            self.assertTrue(request("upgrade_logs")["missing"])

    def test_status_uses_actual_port_directory_and_auth_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            (home / "venv").symlink_to(Path(sys.executable).parent.parent)
            shared = root / 'share "quoted"'
            workdir = shared / ".qwenpaw"
            secret = shared / ".qwenpaw.secret"
            workdir.mkdir(parents=True)
            secret.mkdir()
            (secret / "auth.json").write_text(
                json.dumps({"user": {"username": "admin"}}), encoding="utf-8"
            )
            env = dict(
                os.environ,
                TRIM_APPDEST=str(ROOT / "app"),
                TRIM_PKGHOME=str(home),
                TRIM_PKGETC=str(root / "etc"),
                TRIM_PKGVAR=str(root / "var"),
                TRIM_DATA_SHARE_PATHS=str(shared),
                TRIM_SERVICE_PORT="19123",
                QUERY_STRING="action=status",
                REQUEST_METHOD="GET",
            )
            result = subprocess.run(
                ["bash", str(ROOT / "app/ui/api.cgi")],
                env=env, capture_output=True, text=True, check=True,
            )
            payload = json.loads(result.stdout.split("\n\n", 1)[1])
            self.assertTrue(payload["authEnabled"])
            self.assertTrue(payload["authConfigured"])
            self.assertEqual(payload["port"], 19123)
            self.assertEqual(payload["workingDir"], str(workdir))

    def test_cgi_routes_only_known_pages_to_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            www = root / "www"
            www.mkdir()
            (www / "index.html").write_text("frontend", encoding="utf-8")
            env = dict(os.environ, TRIM_APPDEST=str(root))
            for path in ("files", "logs", "about", "tunnel"):
                result = subprocess.run(
                    ["bash", str(ROOT / "app/ui/index.cgi")],
                    env=dict(env, REQUEST_URI=f"/index.cgi/{path}"),
                    capture_output=True, text=True, check=True,
                )
                self.assertIn("Content-Type: text/html", result.stdout)
                self.assertTrue(result.stdout.endswith("frontend"))
            result = subprocess.run(
                ["bash", str(ROOT / "app/ui/index.cgi")],
                env=dict(env, REQUEST_URI="/index.cgi/missing.js"),
                capture_output=True, text=True, check=True,
            )
            self.assertIn("404 Not Found", result.stdout)

    def test_bundle_without_console_is_rejected_before_creating_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = dict(
                os.environ,
                TRIM_APPDEST=str(root / "target"),
                TRIM_PKGHOME=str(root / "home"),
                TRIM_PKGETC=str(root / "etc"),
            )
            result = subprocess.run(
                ["bash", "-c", 'source "$1"; qwenpaw_setup && qwenpaw_prepare_runtime bundle',
                 "bash", str(ROOT / "app/qwenpaw/runtime.sh")],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("安装包缺少官方控制台", result.stderr)
            self.assertFalse((root / "home/qwenpaw-runtimes").exists())

    def test_configuration_persists_log_level_without_starting_stopped_service(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            etc = root / "etc"
            var = root / "var"
            etc.mkdir()
            var.mkdir()
            env = dict(
                os.environ,
                TRIM_APPDEST=str(ROOT / "app"),
                TRIM_PKGETC=str(etc),
                TRIM_PKGVAR=str(var),
                TRIM_PKGHOME=str(root / "home"),
                wizard_log_level="debug",
            )
            result = subprocess.run(
                ["bash", str(ROOT / "cmd/config_callback")],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((etc / "qwenpaw-log-level").read_text(), "debug\n")
            self.assertFalse((var / "qwenpaw.pid").exists())
            env.pop("wizard_log_level")
            result = subprocess.run(
                ["bash", "-c", 'source "$1"; qwenpaw_setup && printf "%s" "$QWENPAW_LOG_LEVEL"',
                 "bash", str(ROOT / "app/qwenpaw/runtime.sh")],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "debug")

    def test_configuration_rejects_invalid_log_level(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = dict(
                os.environ,
                TRIM_APPDEST=str(ROOT / "app"),
                TRIM_PKGETC=str(root / "etc"),
                TRIM_PKGVAR=str(root / "var"),
                TRIM_PKGHOME=str(root / "home"),
                wizard_log_level="invalid",
            )
            result = subprocess.run(
                ["bash", str(ROOT / "cmd/config_callback")],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "etc/qwenpaw-log-level").exists())

    def test_rejects_runtime_pointer_outside_package_home(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "qwenpaw-active-runtime").write_text("/tmp/other\n", encoding="utf-8")
            env = dict(os.environ, TRIM_PKGHOME=str(root))
            result = subprocess.run(
                ["bash", "-c", 'source "$1"; qwenpaw_setup', "bash",
                 str(ROOT / "app/qwenpaw/runtime.sh")],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid active runtime path", result.stderr)


if __name__ == "__main__":
    unittest.main()
