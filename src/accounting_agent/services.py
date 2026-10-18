"""Operacje aplikacji wspólne dla wiersza poleceń i aplikacji okienkowej."""

import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from accounting_agent.config import Config, ConfigError, app_data_dir
from accounting_agent.credentials import get_key_password, load_private_key
from accounting_agent.invoice import parse_invoice
from accounting_agent.ksef import KsefClient, Session
from accounting_agent.matching import (
    Debit,
    InvoiceRef,
    UnpaidInvoice,
    classify,
    explain_unpaid,
    match,
    settle_corrections,
    unpaid,
)
from accounting_agent.naming import invoice_filename, month_folder
from accounting_agent.pdf import render_invoice_pdf
from accounting_agent.report import write_report
from accounting_agent.statements.models import Statement, StatementError
from accounting_agent.statements.reader import read_statement

TIMEZONE = ZoneInfo("Europe/Warsaw")
# Płatności dotyczą też starszych faktur (w sierpniu 2026 zapłacono fakturę z lutego).
INVOICE_LOOKBACK_MONTHS = 12
# KSeF przyjmuje zakres dat do 100 dni w jednym zapytaniu.
KSEF_QUERY_DAYS = 90

# Postęp operacji: komunikat oraz opcjonalnie liczba wykonanych i wszystkich kroków.
Progress = Callable[[str, int | None, int | None], None]


def no_progress(message: str, done: int | None = None, total: int | None = None) -> None:
    pass


@dataclass(frozen=True)
class InvoiceFile:
    ksef_number: str
    issue_date: str
    number: str
    seller: str
    seller_nip: str
    gross: float
    currency: str
    invoice_type: str
    file_name: str
    downloaded: bool = False


@dataclass
class DownloadResult:
    folder: Path
    invoices: list[InvoiceFile]
    saved: int


@dataclass
class ReconcileResult:
    folder: Path
    report: Path
    statements: list[Statement]
    unreadable: list[str]
    debits: list[Debit]
    unpaid: list[UnpaidInvoice]
    invoice_count: int


def invoices_folder(config: Config, month: str) -> Path:
    start, _ = month_range(month)
    return config.output_dir / month_folder(start.year, start.month)


def statements_folder(config: Config, month: str) -> Path:
    start, _ = month_range(month)
    return config.statements_dir / month_folder(start.year, start.month)


def download_invoices(
    config: Config, month: str, progress: Progress = no_progress
) -> DownloadResult:
    date_from, date_to = month_range(month)
    folder = invoices_folder(config, month)
    folder.mkdir(parents=True, exist_ok=True)

    progress("Logowanie do KSeF…", None, None)
    with KsefClient(config.ksef_env) as client:
        session = authenticate(client, config)
        try:
            progress("Pobieranie listy faktur…", None, None)
            metadata = client.query_purchase_invoices(session, date_from, date_to)
            files = [_invoice_file(meta) for meta in metadata]
            _save_index(month, files)
            saved = 0
            for done, (meta, file) in enumerate(zip(metadata, files, strict=True), 1):
                path = folder / file.file_name
                if path.exists():
                    progress(f"Już pobrana: {file.file_name}", done, len(files))
                    continue
                xml = client.get_invoice_xml(session, meta["ksefNumber"])
                render_invoice_pdf(parse_invoice(xml, meta["ksefNumber"]), path)
                saved += 1
                progress(f"Zapisano: {file.file_name}", done, len(files))
        finally:
            client.close_session(session)
    return DownloadResult(folder, month_invoices(config, month), saved)


def month_invoices(config: Config, month: str) -> list[InvoiceFile]:
    """Faktury miesiąca z ostatniego pobrania, z informacją, czy PDF jest na dysku."""
    index = _index_path(month)
    if not index.is_file():
        return []
    folder = invoices_folder(config, month)
    files = [InvoiceFile(**item) for item in json.loads(index.read_text(encoding="utf-8"))]
    return [
        InvoiceFile(**{**asdict(f), "downloaded": (folder / f.file_name).is_file()}) for f in files
    ]


