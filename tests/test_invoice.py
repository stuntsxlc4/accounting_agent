"""Odczyt faktury FA(3) i jej wizualizacja PDF, na wymyślonych danych."""

from datetime import date
from decimal import Decimal

import pdfplumber

from accounting_agent.invoice import parse_invoice
from accounting_agent.pdf import render_invoice_pdf

NS = "http://crd.gov.pl/wzor/2025/06/25/13775/"

INVOICE = f"""<?xml version="1.0" encoding="UTF-8"?>
<Faktura xmlns="{NS}">
  <Naglowek><KodFormularza kodSystemowy="FA (3)" wersjaSchemy="1-0E">FA</KodFormularza></Naglowek>
  <Podmiot1>
    <DaneIdentyfikacyjne><NIP>1111111111</NIP><Nazwa>Testowy Sprzedawca sp. z o.o.</Nazwa></DaneIdentyfikacyjne>
    <Adres><KodKraju>PL</KodKraju><AdresL1>ul. Testowa 1</AdresL1><AdresL2>00-001 Warszawa</AdresL2></Adres>
  </Podmiot1>
  <Podmiot2>
    <DaneIdentyfikacyjne><NIP>2222222222</NIP><Nazwa>Testowy Nabywca S.A.</Nazwa></DaneIdentyfikacyjne>
    <Adres><KodKraju>PL</KodKraju><AdresL1>ul. Kupiecka 2 00-002 Warszawa</AdresL1></Adres>
  </Podmiot2>
  <Podmiot3>
    <DaneIdentyfikacyjne><IDWew>1111111111-00001</IDWew><Nazwa>Oddział Testowy</Nazwa></DaneIdentyfikacyjne>
    <Adres><KodKraju>PL</KodKraju><AdresL1>ul. Boczna 3</AdresL1></Adres>
    <Rola>5</Rola>
  </Podmiot3>
  <Fa>
    <KodWaluty>PLN</KodWaluty>
    <P_1>2026-09-09</P_1>
    <P_1M>Warszawa</P_1M>
    <P_2>FV 1/09/2026</P_2>
    <OkresFa><P_6_Od>2026-08-09</P_6_Od><P_6_Do>2026-09-08</P_6_Do></OkresFa>
    <P_13_1>200.00</P_13_1><P_14_1>46.00</P_14_1>
    <P_13_2>0.00</P_13_2><P_14_2>0.00</P_14_2>
    <P_15>246.00</P_15>
    <RodzajFaktury>VAT</RodzajFaktury>
    <DodatkowyOpis><Klucz>Opis</Klucz><Wartosc>Faktura testowa</Wartosc></DodatkowyOpis>
    <FaWiersz>
      <NrWierszaFa>1</NrWierszaFa><P_7>Usługa testowa</P_7><P_8A>szt.</P_8A><P_8B>2</P_8B>
      <P_9A>100.00</P_9A><P_11>200.00</P_11><P_11A>246.00</P_11A><P_12>23</P_12>
    </FaWiersz>
    <Rozliczenie>
      <Obciazenia><Kwota>0.28</Kwota><Powod>Opłaty nieobjęte podatkiem VAT</Powod></Obciazenia>
      <DoZaplaty>246.28</DoZaplaty>
    </Rozliczenie>
    <Platnosc>
      <TerminPlatnosci><Termin>2026-09-23</Termin></TerminPlatnosci>
      <FormaPlatnosci>6</FormaPlatnosci>
      <RachunekBankowy><NrRB>PL89114012382444801084571141</NrRB><NazwaBanku>Bank Testowy</NazwaBanku></RachunekBankowy>
    </Platnosc>
  </Fa>
  <Stopka><Rejestry><KRS>0000000001</KRS><REGON>000000002</REGON></Rejestry></Stopka>
</Faktura>""".encode()

CORRECTION = f"""<?xml version="1.0" encoding="UTF-8"?>
<Faktura xmlns="{NS}">
  <Podmiot1><DaneIdentyfikacyjne><NIP>1111111111</NIP><Nazwa>Wspólnota Testowa</Nazwa></DaneIdentyfikacyjne></Podmiot1>
  <Podmiot2><DaneIdentyfikacyjne><NIP>2222222222</NIP><Nazwa>Nabywca</Nazwa></DaneIdentyfikacyjne></Podmiot2>
  <Fa>
    <KodWaluty>PLN</KodWaluty>
    <P_1>2026-08-17</P_1>
    <P_2>Faktura korekta 109/KOR/26-08</P_2>
    <P_6>2026-08-31</P_6>
    <P_13_7>-224.24</P_13_7>
    <P_15>-224.24</P_15>
    <RodzajFaktury>KOR</RodzajFaktury>
    <PrzyczynaKorekty>Korekta naliczenia</PrzyczynaKorekty>
    <DaneFaKorygowanej>
      <DataWystFaKorygowanej>2026-08-03</DataWystFaKorygowanej>
      <NrFaKorygowanej>Faktura 95/ZAL/26-08</NrFaKorygowanej>
    </DaneFaKorygowanej>
    <FaWiersz><NrWierszaFa>1</NrWierszaFa><P_7>Zaliczka</P_7><P_8A>m2</P_8A><P_8B>10</P_8B>
      <P_9A>22.42</P_9A><P_11>224.24</P_11><P_12>zw</P_12><StanPrzed>1</StanPrzed></FaWiersz>
    <Platnosc><Zaplacono>1</Zaplacono><DataZaplaty>2026-08-17</DataZaplaty><FormaPlatnosci>2</FormaPlatnosci></Platnosc>
  </Fa>
</Faktura>""".encode()


