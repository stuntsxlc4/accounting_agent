"""Wyciągi UniCredit (PDF, wyciąg okresowy)."""

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

DATE_FORMAT = "%d.%m.%Y"
DATE_MAX_X = 80  # data transakcji / data zaksięgowania
COUNTERPARTY_X = (130, 285)  # "Opis / Dane kontrahenta"
TABLE_END = ("Uwaga", "Wydany", "Dokument został")


def is_unicredit(text: str) -> bool:
    return "UniCredit" in text and "Wyciąg bankowy" in text


def parse_unicredit(path: Path) -> Statement:
    statement = Statement(bank="UniCredit", path=path)
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
            amount_min_x = columns["amount"] - 50
            for row in rows:
                if row.text.startswith(TABLE_END):
                    current = None
                    continue
                first = row.words[0]
                row_date = parse_date(first.text, DATE_FORMAT) if first.x0 < DATE_MAX_X else None
                by_column = {nearest_column(a, columns): a for a in row.amounts(amount_min_x)}
                if row_date and "amount" in by_column:
                    current = _transaction(row, row_date, by_column, amount_min_x)
                    statement.transactions.append(current)
                elif current is not None:
                    _continue(current, row, row_date, amount_min_x)

    if not columns:
        raise StatementError(f"{path.name}: nie rozpoznano układu wyciągu UniCredit")
    return statement


def _columns(rows: list[Row]) -> dict[str, float]:
    for row in rows:
        texts = [w.text for w in row.words]
        if "Kwota" in texts and "Saldo" in texts:
            kwota = row.words[texts.index("Kwota")]
            return {"amount": kwota.x1, "balance": row.words[-1].x1}
    return {}


def _read_header(rows: list[Row], statement: Statement) -> None:
    for i, row in enumerate(rows):
        text = row.text
        nxt = rows[i + 1].text if i + 1 < len(rows) else ""
        if "Dokument za okres:" in text:
            dates = re.findall(r"\d{2}\.\d{2}\.\d{4}", nxt)
            if len(dates) == 2:
                statement.period_from = parse_date(dates[0], DATE_FORMAT)
                statement.period_to = parse_date(dates[1], DATE_FORMAT)
        elif "Numer rachunku" in text and not statement.account:
            account = re.search(r"PL\d{26}", nxt)
            if account:
                statement.account = account.group(0)[2:]
        elif "Waluta rachunku" in text:
            currency = re.search(r"\b(PLN|EUR|USD|CHF|GBP)\b", nxt)
            if currency:
                statement.currency = currency.group(1)
        elif text.startswith("Saldo początkowe Saldo końcowe"):
            values = rows[i + 1].amounts()
            if len(values) >= 2:
                statement.opening_balance = parse_amount(values[0].text)
                statement.closing_balance = parse_amount(values[1].text)


def _transaction(row: Row, row_date, by_column: dict, amount_min_x: float) -> Transaction:
    balance = by_column.get("balance")
    transaction = Transaction(
        booking_date=row_date,
        operation_date=row_date,
        amount=parse_amount(by_column["amount"].text),
        balance_after=parse_amount(balance.text) if balance else None,
        counterparty=row.text_between(*COUNTERPARTY_X),
    )
    transaction.lines.append(row.text_between(COUNTERPARTY_X[1], amount_min_x))
    return transaction


def _continue(transaction: Transaction, row: Row, row_date, amount_min_x: float) -> None:
    if row_date:  # drugi wiersz operacji: data zaksięgowania
        transaction.booking_date = row_date
    counterparty = row.text_between(*COUNTERPARTY_X)
    if counterparty:
        transaction.counterparty = f"{transaction.counterparty} {counterparty}".strip()
    description = row.text_between(COUNTERPARTY_X[1], amount_min_x)
    if description:
        transaction.lines.append(description)
