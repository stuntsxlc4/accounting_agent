from datetime import date

import pytest

from accounting_agent.formatting import bank_account
from accounting_agent.naming import invoice_filename, month_folder, short_company_name
from accounting_agent.services import parse_month


@pytest.mark.parametrize(
    ("number", "seller", "kind", "expected"),
    [
        (
            "INV 53/07/2026",
            "Stacja Paliw Shell",
            "Vat",
            "10-08-2026_INV_53_07_2026_Stacja_Paliw_Shell.pdf",
        ),
        (
            "F 13381K2/1024/26",
            "Shell Polska sp. z o.o.",
            "Vat",
            "10-08-2026_INV_F_13381K2_1024_26_Shell.pdf",
        ),
        ("509417000826", "T-Mobile Polska S.A.", "Vat", "10-08-2026_INV_509417000826_T-Mobile.pdf"),
        (
            "Faktura korekta 105/KOR/26-04",
            "WSPÓLNOTA MIESZKANIOWA SOLEC 24",
            "Kor",
            "10-08-2026_KOR_105_KOR_26-04_WSPÓLNOTA_MIESZKANIOWA_SOLEC_24.pdf",
        ),
    ],
)
def test_invoice_filename(number, seller, kind, expected):
    assert invoice_filename(date(2026, 8, 10), number, seller, kind) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("WARDYŃSKI I WSPÓLNICY SPÓŁKA KOMANDYTOWA", "WARDYŃSKI I WSPÓLNICY"),
        ("Bonnier Business (Polska) Spółka z o.o.", "Bonnier Business"),
        ("Polska Grupa Energetyczna S.A.", "Polska Grupa Energetyczna"),
        ("ELSA", "ELSA"),
        ('"LUDNA 2" SP. Z O. O.', "LUDNA 2"),
    ],
)
def test_short_company_name(name, expected):
    assert short_company_name(name) == expected


def test_long_names_fit_windows_path_limit():
    name = invoice_filename(date(2026, 8, 10), "X" * 200, "Y" * 200, "Vat")
    assert len(name) <= 125


def test_month_folder():
    assert month_folder(2026, 8) == "Sierpień 2026"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("10", "2026-10"), ("01", "2026-01"), ("11", "2025-11"), ("2025-12", "2025-12")],
)
def test_parse_month(text, expected):
    assert parse_month(text, today=date(2026, 10, 16)) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("83105010121000009031278782", "83 1050 1012 1000 0090 3127 8782"),
        ("PL83105010121000009031278782", "PL83 1050 1012 1000 0090 3127 8782"),
        ("CH9100308308156508610", "CH9100308308156508610"),
    ],
)
def test_bank_account(number, expected):
    assert bank_account(number) == expected
