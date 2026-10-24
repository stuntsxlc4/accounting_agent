"""Klient KSeF wobec podstawionego serwera (bez połączenia z prawdziwym KSeF)."""

import datetime as dt
import json

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml.xades import XAdESVerifier

from accounting_agent import ksef
from accounting_agent.ksef import KsefClient, KsefError, KsefRateLimitError

TOKEN = {"token": "jwt", "validUntil": "2026-10-24T20:00:00+00:00"}


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(ksef, "AUTH_POLL_INTERVAL", 0)
    monkeypatch.setattr(ksef, "INVOICE_DOWNLOAD_INTERVAL", 0)
    monkeypatch.setattr(ksef.time, "sleep", lambda seconds: None)


@pytest.fixture(scope="module")
def certificate():
    """Samopodpisany certyfikat EC, jak certyfikat KSeF (tylko do testów)."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test")])
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
    return cert.public_bytes(serialization.Encoding.PEM).decode(), key


class FakeKsef:
    """Serwer KSeF: odpowiedzi przypisane do metody i ścieżki, z zapisem zapytań."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = f"{request.method} {request.url.path.removeprefix('/v2')}"
        handler = self.routes[key]
        if isinstance(handler, list):
            handler = handler.pop(0) if len(handler) > 1 else handler[0]
        return handler(request) if callable(handler) else handler

    def client(self) -> KsefClient:
        return KsefClient("test", transport=httpx.MockTransport(self))


def ok(body: dict | None = None, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body) if body is not None else httpx.Response(status)


def auth_routes(statuses: list[dict]) -> dict:
    return {
        "POST /auth/challenge": ok({"challenge": "20250604-CR-461EA5B000-537A6BA15D-D7"}),
        "POST /auth/xades-signature": ok(
            {"referenceNumber": "REF", "authenticationToken": {"token": "auth", "validUntil": "x"}},
            202,
        ),
        "GET /auth/REF": [ok({"status": s}) for s in statuses],
        "POST /auth/token/redeem": ok({"accessToken": TOKEN, "refreshToken": TOKEN}),
        "DELETE /auth/sessions/current": ok(status=204),
    }


def test_authentication_flow(certificate):
    cert, key = certificate
    server = FakeKsef(auth_routes([{"code": 100}, {"code": 200}]))
    with server.client() as client:
        session = client.authenticate("5265877635", cert, key)
        client.close_session(session)
    assert session.access.token == "jwt"
    paths = [f"{r.method} {r.url.path}" for r in server.requests]
    assert paths.count("GET /v2/auth/REF") == 2  # odpytywanie do skutku

    signed = next(r for r in server.requests if r.url.path.endswith("/xades-signature"))
    assert signed.headers["content-type"] == "application/xml"
    XAdESVerifier().verify(signed.content, x509_cert=cert, expect_references=3)
    document = etree.fromstring(signed.content)
    assert document.findtext(f"{{{ksef.AUTH_NS}}}ContextIdentifier/{{{ksef.AUTH_NS}}}Nip") == (
        "5265877635"
    )
    redeem = next(r for r in server.requests if r.url.path.endswith("/redeem"))
    assert redeem.headers["authorization"] == "Bearer auth"


def test_authentication_without_permissions(certificate):
    cert, key = certificate
    server = FakeKsef(
        auth_routes([{"code": 415, "description": "x", "details": ["Brak uprawnień"]}])
    )
    with server.client() as client, pytest.raises(KsefError, match="nie ma w KSeF uprawnień"):
        client.authenticate("5265877635", cert, key)


def test_rate_limit_with_long_wait_reports_retry_time():
    server = FakeKsef(
        {"POST /auth/challenge": httpx.Response(429, headers={"Retry-After": "1800"})}
    )
    with server.client() as client, pytest.raises(KsefRateLimitError) as error:
        client._request("POST", "/auth/challenge")
    assert error.value.retry_at is not None
    assert "Spróbuj ponownie po" in str(error.value)


def test_rate_limit_with_short_wait_is_retried():
    server = FakeKsef(
        {
            "POST /auth/challenge": [
                httpx.Response(429, headers={"Retry-After": "2"}),
                ok({"challenge": "C"}),
            ]
        }
    )
    with server.client() as client:
        assert client._request("POST", "/auth/challenge") == {"challenge": "C"}
    assert len(server.requests) == 2


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(503), "chwilowo niedostępny"),
        (httpx.Response(401), "odmówił dostępu"),
        (httpx.Response(400, json={"detail": "Niepoprawny zakres dat"}), "Niepoprawny zakres dat"),
    ],
)
def test_http_errors_have_readable_messages(response, message):
    server = FakeKsef({"POST /auth/challenge": response})
    with server.client() as client, pytest.raises(KsefError, match=message):
        client._request("POST", "/auth/challenge")


def test_no_connection():
    def offline(request):
        raise httpx.ConnectError("brak sieci")

    with KsefClient("test", transport=httpx.MockTransport(offline)) as client:
        with pytest.raises(KsefError, match="Brak połączenia z KSeF"):
            client._request("POST", "/auth/challenge")


def test_query_purchase_invoices_follows_pages():
    pages = [
        ok({"invoices": [{"ksefNumber": "A"}], "hasMore": True, "isTruncated": False}),
        ok({"invoices": [{"ksefNumber": "B"}], "hasMore": False, "isTruncated": False}),
    ]
    server = FakeKsef({"POST /invoices/query/metadata": pages})
    session = ksef.Session(access=ksef.Token("jwt", dt.datetime.now(dt.UTC)))
    start = dt.datetime(2026, 8, 1, tzinfo=dt.UTC)
    with server.client() as client:
        invoices = client.query_purchase_invoices(session, start, start + dt.timedelta(days=30))
    assert [i["ksefNumber"] for i in invoices] == ["A", "B"]
    first, second = server.requests
    assert json.loads(first.content)["subjectType"] == "Subject2"
    assert first.url.params["pageOffset"] == "0" and second.url.params["pageOffset"] == "1"


def test_query_stops_when_results_are_truncated():
    server = FakeKsef(
        {
            "POST /invoices/query/metadata": ok(
                {"invoices": [], "hasMore": True, "isTruncated": True}
            )
        }
    )
    session = ksef.Session(access=ksef.Token("jwt", dt.datetime.now(dt.UTC)))
    start = dt.datetime(2026, 8, 1, tzinfo=dt.UTC)
    with server.client() as client, pytest.raises(KsefError, match="10 000"):
        client.query_purchase_invoices(session, start, start)


def test_get_invoice_xml():
    server = FakeKsef({"GET /invoices/ksef/K-1": httpx.Response(200, content=b"<Faktura/>")})
    session = ksef.Session(access=ksef.Token("jwt", dt.datetime.now(dt.UTC)))
    with server.client() as client:
        assert client.get_invoice_xml(session, "K-1") == b"<Faktura/>"
    assert server.requests[0].headers["accept"] == "application/xml"
