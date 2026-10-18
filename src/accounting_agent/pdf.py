"""Wizualizacja faktury FA(3) jako PDF."""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

from accounting_agent.formatting import bank_account
from accounting_agent.invoice import Invoice, Line, Party

FONT_CANDIDATES = {
    "darwin": (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ),
    "win32": ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
}
FONT = "InvoiceFont"
GREY = (110, 110, 110)
LINE_GREY = (200, 200, 200)
HEADER_FILL = (240, 240, 240)


def render_invoice_pdf(invoice: Invoice, path: Path) -> None:
    pdf = FPDF(format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    _add_fonts(pdf)
    pdf.set_title(f"{invoice.kind_label} {invoice.number}")
    pdf.add_page()

    _header(pdf, invoice)
    _parties(pdf, invoice)
    _lines(pdf, invoice)
    _summary(pdf, invoice)
    _payment(pdf, invoice)
    _notes(pdf, invoice)
    _footer(pdf, invoice)

    pdf.output(str(path))


def _add_fonts(pdf: FPDF) -> None:
    regular, bold = FONT_CANDIDATES.get(sys.platform, FONT_CANDIDATES["win32"])
    pdf.add_font(FONT, "", regular)
    pdf.add_font(FONT, "B", bold)


def _header(pdf: FPDF, inv: Invoice) -> None:
    pdf.set_font(FONT, "B", 16)
    pdf.cell(0, 8, inv.kind_label, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "B", 12)
    pdf.cell(0, 7, f"nr {inv.number}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "", 8)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 5, f"Numer KSeF: {inv.ksef_number}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(2)

    pdf.set_font(FONT, "", 9)
    issued = f"Data wystawienia: {inv.issue_date:%d.%m.%Y}"
    if inv.issue_place:
        issued += f", {inv.issue_place}"
    pdf.cell(0, 5, issued, new_x="LMARGIN", new_y="NEXT")
    if inv.sale_date:
        pdf.cell(0, 5, f"Data sprzedaży: {inv.sale_date:%d.%m.%Y}", new_x="LMARGIN", new_y="NEXT")
    if inv.sale_period:
        start, end = inv.sale_period
        pdf.cell(0, 5, f"Okres: {start:%d.%m.%Y} – {end:%d.%m.%Y}", new_x="LMARGIN", new_y="NEXT")
    for number, issued_on in inv.corrected:
        pdf.cell(0, 5, f"Korygowana faktura: {number} z {issued_on}", new_x="LMARGIN", new_y="NEXT")
    if inv.correction_reason:
        pdf.multi_cell(0, 5, f"Przyczyna korekty: {inv.correction_reason}", align="L")
    pdf.ln(4)


def _parties(pdf: FPDF, inv: Invoice) -> None:
    width = (pdf.epw - 6) / 2
    top = pdf.get_y()
    _party_box(pdf, "Sprzedawca", inv.seller, pdf.l_margin, top, width)
    left_bottom = pdf.get_y()
    _party_box(pdf, "Nabywca", inv.buyer, pdf.l_margin + width + 6, top, width)
    pdf.set_y(max(left_bottom, pdf.get_y()) + 2)

    for party in inv.other_parties:
        _party_box(pdf, party.role or "Podmiot trzeci", party, pdf.l_margin, pdf.get_y(), pdf.epw)
        pdf.ln(2)
    pdf.ln(2)


def _party_box(pdf: FPDF, title: str, party: Party, x: float, y: float, width: float) -> None:
    pdf.set_xy(x, y)
    pdf.set_font(FONT, "B", 8)
    pdf.set_text_color(*GREY)
    pdf.cell(width, 5, title.upper(), new_x="LEFT", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.set_font(FONT, "B", 10)
    pdf.multi_cell(width, 5, party.name, new_x="LEFT", new_y="NEXT", align="L")
    pdf.set_font(FONT, "", 9)
    if party.nip:
        pdf.cell(width, 5, f"NIP: {party.nip}", new_x="LEFT", new_y="NEXT")
    for line in party.address:
        pdf.multi_cell(width, 5, line, new_x="LEFT", new_y="NEXT", align="L")


def _lines(pdf: FPDF, inv: Invoice) -> None:
    uses_gross_price = any(line.unit_gross is not None for line in inv.lines)
    has_gross = any(line.gross is not None for line in inv.lines)
    columns = [
        ("Lp", 7, "CENTER", lambda line: line.number),
        ("Nazwa", 63, "LEFT", _line_name),
        ("J.m.", 11, "CENTER", lambda line: line.unit),
        ("Ilość", 15, "RIGHT", lambda line: _num(line.quantity, quantity=True)),
        (
            "Cena brutto" if uses_gross_price else "Cena netto",
            20,
            "RIGHT",
            lambda line: _num(line.unit_gross if uses_gross_price else line.unit_net),
        ),
        ("Netto", 22, "RIGHT", lambda line: _num(line.net)),
        ("VAT", 10, "CENTER", lambda line: _rate(line.vat_rate)),
    ]
    if has_gross:
        columns.append(("Brutto", 22, "RIGHT", lambda line: _num(line.gross)))

    pdf.set_font(FONT, "", 8)
    pdf.set_draw_color(*LINE_GREY)
    with pdf.table(
        col_widths=[c[1] for c in columns],
        text_align=[c[2] for c in columns],
        headings_style=FontFace(emphasis="BOLD", fill_color=HEADER_FILL),
        line_height=5,
        borders_layout="HORIZONTAL_LINES",
    ) as table:
        table.row([c[0] for c in columns])
        for line in inv.lines:
            table.row([c[3](line) for c in columns])
    pdf.ln(4)


def _line_name(line: Line) -> str:
    return f"{line.name} (przed korektą)" if line.before_correction else line.name


def _summary(pdf: FPDF, inv: Invoice) -> None:
    width = 100
    pdf.set_x(pdf.l_margin + pdf.epw - width)
    pdf.set_font(FONT, "", 8)
    with pdf.table(
        width=width,
        align="RIGHT",
        col_widths=(25, 25, 25, 25),
        text_align=("LEFT", "RIGHT", "RIGHT", "RIGHT"),
        headings_style=FontFace(emphasis="BOLD", fill_color=HEADER_FILL),
        line_height=5,
        borders_layout="HORIZONTAL_LINES",
    ) as table:
        table.row(("Stawka", "Netto", "VAT", "Brutto"))
        rows = [r for r in inv.vat_summary if r.net or r.vat] or inv.vat_summary
        for row in rows:
            gross = row.net + (row.vat or Decimal(0))
            table.row((row.label, _num(row.net), _num(row.vat), _num(gross)))
    pdf.ln(3)

    pdf.set_font(FONT, "B", 11)
    pdf.cell(
        0, 6, f"Razem: {_num(inv.total)} {inv.currency}", align="R", new_x="LMARGIN", new_y="NEXT"
    )
    pdf.set_font(FONT, "", 9)
    for reason, value in inv.charges:
        pdf.cell(
            0,
            5,
            f"{reason}: {_num(value)} {inv.currency}",
            align="R",
            new_x="LMARGIN",
            new_y="NEXT",
        )
    if inv.to_pay is not None and inv.to_pay != inv.total:
        pdf.set_font(FONT, "B", 11)
        pdf.cell(
            0,
            6,
            f"Do zapłaty: {_num(inv.to_pay)} {inv.currency}",
            align="R",
            new_x="LMARGIN",
            new_y="NEXT",
        )
    pdf.ln(4)


def _payment(pdf: FPDF, inv: Invoice) -> None:
    payment = inv.payment
    if payment is None:
        return
    rows = []
    if payment.form:
        rows.append(f"Forma płatności: {payment.form}")
    if payment.paid:
        paid = "Zapłacono"
        if payment.paid_date:
            paid += f" {payment.paid_date:%d.%m.%Y}"
        rows.append(paid)
    for due in payment.due_dates:
        rows.append(f"Termin płatności: {due:%d.%m.%Y}")
    for account, bank in payment.bank_accounts:
        rows.append(f"Rachunek: {bank_account(account)}" + (f" ({bank})" if bank else ""))
    if not rows:
        return
    _section_title(pdf, "Płatność")
    pdf.set_font(FONT, "", 9)
    for row in rows:
        pdf.multi_cell(0, 5, row, new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.ln(3)


def _notes(pdf: FPDF, inv: Invoice) -> None:
    if not inv.notes:
        return
    _section_title(pdf, "Uwagi")
    pdf.set_font(FONT, "", 8)
    for key, value in inv.notes:
        pdf.multi_cell(0, 4.5, f"{key}: {value}", new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.ln(3)


def _footer(pdf: FPDF, inv: Invoice) -> None:
    pdf.set_font(FONT, "", 7)
    pdf.set_text_color(*GREY)
    if inv.registry:
        registry = ", ".join(f"{label}: {value}" for label, value in inv.registry)
        pdf.multi_cell(0, 4, registry, new_x="LMARGIN", new_y="NEXT", align="L")
    generated = f"{datetime.now():%d.%m.%Y %H:%M}"
    pdf.multi_cell(
        0,
        4,
        f"Wizualizacja faktury pobranej z KSeF (nr {inv.ksef_number}). Wygenerowano {generated}. "
        "Oryginałem faktury jest plik XML w KSeF.",
        new_x="LMARGIN",
        new_y="NEXT",
        align="L",
    )
    pdf.set_text_color(0)


def _section_title(pdf: FPDF, title: str) -> None:
    pdf.set_font(FONT, "B", 8)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 5, title.upper(), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)


def _num(value: Decimal | None, quantity: bool = False) -> str:
    if value is None:
        return ""
    if quantity:
        text = f"{value.normalize():f}"
        whole, _, frac = text.partition(".")
        return f"{int(whole):,}".replace(",", " ") + (f",{frac}" if frac else "")
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def _rate(rate: str) -> str:
    return f"{rate}%" if rate.isdigit() else rate
