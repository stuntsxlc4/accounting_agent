"""API aplikacji okienkowej: interfejs (React) rozmawia z backendem przez HTTP na localhost."""

import hashlib
import logging
import sys
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.x509.oid import NameOID
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from send2trash import send2trash

from accounting_agent import storage
from accounting_agent.config import TIMEZONE, Config, ConfigError, load_config
from accounting_agent.jobs import EXPECTED_ERRORS, JobRunner
from accounting_agent.ksef import KsefClient
from accounting_agent.naming import month_folder
from accounting_agent.payments import (
    CARD_PAID,
    CASH,
    CONFLICT,
    TO_EXPLAIN,
    TRANSFER_PAID,
    UNPAID,
    InvoiceStatus,
)
from accounting_agent.services import (
    Progress,
    authenticate,
    download_invoices,
    invoices_fetched_at,
    invoices_folder,
    month_invoices,
    month_range,
    month_statuses,
    open_path,
    reconcile,
    set_cash,
    statements_folder,
)

TOKEN_HEADER = "X-App-Token"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

log = logging.getLogger(__name__)


class MonthRequest(BaseModel):
    month: str


class CashRequest(BaseModel):
    month: str
    ksef_number: str
    cash: bool


class OpenRequest(BaseModel):
    target: str  # invoices_folder | statements_folder | invoice | report | logs
    month: str | None = None
    name: str | None = None


