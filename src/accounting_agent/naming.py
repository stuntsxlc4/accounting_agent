"""Nazwy plików faktur, bezpieczne dla Windows i macOS."""

import re
from datetime import date

FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_PART_LENGTH = 80


def invoice_filename(
    issue_date: date, number: str, seller_name: str, extension: str = "pdf"
) -> str:
    parts = [issue_date.isoformat(), _clean(number), _clean(seller_name)]
    return "_".join(p for p in parts if p) + f".{extension}"


def _clean(value: str) -> str:
    value = value.replace('"', "")
    value = FORBIDDEN_CHARS.sub("-", value)
    value = " ".join(value.split())
    return value[:MAX_PART_LENGTH].rstrip(" .")
