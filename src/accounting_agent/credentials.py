"""Hasło do klucza certyfikatu KSeF w systemowym sejfie.

macOS: Pęk kluczy, Windows: Menedżer poświadczeń.
"""

from datetime import UTC, datetime
from pathlib import Path

import keyring
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes, PublicKeyTypes
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_private_key,
)

KEYRING_SERVICE = "accounting-agent"
KEYRING_KEY_PASSWORD = "ksef-key-password"


class CredentialsError(Exception):
    pass


def get_key_password() -> str:
    password = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY_PASSWORD)
    if password is None:
        raise CredentialsError(
            "Brak zapisanego hasła do certyfikatu KSeF. Wpisz je ponownie w Ustawieniach."
        )
    return password


def set_key_password(password: str) -> None:
    keyring.set_password(KEYRING_SERVICE, KEYRING_KEY_PASSWORD, password)


def load_private_key(key_path: Path, password: str) -> PrivateKeyTypes:
    try:
        return load_pem_private_key(key_path.read_bytes(), password.encode())
    except ValueError as e:
        raise CredentialsError(f"Nie udało się odczytać klucza {key_path.name}: złe hasło?") from e


def verify_certificate(certificate: bytes, key: bytes, password: str) -> bytes:
    """Sprawdza pliki certyfikatu KSeF przed zapisaniem: ważność, hasło i parę klucz–certyfikat.

    Zwraca certyfikat w formacie PEM (KSeF wydaje go w PEM, ale przyjmujemy też DER).
    """
    try:
        cert = x509.load_pem_x509_certificate(certificate)
    except ValueError:
        try:
            cert = x509.load_der_x509_certificate(certificate)
        except ValueError as e:
            raise CredentialsError("Wybrany plik nie jest certyfikatem.") from e
    if cert.not_valid_after_utc < datetime.now(UTC):
        expired = cert.not_valid_after_utc.date().isoformat()
        raise CredentialsError(f"Certyfikat wygasł {expired}. Wygeneruj nowy w KSeF.")
    try:
        private_key = load_pem_private_key(key, password.encode())
    except (ValueError, TypeError) as e:
        raise CredentialsError(
            "Nie udało się odczytać klucza: złe hasło albo wybrany plik nie jest kluczem."
        ) from e
    if _public_bytes(private_key.public_key()) != _public_bytes(cert.public_key()):
        raise CredentialsError("Klucz nie pasuje do certyfikatu. Wybierz pliki z tej samej pary.")
    return cert.public_bytes(Encoding.PEM)


def _public_bytes(key: PublicKeyTypes) -> bytes:
    return key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