def test_parse_invoice():
    inv = parse_invoice(INVOICE, "KSEF-TEST-1")
    assert (inv.number, inv.issue_date, inv.issue_place) == (
        "FV 1/09/2026",
        date(2026, 9, 9),
        "Warszawa",
    )
    assert inv.kind_label == "Faktura VAT"
    assert inv.sale_date is None and inv.sale_period == (date(2026, 8, 9), date(2026, 9, 8))
    assert (inv.seller.name, inv.seller.nip) == ("Testowy Sprzedawca sp. z o.o.", "1111111111")
    assert inv.seller.address == ["ul. Testowa 1", "00-001 Warszawa"]
    assert inv.buyer.nip == "2222222222"
    assert inv.other_parties[0].role == "Wystawca faktury"
    line = inv.lines[0]
    assert (line.name, line.quantity, line.unit_net, line.gross, line.vat_rate) == (
        "Usługa testowa",
        Decimal("2"),
        Decimal("100.00"),
        Decimal("246.00"),
        "23",
    )
    assert [(v.label, v.net, v.vat) for v in inv.vat_summary] == [
        ("23% / 22%", Decimal("200.00"), Decimal("46.00")),
        ("8% / 7%", Decimal("0.00"), Decimal("0.00")),
    ]
    assert (inv.total, inv.to_pay) == (Decimal("246.00"), Decimal("246.28"))
    assert inv.charges == [("Opłaty nieobjęte podatkiem VAT", Decimal("0.28"))]
    assert inv.payment.form == "przelew" and not inv.payment.paid
    assert inv.payment.due_dates == [date(2026, 9, 23)]
    assert inv.payment.bank_accounts == [("PL89114012382444801084571141", "Bank Testowy")]
    assert inv.notes == [("Opis", "Faktura testowa")]
    assert inv.registry == [("KRS", "0000000001"), ("REGON", "000000002")]


def test_parse_correction():
    inv = parse_invoice(CORRECTION, "KSEF-TEST-2")
    assert inv.kind_label == "Faktura korygująca"
    assert inv.corrected == [("Faktura 95/ZAL/26-08", "2026-08-03")]
    assert inv.correction_reason == "Korekta naliczenia"
    assert inv.lines[0].before_correction and inv.lines[0].vat_rate == "zw"
    assert inv.payment.paid and inv.payment.form == "karta"
    assert inv.payment.paid_date == date(2026, 8, 17)


def test_render_invoice_pdf(tmp_path):
    path = tmp_path / "faktura.pdf"
    render_invoice_pdf(parse_invoice(INVOICE, "KSEF-TEST-1"), path)
    text = _pdf_text(path)
    for expected in [
        "Faktura VAT",
        "nr FV 1/09/2026",
        "Numer KSeF: KSEF-TEST-1",
        "Testowy Sprzedawca sp. z o.o.",
        "Oddział Testowy",
        "Usługa testowa",
        "Okres: 09.08.2026 – 08.09.2026",
        "Razem: 246,00 PLN",
        "Do zapłaty: 246,28 PLN",
        "PL89 1140 1238 2444 8010 8457 1141",
        "Termin płatności: 23.09.2026",
        "KRS: 0000000001",
    ]:
        assert expected in text, expected
    # zerowe stawki VAT nie są pokazywane w podsumowaniu
    assert "8% / 7%" not in text


def test_render_correction_pdf(tmp_path):
    path = tmp_path / "korekta.pdf"
    render_invoice_pdf(parse_invoice(CORRECTION, "KSEF-TEST-2"), path)
    text = _pdf_text(path)
    assert "Faktura korygująca" in text
    assert "Korygowana faktura: Faktura 95/ZAL/26-08 z 2026-08-03" in text
    assert "(przed korektą)" in text
    assert "Zapłacono 17.08.2026" in text


def _pdf_text(path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)
