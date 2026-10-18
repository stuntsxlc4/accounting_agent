"""Długie operacje (pobieranie z KSeF, porównanie) wykonywane w tle, z postępem dla interfejsu."""

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from accounting_agent.config import ConfigError
from accounting_agent.credentials import CredentialsError
from accounting_agent.ksef import KsefError
from accounting_agent.services import Progress
from accounting_agent.statements.models import StatementError

EXPECTED_ERRORS = (ConfigError, CredentialsError, KsefError, StatementError)
UNEXPECTED_ERROR = (
    "Wystąpił nieoczekiwany błąd. Szczegóły zapisano w dzienniku aplikacji "
    "(Ustawienia → Dziennik zdarzeń)."
)

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    kind: str
    status: str = "running"  # running | done | error
    message: str = ""
    done: int | None = None
    total: int | None = None
    error: str | None = None
    result: Any = None


class JobRunner:
    """Jedno zadanie naraz: KSeF ma limity zapytań, równoległe operacje nic by nie dały."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, work: Callable[[Progress], Any]) -> Job:
        job = Job(id=uuid.uuid4().hex, kind=kind, message="Oczekuje…")
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job, work)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def running(self) -> Job | None:
        with self._lock:
            return next((j for j in self._jobs.values() if j.status == "running"), None)

    def _run(self, job: Job, work: Callable[[Progress], Any]) -> None:
        def progress(message: str, done: int | None = None, total: int | None = None) -> None:
            with self._lock:
                job.message, job.done, job.total = message, done, total

        try:
            result = work(progress)
            with self._lock:
                job.result, job.status, job.message = result, "done", "Gotowe"
        except EXPECTED_ERRORS as e:
            log.warning("Zadanie %s zakończone błędem: %s", job.kind, e)
            with self._lock:
                job.error, job.status = str(e), "error"
        except Exception:
            log.exception("Błąd zadania %s", job.kind)
            with self._lock:
                job.error, job.status = UNEXPECTED_ERROR, "error"
