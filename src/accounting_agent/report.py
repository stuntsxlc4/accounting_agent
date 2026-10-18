"""Zestawienie porównania faktur z wyciągami w Excelu."""

from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from accounting_agent.matching import (
    CORRECTED_TO_ZERO,
    CORRECTION,
    EXPECTS_INVOICE,
    NOT_PAID,
    OTHER_CARD,
    PAID_OTHERWISE,
    Debit,
    UnpaidInvoice,
)
from accounting_agent.statements.models import Statement

MONEY = "#,##0.00"
DATE = "DD-MM-YYYY"
BOLD = Font(bold=True)
TITLE = Font(bold=True, size=14)
SECTION = Font(bold=True, size=12)
HEADER_FILL = PatternFill("solid", fgColor="D9D9D9")
MATCHED_FILL = PatternFill("solid", fgColor="E2EFDA")
MISSING_FILL = PatternFill("solid", fgColor="F8CBAD")
NEUTRAL_FILL = PatternFill("solid", fgColor="F2F2F2")
OTHER_CARD_FILL = PatternFill("solid", fgColor="FFF2CC")
# Kolejność i kolory grup w arkuszu "Faktury bez płatności"
UNPAID_GROUPS = [
    (NOT_PAID, MISSING_FILL),
    (OTHER_CARD, OTHER_CARD_FILL),
    (PAID_OTHERWISE, MATCHED_FILL),
    (CORRECTED_TO_ZERO, NEUTRAL_FILL),
    (CORRECTION, NEUTRAL_FILL),
]

DEBIT_COLUMNS = [
    ("Data obciążenia", 14),
    ("Data operacji", 14),
    ("Kwota obciążenia", 16),
    ("Waluta", 8),
    ("Rodzaj", 16),
    ("Kontrahent / opis operacji", 60),
    ("Faktura – numer", 24),
    ("Faktura – data", 14),
    ("Faktura – sprzedawca", 32),
    ("Faktura – brutto", 16),
    ("Dopasowanie", 22),
    ("Uwagi", 40),
]


def write_report(
    path: Path,
    title: str,
    statements: list[Statement],
    debits: list[Debit],
    unpaid: list[UnpaidInvoice],
    unreadable: list[str],
) -> None:
    wb = Workbook()
    summary = wb.active
    summary.title = "Podsumowanie"

    by_account: dict[str, list[Debit]] = defaultdict(list)
    for debit in debits:
        by_account[account_label(debit.bank, debit.account, statements)].append(debit)

    _summary_sheet(summary, title, statements, by_account, unpaid, unreadable)
    for sheet_name, account_debits in sorted(by_account.items()):
        _bank_sheet(wb.create_sheet(sheet_name), sheet_name, account_debits, statements)
    _unpaid_sheet(wb.create_sheet("Faktury bez płatności"), unpaid)
    wb.save(path)


def _summary_sheet(ws, title, statements, by_account, unpaid, unreadable) -> None:
    ws["A1"] = title
    ws["A1"].font = TITLE
    headers = ["Wyciąg", "Obciążeń", "Z fakturą", "BRAK FAKTURY", "Bez faktury z natury"]
    _header_row(ws, 3, headers)
    row = 4
    for sheet_name, debits in sorted(by_account.items()):
        expecting = [d for d in debits if d.kind in EXPECTS_INVOICE]
        values = [
            sheet_name,
            len(debits),
            sum(1 for d in expecting if d.invoice),
            sum(1 for d in expecting if not d.invoice),
            len(debits) - len(expecting),
        ]
        for col, value in enumerate(values, 1):
            ws.cell(row=row, column=col, value=value)
        if values[3]:
            ws.cell(row=row, column=4).fill = MISSING_FILL
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Faktury bez płatności na wyciągach").font = BOLD
    ws.cell(row=row, column=2, value=len(unpaid))
    for status, fill in UNPAID_GROUPS:
        row += 1
        ws.cell(row=row, column=1, value=f"  {status}").fill = fill
        ws.cell(row=row, column=2, value=sum(1 for u in unpaid if u.status == status))
    row += 1
    ws.cell(row=row, column=1, value="Odczytane pliki wyciągów").font = BOLD
    ws.cell(row=row, column=2, value=len(statements))
    for message in unreadable:
        row += 1
        ws.cell(row=row, column=1, value="Nie odczytano").font = BOLD
        ws.cell(row=row, column=2, value=message).fill = MISSING_FILL
    _widths(ws, [28, 14, 14, 16, 22])


