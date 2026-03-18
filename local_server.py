from __future__ import annotations
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable
import config


_server: HTTPServer | None = None
_thread: threading.Thread | None = None


class _Handler(BaseHTTPRequestHandler):
    """ブックマークレットからのリクエストを受け取るハンドラー"""

    on_receive: Callable[[str, str], None] | None = None

    def do_POST(self) -> None:
        if self.path != "/bookmarklet":
            self._respond(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            url: str = data.get("url", "")
            html: str = data.get("html", "")
            if not url or not html:
                self._respond(400, {"error": "url and html are required"})
                return
            self._respond(200, {"status": "ok"})
            if _Handler.on_receive:
                _Handler.on_receive(url, html)
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        """CORSプリフライトリクエスト対応"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        # サーバーログを抑制する
        pass


def start(on_receive: Callable[[str, str], None]) -> None:
    """
    ローカルサーバーをバックグラウンドスレッドで起動する。
    on_receive(url, html) はリクエスト受信時に呼ばれる。
    """
    global _server, _thread
    if _server is not None:
        return
    _Handler.on_receive = on_receive
    _server = HTTPServer(("127.0.0.1", config.BOOKMARKLET_PORT), _Handler)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()


def stop() -> None:
    """サーバーを停止する"""
    global _server, _thread
    if _server:
        _server.shutdown()
        _server = None
        _thread = None

