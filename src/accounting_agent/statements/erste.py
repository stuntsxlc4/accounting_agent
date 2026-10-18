"""Wyciągi Erste Bank Polska (PDF, wyciąg miesięczny)."""

import re
from pathlib import Path

import pdfplumber

from accounting_agent.statements.models import Statement, StatementError, Transaction
from accounting_agent.statements.pdfrows import (
    Row,
    nearest_column,
    page_rows,
    parse_amount,
    parse_date,
)

DATE_FORMAT = "%Y-%m-%d"
BOOKING_DATE_MAX_X = 75  # data księgowania
DESCRIPTION_X = 75  # data operacji i opis zaczynają się od x≈80
TABLE_END = ("Erste Bank Polska S.A.", "Pieniądze na rachunku", "POŚWIADCZENIE")


def is_erste(text: str) -> bool:
    return "ERSTE BANK POLSKA" in text.upper() and "WYCIĄG Z RACHUNKU" in text.upper()


def parse_erste(path: Path) -> Statement:
    statement = Statement(bank="Erste", path=path)
    columns: dict[str, float] = {}
    current: Transaction | None = None

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            rows = page_rows(page)
            if not columns:
                columns = _columns(rows)
                _read_header(rows, statement)
            if not columns:
                continue
            amount_min_x = columns["debit"] - 70
            for row in rows:
                text = row.text
                if text.startswith(TABLE_END):
                    current = None
                    continue
                amounts = row.amounts(amount_min_x)
                if "Saldo początkowe:" in text and amounts:
                    statement.opening_balance = parse_amount(amounts[-1].text)
                    continue
                if "Saldo końcowe:" in text and amounts:
                    statement.closing_balance = parse_amount(amounts[-1].text)
                    current = None
                    continue

                first = row.words[0]
                booking = (
                    parse_date(first.text, DATE_FORMAT) if first.x0 < BOOKING_DATE_MAX_X else None
                )
                by_column = {nearest_column(a, columns): a for a in amounts}
                if booking and ("debit" in by_column or "credit" in by_column):
                    current = _transaction(row, booking, by_column, amount_min_x)
                    statement.transactions.append(current)
                elif current is not None:
                    description = row.text_between(DESCRIPTION_X, amount_min_x)
                    if description:
                        current.lines.append(description)

    if not columns:
        raise StatementError(f"{path.name}: nie rozpoznano układu wyciągu Erste")
    return statement


def _columns(rows: list[Row]) -> dict[str, float]:
    for row in rows:
        by_text = {w.text: w for w in row.words}
        if {"OBCIĄŻENIA", "UZNANIA", "SALDO"} <= by_text.keys():
            return {
                "debit": by_text["OBCIĄŻENIA"].x1,
                "credit": by_text["UZNANIA"].x1,
                "balance": by_text["SALDO"].x1,
            }
    return {}


def _read_header(rows: list[Row], statement: Statement) -> None:
    for i, row in enumerate(rows):
        text = row.text
        if text.startswith("DATA WYCIĄGU") and i + 1 < len(rows):
            dates = re.findall(r"\d{4}-\d{2}-\d{2}", rows[i + 1].text)
            if len(dates) >= 3:
                statement.period_from = parse_date(dates[1], DATE_FORMAT)
                statement.period_to = parse_date(dates[2], DATE_FORMAT)
        elif text.startswith("NR RACHUNKU") and i + 1 < len(rows):
            statement.account = "".join(re.findall(r"\d+", rows[i + 1].text))[:26]
        elif text.startswith("NAZWA RACHUNKU") and i + 1 < len(rows):
            currency = re.search(r"\b(PLN|EUR|USD|CHF|GBP)\b", rows[i + 1].text)
            if currency:
                statement.currency = currency.group(1)


def _transaction(row: Row, booking, by_column: dict, amount_min_x: float) -> Transaction:
    debit, credit = by_column.get("debit"), by_column.get("credit")
    amount = -parse_amount(debit.text) if debit else parse_amount(credit.text)
    balance = by_column.get("balance")
    words = [w for w in row.words if DESCRIPTION_X <= w.x0 < amount_min_x]
    operation_date = parse_date(words[0].text, DATE_FORMAT) if words else None
    if operation_date:
        words = words[1:]
    return Transaction(
        booking_date=booking,
        operation_date=operation_date,
        amount=amount,
        balance_after=parse_amount(balance.text) if balance else None,
        lines=[" ".join(w.text for w in words)],
    )
