from datetime import date
from decimal import Decimal

import pytest

from accounting_agent.statements.models import StatementError
from accounting_agent.statements.pdfrows import parse_amount
from accounting_agent.statements.reader import ScannedStatementError, read_statement

from . import pdfgen


def test_alior(tmp_path):
    s = read_statement(pdfgen.alior(tmp_path / "alior.pdf"))
    assert (s.bank, s.account, s.currency) == ("Alior", "58249000050000453016739104", "PLN")
    assert (s.period_from, s.period_to) == (date(2026, 8, 11), date(2026, 8, 11))
    assert (s.opening_balance, s.closing_balance) == (Decimal("20000.00"), Decimal("18637.95"))
    assert [t.amount for t in s.transactions] == [
        Decimal("15.83"),
        Decimal("-246.28"),
        Decimal("-1131.60"),
    ]
    transfer = s.transactions[1]
    assert transfer.counterparty.endswith("T-mobile Polska S.A.")
    assert "FV: 509417000826" in transfer.text and "Ident.: 5261040567" in transfer.text
    assert transfer.operation_date == date(2026, 8, 12)
    # transakcja z drugiej strony wyciągu
    assert "31/07/2026" in s.transactions[2].text


def test_alior_rejects_wrong_balance(tmp_path):
    with pytest.raises(StatementError, match="saldo"):
        read_statement(pdfgen.alior(tmp_path / "alior.pdf", closing="18 000,00"))


def test_erste(tmp_path):
    s = read_statement(pdfgen.erste(tmp_path / "erste.pdf"))
    assert (s.bank, s.account, s.currency) == ("Erste", "17109018830000000161152280", "PLN")
    assert (s.period_from, s.period_to) == (date(2026, 8, 1), date(2026, 8, 31))
    assert s.closing_balance == Decimal("10683272.92")
    fee, card, credit = s.transactions
    assert fee.amount == Decimal("-55.00") and fee.text.startswith("OPŁATA/PROWIZJA")
    assert card.amount == Decimal("-384.50")
    assert (card.booking_date, card.operation_date) == (date(2026, 8, 14), date(2026, 8, 12))
    assert "ORLEN STACJA NR 555" in card.text
    assert credit.amount == Decimal("7150000.00")


def test_unicredit(tmp_path):
    s = read_statement(pdfgen.unicredit(tmp_path / "unicredit.pdf"))
    assert (s.bank, s.account, s.currency) == ("UniCredit", "42291000192469800301049172", "PLN")
    assert (s.opening_balance, s.closing_balance) == (Decimal("0.00"), Decimal("500.00"))
    incoming, deposit = s.transactions
    assert incoming.amount == Decimal("1000.00")
    assert (incoming.operation_date, incoming.booking_date) == (
        date(2026, 8, 25),
        date(2026, 8, 26),
    )
    assert deposit.amount == Decimal("-500.00") and "Otwarcie lokaty" in deposit.text


def test_scanned_statement(tmp_path):
    with pytest.raises(ScannedStatementError):
        read_statement(pdfgen.plain(tmp_path / "skan.pdf", None))


def test_unknown_bank(tmp_path):
    with pytest.raises(StatementError, match="nieznany bank"):
        read_statement(pdfgen.plain(tmp_path / "inny.pdf", "Wyciąg z innego banku"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("-1 131,60", Decimal("-1131.60")),
        ("3.533.657,42", Decimal("3533657.42")),
        ("2 000 000.00", Decimal("2000000.00")),
        ("1,234.56", Decimal("1234.56")),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected
