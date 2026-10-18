"""Aplikacja okienkowa: lokalny serwer API + okno z interfejsem."""

import secrets
import socket
import threading
import time

import uvicorn
import webview

from accounting_agent import storage
from accounting_agent.api import create_app
from accounting_agent.config import APP_NAME

STARTUP_TIMEOUT = 15.0


def main() -> None:
    storage.setup_logging()
    token = secrets.token_urlsafe(32)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(token), host="127.0.0.1", port=port, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True).start()
    _wait_until_started(server)

    webview.create_window(
        APP_NAME,
        f"http://127.0.0.1:{port}/?token={token}",
        width=1320,
        height=860,
        min_size=(1040, 700),
    )
    webview.start()
    server.should_exit = True


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_started(server: uvicorn.Server) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Serwer aplikacji nie wystartował")
        time.sleep(0.05)
