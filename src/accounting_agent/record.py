"""Wynik porównania wyciągów (strona obciążeń) w postaci zapisywanej na dysku.

Ten sam zapis służy interfejsowi, historii i zestawieniu Excel. Strona faktur nie jest tu
zapisywana: statusy płatności pochodzą z rejestru płatności i zmieniają się, gdy płatność
pojawi się na wyciągu z kolejnego miesiąca.
"""

import re
from collections import defaultdict

from accounting_agent.matching import CARD, EXPECTS_INVOICE, Debit
from accounting_agent.statements.models import Statement

# Sklep w opisie płatności kartą, np. "... PŁATNOŚĆ KARTĄ 384.50 PLN ORLEN STACJA NR 555 WARSZAWA"
# W walucie obcej po kwocie jest kurs: "12.00 EUR 1 EUR=4.4782 PLN RATSKELLER PASSAU".
CARD_MERCHANT = re.compile(r"\d+[.,]\d{2} [A-Z]{3}(?: 1 [A-Z]{3}=[\d.,]+ [A-Z]{3})? (.+)$")
# Numer rachunku na początku danych kontrahenta w wyciągu, np. "67 1140 2004 ... Elipsa"
ACCOUNT_PREFIX = re.compile(r"^((?:PL)?\d{2}(?: ?\d{4}){6}|PL\d{20,})\s*(.*)$")


def build(
    statements: list[Statement],
    debits: list[Debit],
    unreadable: list[str],
    invoice_count: int,
    report_name: str,
) -> dict:
    by_account: dict[str, list[Debit]] = defaultdict(list)
    for debit in debits:
        by_account[account_label(debit.bank, debit.account, statements)].append(debit)
    return {
        "report": report_name,
        "statements": len(statements),
        "unreadable": unreadable,
        "invoice_count": invoice_count,
        "accounts": _accounts(statements),
        "banks": [
            {
                "name": name,
                "matched": [debit_row(d) for d in items if d.kind in EXPECTS_INVOICE and d.invoice],
                "missing": [
                    debit_row(d) for d in items if d.kind in EXPECTS_INVOICE and not d.invoice
                ],
                "other": [debit_row(d) for d in items if d.kind not in EXPECTS_INVOICE],
            }
            for name, items in sorted(by_account.items())
        ],
    }


def debit_row(debit: Debit) -> dict:
    t = debit.transaction
    invoice = debit.invoice
    return {
        "booking_date": t.booking_date.isoformat(),
        "operation_date": t.operation_date.isoformat() if t.operation_date else None,
        "amount": float(debit.amount),
        "currency": debit.currency,
        "kind": debit.kind,
        **_counterparty(t.counterparty or _card_merchant(debit)),
        "description": t.text,
        "invoice": {
            "ksef_number": invoice.ksef_number,
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


def account_label(bank: str, account: str, statements: list[Statement]) -> str:
    """Nazwa banku, z końcówką numeru rachunku, gdy bank ma kilka rachunków."""
    accounts = {s.account for s in statements if s.bank == bank}
    return f"{bank} {account[-4:]}" if len(accounts) > 1 else bank


def _accounts(statements: list[Statement]) -> list[dict]:
    grouped: dict[str, list[Statement]] = defaultdict(list)
    for s in statements:
        grouped[account_label(s.bank, s.account, statements)].append(s)
    result = []
    for name, items in sorted(grouped.items()):
        dates = sorted(d for s in items for d in (s.period_from, s.period_to) if d)
        result.append(
            {
                "name": name,
                "bank": items[0].bank,
                "account": items[0].account,
                "currency": items[0].currency,
                "period_from": dates[0].isoformat() if dates else None,
                "period_to": dates[-1].isoformat() if dates else None,
                "files": len(items),
            }
        )
    return result


def _card_merchant(debit: Debit) -> str:
    found = CARD_MERCHANT.search(debit.transaction.text) if debit.kind == CARD else None
    return found.group(1) if found else ""


def _counterparty(text: str) -> dict:
    """Dane kontrahenta z wyciągu rozdzielone na numer rachunku i nazwę."""
    found = ACCOUNT_PREFIX.match(text)
    if found:
        return {"account": found.group(1), "counterparty": found.group(2).lstrip("- ")}
    return {"account": "", "counterparty": text}