def reconcile(
    config: Config, month: str, folder: Path | None = None, progress: Progress = no_progress
) -> ReconcileResult:
    date_from, date_to = month_range(month)
    folder = folder or statements_folder(config, month)
    pdfs = sorted(p for p in folder.glob("*") if p.suffix.lower() == ".pdf")
    if not pdfs:
        raise ConfigError(f"Brak wyciągów PDF w folderze {folder}")

    statements, unreadable = [], []
    for done, pdf in enumerate(pdfs, 1):
        progress(f"Odczyt wyciągu: {pdf.name}", done, len(pdfs))
        try:
            statements.append(read_statement(pdf))
        except StatementError as e:
            unreadable.append(str(e))

    debits = [
        Debit(s.bank, s.account, s.currency, t, classify(t))
        for s in statements
        for t in s.transactions
        if t.is_debit
    ]
    lookback_from = _months_before(date_from, INVOICE_LOOKBACK_MONTHS - 1)
    progress("Logowanie do KSeF…", None, None)
    with KsefClient(config.ksef_env) as client:
        session = authenticate(client, config)
        try:
            progress("Pobieranie faktur z ostatnich 12 miesięcy…", None, None)
            invoices = _fetch_invoices(client, session, lookback_from, date_to)
            match(debits, invoices)
            not_found = unpaid(invoices, debits, date_from.date(), date_to.date())
            explained = []
            for done, invoice in enumerate(not_found, 1):
                progress(f"Sposób płatności: {invoice.number}", done, len(not_found))
                xml = client.get_invoice_xml(session, invoice.ksef_number)
                explained.append(explain_unpaid(invoice, parse_invoice(xml, invoice.ksef_number)))
            not_paid = settle_corrections(explained)
        finally:
            client.close_session(session)

    name = month_folder(date_from.year, date_from.month)
    report = folder / f"Porównanie_faktur_i_wyciągów_{name.replace(' ', '_')}.xlsx"
    progress("Zapis zestawienia Excel…", None, None)
    write_report(
        report, f"Porównanie faktur z wyciągami – {name}", statements, debits, not_paid, unreadable
    )
    return ReconcileResult(folder, report, statements, unreadable, debits, not_paid, len(invoices))


def authenticate(client: KsefClient, config: Config) -> Session:
    key = load_private_key(config.key_path, get_key_password())
    return client.authenticate(config.nip, config.cert_path.read_text(), key)


def parse_month(text: str, today: date | None = None) -> str:
    """Miesiąc jako RRRR-MM z "RRRR-MM" albo samego numeru miesiąca ("1", "01", "10").

    Sam numer oznacza ostatnie wystąpienie tego miesiąca: bieżący lub wcześniejszy
    miesiąc w tym roku, późniejszy w poprzednim roku.
    """
    text = text.strip()
    if text.isdigit() and 1 <= int(text) <= 12:
        today = today or datetime.now(TIMEZONE).date()
        month = int(text)
        year = today.year if month <= today.month else today.year - 1
        return f"{year}-{month:02d}"
    try:
        return f"{datetime.strptime(text, '%Y-%m'):%Y-%m}"
    except ValueError as e:
        raise ConfigError(f"Nieznany miesiąc: {text}. Podaj numer 01–12 albo RRRR-MM.") from e


def month_range(month: str) -> tuple[datetime, datetime]:
    try:
        start = datetime.strptime(month, "%Y-%m").replace(tzinfo=TIMEZONE)
    except ValueError as e:
        raise ConfigError(f"Miesiąc w formacie RRRR-MM, np. 2026-08 (podano: {month})") from e
    next_month = start.replace(year=start.year + start.month // 12, month=start.month % 12 + 1)
    return start, next_month - timedelta(seconds=1)


def open_path(path: Path) -> None:
    """Otwiera plik lub folder w domyślnym programie systemu."""
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.run(["open", str(path)], check=False)


def _invoice_file(meta: dict) -> InvoiceFile:
    return InvoiceFile(
        ksef_number=meta["ksefNumber"],
        issue_date=meta["issueDate"],
        number=meta["invoiceNumber"],
        seller=meta["seller"].get("name") or "",
        seller_nip=meta["seller"]["nip"],
        gross=meta["grossAmount"],
        currency=meta["currency"],
        invoice_type=meta["invoiceType"],
        file_name=invoice_filename(
            date.fromisoformat(meta["issueDate"]),
            meta["invoiceNumber"],
            meta["seller"].get("name") or "",
            meta["invoiceType"],
        ),
    )


def _index_path(month: str) -> Path:
    return app_data_dir() / "faktury" / f"{month}.json"


def _save_index(month: str, files: list[InvoiceFile]) -> None:
    path = _index_path(month)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(f) for f in files]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _fetch_invoices(
    client: KsefClient, session: Session, date_from: datetime, date_to: datetime
) -> list[InvoiceRef]:
    invoices = []
    start = date_from
    while start <= date_to:
        end = min(start + timedelta(days=KSEF_QUERY_DAYS) - timedelta(seconds=1), date_to)
        invoices += client.query_purchase_invoices(session, start, end)
        start = end + timedelta(seconds=1)
    return [InvoiceRef.from_metadata(meta) for meta in invoices]


def _months_before(start: datetime, months: int) -> datetime:
    index = start.year * 12 + start.month - 1 - months
    return start.replace(year=index // 12, month=index % 12 + 1)
