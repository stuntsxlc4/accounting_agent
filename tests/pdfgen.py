"""Sztuczne wyciągi PDF do testów czytników.

Słowa są rozmieszczone w tych samych kolumnach co w prawdziwych wyciągach banków (pozycje
w punktach, od lewej i od góry strony). Dane są wymyślone.
"""

import sys
from pathlib import Path

from fpdf import FPDF

from accounting_agent.pdf import FONT_CANDIDATES


class StatementPdf:
    def __init__(self, font_size: float = 8):
        self.pdf = FPDF(unit="pt", format="A4")
        regular, _ = FONT_CANDIDATES.get(sys.platform, FONT_CANDIDATES["win32"])
        self.pdf.add_font("Test", "", regular)
        self.pdf.set_auto_page_break(False)
        self.font_size = font_size
        self.page()

    def page(self) -> StatementPdf:
        self.pdf.add_page()
        self.pdf.set_font("Test", size=self.font_size)
        return self

    def row(self, top: float, *cells: tuple) -> StatementPdf:
        """Komórki: (x, tekst) wyrównane do lewej albo (x_prawy, tekst, "R") do prawej."""
        baseline = top + self.font_size
        for cell in cells:
            if len(cell) == 3:
                right, text, _ = cell
                x = right - self.pdf.get_string_width(text)
            else:
                x, text = cell
            self.pdf.text(x, baseline, text)
        return self

    def save(self, path: Path) -> Path:
        self.pdf.output(str(path))
        return path


def alior(path: Path, closing: str = "18 637,95") -> Path:
    """Wyciąg dzienny Alior: odsetki (uznanie), przelew split payment, druga strona."""
    pdf = StatementPdf()
    pdf.row(47, (70, "Wyciąg za okres:"), (159, "2026.08.11"), (213, "-"), (220, "2026.08.11"))
    pdf.row(98, (70, "Wyciąg z rachunku bankowego"))
    pdf.row(316, (70, "Numer klienta:"), (266, "50967117"), (329, "Waluta rachunku:"), (550, "PLN"))
    pdf.row(
        326,
        (70, "Numer rachunku:"),
        (159, "58 2490 0005 0000 4530 1673 9104"),
        (329, "IBAN:"),
        (404, "PL 58 2490 0005 0000 4530 1673 9104"),
    )
    pdf.row(416, (71, "Data księg."), (264, "Opis"), (416, "Kwota"), (478, "Kwota"))
    pdf.row(
        425,
        (71, "Data waluty"),
        (123, "Kontrahent"),
        (264, "operacji"),
        (399, "obciążenia"),
        (472, "uznania"),
        (542, "Saldo"),
    )
    pdf.row(440, (71, "2026.08.11"), (264, "SALDO POCZĄTKOWE"), (562, "20 000,00", "R"))
    pdf.row(
        459,
        (72, "2026.08.11"),
        (265, "ROZLICZENIE ODSETEK -"),
        (505, "15,83", "R"),
        (564, "20 015,83", "R"),
    )
    pdf.row(469, (265, "LOKATA"))
    pdf.row(
        545,
        (72, "2026.08.11"),
        (123, "89 1140 1238 2444 8010 8457 1141"),
        (265, "SP PRZELEW NA RACHUNKI"),
        (444, "-246,28", "R"),
        (564, "19 769,55", "R"),
    )
    pdf.row(555, (72, "2026.08.12"), (124, "T-mobile Polska S.A."), (265, "W INNYM BANKU"))
    pdf.row(571, (265, "Tytuł: 509417000826"))
    pdf.row(588, (265, "Ident.: 5261040567"))
    pdf.row(597, (265, "FV: 509417000826"))
    pdf.row(737, (70, "Infolinia Alior Banku jest dostępna pod numerami: 12 370 70 00"))
    pdf.row(754, (70, "Alior Bank SA, ul. Chmielna 69, 00-801 Warszawa"))

    pdf.page()
    pdf.row(98, (70, "Wyciąg z rachunku bankowego"))
    pdf.row(
        130,
        (72, "2026.08.11"),
        (123, "39 1140 2004 0000 3402 8544 2626"),
        (265, "SP PRZELEW NA RACHUNKI"),
        (444, "-1 131,60", "R"),
        (564, "18 637,95", "R"),
    )
    pdf.row(140, (124, "WS Accounting Sp. z o.o."), (265, "Tytuł: 31/07/2026"))
    pdf.row(160, (71, "2026.08.11"), (264, "SALDO KOŃCOWE"), (564, closing, "R"))
    pdf.row(180, (70, "Podsumowanie"))
    return pdf.save(path)


