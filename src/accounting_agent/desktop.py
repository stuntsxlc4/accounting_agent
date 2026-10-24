"""Aplikacja okienkowa: lokalny serwer API + okno z interfejsem."""

import logging
import os
import secrets
import socket
import sys
import threading
import time

import uvicorn
import webview

from accounting_agent import storage
from accounting_agent.api import create_app
from accounting_agent.config import APP_NAME, app_data_dir

STARTUP_TIMEOUT = 15.0
LOCK_FILE = "aplikacja.lock"

log = logging.getLogger(__name__)


def main() -> None:
    storage.setup_logging()
    if _single_instance() is None:
        _show_message(f"Aplikacja {APP_NAME} jest już uruchomiona.")
        return
    try:
        token = secrets.token_urlsafe(32)
        server, port = start_server(token)
        webview.create_window(
            APP_NAME,
            f"http://127.0.0.1:{port}/?token={token}",
            width=1320,
            height=860,
            min_size=(1040, 700),
        )
        webview.start()
        server.should_exit = True
    except Exception:
        log.exception("Nie udało się uruchomić aplikacji")
        _show_message(
            "Nie udało się uruchomić aplikacji. Szczegóły zapisano w dzienniku zdarzeń:\n"
            f"{storage.log_dir()}"
        )


def start_server(token: str) -> tuple[uvicorn.Server, int]:
    port = _free_port()
    # log_config=None: dziennik zdarzeń aplikacji zamiast konsoli, której program okienkowy nie ma
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(token), host="127.0.0.1", port=port, log_level="warning", log_config=None
        )
    )
    threading.Thread(target=server.run, daemon=True).start()
    _wait_until_started(server)
    return server, port


def _single_instance() -> int | None:
    """Blokada pliku: druga kopia aplikacji dublowałaby zapytania do KSeF i zadania w tle."""
    path = app_data_dir() / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT)
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def _show_message(text: str) -> None:
    log.warning(text)
    if sys.platform == "win32":
        import ctypes

        MB_ICONINFORMATION = 0x40
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, MB_ICONINFORMATION)
    else:
        print(text, file=sys.stderr)


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
