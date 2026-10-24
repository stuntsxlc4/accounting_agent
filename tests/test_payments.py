from datetime import date
from decimal import Decimal

from accounting_agent import payments, services, storage
from accounting_agent.invoice import Invoice, Payment
from accounting_agent.matching import Debit, InvoiceRef, classify, match
from accounting_agent.payments import (
    CARD_PAID,
    CASH,
    CONFLICT,
    CORRECTED_TO_ZERO,
    CORRECTION,
    TO_EXPLAIN,
    TRANSFER_PAID,
    UNPAID,
)
from accounting_agent.statements.models import Transaction

T_MOBILE = InvoiceRef(
    "KSEF-TM-09",
    "509417000926",
    date(2026, 9, 9),
    "T-Mobile Polska S.A.",
    "5261040567",
    Decimal("246.28"),
    "PLN",
    "Vat",
)
WS = InvoiceRef(
    "KSEF-WS-09",
    "30/09/2026",
    date(2026, 9, 28),
    "WS ACCOUNTING SP. Z O.O.",
    "1231571298",
    Decimal("1131.60"),
    "PLN",
    "Vat",
)


def transfer(title: str, amount: str, booked: date) -> Debit:
    t = Transaction(
        booking_date=booked, amount=-Decimal(amount), lines=[f"SP PRZELEW Tytuł: {title}"]
    )
    return Debit("Alior", "1", "PLN", t, classify(t))


def reconcile(register: dict, debits: list[Debit], invoices: list[InvoiceRef], month: str) -> None:
    """To samo, co services.reconcile robi z rejestrem, bez KSeF i plików."""
    payments.clear_statement_month(register, month)
    paid_before = payments.bank_paid(register)
    match(debits, [i for i in invoices if i.ksef_number not in paid_before])
    for debit in debits:
        if debit.invoice:
            payments.record_payment(register, debit, month)


def status_of(invoice: InvoiceRef, register: dict, last: str) -> payments.InvoiceStatus:
    return payments.statuses([invoice], register, last)[0]


def test_september_invoice_paid_in_october_updates_september():
    register: dict = {}
    reconcile(register, [], [T_MOBILE, WS], "2026-09")
    assert status_of(T_MOBILE, register, "2026-09").status == UNPAID

    october = [transfer("509417000926", "246.28", date(2026, 10, 11))]
    reconcile(register, october, [T_MOBILE, WS], "2026-10")

    paid = status_of(T_MOBILE, register, "2026-10")
    assert paid.status == TRANSFER_PAID and paid.paid_later and paid.statement_month == "2026-10"
    assert status_of(WS, register, "2026-10").status == UNPAID


def test_rerunning_a_month_does_not_duplicate_payments():
    register: dict = {}
    october = [transfer("509417000926", "246.28", date(2026, 10, 11))]
    reconcile(register, october, [T_MOBILE], "2026-10")
    reconcile(
        register, [transfer("509417000926", "246.28", date(2026, 10, 11))], [T_MOBILE], "2026-10"
    )
    assert register["KSEF-TM-09"]["payment"]["statement_month"] == "2026-10"
    assert status_of(T_MOBILE, register, "2026-10").status == TRANSFER_PAID


def test_paid_invoice_is_not_matched_again_in_a_later_month():
    register: dict = {}
    reconcile(register, [transfer("30/09/2026", "1131.60", date(2026, 10, 2))], [WS], "2026-10")
    november = [transfer("inna faktura", "1131.60", date(2026, 11, 2))]
    reconcile(register, november, [WS], "2026-11")
    assert november[0].invoice is None
    assert register["KSEF-WS-09"]["payment"]["statement_month"] == "2026-10"


def test_card_payment_status():
    register: dict = {}
    t = Transaction(
        booking_date=date(2026, 9, 10),
        amount=-Decimal("246.28"),
        lines=["TRANSAKCJA KARTĄ VB DEBIT", "246.28 PLN T-MOBILE SALON"],
    )
    debit = Debit("Erste", "2", "PLN", t, classify(t))
    reconcile(register, [debit], [T_MOBILE], "2026-09")
    assert status_of(T_MOBILE, register, "2026-09").status == CARD_PAID


