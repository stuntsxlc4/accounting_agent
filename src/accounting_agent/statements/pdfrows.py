"""Wiersze tekstu z PDF wyciągu, z położeniem słów na stronie."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

ROW_TOLERANCE = 3.0
NUMBER_GAP = 4.0
NUMBER_PART = re.compile(r"^-?[\d.,]+$")
AMOUNT = re.compile(r"^-?\d{1,3}(?:[ .]\d{3})*[.,]\d{2}$")


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float
    top: float


@dataclass(frozen=True)
class Row:
    top: float
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    def text_between(self, x_from: float, x_to: float) -> str:
        return " ".join(w.text for w in self.words if x_from <= w.x0 < x_to)

    def amounts(self, min_x: float = 0) -> list[Word]:
        """Kwoty w wierszu: sąsiednie fragmenty liczby ("1", "131,60") łączone w jedną."""
        tokens: list[Word] = []
        for w in self.words:
            if w.x0 < min_x or not NUMBER_PART.match(w.text):
                continue
            prev = tokens[-1] if tokens else None
            if prev and w.x0 - prev.x1 <= NUMBER_GAP and not AMOUNT.match(prev.text):
                tokens[-1] = Word(f"{prev.text} {w.text}", prev.x0, w.x1, prev.top)
            else:
                tokens.append(w)
        return [t for t in tokens if AMOUNT.match(t.text)]


def page_rows(page) -> list[Row]:
    words = sorted(
        (
            Word(w["text"].replace("­", "-"), w["x0"], w["x1"], w["top"])
            for w in page.extract_words(keep_blank_chars=False)
        ),
        key=lambda w: (w.top, w.x0),
    )
    rows: list[list[Word]] = []
    for w in words:
        if rows and w.top - rows[-1][0].top <= ROW_TOLERANCE:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [Row(r[0].top, tuple(sorted(r, key=lambda w: w.x0))) for r in rows]


def parse_amount(text: str) -> Decimal:
    """Kwota w formacie polskim lub angielskim: "-1 131,60", "3.533.657,42", "2 000 000.00"."""
    value = text.replace(" ", "")
    if "," in value and "." in value:
        decimal_sep = "," if value.rfind(",") > value.rfind(".") else "."
    elif "," in value:
        decimal_sep = ","
    else:
        decimal_sep = "."
    thousands_sep = "." if decimal_sep == "," else ","
    return Decimal(value.replace(thousands_sep, "").replace(decimal_sep, "."))


def parse_date(text: str, fmt: str) -> date | None:
    try:
        return datetime.strptime(text, fmt).date()
    except ValueError:
        return None


def nearest_column(word: Word, columns: dict[str, float]) -> str:
    """Kolumna, do której prawej krawędzi kwota jest najbliżej (kwoty są wyrównane do prawej)."""
    return min(columns, key=lambda name: abs(columns[name] - word.x1))