def _bank_sheet(ws, sheet_name: str, debits: list[Debit], statements: list[Statement]) -> None:
    own = [s for s in statements if account_label(s.bank, s.account, statements) == sheet_name]
    ws["A1"] = f"{sheet_name} – rachunek {_account(own[0].account)} ({own[0].currency})"
    ws["A1"].font = TITLE
    periods = sorted(p for s in own for p in (s.period_from, s.period_to) if p)
    if periods:
        ws["A2"] = f"Okres: {periods[0]:%d-%m-%Y} – {periods[-1]:%d-%m-%Y}, plików: {len(own)}"

    expecting = sorted(
        (d for d in debits if d.kind in EXPECTS_INVOICE), key=lambda d: d.transaction.booking_date
    )
    other = sorted(
        (d for d in debits if d.kind not in EXPECTS_INVOICE),
        key=lambda d: d.transaction.booking_date,
    )
    sections = [
        ("Obciążenia z fakturą", [d for d in expecting if d.invoice], MATCHED_FILL, True),
        (
            "Obciążenia BEZ FAKTURY – do wyjaśnienia",
            [d for d in expecting if not d.invoice],
            MISSING_FILL,
            True,
        ),
        (
            "Obciążenia bez faktury z natury (opłaty, lokaty, podatki, ZUS, wynagrodzenia, "
            "przelewy własne)",
            other,
            NEUTRAL_FILL,
            False,
        ),
    ]

    row = 4
    for name, section_debits, fill, with_total in sections:
        ws.cell(row=row, column=1, value=f"{name}: {len(section_debits)}").font = SECTION
        row += 1
        _header_row(ws, row, [c[0] for c in DEBIT_COLUMNS])
        row += 1
        for debit in section_debits:
            _debit_row(ws, row, debit, fill)
            row += 1
        if section_debits and with_total:
            ws.cell(row=row, column=2, value="Razem").font = BOLD
            total = ws.cell(row=row, column=3, value=sum(d.amount for d in section_debits))
            total.font = BOLD
            total.number_format = MONEY
            row += 1
        row += 1

    _widths(ws, [c[1] for c in DEBIT_COLUMNS])
    ws.freeze_panes = "A4"


def _debit_row(ws, row: int, debit: Debit, fill: PatternFill) -> None:
    t = debit.transaction
    invoice = debit.invoice
    description = f"{t.counterparty} | {t.text}" if t.counterparty else t.text
    values = [
        t.booking_date,
        t.operation_date,
        debit.amount,
        debit.currency,
        debit.kind,
        description,
        invoice.number if invoice else ("BRAK FAKTURY" if debit.kind in EXPECTS_INVOICE else ""),
        invoice.issue_date if invoice else None,
        invoice.seller_name if invoice else None,
        invoice.gross if invoice else None,
        debit.method,
        debit.note,
    ]
    for col, value in enumerate(values, 1):
        cell = ws.cell(row=row, column=col, value=value)
        cell.fill = fill
        cell.alignment = Alignment(vertical="top", wrap_text=col == 6)
    for col in (1, 2, 8):
        ws.cell(row=row, column=col).number_format = DATE
    for col in (3, 10):
        ws.cell(row=row, column=col).number_format = MONEY


def _unpaid_sheet(ws, unpaid: list[UnpaidInvoice]) -> None:
    ws["A1"] = "Faktury z miesiąca, których nie znaleziono na wyciągach"
    ws["A1"].font = TITLE
    ws["A2"] = (
        "„Zapłacona kartą spoza wyciągów”: według faktury zapłacono kartą, "
        "ale nie kartą, której wyciągi porównano."
    )
    headers = [
        "Data faktury",
        "Numer",
        "Sprzedawca",
        "NIP",
        "Brutto",
        "Waluta",
        "Status",
        "Płatność według faktury / uwagi",
    ]
    _header_row(ws, 4, headers)
    row = 5
    for status, fill in UNPAID_GROUPS:
        group = sorted(
            (u for u in unpaid if u.status == status), key=lambda u: u.invoice.issue_date
        )
        for item in group:
            invoice = item.invoice
            values = [
                invoice.issue_date,
                invoice.number,
                invoice.seller_name,
                invoice.seller_nip,
                invoice.gross,
                invoice.currency,
                item.status,
                item.details,
            ]
            for col, value in enumerate(values, 1):
                ws.cell(row=row, column=col, value=value).fill = fill
            ws.cell(row=row, column=1).number_format = DATE
            ws.cell(row=row, column=5).number_format = MONEY
            row += 1
    _widths(ws, [14, 30, 45, 14, 14, 8, 30, 36])
    ws.freeze_panes = "A5"


def _header_row(ws, row: int, headers: list[str]) -> None:
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col, value=header)
        cell.font = BOLD
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")


def _widths(ws, widths: list[int]) -> None:
    for col, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width


def account_label(bank: str, account: str, statements: list[Statement]) -> str:
    """Nazwa banku, z końcówką numeru rachunku, gdy bank ma kilka rachunków."""
    accounts = {s.account for s in statements if s.bank == bank}
    return f"{bank} {account[-4:]}" if len(accounts) > 1 else bank


def _account(number: str) -> str:
    if len(number) == 26 and number.isdigit():
        return f"{number[:2]} " + " ".join(number[i : i + 4] for i in range(2, 26, 4))
    return number
