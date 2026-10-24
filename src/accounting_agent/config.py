import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

KSEF_ENVS = ("test", "demo", "prod")
NIP_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)

# Ten Komputer > Obrazy > AAA Ludna 2 > AAA L2 Księgowość > Faktury ZAKUPOWE > <Miesiąc RRRR>
INVOICE_FOLDERS = ("AAA Ludna 2", "AAA L2 Księgowość", "Faktury ZAKUPOWE")
# Wyciągi: Ten Komputer > Obrazy > AAA Ludna 2 > AAA L2 Księgowość > Wyciągi > <Miesiąc RRRR>
STATEMENT_FOLDERS = ("AAA Ludna 2", "AAA L2 Księgowość", "Wyciągi")
APP_NAME = "Faktury KSeF"
# Daty i miesiące liczone są według czasu polskiego, niezależnie od ustawień komputera.
TIMEZONE = ZoneInfo("Europe/Warsaw")
FOLDERID_PICTURES = uuid.UUID("33E28130-4E1E-4676-835A-98395C3BC3BB")
# Ustawienia z kreatora pierwszego uruchomienia, w danych aplikacji
SETTINGS_FILE = "ustawienia.json"
CERT_FILE = "certyfikat.crt"
KEY_FILE = "klucz.key"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    ksef_env: str
    nip: str
    cert_path: Path
    key_path: Path
    output_dir: Path
    statements_dir: Path


def load_config(env_file: Path | None = None) -> Config:
    """Ustawienia zapisane przez kreator w danych aplikacji.

    W trybie deweloperskim (uruchomienie z kodu, nie z paczki) pierwszeństwo ma plik .env
    w bieżącym folderze.
    """
    env_file = env_file or Path.cwd() / ".env"
    if env_file.is_file() and not getattr(sys, "frozen", False):
        return _from_env(env_file)
    return _from_settings()


def save_settings(nip: str, certificate_pem: bytes, key_pem: bytes) -> None:
    """Zapisuje ustawienia z kreatora: NIP i kopię plików certyfikatu."""
    folder = certificate_dir()
    folder.mkdir(parents=True, exist_ok=True)
    _write_atomic(folder / CERT_FILE, certificate_pem)
    _write_atomic(folder / KEY_FILE, key_pem)
    settings = {"ksef_env": "prod", "nip": normalize_nip(nip)}
    _write_atomic(app_data_dir() / SETTINGS_FILE, json.dumps(settings, indent=1).encode("utf-8"))


def normalize_nip(text: str) -> str:
    nip = text.replace("-", "").replace(" ", "").strip()
    if not _is_valid_nip(nip):
        raise ConfigError(f"Niepoprawny NIP: {text}")
    return nip


def certificate_dir() -> Path:
    return app_data_dir() / "certyfikat"


def app_data_dir() -> Path:
    """Dane aplikacji: Windows %LOCALAPPDATA%, macOS ~/Library/Application Support."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / "Library" / "Application Support"
    return base / APP_NAME


def pictures_dir() -> Path:
    """Folder Obrazy użytkownika (Windows: także gdy przeniesiony do OneDrive)."""
    if sys.platform == "win32":
        import ctypes

        guid = (ctypes.c_byte * 16).from_buffer_copy(FOLDERID_PICTURES.bytes_le)
        path = ctypes.c_wchar_p()
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(path)
        )
        try:
            if result == 0 and path.value:
                return Path(path.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(path)
    return Path.home() / "Pictures"


def _from_env(env_file: Path) -> Config:
    load_dotenv(env_file)
    base = env_file.parent
    return _config(
        _require("KSEF_ENV"),
        _require("KSEF_NIP"),
        _existing_file(base, "KSEF_CERT_PATH"),
        _existing_file(base, "KSEF_KEY_PATH"),
    )


def _from_settings() -> Config:
    path = app_data_dir() / SETTINGS_FILE
    if not path.is_file():
        raise ConfigError("Aplikacja nie jest jeszcze skonfigurowana")
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ConfigError(f"Nie można odczytać ustawień aplikacji: {path}") from e
    folder = certificate_dir()
    for name in (CERT_FILE, KEY_FILE):
        if not (folder / name).is_file():
            raise ConfigError("Brak plików certyfikatu KSeF. Wskaż je ponownie w Ustawieniach.")
    return _config(
        settings.get("ksef_env", "prod"),
        settings.get("nip", ""),
        folder / CERT_FILE,
        folder / KEY_FILE,
    )


def _config(ksef_env: str, nip: str, cert_path: Path, key_path: Path) -> Config:
    if ksef_env not in KSEF_ENVS:
        raise ConfigError(f"KSEF_ENV musi być jednym z: {', '.join(KSEF_ENVS)}")
    return Config(
        ksef_env=ksef_env,
        nip=normalize_nip(nip),
        cert_path=cert_path,
        key_path=key_path,
        output_dir=pictures_dir().joinpath(*INVOICE_FOLDERS),
        statements_dir=pictures_dir().joinpath(*STATEMENT_FOLDERS),
    )


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Brak wartości {name} w .env")
    return value


def _existing_file(base: Path, name: str) -> Path:
    path = base / _require(name)
    if not path.is_file():
        raise ConfigError(f"{name}: plik nie istnieje: {path}")
    return path


def _write_atomic(path: Path, content: bytes) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(content)
    os.replace(tmp, path)


def _is_valid_nip(nip: str) -> bool:
    if len(nip) != 10 or not nip.isdigit():
        return False
    checksum = sum(int(d) * w for d, w in zip(nip[:9], NIP_WEIGHTS, strict=True)) % 11
    return checksum == int(nip[9])
