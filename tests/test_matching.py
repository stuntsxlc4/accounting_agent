from datetime import date
from decimal import Decimal

from accounting_agent.matching import (
    BY_AMOUNT,
    BY_AMOUNT_AND_NAME,
    BY_NUMBER,
    Debit,
    InvoiceRef,
    classify,
    match,
)
from accounting_agent.statements.models import Transaction


def invoice(
    number, gross, seller="Shell Polska sp. z o.o.", nip="5261009190", issued=date(2026, 8, 8)
):
    return InvoiceRef(number, number, issued, seller, nip, Decimal(gross), "PLN", "Vat")


def debit(text, amount, booked=date(2026, 8, 11), counterparty=""):
    t = Transaction(
        booking_date=booked, amount=-Decimal(amount), lines=[text], counterparty=counterparty
    )
    return Debit("Alior", "1", "PLN", t, classify(t))


def test_classify():
    assert classify(debit("TRANSAKCJA KARTĄ VB DEBIT ORLEN", "1").transaction) == "karta"
    assert classify(debit("ZAWARCIE LOKATY O/N", "1").transaction) == "lokata"
    assert classify(debit("OPŁATY OKRESOWE", "1").transaction) == "opłata bankowa"
    assert classify(debit("PRZELEW ELIXIR - ZUS", "1").transaction) == "ZUS"
    assert classify(debit("Wynagrodzenie za 08.2026", "1").transaction) == "wynagrodzenie"
    assert classify(debit("SP PRZELEW NA RACHUNKI", "1").transaction) == "przelew"
    for own in (
        "Przekazanie środków na Rachunek Własny",
        "Przelew Własny na Rachunek firmowy UniCredit",
    ):
        assert classify(debit(own, "1").transaction) == "przelew własny"


def test_match_by_number_amount_and_name_amount_only():
    by_number = debit(
        "SP PRZELEW Tytuł: 509417000826 Ident.: 5261040567 FV: 509417000826", "246.28"
    )
    by_name = debit("TRANSAKCJA KARTĄ VB DEBIT ORLEN STACJA NR 555", "384.50")
    by_amount = debit("TRANSAKCJA KARTĄ VB DEBIT PB.PL* APSPAY", "19.90")
    missing = debit("TRANSAKCJA KARTĄ VB DEBIT CASTORAMA", "185.80")
    invoices = [
        invoice("509417000826", "246.00", "T-Mobile Polska S.A.", "5261040567"),
        invoice("F 16678/0555/26", "384.50", "ORLEN S.A.", "7740001454"),
        invoice(
            "PB/014126/FV/2026", "19.90", "Bonnier Business (Polska) Spółka z o.o.", "1130155210"
        ),
    ]
    debits = [by_number, by_name, by_amount, missing]
    match(debits, invoices)
    assert by_number.method == BY_NUMBER and "+0.28" in by_number.note
    assert by_name.method == BY_AMOUNT_AND_NAME
    assert by_amount.method == BY_AMOUNT
    assert missing.invoice is None


def test_invoice_matched_only_once():
    first, second = debit("KARTĄ ORLEN", "100.00"), debit("KARTĄ ORLEN", "100.00")
    match([first, second], [invoice("F 1", "100.00", "ORLEN S.A.")])
    assert [first.invoice is not None, second.invoice is not None].count(True) == 1


def test_card_merchant_skips_exchange_rate():
    from accounting_agent.record import debit_row

    card = debit(
        "TRANSAKCJA KARTĄ VB DEBIT PŁATNOŚĆ KARTĄ 12.00 EUR 1 EUR=4.4782 PLN RATSKELLER PASSAU",
        "53.74",
    )
    assert debit_row(card)["counterparty"] == "RATSKELLER PASSAU"
    local = debit("TRANSAKCJA KARTĄ VB DEBIT PŁATNOŚĆ KARTĄ 82.94 PLN CASTORAMA WARSZAWA", "82.94")
    assert debit_row(local)["counterparty"] == "CASTORAMA WARSZAWA"
