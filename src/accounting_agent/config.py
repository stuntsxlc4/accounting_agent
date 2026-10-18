import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

KSEF_ENVS = ("test", "demo", "prod")
NIP_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)

# Ten Komputer > Obrazy > AAA Ludna 2 > AAA L2 Księgowość > Faktury ZAKUPOWE > <Miesiąc RRRR>
INVOICE_FOLDERS = ("AAA Ludna 2", "AAA L2 Księgowość", "Faktury ZAKUPOWE")
# Wyciągi: Ten Komputer > Obrazy > AAA Ludna 2 > AAA L2 Księgowość > Wyciągi > <Miesiąc RRRR>
STATEMENT_FOLDERS = ("AAA Ludna 2", "AAA L2 Księgowość", "Wyciągi")
APP_NAME = "Faktury KSeF"
FOLDERID_PICTURES = uuid.UUID("33E28130-4E1E-4676-835A-98395C3BC3BB")


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
    env_file = env_file or Path.cwd() / ".env"
    if not env_file.is_file():
        raise ConfigError(f"Brak pliku konfiguracji: {env_file}")
    load_dotenv(env_file)
    base = env_file.parent

    ksef_env = _require("KSEF_ENV")
    if ksef_env not in KSEF_ENVS:
        raise ConfigError(f"KSEF_ENV musi być jednym z: {', '.join(KSEF_ENVS)}")

    nip = _require("KSEF_NIP").replace("-", "").replace(" ", "")
    if not _is_valid_nip(nip):
        raise ConfigError(f"Niepoprawny NIP: {nip}")

    return Config(
        ksef_env=ksef_env,
        nip=nip,
        cert_path=_existing_file(base, "KSEF_CERT_PATH"),
        key_path=_existing_file(base, "KSEF_KEY_PATH"),
        output_dir=pictures_dir().joinpath(*INVOICE_FOLDERS),
        statements_dir=pictures_dir().joinpath(*STATEMENT_FOLDERS),
    )


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


def _is_valid_nip(nip: str) -> bool:
    if len(nip) != 10 or not nip.isdigit():
        return False
    checksum = sum(int(d) * w for d, w in zip(nip[:9], NIP_WEIGHTS, strict=True)) % 11
    return checksum == int(nip[9])
