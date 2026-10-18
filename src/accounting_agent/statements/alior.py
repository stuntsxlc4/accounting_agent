"""Wyciągi Alior Bank (PDF, wyciąg dzienny lub okresowy)."""

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

DATE_FORMAT = "%Y.%m.%d"
DATE_MAX_X = 120  # kolumna "Data księg. / Data waluty"
COUNTERPARTY_X = (120, 260)  # kolumna "Kontrahent"
TABLE_END = ("Infolinia", "Podsumowanie", "Ten dokument")


def is_alior(text: str) -> bool:
    return "Alior Bank" in text and "Wyciąg z rachunku bankowego" in text


def parse_alior(path: Path) -> Statement:
    statement = Statement(bank="Alior", path=path)
    columns: dict[str, float] = {}
    current: Transaction | None = None

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            rows = page_rows(page)
            if not columns:
                columns = _columns(rows)
                _read_header(rows, statement)
            amount_min_x = columns["debit"] - 60
            in_table = False
            for row in rows:
                text = row.text
                if not in_table:
                    in_table = _is_table_start(row)
                    continue
                if text.startswith(TABLE_END):
                    break

                first = row.words[0]
                booking = parse_date(first.text, DATE_FORMAT) if first.x0 < DATE_MAX_X else None
                amounts = {nearest_column(a, columns): a for a in row.amounts(amount_min_x)}

                if booking and "SALDO POCZĄTKOWE" in text and statement.opening_balance is None:
                    statement.opening_balance = parse_amount(amounts["balance"].text)
                elif booking and "SALDO KOŃCOWE" in text:
                    statement.closing_balance = parse_amount(amounts["balance"].text)
                    current = None
                elif booking and ("debit" in amounts or "credit" in amounts):
                    current = _transaction(row, booking, amounts, amount_min_x)
                    statement.transactions.append(current)
                elif current is not None:
                    _continue(current, row, amount_min_x)

    if not columns:
        raise StatementError(f"{path.name}: nie rozpoznano układu wyciągu Alior")
    return statement


def _columns(rows: list[Row]) -> dict[str, float]:
    for row in rows:
        by_text = {w.text: w for w in row.words}
        if {"obciążenia", "uznania", "Saldo"} <= by_text.keys():
            return {
                "debit": by_text["obciążenia"].x1,
                "credit": by_text["uznania"].x1,
                "balance": by_text["Saldo"].x1,
            }
    return {}


def _read_header(rows: list[Row], statement: Statement) -> None:
    for row in rows:
        text = row.text
        if text.startswith("Numer rachunku:"):
            statement.account = "".join(re.findall(r"\d+", text.split("IBAN")[0]))
        elif text.startswith("Wyciąg za okres:"):
            dates = re.findall(r"\d{4}\.\d{2}\.\d{2}", text)
            if len(dates) == 2:
                statement.period_from = parse_date(dates[0], DATE_FORMAT)
                statement.period_to = parse_date(dates[1], DATE_FORMAT)
        elif "Waluta rachunku:" in text:
            statement.currency = text.split("Waluta rachunku:")[-1].split()[0]


def _is_table_start(row: Row) -> bool:
    texts = [w.text for w in row.words]
    # strona 1: nagłówek kolumn; kolejne strony: tytuł wyciągu nad tabelą
    return "Saldo" in texts and "uznania" in texts or row.text == "Wyciąg z rachunku bankowego"


def _transaction(row: Row, booking, amounts: dict, amount_min_x: float) -> Transaction:
    debit, credit = amounts.get("debit"), amounts.get("credit")
    amount = parse_amount(debit.text) if debit else parse_amount(credit.text)
    if debit and amount > 0:
        amount = -amount
    balance = amounts.get("balance")
    transaction = Transaction(
        booking_date=booking,
        amount=amount,
        balance_after=parse_amount(balance.text) if balance else None,
        counterparty=row.text_between(*COUNTERPARTY_X),
    )
    transaction.lines.append(row.text_between(COUNTERPARTY_X[1], amount_min_x))
    return transaction


def _continue(transaction: Transaction, row: Row, amount_min_x: float) -> None:
    words = row.words
    if words and words[0].x0 < DATE_MAX_X and parse_date(words[0].text, DATE_FORMAT):
        if transaction.operation_date is None:
            transaction.operation_date = parse_date(words[0].text, DATE_FORMAT)
    counterparty = row.text_between(*COUNTERPARTY_X)
    if counterparty:
        transaction.counterparty = f"{transaction.counterparty} {counterparty}".strip()
    description = row.text_between(COUNTERPARTY_X[1], amount_min_x)
    if description:
        transaction.lines.append(description)
