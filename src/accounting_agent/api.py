"""API aplikacji okienkowej: interfejs (React) rozmawia z backendem przez HTTP na localhost."""

import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.x509.oid import NameOID
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from accounting_agent.config import Config, ConfigError, load_config
from accounting_agent.jobs import Job, JobRunner
from accounting_agent.ksef import KsefClient
from accounting_agent.matching import EXPECTS_INVOICE, Debit
from accounting_agent.naming import month_folder
from accounting_agent.report import account_label
from accounting_agent.services import (
    TIMEZONE,
    ReconcileResult,
    authenticate,
    download_invoices,
    invoices_folder,
    month_invoices,
    month_range,
    open_path,
    reconcile,
    statements_folder,
)

TOKEN_HEADER = "X-App-Token"


class MonthRequest(BaseModel):
    month: str


class OpenRequest(BaseModel):
    target: str  # invoices_folder | statements_folder | invoice | report
    month: str
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

    @app.get("/api/status")
    def status() -> dict:
        now = datetime.now(TIMEZONE)
        previous = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        result = {"current_month": now.strftime("%Y-%m"), "previous_month": previous}
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

    @app.get("/api/invoices")
    def invoices(month: str) -> dict:
        config = _config()
        return {
            "month": month,
            "label": _label(month),
            "folder": str(invoices_folder(config, month)),
            "invoices": [asdict(i) for i in month_invoices(config, month)],
        }

    @app.post("/api/invoices/download")
    def download(request: MonthRequest) -> dict:
        config = _config()
        _ensure_idle(jobs)

        def work(progress):
            result = download_invoices(config, request.month, progress)
            return {"saved": result.saved, "count": len(result.invoices)}

        return _job(jobs.submit("download", work))

    @app.get("/api/statements")
    def statements(month: str) -> dict:
        folder = statements_folder(_config(), month)
        files = sorted(folder.glob("*")) if folder.is_dir() else []
        return {
            "month": month,
            "label": _label(month),
            "folder": str(folder),
            "files": [
                {"name": f.name, "size": f.stat().st_size}
                for f in files
                if f.suffix.lower() == ".pdf"
            ],
            "report": next((f.name for f in files if f.suffix.lower() == ".xlsx"), None),
        }

    @app.post("/api/statements/upload")
    async def upload(month: str, files: list[UploadFile]) -> dict:
        folder = statements_folder(_config(), month)
        folder.mkdir(parents=True, exist_ok=True)
        for file in files:
            name = Path(file.filename or "").name
            if not name.lower().endswith(".pdf"):
                raise HTTPException(400, f"To nie jest plik PDF: {name}")
            (folder / name).write_bytes(await file.read())
        return statements(month)

    @app.post("/api/reconcile")
    def reconcile_month(request: MonthRequest) -> dict:
        config = _config()
        _ensure_idle(jobs)
        return _job(
            jobs.submit(
                "reconcile",
                lambda progress: _reconcile_json(reconcile(config, request.month, None, progress)),
            )
        )

    @app.post("/api/ksef/test")
    def test_connection() -> dict:
        config = _config()
        _ensure_idle(jobs)

        def work(progress):
            progress("Logowanie do KSeF…")
            with KsefClient(config.ksef_env) as client:
                session = authenticate(client, config)
                client.close_session(session)
            return {"message": f"Zalogowano w kontekście NIP {config.nip}"}

        return _job(jobs.submit("test", work))

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str) -> dict:
        found = jobs.get(job_id)
        if found is None:
            raise HTTPException(404, "Nie ma takiego zadania")
        return asdict(found)

    @app.post("/api/open")
    def open_target(request: OpenRequest) -> dict:
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
        path = folder / Path(request.name).name if request.name else folder
        if not path.exists():
            raise HTTPException(404, f"Nie znaleziono: {path.name}")
        open_path(path)
        return {"opened": str(path)}

    frontend_dir = frontend_dir or _default_frontend_dir()
    if frontend_dir and frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    return app


def _config() -> Config:
    try:
        return load_config()
    except ConfigError as e:
        raise HTTPException(409, str(e)) from e


def _ensure_idle(jobs: JobRunner) -> None:
    if jobs.running():
        raise HTTPException(409, "Trwa inna operacja, poczekaj na jej zakończenie")


def _job(job: Job) -> dict:
    return {"job_id": job.id}


def _label(month: str) -> str:
    start, _ = month_range(month)
    return month_folder(start.year, start.month)


def _certificate(config: Config) -> dict:
    cert = x509.load_pem_x509_certificate(config.cert_path.read_bytes())
    names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    valid_to = cert.not_valid_after_utc
    return {
        "name": names[0].value if names else "",
        "valid_to": valid_to.date().isoformat(),
        "days_left": (valid_to - datetime.now(valid_to.tzinfo)).days,
    }


def _reconcile_json(result: ReconcileResult) -> dict:
    banks: dict[str, list[Debit]] = {}
    for debit in result.debits:
        banks.setdefault(account_label(debit.bank, debit.account, result.statements), []).append(
            debit
        )
    return {
        "report": result.report.name,
        "statements": len(result.statements),
        "unreadable": result.unreadable,
        "invoice_count": result.invoice_count,
        "banks": [
            {
                "name": name,
                "matched": [_debit(d) for d in debits if d.kind in EXPECTS_INVOICE and d.invoice],
                "missing": [
                    _debit(d) for d in debits if d.kind in EXPECTS_INVOICE and not d.invoice
                ],
                "other": [_debit(d) for d in debits if d.kind not in EXPECTS_INVOICE],
            }
            for name, debits in sorted(banks.items())
        ],
        "unpaid": [
            {
                "issue_date": u.invoice.issue_date.isoformat(),
                "number": u.invoice.number,
                "seller": u.invoice.seller_name,
                "gross": float(u.invoice.gross),
                "currency": u.invoice.currency,
                "status": u.status,
                "details": u.details,
            }
            for u in sorted(result.unpaid, key=lambda u: u.invoice.issue_date)
        ],
    }


def _debit(debit: Debit) -> dict:
    t = debit.transaction
    invoice = debit.invoice
    return {
        "booking_date": t.booking_date.isoformat(),
        "operation_date": t.operation_date.isoformat() if t.operation_date else None,
        "amount": float(debit.amount),
        "currency": debit.currency,
        "kind": debit.kind,
        "description": f"{t.counterparty} | {t.text}" if t.counterparty else t.text,
        "invoice": {
            "number": invoice.number,
            "issue_date": invoice.issue_date.isoformat(),
            "seller": invoice.seller_name,
            "gross": float(invoice.gross),
        }
        if invoice
        else None,
        "method": debit.method,
        "note": debit.note,
    }


def _default_frontend_dir() -> Path | None:
    """Zbudowany frontend: obok pakietu w trybie deweloperskim, w paczce PyInstaller w _MEIPASS."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "frontend"
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


# Serwer deweloperski bez tokenu: uv run uvicorn accounting_agent.api:dev_app --reload
dev_app = create_app(token=None, frontend_dir=Path("/nonexistent"))