def erste(path: Path) -> Path:
    """Wyciąg miesięczny Erste: opłata, płatność kartą, uznanie."""
    pdf = StatementPdf()
    pdf.row(60, (22, "DATA WYCIĄGU"), (120, "WYCIĄG OD"), (200, "DO"), (260, "NR WYCIĄGU"))
    pdf.row(70, (22, "2026-08-31"), (120, "2026-08-01"), (200, "2026-08-31"), (260, "2026/008"))
    pdf.row(90, (22, "NR RACHUNKU"), (260, "NR KLIENTA"))
    pdf.row(100, (22, "17 1090 1883 0000 0001 6115 2280"), (260, "0063010067"))
    pdf.row(120, (22, "WYCIĄG Z RACHUNKU BANKOWEGO"), (300, "ERSTE BANK POLSKA S.A."))
    pdf.row(240, (26, "NAZWA RACHUNKU"), (167, "WALUTA"), (218, "STOPA PROCENTOWA"))
    pdf.row(255, (26, "Rachunek bieżący - Konto Firmowe"), (167, "PLN"), (218, "0,00000%"))
    pdf.row(
        299,
        (23, "DATA"),
        (78, "OPIS TRANSAKCJI"),
        (406, "OBCIĄŻENIA"),
        (469, "UZNANIA"),
        (535, "SALDO"),
    )
    pdf.row(320, (22, "2026-08-01"), (76, "Saldo początkowe:"), (570, "3.533.712,42", "R"))
    pdf.row(
        341,
        (27, "2026-08-05"),
        (80, "2026-08-05"),
        (124, "OPŁATA/PROWIZJA Opłata za Moja Firma plus"),
        (450, "55,00", "R"),
        (558, "3.533.657,42", "R"),
    )
    pdf.row(
        448,
        (27, "2026-08-14"),
        (80, "2026-08-12"),
        (124, "TRANSAKCJA KARTĄ VB DEBIT 423725******1915"),
        (450, "384,50", "R"),
        (562, "3.533.272,92", "R"),
    )
    pdf.row(463, (80, "384.50 PLN ORLEN STACJA NR 555 WARSZAWA"))
    pdf.row(
        490,
        (27, "2026-08-20"),
        (80, "2026-08-20"),
        (124, "UZNANIE 33735689"),
        (506, "7.150.000,00", "R"),
        (562, "10.683.272,92", "R"),
    )
    pdf.row(
        600,
        (76, "Saldo końcowe:"),
        (450, "439,50", "R"),
        (506, "7.150.000,00", "R"),
        (562, "10.683.272,92", "R"),
    )
    pdf.row(810, (15, "Erste Bank Polska S.A. Dokument pochodzi z naszego systemu"))
    return pdf.save(path)


def unicredit(path: Path) -> Path:
    """Wyciąg UniCredit: przelew przychodzący i otwarcie lokaty."""
    pdf = StatementPdf()
    pdf.row(40, (37, "Wyciąg bankowy"))
    pdf.row(55, (37, "UniCredit S.A. Spółka Akcyjna Oddział w Polsce"), (420, "Dokument za okres:"))
    pdf.row(65, (420, "01.08.2026 - 31.08.2026"))
    pdf.row(260, (37, "Adres"), (306, "Numer rachunku"))
    pdf.row(270, (37, "STEFANA OKRZEI 8/52"), (306, "PL42291000192469800301049172"))
    pdf.row(345, (306, "Waluta rachunku"))
    pdf.row(355, (306, "PLN"))
    pdf.row(
        447,
        (37, "Saldo początkowe"),
        (127, "Saldo końcowe"),
        (306, "Suma uznań"),
        (396, "Suma obciążeń"),
    )
    pdf.row(457, (37, "0.00 PLN"), (127, "500.00 PLN"), (306, "1 000.00 PLN"), (396, "500.00 PLN"))
    pdf.row(
        560,
        (40, "Data transakcji"),
        (135, "Opis"),
        (287, "Tytuł operacji"),
        (359, "Rodzaj operacji"),
        (462, "Kwota"),
        (506, "Saldo po operacji"),
    )
    pdf.row(
        592,
        (40, "25.08.2026"),
        (135, "PL171090188300000001611"),
        (287, "Przekazanie srodkow"),
        (359, "Przelew przychodzący"),
        (473, "1 000.00", "R"),
        (478, "PLN"),
        (559, "1 000.00", "R"),
        (564, "PLN"),
    )
    pdf.row(599, (40, "26.08.2026"), (135, "52280"), (287, "na Rachunek Wlasny"))
    pdf.row(
        630,
        (40, "28.08.2026"),
        (135, "PL712910001924698003011"),
        (287, "Otwarcie lokaty"),
        (359, "Inny"),
        (485, "-500.00", "R"),
        (559, "500.00", "R"),
        (564, "PLN"),
    )
    pdf.row(800, (188, "Wydany 08.10.2026 13:46:03"))
    return pdf.save(path)


def plain(path: Path, text: str | None) -> Path:
    """PDF z dowolnym tekstem albo pusty (jak skan bez warstwy tekstowej)."""
    pdf = StatementPdf()
    if text:
        pdf.row(100, (50, text))
    return pdf.save(path)
