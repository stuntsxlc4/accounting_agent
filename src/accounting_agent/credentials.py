"""Hasło do klucza certyfikatu KSeF w systemowym sejfie.

macOS: Pęk kluczy, Windows: Menedżer poświadczeń.
"""

from pathlib import Path

import keyring
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from cryptography.hazmat.primitives.serialization import load_pem_private_key

KEYRING_SERVICE = "accounting-agent"
KEYRING_KEY_PASSWORD = "ksef-key-password"


class CredentialsError(Exception):
    pass


def get_key_password() -> str:
    password = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY_PASSWORD)
    if password is None:
        raise CredentialsError("Brak hasła do klucza w sejfie. Uruchom: uv run ksef ustaw-haslo")
    return password


def set_key_password(password: str) -> None:
    keyring.set_password(KEYRING_SERVICE, KEYRING_KEY_PASSWORD, password)


def load_private_key(key_path: Path, password: str) -> PrivateKeyTypes:
    try:
        return load_pem_private_key(key_path.read_bytes(), password.encode())
    except ValueError as e:
        raise CredentialsError(f"Nie udało się odczytać klucza {key_path.name}: złe hasło?") from e
