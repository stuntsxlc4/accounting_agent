"""Odczyt faktury w schemacie FA(3) z KSeF."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from lxml import etree

INVOICE_KINDS = {
    "VAT": "Faktura VAT",
    "KOR": "Faktura korygująca",
    "ZAL": "Faktura zaliczkowa",
    "ROZ": "Faktura rozliczeniowa",
    "UPR": "Faktura uproszczona",
    "KOR_ZAL": "Faktura korygująca zaliczkową",
    "KOR_ROZ": "Faktura korygująca rozliczeniową",
}

PAYMENT_FORMS = {
    "1": "gotówka",
    "2": "karta",
    "3": "bon",
    "4": "czek",
    "5": "kredyt",
    "6": "przelew",
    "7": "mobilna",
}

PARTY3_ROLES = {
    "1": "Faktor",
    "2": "Odbiorca",
    "3": "Podmiot pierwotny",
    "4": "Dodatkowy nabywca",
    "5": "Wystawca faktury",
    "6": "Dokonujący płatności",
    "7": "JST – wystawca",
    "8": "JST – odbiorca",
    "9": "Członek grupy VAT – wystawca",
    "10": "Członek grupy VAT – odbiorca",
    "11": "Pracownik",
}

# Pola podsumowania (netto, VAT) w kolejności z wzoru FA(3).
VAT_SUMMARY_FIELDS = [
    ("23% / 22%", "P_13_1", "P_14_1"),
    ("8% / 7%", "P_13_2", "P_14_2"),
    ("5%", "P_13_3", "P_14_3"),
    ("ryczałt taxi", "P_13_4", "P_14_4"),
    ("OSS", "P_13_5", "P_14_5"),
    ("0% kraj", "P_13_6_1", None),
    ("0% WDT", "P_13_6_2", None),
    ("0% eksport", "P_13_6_3", None),
    ("zw", "P_13_7", None),
    ("np I", "P_13_8", None),
    ("np II", "P_13_9", None),
    ("oo", "P_13_10", None),
    ("marża", "P_13_11", None),
]


@dataclass(frozen=True)
class Party:
    name: str
    nip: str | None
    address: list[str]
    role: str | None = None


@dataclass(frozen=True)
class Line:
    number: str
    name: str
    unit: str
    quantity: Decimal | None
    unit_net: Decimal | None
    unit_gross: Decimal | None
    net: Decimal | None
    gross: Decimal | None
    vat_rate: str
    before_correction: bool


@dataclass(frozen=True)
class VatSummary:
    label: str
    net: Decimal
    vat: Decimal | None


@dataclass(frozen=True)
class Payment:
    form: str | None
    paid: bool
    paid_date: date | None
    due_dates: list[date]
    bank_accounts: list[tuple[str, str | None]]


@dataclass(frozen=True)
class Invoice:
    ksef_number: str
    kind: str
    number: str
    issue_date: date
    issue_place: str | None
    sale_date: date | None
    sale_period: tuple[date, date] | None
    currency: str
    seller: Party
    buyer: Party
    other_parties: list[Party]
    lines: list[Line]
    vat_summary: list[VatSummary]
    total: Decimal
    charges: list[tuple[str, Decimal]]
    to_pay: Decimal | None
    payment: Payment | None
    corrected: list[tuple[str, str]]
    correction_reason: str | None
    notes: list[tuple[str, str]] = field(default_factory=list)
    registry: list[tuple[str, str]] = field(default_factory=list)

    @property
    def kind_label(self) -> str:
        return INVOICE_KINDS.get(self.kind, f"Faktura {self.kind}")


def parse_invoice(xml: bytes, ksef_number: str) -> Invoice:
    root = etree.fromstring(xml)
    ns = {"fa": etree.QName(root).namespace}

    def find(el, path):
        return el.find(_q(path), ns) if el is not None else None

    def findall(el, path):
        return el.findall(_q(path), ns) if el is not None else []

    def text(el, path) -> str | None:
        node = find(el, path)
        return node.text.strip() if node is not None and node.text else None

    def amount(el, path) -> Decimal | None:
        value = text(el, path)
        return Decimal(value) if value is not None else None

    def party(el) -> Party:
        ids = find(el, "DaneIdentyfikacyjne")
        address = [line for line in (text(el, "Adres/AdresL1"), text(el, "Adres/AdresL2")) if line]
        role = PARTY3_ROLES.get(text(el, "Rola") or "") or text(el, "OpisRoli")
        return Party(
            name=text(ids, "Nazwa") or "",
            nip=text(ids, "NIP") or text(ids, "IDWew") or text(ids, "NrID"),
            address=address,
            role=role,
        )

    fa = find(root, "Fa")

    def day(el, path) -> date | None:
        value = text(el, path)
        return date.fromisoformat(value) if value else None

    period_from, period_to = day(fa, "OkresFa/P_6_Od"), day(fa, "OkresFa/P_6_Do")

    lines = [
        Line(
            number=text(row, "NrWierszaFa") or "",
            name=text(row, "P_7") or "",
            unit=text(row, "P_8A") or "",
            quantity=amount(row, "P_8B"),
            unit_net=amount(row, "P_9A"),
            unit_gross=amount(row, "P_9B"),
            net=amount(row, "P_11"),
            gross=amount(row, "P_11A"),
            vat_rate=text(row, "P_12") or "",
            before_correction=text(row, "StanPrzed") == "1",
        )
        for row in findall(fa, "FaWiersz")
    ]

    vat_summary = []
    for label, net_field, vat_field in VAT_SUMMARY_FIELDS:
        net = amount(fa, net_field)
        if net is not None:
            vat = amount(fa, vat_field) if vat_field else None
            vat_summary.append(VatSummary(label=label, net=net, vat=vat))

    payment_el = find(fa, "Platnosc")
    payment = None
    if payment_el is not None:
        paid_date = text(payment_el, "DataZaplaty")
        payment = Payment(
            form=PAYMENT_FORMS.get(text(payment_el, "FormaPlatnosci") or "")
            or text(payment_el, "OpisPlatnosci"),
            paid=text(payment_el, "Zaplacono") == "1",
            paid_date=date.fromisoformat(paid_date) if paid_date else None,
            due_dates=[
                date.fromisoformat(d.text)
                for d in findall(payment_el, "TerminPlatnosci/Termin")
                if d.text
            ],
            bank_accounts=[
                (text(acc, "NrRB") or "", text(acc, "NazwaBanku"))
                for acc in findall(payment_el, "RachunekBankowy")
            ],
        )

    footer = find(root, "Stopka")
    registry = [
        (label, value)
        for label, value in (
            ("KRS", text(footer, "Rejestry/KRS")),
            ("REGON", text(footer, "Rejestry/REGON")),
            ("BDO", text(footer, "Rejestry/BDO")),
        )
        if value
    ]

    return Invoice(
        ksef_number=ksef_number,
        kind=text(fa, "RodzajFaktury") or "VAT",
        number=text(fa, "P_2") or "",
        issue_date=date.fromisoformat(text(fa, "P_1")),
        issue_place=text(fa, "P_1M"),
        sale_date=day(fa, "P_6"),
        sale_period=(period_from, period_to) if period_from and period_to else None,
        currency=text(fa, "KodWaluty") or "PLN",
        seller=party(find(root, "Podmiot1")),
        buyer=party(find(root, "Podmiot2")),
        other_parties=[party(p) for p in findall(root, "Podmiot3")],
        lines=lines,
        vat_summary=vat_summary,
        total=amount(fa, "P_15") or Decimal(0),
        charges=[
            (text(c, "Powod") or "", amount(c, "Kwota") or Decimal(0))
            for c in findall(fa, "Rozliczenie/Obciazenia")
        ],
        to_pay=amount(fa, "Rozliczenie/DoZaplaty"),
        payment=payment,
        corrected=[
            (text(c, "NrFaKorygowanej") or "", text(c, "DataWystFaKorygowanej") or "")
            for c in findall(fa, "DaneFaKorygowanej")
        ],
        correction_reason=text(fa, "PrzyczynaKorekty"),
        notes=[
            (text(n, "Klucz") or "", text(n, "Wartosc") or "") for n in findall(fa, "DodatkowyOpis")
        ],
        registry=registry,
    )


def _q(path: str) -> str:
    return "/".join(f"fa:{part}" for part in path.split("/"))
