"""Kreator pierwszego uruchomienia: certyfikat, zapis ustawień, jedna kopia aplikacji."""

import datetime as dt

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from accounting_agent import api, config, desktop
from accounting_agent.config import ConfigError, load_config
from accounting_agent.credentials import CredentialsError, verify_certificate

from .test_api import client

PASSWORD = "tajne-haslo"
NIP = "526-587-76-35"


def certificate_pair(days: int = 30, password: str = PASSWORD) -> tuple[bytes, bytes]:
    """Samopodpisany certyfikat EC z kluczem zaszyfrowanym hasłem, jak z KSeF."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Jan Testowy")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - dt.timedelta(days=60))
        .not_valid_after(now + dt.timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password.encode()),
    )
    return cert.public_bytes(serialization.Encoding.PEM), key_pem


def test_verify_certificate_accepts_pem_and_der():
    cert_pem, key_pem = certificate_pair()
    assert verify_certificate(cert_pem, key_pem, PASSWORD) == cert_pem
    der = x509.load_pem_x509_certificate(cert_pem).public_bytes(serialization.Encoding.DER)
    assert verify_certificate(der, key_pem, PASSWORD) == cert_pem


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("wrong_password", "złe hasło"),
        ("other_key", "nie pasuje"),
        ("expired", "wygasł"),
        ("not_certificate", "nie jest certyfikatem"),
    ],
)
def test_verify_certificate_rejects(case, message):
    cert_pem, key_pem = certificate_pair(days=-1 if case == "expired" else 30)
    password = "inne" if case == "wrong_password" else PASSWORD
    if case == "other_key":
        _, key_pem = certificate_pair()
    if case == "not_certificate":
        cert_pem = b"to nie certyfikat"
    with pytest.raises(CredentialsError, match=message):
        verify_certificate(cert_pem, key_pem, password)


@pytest.fixture
def saved_passwords(app_dirs, tmp_path, monkeypatch) -> list[str]:
    """Ustawienia czytane naprawdę z danych aplikacji (bez .env), hasła zamiast do sejfu
    trafiają na listę."""
    saved = []
    monkeypatch.setattr(api, "load_config", load_config)
    monkeypatch.setattr(api, "set_key_password", saved.append)
    monkeypatch.chdir(tmp_path)
    return saved


def setup(c, nip=NIP, password=PASSWORD, pair=None):
    cert_pem, key_pem = pair or certificate_pair()
    return c.post(
        "/api/setup",
        data={"nip": nip, "password": password},
        files={"certificate": ("cert.crt", cert_pem), "key": ("cert.key", key_pem)},
    )


def test_setup_saves_settings_used_by_the_app(saved_passwords):
    pair = certificate_pair()

    response = setup(client(), pair=pair)

    status = response.json()
    assert response.status_code == 200 and status["configured"]
    assert status["nip"] == "5265877635" and status["certificate"]["name"] == "Jan Testowy"
    assert saved_passwords == [PASSWORD]
    loaded = load_config()
    assert loaded.nip == "5265877635" and loaded.ksef_env == "prod"
    assert loaded.cert_path.read_bytes() == pair[0]
    assert loaded.key_path.read_bytes() == pair[1]


@pytest.mark.parametrize(
    ("nip", "password", "message"),
    [("1234567890", PASSWORD, "Niepoprawny NIP"), (NIP, "inne", "złe hasło")],
)
def test_setup_rejects_invalid_data_and_saves_nothing(saved_passwords, nip, password, message):
    response = setup(client(), nip=nip, password=password)

    assert response.status_code == 400 and message in response.json()["detail"]
    assert saved_passwords == []
    assert not client().get("/api/status").json()["configured"]
    with pytest.raises(ConfigError, match="nie jest jeszcze skonfigurowana"):
        load_config()


def test_missing_certificate_files_are_reported(saved_passwords):
    setup(client())
    (config.certificate_dir() / config.KEY_FILE).unlink()

    with pytest.raises(ConfigError, match="Brak plików certyfikatu"):
        load_config()


def test_only_one_copy_of_the_app_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "app_data_dir", lambda: tmp_path)
    first = desktop._single_instance()
    assert first is not None
    assert desktop._single_instance() is None
