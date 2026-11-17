"""Small server-side client for the fnOS open API."""

import http.client
import json
import os
import socket


SOCKET_PATH = "/var/run/trim_open_gateway_apiscope.socket"
APP_NAME = "com.dustinky.qwenpaw"


class UnixHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET_PATH)


def convert_path(path, language="zh-CN"):
    """Return a semantic path, or None when fnOS cannot convert it."""
    token = os.environ.get("TRIM_API_TOKEN")
    if not token or not path:
        return None

    real_path = os.path.realpath(path)
    request = {
        "reqId": "qwenpaw-status",
        "req": "trim.file.convertPath",
        "appName": APP_NAME,
        "data": {"path": real_path, "language": language},
    }
    conn = UnixHTTPConnection("localhost", timeout=1)
    try:
        conn.request(
            "POST",
            "/api/v1/trimapp",
            body=json.dumps(request, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        response = conn.getresponse()
        if response.status != 200:
            return None
        payload = json.loads(response.read(1024 * 1024))
        if not isinstance(payload, dict) or payload.get("code") != 0:
            return None
        data = payload.get("data")
        if not isinstance(data, dict) or data.get("status") != 0:
            return None
        results = data.get("result")
        if not isinstance(results, list):
            return None
        for item in results:
            if isinstance(item, dict) and item.get("path") == real_path:
                semantic = item.get("semanticPath")
                return semantic if isinstance(semantic, str) and semantic.strip() else None
    except (OSError, http.client.HTTPException, ValueError, UnicodeError):
        return None
    finally:
        conn.close()
    return None
