"""Nazwy plików faktur, bezpieczne dla Windows i macOS.

Wzór: RRRR-MM-DD_INV numer_Sprzedawca.pdf (korekty: KOR zamiast INV).
"""

import re
from datetime import date

FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_PART_LENGTH = 80

# Słowa, którymi część wystawców poprzedza numer, np. "Faktura korekta 105/KOR/26".
NUMBER_PREFIX = re.compile(r"^(?:(?:faktura|korekta|korygująca|vat)\s+)+", re.IGNORECASE)

LEGAL_FORMS = [
    r"prosta spółka akcyjna",
    r"spółka komandytowo[- ]akcyjna",
    r"spółka z ograniczoną odpowiedzialnością",
    r"spółka akcyjna",
    r"spółka komandytowa",
    r"spółka jawna",
    r"spółka partnerska",
    r"spółka cywilna",
    r"(?:sp\.?|spółka)\s*z\s*o\.?\s*o\.?",
    r"s\.\s*k\.\s*a\.?",
    r"p\.\s*s\.\s*a\.?",
    r"s\.\s*a\.?",
    r"sa",
    r"sp\.\s*k\.?",
    r"sp\.\s*j\.?",
    r"sp\.\s*p\.?",
    r"s\.\s*c\.?",
]
LEGAL_FORM_SUFFIX = re.compile(r"(?:^|[\s,])(?:" + "|".join(LEGAL_FORMS) + r")\s*$", re.IGNORECASE)
# "Polska" po nazwie marki: "Shell Polska" -> "Shell", "Bonnier (Polska)" -> "Bonnier".
POLSKA_WORD = re.compile(r"(?<=\S)\s+\(?polska\)?(?=\s|$)", re.IGNORECASE)


def invoice_filename(
    issue_date: date,
    number: str,
    seller_name: str,
    invoice_type: str,
    extension: str = "pdf",
) -> str:
    label = "KOR" if invoice_type.upper().startswith("KOR") else "INV"
    number = _clean(NUMBER_PREFIX.sub("", number.strip()))
    parts = [issue_date.isoformat(), f"{label} {number}", _clean(short_company_name(seller_name))]
    return "_".join(p for p in parts if p) + f".{extension}"


def short_company_name(name: str) -> str:
    """Nazwa sprzedawcy bez formy prawnej i dopisku "Polska"."""
    short = " ".join(name.replace('"', "").split())
    while True:
        stripped = LEGAL_FORM_SUFFIX.sub("", short).strip(" ,-")
        if stripped == short:
            break
        short = stripped
    short = POLSKA_WORD.sub("", short).strip(" ,-")
    return short or name


def _clean(value: str) -> str:
    value = value.replace('"', "")
    value = FORBIDDEN_CHARS.sub("-", value)
    value = " ".join(value.split())
    return value[:MAX_PART_LENGTH].rstrip(" .")
