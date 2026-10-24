"""Operacje aplikacji wspólne dla wiersza poleceń i aplikacji okienkowej."""

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from accounting_agent import payments, record, storage
from accounting_agent.config import TIMEZONE, Config, ConfigError, app_data_dir
from accounting_agent.credentials import get_key_password, load_private_key
from accounting_agent.invoice import parse_invoice
from accounting_agent.ksef import KsefClient, Session
from accounting_agent.matching import Debit, InvoiceRef, classify, match
from accounting_agent.naming import invoice_filename, month_folder
from accounting_agent.payments import InvoiceStatus
from accounting_agent.pdf import render_invoice_pdf
from accounting_agent.report import write_report
from accounting_agent.statements.models import StatementError
from accounting_agent.statements.reader import read_statement

# Płatności dotyczą też starszych faktur (w sierpniu 2026 zapłacono fakturę z lutego).
INVOICE_LOOKBACK_MONTHS = 12
# KSeF przyjmuje zakres dat do 100 dni w jednym zapytaniu, czyli najwyżej 3 pełne miesiące.
MONTHS_PER_QUERY = 3
# Lista faktur zamkniętego miesiąca jest pewna, gdy pobrano ją co najmniej tyle dni po jego
# końcu (faktury trafiają do KSeF z opóźnieniem, np. wystawione w trybie offline).
MONTH_SETTLE_DAYS = 14

KSEF_NUMBER = re.compile(r"[0-9A-Z-]{35,36}")

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
    record: dict
    statuses: list[InvoiceStatus]
    # Wcześniejsze miesiące, których faktury zostały opłacone na wyciągach tego miesiąca
    updated_months: list[str]


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
            _store_month(month, metadata)
            files = [_invoice_file(meta) for meta in metadata]
            saved = 0
            for done, (meta, file) in enumerate(zip(metadata, files, strict=True), 1):
                path = folder / file.file_name
                if path.exists():
                    progress(f"Już pobrana: {file.file_name}", done, len(files))
                    continue
                xml = invoice_xml(client, session, meta["ksefNumber"])
                render_invoice_pdf(parse_invoice(xml, meta["ksefNumber"]), path)
                saved += 1
                progress(f"Zapisano: {file.file_name}", done, len(files))
        finally:
            client.close_session(session)
    return DownloadResult(folder, month_invoices(config, month), saved)


def month_invoices(config: Config, month: str) -> list[InvoiceFile]:
    """Faktury miesiąca z ostatniego pobrania, z informacją, czy PDF jest na dysku."""
    cached = _load_month(month)
    if cached is None:
        return []
    folder = invoices_folder(config, month)
    files = [_invoice_file(meta) for meta in cached[1]]
    return [
        InvoiceFile(**{**asdict(f), "downloaded": (folder / f.file_name).is_file()}) for f in files
    ]


