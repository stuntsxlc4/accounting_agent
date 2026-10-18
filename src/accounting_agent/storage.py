"""Dane aplikacji zapisywane lokalnie: wyniki porównań i historia operacji."""

import json
import logging
import os
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from accounting_agent.config import app_data_dir

TIMEZONE = ZoneInfo("Europe/Warsaw")
HISTORY_LIMIT = 200
LOG_FILE_BYTES = 1_000_000
LOG_FILE_COUNT = 5

_lock = threading.Lock()


def save_reconcile(month: str, result: dict) -> dict:
    record = {"month": month, "created_at": _now(), "result": result}
    _write_json(_reconcile_path(month), record)
    return record


def last_reconcile(month: str) -> dict | None:
    return _read_json(_reconcile_path(month))


def add_history(kind: str, month: str, summary: str, ok: bool = True) -> None:
    with _lock:
        items = _read_json(_history_path()) or []
        items.insert(0, {"kind": kind, "month": month, "summary": summary, "ok": ok, "at": _now()})
        _write_json(_history_path(), items[:HISTORY_LIMIT])


def history(limit: int = 10) -> list[dict]:
    with _lock:
        return (_read_json(_history_path()) or [])[:limit]


def log_dir() -> Path:
    return app_data_dir() / "logi"


def setup_logging() -> Path:
    """Dziennik zdarzeń aplikacji w pliku, z rotacją (5 × 1 MB)."""
    path = log_dir() / "aplikacja.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path, maxBytes=LOG_FILE_BYTES, backupCount=LOG_FILE_COUNT, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for noisy in ("httpx", "httpcore", "fontTools", "pdfminer", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if not any(getattr(h, "baseFilename", None) == str(path) for h in root.handlers):
        root.addHandler(handler)
    return path


def _reconcile_path(month: str) -> Path:
    return app_data_dir() / "porownania" / f"{month}.json"


def _history_path() -> Path:
    return app_data_dir() / "historia.json"


def _now() -> str:
    return datetime.now(TIMEZONE).isoformat(timespec="seconds")


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        logging.getLogger(__name__).exception("Nie można odczytać %s", path)
        return None


def _write_json(path: Path, data: Any) -> None:
    """Zapis przez plik tymczasowy, żeby przerwany zapis nie uszkodził danych."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