def create_app(token: str | None, frontend_dir: Path | None = None) -> FastAPI:
    """Aplikacja FastAPI. Z tokenem przyjmuje tylko zapytania z okna aplikacji."""
    app = FastAPI(title="Faktury KSeF", docs_url=None, redoc_url=None, openapi_url=None)
    jobs = JobRunner()

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        if token and request.url.path.startswith("/api/"):
            if request.headers.get(TOKEN_HEADER) != token:
                return JSONResponse({"detail": "Brak dostępu"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.exception("Błąd API %s %s", request.method, request.url.path)
        return JSONResponse(
            {"detail": "Wystąpił nieoczekiwany błąd. Szczegóły zapisano w dzienniku aplikacji."},
            status_code=500,
        )

    @app.get("/api/status")
    def status() -> dict:
        now = datetime.now(TIMEZONE)
        previous = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        result = {"previous_month": previous}
        try:
            config = load_config()
        except ConfigError as e:
            return {**result, "configured": False, "error": str(e)}
        return {
            **result,
            "configured": True,
            "nip": config.nip,
            "environment": config.ksef_env,
            "certificate": _certificate(config),
            "invoices_dir": str(config.output_dir),
            "statements_dir": str(config.statements_dir),
        }

    @app.get("/api/overview")
    def overview(month: str) -> dict:
        """Stan miesiąca dla Pulpitu: faktury, wyciągi, ostatnie porównanie."""
        config = _config()
        invoices_list = month_invoices(config, month)
        fetched_at = invoices_fetched_at(month)
        last = storage.last_reconcile(month)
        return {
            "month": month,
            "label": _label(month),
            "invoices": {
                "count": len(invoices_list),
                "downloaded": sum(1 for i in invoices_list if i.downloaded),
                "fetched_at": fetched_at.isoformat(timespec="seconds") if fetched_at else None,
            },
            "statements": len(_statement_files(statements_folder(config, month))),
            "reconcile": _reconcile_summary(last) if last else None,
            "payments": _payments_summary(month_statuses(month)),
            "to_explain": _to_explain(),
        }

    @app.get("/api/history")
    def history() -> list[dict]:
        return storage.history(limit=8)

    @app.get("/api/invoices")
    def invoices(month: str) -> dict:
        config = _config()
        fetched_at = invoices_fetched_at(month)
        statuses = {s.invoice.ksef_number: _status_row(s) for s in month_statuses(month)}
        return {
            "month": month,
            "label": _label(month),
            "folder": str(invoices_folder(config, month)),
            "fetched_at": fetched_at.isoformat(timespec="seconds") if fetched_at else None,
            "invoices": [
                {**asdict(i), "payment": statuses.get(i.ksef_number)}
                for i in month_invoices(config, month)
            ],
        }

    @app.post("/api/invoices/download")
    def download(request: MonthRequest) -> dict:
        config = _config()
        _ensure_idle(jobs)

        def work(progress: Progress) -> dict:
            result = download_invoices(config, request.month, progress)
            summary = f"Faktur w KSeF: {len(result.invoices)}, nowych plików: {result.saved}"
            storage.add_history("download", request.month, summary)
            return {"saved": result.saved, "count": len(result.invoices)}

        return _submit(jobs, "download", request.month, work)

    @app.get("/api/statements")
    def statements(month: str) -> dict:
        folder = statements_folder(_config(), month)
        files = _statement_files(folder)
        report = (
            next((f.name for f in sorted(folder.glob("*.xlsx"))), None) if folder.is_dir() else None
        )
        return {
            "month": month,
            "label": _label(month),
            "folder": str(folder),
            "files": [{"name": f.name, "size": f.stat().st_size} for f in files],
            "report": report,
        }

    @app.post("/api/statements/upload")
    async def upload(month: str, files: list[UploadFile], overwrite: bool = False) -> dict:
        """Dodaje wyciągi. Pliki identyczne z istniejącymi są pomijane, a pliki o tej samej
        nazwie i innej treści zastępowane tylko po potwierdzeniu (overwrite=true)."""
        folder = statements_folder(_config(), month)
        incoming = []
        for file in files:
            name = Path(file.filename or "").name
            if not name.lower().endswith(".pdf"):
                raise HTTPException(400, f"To nie jest plik PDF: {name}")
            content = await file.read()
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(400, f"Plik jest za duży: {name}")
            if not content.startswith(b"%PDF"):
                raise HTTPException(400, f"Plik nie jest poprawnym PDF: {name}")
            incoming.append((name, content))

        conflicts = [
            name
            for name, content in incoming
            if (folder / name).is_file()
            and _digest((folder / name).read_bytes()) != _digest(content)
        ]
        if conflicts and not overwrite:
            return JSONResponse(
                {"detail": "Pliki o tych nazwach już są w folderze", "conflicts": conflicts},
                status_code=409,
            )

        folder.mkdir(parents=True, exist_ok=True)
        added, replaced, skipped = [], [], []
        for name, content in incoming:
            path = folder / name
            if path.is_file() and _digest(path.read_bytes()) == _digest(content):
                skipped.append(name)
                continue
            (replaced if path.is_file() else added).append(name)
            path.write_bytes(content)
        log.info("Wyciągi %s: dodane %s, zastąpione %s", month, added, replaced)
        return {
            **statements(month),
            "added": added,
            "replaced": replaced,
            "skipped": skipped,
        }

    @app.delete("/api/statements")
    def remove_statement(month: str, name: str) -> dict:
        """Przenosi wyciąg do kosza systemu (można go stamtąd przywrócić)."""
        path = statements_folder(_config(), month) / Path(name).name
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise HTTPException(404, f"Nie znaleziono wyciągu: {name}")
        send2trash(path)
        log.info("Wyciąg przeniesiony do kosza: %s", path)
        return statements(month)

    @app.post("/api/reconcile")
    def reconcile_month(request: MonthRequest) -> dict:
        config = _config()
        _ensure_idle(jobs)

        def work(progress: Progress) -> dict:
            result = reconcile(config, request.month, None, progress)
            record = storage.last_reconcile(request.month)
            summary = _reconcile_summary(record)
            later = f", zaktualizowano też: {', '.join(map(_label, result.updated_months))}"
            storage.add_history(
                "reconcile",
                request.month,
                f"Z fakturą: {summary['matched']}, bez faktury: {summary['missing']}, "
                f"faktur niezapłaconych: {summary['unpaid']}"
                + (later if result.updated_months else ""),
            )
            return {**record, "updated_months": result.updated_months}

        return _submit(jobs, "reconcile", request.month, work)

    @app.get("/api/reconcile/last")
    def last_reconcile(month: str) -> dict:
        return {"record": storage.last_reconcile(month)}

    @app.get("/api/payments")
    def month_payments(month: str) -> dict:
        reconciled = storage.reconciled_months()
        return {
            "month": month,
            "label": _label(month),
            "reconciled": month in reconciled,
            "last_reconciled": reconciled[-1] if reconciled else None,
            "invoices": [_status_row(s) for s in month_statuses(month)],
        }

    @app.post("/api/payments/cash")
    def mark_cash(request: CashRequest) -> dict:
        """Ręczne oznaczenie faktury jako zapłaconej gotówką (z własnych środków)."""
        set_cash(_config(), request.month, request.ksef_number, request.cash)
        log.info("Gotówka %s: %s", "oznaczona" if request.cash else "cofnięta", request.ksef_number)
        return month_payments(request.month)

    @app.post("/api/ksef/test")
    def test_connection() -> dict:
        config = _config()
        _ensure_idle(jobs)

        def work(progress: Progress) -> dict:
            progress("Logowanie do KSeF…", None, None)
            with KsefClient(config.ksef_env) as client:
                session = authenticate(client, config)
                client.close_session(session)
            return {"message": f"Zalogowano w kontekście NIP {config.nip}"}

        return _submit(jobs, "test", None, work)

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str) -> dict:
        found = jobs.get(job_id)
        if found is None:
            raise HTTPException(404, "Nie ma takiego zadania")
        return asdict(found)

    @app.get("/api/jobs")
    def running_job() -> dict:
        found = jobs.running()
        return {"job": asdict(found) if found else None}

    @app.post("/api/open")
    def open_target(request: OpenRequest) -> dict:
        if request.target == "logs":
            path = storage.log_dir()
            path.mkdir(parents=True, exist_ok=True)
            open_path(path)
            return {"opened": str(path)}
        if not request.month:
            raise HTTPException(400, "Brak miesiąca")
        config = _config()
        folders = {
            "invoices_folder": invoices_folder(config, request.month),
            "statements_folder": statements_folder(config, request.month),
            "invoice": invoices_folder(config, request.month),
            "report": statements_folder(config, request.month),
        }
        folder = folders.get(request.target)
        if folder is None:
            raise HTTPException(400, "Nieznany cel")
        if request.target.endswith("_folder"):
            folder.mkdir(parents=True, exist_ok=True)
        path = folder / Path(request.name).name if request.name else folder
        if not path.exists():
            raise HTTPException(404, f"Nie znaleziono: {path.name}")
        open_path(path)
        return {"opened": str(path)}

    frontend_dir = frontend_dir or _default_frontend_dir()
    if frontend_dir and frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    return app


def _submit(jobs: JobRunner, kind: str, month: str | None, work: Callable[[Progress], Any]):
    """Uruchamia zadanie w tle; nieudane operacje trafiają do historii."""

    def tracked(progress: Progress) -> Any:
        try:
            return work(progress)
        except EXPECTED_ERRORS as e:
            if month:
                storage.add_history(kind, month, str(e), ok=False)
            raise

    return {"job_id": jobs.submit(kind, tracked).id}


def _config() -> Config:
    try:
        return load_config()
    except ConfigError as e:
        raise HTTPException(409, str(e)) from e


def _ensure_idle(jobs: JobRunner) -> None:
    if jobs.running():
        raise HTTPException(409, "Trwa inna operacja, poczekaj na jej zakończenie")


def _label(month: str) -> str:
    start, _ = month_range(month)
    return month_folder(start.year, start.month)


def _statement_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".pdf")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _certificate(config: Config) -> dict:
    cert = x509.load_pem_x509_certificate(config.cert_path.read_bytes())
    names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    valid_to = cert.not_valid_after_utc
    return {
        "name": names[0].value if names else "",
        "valid_to": valid_to.date().isoformat(),
        "days_left": (valid_to - datetime.now(valid_to.tzinfo)).days,
    }