def invoice_xml(client: KsefClient, session: Session, ksef_number: str) -> bytes:
    """XML faktury z lokalnej kopii, a gdy jej brak, z KSeF (z zapisem kopii).

    Faktura w KSeF jest niezmienna, więc raz pobrany XML nie wymaga ponownego pobierania.
    """
    if not KSEF_NUMBER.fullmatch(ksef_number):
        raise ValueError(f"Niepoprawny numer KSeF: {ksef_number}")
    path = app_data_dir() / "xml" / f"{ksef_number}.xml"
    if path.is_file():
        return path.read_bytes()
    xml = client.get_invoice_xml(session, ksef_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(xml)
    os.replace(tmp, path)
    return xml


def invoices_fetched_at(month: str) -> datetime | None:
    """Kiedy ostatnio pobrano z KSeF listę faktur miesiąca."""
    cached = _load_month(month)
    return cached[0] if cached else None


def reconcile(
    config: Config, month: str, folder: Path | None = None, progress: Progress = no_progress
) -> ReconcileResult:
    """Porównuje wyciągi miesiąca z fakturami i aktualizuje rejestr płatności.

    Płatności dopasowywane są także do niezapłaconych faktur z wcześniejszych miesięcy;
    zestawienia tych miesięcy są wtedy przeliczane.
    """
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
    months = [_shift_month(month, -i) for i in reversed(range(INVOICE_LOOKBACK_MONTHS))]
    recent = {month, _shift_month(month, -1)}

    register = payments.load()
    # Ponowne porównanie tego samego miesiąca zastępuje jego wcześniejsze dopasowania.
    changed = payments.clear_statement_month(register, month)

    progress("Logowanie do KSeF…", None, None)
    with KsefClient(config.ksef_env) as client:
        session = authenticate(client, config)
        try:
            invoices = [
                InvoiceRef.from_metadata(meta)
                for meta in _invoice_metadata(client, session, months, progress)
            ]
            paid_before = payments.bank_paid(register)
            match(debits, [i for i in invoices if i.ksef_number not in paid_before])
            for debit in debits:
                if debit.invoice:
                    payments.record_payment(register, debit, month)
                    changed.add(debit.invoice.ksef_number)

            paid = payments.bank_paid(register)
            to_read = [
                i for i in invoices if _invoice_month(i) in recent and i.ksef_number not in paid
            ]
            for done, invoice in enumerate(to_read, 1):
                progress(f"Dane płatności z faktury: {invoice.number}", done, len(to_read))
                xml = invoice_xml(client, session, invoice.ksef_number)
                payments.remember_invoice(
                    register, invoice, parse_invoice(xml, invoice.ksef_number)
                )
        finally:
            client.close_session(session)
    payments.save(register)

    start, _ = month_range(month)
    name = month_folder(start.year, start.month)
    report = folder / f"Porównanie_faktur_i_wyciągów_{name.replace(' ', '_')}.xlsx"
    result = record.build(statements, debits, unreadable, len(invoices), report.name)
    storage.save_reconcile(month, result)

    progress("Zapis zestawienia Excel…", None, None)
    write_report(report, _report_title(month), result, month_statuses(month))
    updated = sorted({_invoice_month(i) for i in invoices if i.ksef_number in changed} - {month})
    for earlier in updated:
        write_month_report(config, earlier)
    return ReconcileResult(folder, report, result, month_statuses(month), updated)


def month_statuses(month: str) -> list[InvoiceStatus]:
    """Status płatności faktur wystawionych w miesiącu, według rejestru płatności."""
    cached = _load_month(month)
    if cached is None:
        return []
    invoices = [InvoiceRef.from_metadata(meta) for meta in cached[1]]
    reconciled = storage.reconciled_months()
    return payments.statuses(invoices, payments.load(), reconciled[-1] if reconciled else None)


def set_cash(config: Config, month: str, ksef_number: str, cash: bool) -> list[InvoiceStatus]:
    """Ręczne oznaczenie faktury jako zapłaconej gotówką (z własnych środków) albo cofnięcie."""
    statuses = month_statuses(month)
    if not any(s.invoice.ksef_number == ksef_number for s in statuses):
        raise ConfigError("Nie znaleziono tej faktury w miesiącu")
    register = payments.load()
    payments.set_cash(
        register, ksef_number, cash, datetime.now(TIMEZONE).isoformat(timespec="seconds")
    )
    payments.save(register)
    write_month_report(config, month)
    return month_statuses(month)


def write_month_report(config: Config, month: str) -> Path | None:
    """Przelicza zestawienie Excel miesiąca, jeśli porównanie było już wykonane."""
    saved = storage.last_reconcile(month)
    folder = statements_folder(config, month)
    if not saved or "accounts" not in saved["result"] or not folder.is_dir():
        return None
    path = folder / saved["result"]["report"]
    write_report(path, _report_title(month), saved["result"], month_statuses(month))
    return path


def _report_title(month: str) -> str:
    start, _ = month_range(month)
    return f"Porównanie faktur z wyciągami – {month_folder(start.year, start.month)}"


def _invoice_month(invoice: InvoiceRef) -> str:
    return invoice.issue_date.strftime("%Y-%m")


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


def _invoice_metadata(
    client: KsefClient, session: Session, months: list[str], progress: Progress
) -> list[dict]:
    """Metadane faktur z podanych miesięcy: z pamięci, a brakujące lub niepewne z KSeF.

    Kolejne miesiące do pobrania łączone są po 3 w jedno zapytanie (limit 20 zapytań/h).
    """
    by_month: dict[str, list[dict]] = {}
    missing = []
    for month in months:
        cached = _load_month(month)
        if cached and _is_settled(month, cached[0]):
            by_month[month] = cached[1]
        else:
            missing.append(month)
    progress(
        f"Faktury z ostatnich {len(months)} miesięcy: z pamięci {len(by_month)}, "
        f"z KSeF {len(missing)}",
        None,
        None,
    )
    for group in _query_groups(missing):
        start, _ = month_range(group[0])
        _, end = month_range(group[-1])
        progress(f"Pobieranie listy faktur z KSeF: {group[0]} – {group[-1]}", None, None)
        fetched = {month: [] for month in group}
        for meta in client.query_purchase_invoices(session, start, end):
            fetched.setdefault(meta["issueDate"][:7], []).append(meta)
        for month in group:
            _store_month(month, fetched[month])
            by_month[month] = fetched[month]
    return [meta for month in months for meta in by_month[month]]


def _query_groups(months: list[str]) -> list[list[str]]:
    """Kolejne miesiące po najwyżej MONTHS_PER_QUERY w grupie."""
    groups: list[list[str]] = []
    for month in months:
        last = groups[-1] if groups else None
        if last and len(last) < MONTHS_PER_QUERY and _shift_month(last[-1], 1) == month:
            last.append(month)
        else:
            groups.append([month])
    return groups


def _is_settled(month: str, fetched_at: datetime) -> bool:
    _, end = month_range(month)
    return fetched_at >= end + timedelta(days=MONTH_SETTLE_DAYS)


def _cache_path(month: str) -> Path:
    return app_data_dir() / "faktury" / f"{month}.json"


def _load_month(month: str) -> tuple[datetime, list[dict]] | None:
    path = _cache_path(month)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return datetime.fromisoformat(data["fetched_at"]), data["invoices"]


def _store_month(month: str, metadata: list[dict]) -> None:
    path = _cache_path(month)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"fetched_at": datetime.now(TIMEZONE).isoformat(), "invoices": metadata}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _shift_month(month: str, delta: int) -> str:
    start, _ = month_range(month)
    index = start.year * 12 + start.month - 1 + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"
