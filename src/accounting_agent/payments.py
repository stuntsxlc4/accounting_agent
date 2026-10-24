"""Rejestr płatności faktur: czy i jak faktura została zapłacona, niezależnie od miesiąca wyciągu.

Płatność za fakturę z września może pojawić się na wyciągu z października. Rejestr łączy
miesiące: porównanie października oznacza wrześniową fakturę jako zapłaconą, a zestawienie
września pokazuje to bez ponownego porównywania.
"""

import re
import threading
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from accounting_agent import storage
from accounting_agent.invoice import Invoice
from accounting_agent.matching import CARD, Debit, InvoiceRef

# Statusy faktury
TRANSFER_PAID = "zapłacona przelewem"
CARD_PAID = "zapłacona kartą"
CASH = "gotówka"
UNPAID = "niezapłacona"
TO_EXPLAIN = "do wyjaśnienia"
CONFLICT = "sprzeczność"
CORRECTED_TO_ZERO = "skorygowana do zera"
CORRECTION = "korekta"

# Faktura bez płatności po tylu porównanych miesiącach wymaga wyjaśnienia.
OVERDUE_MONTHS = 2

REGISTER_FILE = "platnosci.json"
_lock = threading.Lock()


@dataclass(frozen=True)
class InvoiceStatus:
    invoice: InvoiceRef
    status: str
    details: str = ""
    method: str = ""  # przelew | karta
    paid_date: str | None = None
    bank: str = ""
    statement_month: str | None = None
    cash: bool = False

    @property
    def paid_later(self) -> bool:
        """Zapłacona w innym miesiącu niż wystawiona."""
        return bool(self.statement_month) and self.statement_month != _month(self.invoice)


def load() -> dict[str, dict[str, Any]]:
    with _lock:
        return storage.read_data(REGISTER_FILE) or {}


def save(register: dict[str, dict[str, Any]]) -> None:
    with _lock:
        storage.write_data(REGISTER_FILE, register)


def bank_paid(register: dict) -> set[str]:
    """Faktury, których płatność znaleziono już na wyciągu."""
    return {number for number, entry in register.items() if entry.get("payment")}


def clear_statement_month(register: dict, month: str) -> set[str]:
    """Usuwa płatności znalezione na wyciągach danego miesiąca (przed ponownym porównaniem).

    Zwraca numery KSeF faktur, których to dotyczyło.
    """
    cleared = set()
    for number, entry in register.items():
        payment = entry.get("payment")
        if payment and payment["statement_month"] == month:
            entry.pop("payment")
            cleared.add(number)
    return cleared


def record_payment(register: dict, debit: Debit, statement_month: str) -> None:
    invoice = debit.invoice
    t = debit.transaction
    register.setdefault(invoice.ksef_number, {})["payment"] = {
        "method": "karta" if debit.kind == CARD else "przelew",
        "date": (t.operation_date or t.booking_date).isoformat(),
        "booking_date": t.booking_date.isoformat(),
        "bank": debit.bank,
        "amount": str(debit.amount),
        "statement_month": statement_month,
        "match": debit.method,
    }


def set_cash(register: dict, ksef_number: str, cash: bool, marked_at: str) -> None:
    entry = register.setdefault(ksef_number, {})
    if cash:
        entry["cash"] = {"marked_at": marked_at}
    else:
        entry.pop("cash", None)


def remember_invoice(register: dict, invoice: InvoiceRef, parsed: Invoice) -> None:
    """Zapamiętuje dane z XML potrzebne do statusu: sposób płatności i korygowane faktury."""
    entry = register.setdefault(invoice.ksef_number, {})
    entry["hint"] = _payment_hint(parsed)
    if is_correction(invoice):
        entry["correction"] = {
            "number": invoice.number,
            "seller_nip": invoice.seller_nip,
            "gross": str(invoice.gross),
            "corrects": [" ".join(n.split()) for n, _ in parsed.corrected],
            "corrects_dates": [d for _, d in parsed.corrected],
        }


def is_correction(invoice: InvoiceRef) -> bool:
    return invoice.gross <= 0 or invoice.invoice_type.upper().startswith("KOR")


def statuses(
    invoices: list[InvoiceRef], register: dict, last_reconciled: str | None
) -> list[InvoiceStatus]:
    """Status płatności każdej faktury, według rejestru i najnowszego porównanego miesiąca."""
    corrections = [e["correction"] for e in register.values() if e.get("correction")]
    result = []
    for invoice in sorted(invoices, key=lambda i: (i.issue_date, i.number)):
        entry = register.get(invoice.ksef_number, {})
        result.append(_status(invoice, entry, corrections, last_reconciled))
    return result


def _status(
    invoice: InvoiceRef, entry: dict, corrections: list[dict], last_reconciled: str | None
) -> InvoiceStatus:
    hint = entry.get("hint", "")
    if is_correction(invoice):
        info = entry.get("correction", {})
        details = ", ".join(
            f"koryguje {n}" + (f" z {_day(d)}" if d else "")
            for n, d in zip(info.get("corrects", []), info.get("corrects_dates", []), strict=True)
        )
        return InvoiceStatus(invoice, CORRECTION, details)

    payment = entry.get("payment")
    cash = "cash" in entry
    if payment:
        method = payment["method"]
        paid = TRANSFER_PAID if method == "przelew" else CARD_PAID
        details = f"{payment['bank']}, {_day(payment['date'])}"
        if cash:
            paid, details = CONFLICT, f"oznaczona jako gotówka, a jest płatność: {details}"
        return InvoiceStatus(
            invoice,
            paid,
            details,
            method=method,
            paid_date=payment["date"],
            bank=payment["bank"],
            statement_month=payment["statement_month"],
            cash=cash,
        )
    if cash:
        return InvoiceStatus(invoice, CASH, "oznaczona ręcznie", cash=True)

    own = [
        c
        for c in corrections
        if c["seller_nip"] == invoice.seller_nip
        and _norm(invoice.number) in {_norm(n) for n in c["corrects"]}
    ]
    if own and invoice.gross + sum(Decimal(c["gross"]) for c in own) == 0:
        numbers = ", ".join(c["number"] for c in own)
        return InvoiceStatus(invoice, CORRECTED_TO_ZERO, f"korekta: {numbers}")

    overdue = last_reconciled and _months_between(_month(invoice), last_reconciled) >= (
        OVERDUE_MONTHS
    )
    return InvoiceStatus(invoice, TO_EXPLAIN if overdue else UNPAID, hint)


def _payment_hint(parsed: Invoice) -> str:
    """Sposób płatności zapisany w fakturze, np. "wg faktury: karta, zapłacono 08-08-2026"."""
    payment = parsed.payment
    if payment is None:
        return ""
    parts = [payment.form] if payment.form else []
    if payment.paid:
        parts.append(
            f"zapłacono {payment.paid_date:%d-%m-%Y}" if payment.paid_date else "zapłacono"
        )
    parts += [f"termin {due:%d-%m-%Y}" for due in payment.due_dates]
    return "wg faktury: " + ", ".join(parts) if parts else ""


def _month(invoice: InvoiceRef) -> str:
    return invoice.issue_date.strftime("%Y-%m")


def _months_between(earlier: str, later: str) -> int:
    (y1, m1), (y2, m2) = (map(int, earlier.split("-")), map(int, later.split("-")))
    return (y2 - y1) * 12 + (m2 - m1)


def _day(value: str) -> str:
    try:
        return f"{date.fromisoformat(value):%d-%m-%Y}"
    except ValueError:
        return value


def _norm(number: str) -> str:
    return re.sub(r"\s+", "", number).upper()