def _reconcile_summary(record: dict) -> dict:
    result = record["result"]
    statuses = _payments_summary(month_statuses(record["month"]))
    return {
        "created_at": record["created_at"],
        "matched": sum(len(b["matched"]) for b in result["banks"]),
        "missing": sum(len(b["missing"]) for b in result["banks"]),
        "unpaid": statuses["unpaid"] + statuses["to_explain"],
        "unreadable": len(result["unreadable"]),
    }


def _payments_summary(statuses: list[InvoiceStatus]) -> dict:
    count = {s: sum(1 for x in statuses if x.status == s) for s in {x.status for x in statuses}}
    return {
        "paid": count.get(TRANSFER_PAID, 0) + count.get(CARD_PAID, 0),
        "cash": count.get(CASH, 0),
        "unpaid": count.get(UNPAID, 0),
        "to_explain": count.get(TO_EXPLAIN, 0) + count.get(CONFLICT, 0),
    }


def _to_explain() -> list[dict]:
    """Porównane miesiące z fakturami do wyjaśnienia (dla Pulpitu)."""
    result = []
    for month in storage.reconciled_months():
        count = _payments_summary(month_statuses(month))["to_explain"]
        if count:
            result.append({"month": month, "label": _label(month), "count": count})
    return result


def _status_row(status: InvoiceStatus) -> dict:
    invoice = status.invoice
    return {
        "ksef_number": invoice.ksef_number,
        "issue_date": invoice.issue_date.isoformat(),
        "number": invoice.number,
        "seller": invoice.seller_name,
        "seller_nip": invoice.seller_nip,
        "gross": float(invoice.gross),
        "currency": invoice.currency,
        "status": status.status,
        "details": status.details,
        "method": status.method,
        "paid_date": status.paid_date,
        "bank": status.bank,
        "statement_month": status.statement_month,
        "paid_later": status.paid_later,
        "cash": status.cash,
    }


def _default_frontend_dir() -> Path | None:
    """Zbudowany frontend: obok pakietu w trybie deweloperskim, w paczce PyInstaller w _MEIPASS."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "frontend"
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def dev_app() -> FastAPI:
    """Serwer deweloperski bez tokenu (frontend z Vite):
    uv run uvicorn accounting_agent.api:dev_app --factory --port 8765 --reload"""
    storage.setup_logging()
    return create_app(token=None, frontend_dir=Path("/nonexistent"))
