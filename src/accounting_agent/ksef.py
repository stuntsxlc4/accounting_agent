"""Klient API KSeF 2.0.

Dokumentacja: https://github.com/CIRFMF/ksef-docs
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from lxml import etree
from signxml import DigestAlgorithm, SignatureMethod
from signxml.xades import XAdESSigner

BASE_URLS = {
    "test": "https://api-test.ksef.mf.gov.pl/v2",
    "demo": "https://api-demo.ksef.mf.gov.pl/v2",
    "prod": "https://api.ksef.mf.gov.pl/v2",
}
AUTH_NS = "http://ksef.mf.gov.pl/auth/token/2.1"

AUTH_IN_PROGRESS = 100
AUTH_SUCCESS = 200
AUTH_POLL_INTERVAL = 1.0
AUTH_POLL_TIMEOUT = 120.0
PAGE_SIZE = 250

# Limity API: pobranie faktury 16/min i 64/h, lista faktur 16/min i 20/h.
# https://github.com/CIRFMF/ksef-docs/blob/main/limity/limity-api.md
INVOICE_DOWNLOAD_INTERVAL = 4.0
MAX_RETRY_AFTER = 120
MAX_RETRIES = 3


log = logging.getLogger(__name__)

# Komunikaty dla statusów uwierzytelnienia (GET /auth/{referenceNumber})
AUTH_FAILURES = {
    415: "Certyfikat nie ma w KSeF uprawnień do faktur tej firmy (NIP). "
    "Uprawnienia nadaje się w Aplikacji Podatnika KSeF.",
    425: "Sesja w KSeF została unieważniona. Spróbuj ponownie.",
    450: "KSeF odrzucił dane logowania.",
    460: "KSeF nie przyjął certyfikatu: jest nieważny, odwołany albo zawieszony.",
    470: "KSeF odmówił logowania tym certyfikatem.",
    480: "KSeF zablokował logowanie z powodu podejrzenia incydentu bezpieczeństwa. "
    "Skontaktuj się z Ministerstwem Finansów.",
    550: "KSeF przerwał logowanie z przyczyn technicznych. Spróbuj ponownie.",
}


class KsefError(Exception):
    """Błąd KSeF z komunikatem zrozumiałym dla użytkownika."""


class KsefRateLimitError(KsefError):
    def __init__(self, retry_at: datetime | None):
        self.retry_at = retry_at
        when = f" Spróbuj ponownie po {retry_at:%H:%M}." if retry_at else " Spróbuj później."
        super().__init__("KSeF chwilowo ogranicza liczbę zapytań (limit godzinowy)." + when)


@dataclass(frozen=True)
class Token:
    token: str
    valid_until: datetime


@dataclass(frozen=True)
class Session:
    access: Token


def build_auth_request(challenge: str, nip: str) -> etree._Element:
    root = etree.Element(f"{{{AUTH_NS}}}AuthTokenRequest", nsmap={None: AUTH_NS})
    etree.SubElement(root, f"{{{AUTH_NS}}}Challenge").text = challenge
    context = etree.SubElement(root, f"{{{AUTH_NS}}}ContextIdentifier")
    etree.SubElement(context, f"{{{AUTH_NS}}}Nip").text = nip
    etree.SubElement(root, f"{{{AUTH_NS}}}SubjectIdentifierType").text = "certificateSubject"
    return root


def sign_xades(document: etree._Element, cert_pem: str, key: PrivateKeyTypes) -> bytes:
    is_ec = isinstance(key, EllipticCurvePrivateKey)
    signer = XAdESSigner(
        signature_algorithm=SignatureMethod.ECDSA_SHA256 if is_ec else SignatureMethod.RSA_SHA256,
        digest_algorithm=DigestAlgorithm.SHA256,
    )
    signed = signer.sign(document, key=key, cert=cert_pem)
    return etree.tostring(signed, xml_declaration=True, encoding="utf-8")


class KsefClient:
    def __init__(self, env: str):
        self.env = env
        self._http = httpx.Client(
            base_url=BASE_URLS[env],
            headers={"X-Error-Format": "problem-details", "Accept": "application/json"},
            timeout=30.0,
        )
        self._last_invoice_download = 0.0

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> KsefClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def authenticate(self, nip: str, cert_pem: str, key: PrivateKeyTypes) -> Session:
        challenge = self._request("POST", "/auth/challenge")["challenge"]
        signed = sign_xades(build_auth_request(challenge, nip), cert_pem, key)

        init = self._request(
            "POST",
            "/auth/xades-signature",
            content=signed,
            headers={"Content-Type": "application/xml"},
        )
        reference = init["referenceNumber"]
        auth_token = init["authenticationToken"]["token"]

        self._wait_for_auth(reference, auth_token)

        tokens = self._request("POST", "/auth/token/redeem", token=auth_token)
        return Session(access=_token(tokens["accessToken"]))

    def close_session(self, session: Session) -> None:
        self._request("DELETE", "/auth/sessions/current", token=session.access.token)

    def query_purchase_invoices(
        self, session: Session, date_from: datetime, date_to: datetime
    ) -> list[dict]:
        """Metadane faktur, w których jesteśmy nabywcą, wystawionych w podanym okresie."""
        filters = {
            "subjectType": "Subject2",
            "dateRange": {
                "dateType": "Issue",
                "from": date_from.isoformat(),
                "to": date_to.isoformat(),
            },
        }
        invoices: list[dict] = []
        page_offset = 0
        while True:
            page = self._request(
                "POST",
                "/invoices/query/metadata",
                token=session.access.token,
                params={"pageOffset": page_offset, "pageSize": PAGE_SIZE, "sortOrder": "Asc"},
                json=filters,
            )
            invoices.extend(page["invoices"])
            if not page["hasMore"]:
                return invoices
            if page["isTruncated"]:
                raise KsefError("Ponad 10 000 faktur w okresie, zawęź zakres dat")
            page_offset += 1

    def get_invoice_xml(self, session: Session, ksef_number: str) -> bytes:
        wait = self._last_invoice_download + INVOICE_DOWNLOAD_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_invoice_download = time.monotonic()
        response = self._send(
            "GET",
            f"/invoices/ksef/{ksef_number}",
            token=session.access.token,
            headers={"Accept": "application/xml"},
        )
        return response.content

    def _wait_for_auth(self, reference: str, auth_token: str) -> None:
        deadline = time.monotonic() + AUTH_POLL_TIMEOUT
        while True:
            status = self._request("GET", f"/auth/{reference}", token=auth_token)["status"]
            if status["code"] == AUTH_SUCCESS:
                return
            if status["code"] != AUTH_IN_PROGRESS:
                details = "; ".join(status.get("details") or [])
                log.warning("Uwierzytelnianie KSeF nieudane: %s %s", status, details)
                message = AUTH_FAILURES.get(
                    status["code"], f"Logowanie do KSeF nie powiodło się ({status['description']})."
                )
                raise KsefError(f"{message} Szczegóły: {details}" if details else message)
            if time.monotonic() > deadline:
                raise KsefError("Uwierzytelnianie trwa zbyt długo, spróbuj ponownie później")
            time.sleep(AUTH_POLL_INTERVAL)

    def _request(self, method: str, path: str, **kwargs) -> dict:
        response = self._send(method, path, **kwargs)
        return response.json() if response.content else {}

    def _send(
        self, method: str, path: str, *, token: str | None = None, **kwargs
    ) -> httpx.Response:
        if token:
            kwargs.setdefault("headers", {})["Authorization"] = f"Bearer {token}"
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._http.request(method, path, **kwargs)
            except httpx.TimeoutException as e:
                log.warning("KSeF nie odpowiada: %s %s: %s", method, path, e)
                raise KsefError("KSeF nie odpowiada. Spróbuj ponownie za kilka minut.") from e
            except httpx.HTTPError as e:
                log.warning("Brak połączenia z KSeF: %s %s: %s", method, path, e)
                raise KsefError("Brak połączenia z KSeF. Sprawdź połączenie z internetem.") from e
            if response.status_code != 429 or attempt == MAX_RETRIES:
                break
            retry_after = int(response.headers.get("Retry-After", "1"))
            if retry_after > MAX_RETRY_AFTER:
                break
            log.info("Limit zapytań KSeF, czekam %s s", retry_after)
            time.sleep(retry_after)
        if response.is_error:
            log.warning(
                "KSeF %s %s -> %s: %s", method, path, response.status_code, response.text[:1000]
            )
            raise _error(response)
        return response


def _token(data: dict) -> Token:
    return Token(token=data["token"], valid_until=datetime.fromisoformat(data["validUntil"]))


def _error(response: httpx.Response) -> KsefError:
    code = response.status_code
    if code == 429:
        retry_after = response.headers.get("Retry-After", "")
        retry_at = (
            datetime.now() + timedelta(seconds=int(retry_after)) if retry_after.isdigit() else None
        )
        return KsefRateLimitError(retry_at)
    if code in (401, 403):
        return KsefError("KSeF odmówił dostępu. Sprawdź certyfikat i uprawnienia w KSeF.")
    if code >= 500:
        return KsefError(f"KSeF jest chwilowo niedostępny (błąd {code}). Spróbuj ponownie później.")
    detail = _detail(response)
    return KsefError(f"KSeF odrzucił zapytanie: {detail}" if detail else f"KSeF: błąd {code}.")


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    parts = [body.get("detail") or body.get("title")]
    for error in body.get("errors") or []:
        parts.append(error if isinstance(error, str) else str(error))
    return " ".join(p for p in parts if p)
