"""Porównanie obciążeń z wyciągów bankowych z fakturami zakupowymi."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from accounting_agent.invoice import Payment
from accounting_agent.naming import short_company_name
from accounting_agent.statements.models import Transaction

# Rodzaje obciążeń
TRANSFER = "przelew"
CARD = "karta"
BANK_FEE = "opłata bankowa"
DEPOSIT = "lokata"
OWN_TRANSFER = "przelew własny"
SOCIAL_SECURITY = "ZUS"
TAX = "podatek (US)"
SALARY = "wynagrodzenie"
EXPECTS_INVOICE = {TRANSFER, CARD}

# Metody dopasowania, od najpewniejszej
BY_NUMBER = "numer faktury"
BY_AMOUNT_AND_NAME = "kwota i kontrahent"
BY_AMOUNT = "tylko kwota – sprawdź"

# Status faktur, których płatności nie ma na wyciągach
NOT_PAID = "brak płatności"
OTHER_CARD = "zapłacona kartą spoza wyciągów"
PAID_OTHERWISE = "zapłacona wg faktury"
CORRECTION = "korekta"

# Faktura może być wystawiona do kilku dni po płatności kartą lub przedpłacie.
ISSUED_AFTER_PAYMENT_DAYS = 14
# Krótsze numery ("1/2026") szukamy tylko po etykiecie FV:/Tytuł:, żeby nie trafiać w daty.
MIN_NUMBER_IN_TEXT = 6
INVOICE_REF = re.compile(r"(?:FV|Tytuł):\s*(\S+)")
SELLER_NIP = re.compile(r"Ident\.:\s*(\d{10})")


@dataclass(frozen=True)
class InvoiceRef:
    ksef_number: str
    number: str
    issue_date: date
    seller_name: str
    seller_nip: str
    gross: Decimal
    currency: str
    invoice_type: str

    @classmethod
    def from_metadata(cls, meta: dict) -> InvoiceRef:
        return cls(
            ksef_number=meta["ksefNumber"],
            number=meta["invoiceNumber"],
            issue_date=date.fromisoformat(meta["issueDate"]),
            seller_name=meta["seller"].get("name") or "",
            seller_nip=meta["seller"]["nip"],
            gross=Decimal(str(meta["grossAmount"])).quantize(Decimal("0.01")),
            currency=meta["currency"],
            invoice_type=meta["invoiceType"],
        )


@dataclass
class Debit:
    bank: str
    account: str
    currency: str
    transaction: Transaction
    kind: str
    invoice: InvoiceRef | None = None
    method: str = ""
    note: str = ""

    @property
    def amount(self) -> Decimal:
        return -self.transaction.amount

    @property
    def payment_date(self) -> date:
        return self.transaction.operation_date or self.transaction.booking_date


def classify(transaction: Transaction) -> str:
    text = f"{transaction.text} {transaction.counterparty}".lower()
    first_line = transaction.lines[0].lower() if transaction.lines else ""
    if "transakcja kartą" in text or "płatność kartą" in text:
        return CARD
    if "lokat" in text:
        return DEPOSIT
    if "rachunek własny" in text or "rachunek wlasny" in text:
        return OWN_TRANSFER
    if first_line.startswith(("opłat", "prowizj")):
        return BANK_FEE
    if re.search(r"\bzus\b|zakład ubezpieczeń społecznych", text):
        return SOCIAL_SECURITY
    if "organu podatkowego" in text or "urząd skarbowy" in text:
        return TAX
    if "wynagrodzenie" in text:
        return SALARY
    return TRANSFER


def match(debits: list[Debit], invoices: list[InvoiceRef]) -> None:
    """Przypisuje faktury do obciążeń; każda faktura najwyżej raz."""
    available = [i for i in invoices if i.gross > 0]
    candidates = [d for d in debits if d.kind in EXPECTS_INVOICE]

    for debit in candidates:
        invoice = _by_number(debit, available)
        if invoice:
            _assign(debit, invoice, BY_NUMBER, available)

    for debit in candidates:
        if debit.invoice is None:
            same_amount = _same_amount(debit, available)
            named = [i for i in same_amount if _names_match(i.seller_name, debit)]
            if named:
                _assign(debit, _closest(debit, named), BY_AMOUNT_AND_NAME, available)

    for debit in candidates:
        if debit.invoice is None:
            same_amount = _same_amount(debit, available)
            if same_amount:
                invoice = _closest(debit, same_amount)
                _assign(debit, invoice, BY_AMOUNT, available)
                if len(same_amount) > 1:
                    debit.note = f"{len(same_amount)} faktury z tą kwotą, wybrano najbliższą datą"

    for debit in candidates:
        refs = INVOICE_REF.findall(debit.transaction.text)
        if debit.invoice is None and refs:
            debit.note = f"w tytule przelewu: {refs[0]} – nie ma tej faktury w KSeF"


@dataclass(frozen=True)
class UnpaidInvoice:
    invoice: InvoiceRef
    status: str
    payment: str = ""  # sposób płatności z faktury, np. "karta, zapłacono 08-08-2026"


def is_correction(invoice: InvoiceRef) -> bool:
    return invoice.gross <= 0 or invoice.invoice_type.upper().startswith("KOR")


def explain_unpaid(invoice: InvoiceRef, payment: Payment | None) -> UnpaidInvoice:
    """Status faktury bez płatności na wyciągach, według danych o płatności z faktury.

    Faktura opłacona kartą (np. paliwo), której nie ma na wyciągach, była zapłacona
    inną kartą niż ta, której wyciągi porównujemy.
    """
    if is_correction(invoice):
        return UnpaidInvoice(invoice, CORRECTION)
    if payment is None:
        return UnpaidInvoice(invoice, NOT_PAID, "brak danych o płatności na fakturze")
    details = [payment.form] if payment.form else []
    if payment.paid:
        details.append(
            f"zapłacono {payment.paid_date:%d-%m-%Y}" if payment.paid_date else "zapłacono"
        )
    details += [f"termin {due:%d-%m-%Y}" for due in payment.due_dates]
    if payment.paid and payment.form == "karta":
        status = OTHER_CARD
    elif payment.paid:
        status = PAID_OTHERWISE
    else:
        status = NOT_PAID
    return UnpaidInvoice(invoice, status, ", ".join(details))


def unpaid(invoices: list[InvoiceRef], debits: list[Debit], date_from, date_to) -> list:
    matched = {d.invoice.ksef_number for d in debits if d.invoice}
    return [
        i for i in invoices if date_from <= i.issue_date <= date_to and i.ksef_number not in matched
    ]


def _by_number(debit: Debit, invoices: list[InvoiceRef]) -> InvoiceRef | None:
    """Numer faktury w tytule przelewu ("FV:", "Tytuł:" albo w dowolnym miejscu opisu)."""
    text = debit.transaction.text
    refs = {_norm_number(r) for r in INVOICE_REF.findall(text)}
    compact_text = _norm_number(text)
    nip_match = SELLER_NIP.search(text)
    nip = nip_match.group(1) if nip_match else None
    for invoice in invoices:
        number = _norm_number(invoice.number)
        same_seller = nip == invoice.seller_nip or _names_match(invoice.seller_name, debit)
        if number in refs and (nip is None or nip == invoice.seller_nip):
            return invoice
        if len(number) >= MIN_NUMBER_IN_TEXT and number in compact_text and same_seller:
            return invoice
    return None


def _same_amount(debit: Debit, invoices: list[InvoiceRef]) -> list[InvoiceRef]:
    latest_issue = debit.payment_date + timedelta(days=ISSUED_AFTER_PAYMENT_DAYS)
    return [
        i
        for i in invoices
        if i.gross == debit.amount and i.currency == debit.currency and i.issue_date <= latest_issue
    ]


def _closest(debit: Debit, invoices: list[InvoiceRef]) -> InvoiceRef:
    return min(invoices, key=lambda i: abs((i.issue_date - debit.payment_date).days))


def _assign(debit: Debit, invoice: InvoiceRef, method: str, available: list) -> None:
    debit.invoice = invoice
    debit.method = method
    if invoice.gross != debit.amount:
        diff = debit.amount - invoice.gross
        debit.note = f"kwota różni się od brutto faktury o {diff:+.2f}"
    available.remove(invoice)


def _names_match(seller_name: str, debit: Debit) -> bool:
    seller_words = {w for w in _fold(short_company_name(seller_name)).split() if len(w) >= 3}
    debit_words = set(_fold(f"{debit.transaction.text} {debit.transaction.counterparty}").split())
    return bool(seller_words & debit_words)


def _fold(text: str) -> str:
    text = text.upper().replace("Ł", "L")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", " ", text)


def _norm_number(number: str) -> str:
    return re.sub(r"\s+", "", number).upper()
