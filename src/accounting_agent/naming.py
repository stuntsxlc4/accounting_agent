"""Nazwy plików i folderów faktur, bezpieczne dla Windows i macOS.

Plik:   DD-MM-RRRR_INV_numer_Sprzedawca.pdf, np. 10-08-2026_INV_53_07_2026_Shell.pdf
        (korekty: KOR zamiast INV; poza datą wszędzie podkreślniki)
Folder: miesiąc wystawienia, np. "Sierpień 2026"
"""

import re
from datetime import date

SEPARATORS = re.compile(r'[\s<>:"/\\|?*\x00-\x1f]+')
# Limity długości, żeby cała ścieżka zmieściła się w 260 znakach Windows.
MAX_NUMBER_LENGTH = 40
MAX_SELLER_LENGTH = 60

# Słowa, którymi część wystawców poprzedza numer, np. "Faktura korekta 105/KOR/26"
# albo "INV 53/07/2026" – INV i tak dodajemy sami.
NUMBER_PREFIX_WORDS = {"faktura", "korekta", "korygująca", "vat", "inv"}

MONTH_FOLDERS = (
    "Styczeń",
    "Luty",
    "Marzec",
    "Kwiecień",
    "Maj",
    "Czerwiec",
    "Lipiec",
    "Sierpień",
    "Wrzesień",
    "Październik",
    "Listopad",
    "Grudzień",
)

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
    tokens = [t for t in SEPARATORS.split(number) if t]
    while len(tokens) > 1 and tokens[0].lower() in NUMBER_PREFIX_WORDS:
        tokens.pop(0)
    parts = [
        f"{issue_date:%d-%m-%Y}",
        label,
        _underscored("_".join(tokens), MAX_NUMBER_LENGTH),
        _underscored(short_company_name(seller_name), MAX_SELLER_LENGTH),
    ]
    return "_".join(p for p in parts if p) + f".{extension}"


def month_folder(year: int, month: int) -> str:
    return f"{MONTH_FOLDERS[month - 1]} {year}"


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


def _underscored(value: str, max_length: int) -> str:
    value = SEPARATORS.sub("_", value.replace('"', ""))
    return value[:max_length].strip("_.")
