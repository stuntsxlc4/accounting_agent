"""Samosprawdzenie zbudowanej paczki, bez otwierania okna.

Uruchamiane na GitHubie po zbudowaniu instalatora, żeby wykryć moduły i pliki danych,
których zabrakło w paczce: "Faktury KSeF.exe" --self-check (kod wyjścia 0 = paczka kompletna,
szczegóły w dzienniku zdarzeń). Z kodu: uv run python -m accounting_agent.selfcheck
"""

import datetime as dt
import io
import logging
import sys

import httpx
import keyring
import openpyxl
import pdfplumber
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fpdf import FPDF

from accounting_agent import storage
from accounting_agent.api import TOKEN_HEADER
from accounting_agent.desktop import start_server
from accounting_agent.ksef import build_auth_request, sign_xades
from accounting_agent.pdf import FONT_CANDIDATES

SAMPLE_TEXT = "Zażółć gęślą jaźń"

log = logging.getLogger(__name__)


def run() -> int:
    storage.setup_logging()
    try:
        version = _check_server()
        _check_keyring()
        _check_signature()
        _check_documents()
    except Exception:
        log.exception("Samosprawdzenie nie powiodło się")
        return 1
    log.info("Samosprawdzenie wersji %s zakończone poprawnie", version)
    return 0


def _check_server() -> str:
    """Serwer startuje, API odpowiada, a zbudowany interfejs jest w paczce."""
    token = "self-check"
    server, port = start_server(token)
    try:
        base = f"http://127.0.0.1:{port}"
        status = httpx.get(f"{base}/api/status", headers={TOKEN_HEADER: token}).raise_for_status()
        if 'id="root"' not in httpx.get(f"{base}/").raise_for_status().text:
            raise RuntimeError("Brak zbudowanego interfejsu w paczce")
        return status.json()["version"]
    finally:
        server.should_exit = True


def _check_keyring() -> None:
    if type(keyring.get_keyring()).__module__.startswith("keyring.backends.fail"):
        raise RuntimeError("Brak systemowego sejfu na hasło do certyfikatu")


def _check_signature() -> None:
    """Podpis XAdES jak przy logowaniu do KSeF, na jednorazowym certyfikacie."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "self-check")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    sign_xades(build_auth_request("self-check", "0000000000"), cert_pem, key)


def _check_documents() -> None:
    """PDF z polskimi znakami na czcionce systemu, jego odczyt i zapis pliku Excel."""
    regular, _ = FONT_CANDIDATES.get(sys.platform, FONT_CANDIDATES["win32"])
    pdf = FPDF()
    pdf.add_font("Sprawdzenie", "", regular)
    pdf.add_page()
    pdf.set_font("Sprawdzenie", size=12)
    pdf.cell(text=SAMPLE_TEXT)
    with pdfplumber.open(io.BytesIO(pdf.output())) as document:
        if SAMPLE_TEXT not in (document.pages[0].extract_text() or ""):
            raise RuntimeError("Nie udało się odczytać próbnego pliku PDF")
    openpyxl.Workbook().save(io.BytesIO())


if __name__ == "__main__":
    sys.exit(run())