def test_cash_and_conflict():
    register: dict = {}
    payments.set_cash(register, "KSEF-WS-09", True, "2026-10-20T10:00:00")
    assert status_of(WS, register, "2026-10").status == CASH

    reconcile(register, [transfer("30/09/2026", "1131.60", date(2026, 10, 30))], [WS], "2026-10")
    assert status_of(WS, register, "2026-10").status == CONFLICT

    payments.set_cash(register, "KSEF-WS-09", False, "2026-10-21T10:00:00")
    assert status_of(WS, register, "2026-10").status == TRANSFER_PAID


def test_unpaid_becomes_to_explain_after_two_reconciled_months():
    register: dict = {}
    assert status_of(WS, register, "2026-09").status == UNPAID
    assert status_of(WS, register, "2026-10").status == UNPAID
    assert status_of(WS, register, "2026-11").status == TO_EXPLAIN


def test_corrections():
    advance = InvoiceRef(
        "KSEF-ZAL",
        "Faktura 95/ZAL/26-08",
        date(2026, 8, 3),
        "WSPÓLNOTA",
        "7010714667",
        Decimal("224.24"),
        "PLN",
        "Vat",
    )
    correction = InvoiceRef(
        "KSEF-KOR",
        "Faktura korekta 109/KOR/26-08",
        date(2026, 8, 17),
        "WSPÓLNOTA",
        "7010714667",
        Decimal("-224.24"),
        "PLN",
        "Kor",
    )
    parsed = _parsed(corrected=[("Faktura  95/ZAL/26-08", "2026-08-03")])
    register: dict = {}
    payments.remember_invoice(register, correction, parsed)
    result = {
        s.invoice.ksef_number: s
        for s in payments.statuses([advance, correction], register, "2026-08")
    }
    assert result["KSEF-ZAL"].status == CORRECTED_TO_ZERO
    assert result["KSEF-KOR"].status == CORRECTION
    assert "koryguje Faktura 95/ZAL/26-08 z 03-08-2026" in result["KSEF-KOR"].details


def test_payment_hint_from_invoice():
    register: dict = {}
    paid_by_card = Payment("karta", True, date(2026, 9, 9), [], [])
    payments.remember_invoice(register, T_MOBILE, _parsed(payment=paid_by_card))
    status = status_of(T_MOBILE, register, "2026-09")
    assert status.status == UNPAID and status.details == "wg faktury: karta, zapłacono 09-09-2026"


def test_set_cash_updates_month_statuses(app_dirs):
    meta = {
        "ksefNumber": "KSEF-WS-09",
        "invoiceNumber": "30/09/2026",
        "issueDate": "2026-09-28",
        "seller": {"nip": "1231571298", "name": "WS ACCOUNTING"},
        "grossAmount": 1131.6,
        "currency": "PLN",
        "invoiceType": "Vat",
    }
    services._store_month("2026-09", [meta])
    assert services.month_statuses("2026-09")[0].status == UNPAID
    statuses = services.set_cash(app_dirs, "2026-09", "KSEF-WS-09", True)
    assert statuses[0].status == CASH
    assert storage.read_data(payments.REGISTER_FILE)["KSEF-WS-09"]["cash"]


def _parsed(payment=None, corrected=()) -> Invoice:
    return Invoice(
        ksef_number="",
        kind="VAT",
        number="",
        issue_date=date(2026, 9, 1),
        issue_place=None,
        sale_date=None,
        sale_period=None,
        currency="PLN",
        seller=None,
        buyer=None,
        other_parties=[],
        lines=[],
        vat_summary=[],
        total=Decimal(0),
        charges=[],
        to_pay=None,
        payment=payment,
        corrected=list(corrected),
        correction_reason=None,
    )
