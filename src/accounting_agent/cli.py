import argparse
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from getpass import getpass
from pathlib import Path
from zoneinfo import ZoneInfo

from accounting_agent.config import Config, ConfigError, load_config
from accounting_agent.credentials import (
    CredentialsError,
    get_key_password,
    load_private_key,
    set_key_password,
)
from accounting_agent.invoice import parse_invoice
from accounting_agent.ksef import KsefClient, KsefError, Session
from accounting_agent.naming import invoice_filename, month_folder
from accounting_agent.pdf import render_invoice_pdf

TIMEZONE = ZoneInfo("Europe/Warsaw")


def cmd_set_password(args: argparse.Namespace) -> None:
    config = load_config()
    password = getpass(f"Hasło do klucza {config.key_path.name}: ")
    load_private_key(config.key_path, password)
    set_key_password(password)
    print("Hasło poprawne, zapisane w systemowym sejfie.")


def cmd_login(args: argparse.Namespace) -> None:
    config = load_config()
    with KsefClient(config.ksef_env) as client:
        session = _authenticate(client, config)
        print(f"Zalogowano do KSeF ({config.ksef_env}) w kontekście NIP {config.nip}.")
        print(f"Token dostępowy ważny do {session.access.valid_until.astimezone():%Y-%m-%d %H:%M}.")
        client.close_session(session)
        print("Sesja zamknięta.")


def cmd_download(args: argparse.Namespace) -> None:
    config = load_config()
    month = parse_month(args.month) if args.month else _ask_month()
    date_from, date_to = _month_range(month)
    folder_name = month_folder(date_from.year, date_from.month)
    folder = config.output_dir / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    print(f"Pobieram faktury zakupowe: {folder_name}")

    with KsefClient(config.ksef_env) as client:
        session = _authenticate(client, config)
        try:
            invoices = client.query_purchase_invoices(session, date_from, date_to)
            print(f"Faktur w KSeF: {len(invoices)}")
            saved = 0
            for meta in invoices:
                name = invoice_filename(
                    date.fromisoformat(meta["issueDate"]),
                    meta["invoiceNumber"],
                    meta["seller"].get("name") or "",
                    meta["invoiceType"],
                )
                path = folder / name
                if path.exists():
                    print(f"  pominięto (już jest): {path.name}")
                    continue
                xml = client.get_invoice_xml(session, meta["ksefNumber"])
                render_invoice_pdf(parse_invoice(xml, meta["ksefNumber"]), path)
                saved += 1
                print(f"  zapisano: {path.name}")
        finally:
            client.close_session(session)
    print(f"Zapisano {saved} nowych plików w {folder}")
    if args.open_folder:
        _open_folder(folder)


def _authenticate(client: KsefClient, config: Config) -> Session:
    key = load_private_key(config.key_path, get_key_password())
    return client.authenticate(config.nip, config.cert_path.read_text(), key)


def parse_month(text: str, today: date | None = None) -> str:
    """Miesiąc jako RRRR-MM z "RRRR-MM" albo samego numeru miesiąca ("1", "01", "10").

    Sam numer oznacza ostatnie wystąpienie tego miesiąca: bieżący lub wcześniejszy
    miesiąc w tym roku, późniejszy w poprzednim roku.
    """
    text = text.strip()
    if text.isdigit() and 1 <= int(text) <= 12:
        today = today or datetime.now(TIMEZONE).date()
        month = int(text)
        year = today.year if month <= today.month else today.year - 1
        return f"{year}-{month:02d}"
    try:
        return f"{datetime.strptime(text, '%Y-%m'):%Y-%m}"
    except ValueError as e:
        raise ConfigError(f"Nieznany miesiąc: {text}. Podaj numer 01–12 albo RRRR-MM.") from e


def _ask_month() -> str:
    while True:
        text = input("Z którego miesiąca pobrać faktury? Podaj numer (01–12): ")
        try:
            return parse_month(text)
        except ConfigError:
            print("To nie jest numer miesiąca. Wpisz liczbę od 01 do 12, np. 09 to wrzesień.")


def _open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.run(["open", str(path)], check=False)


def _month_range(month: str) -> tuple[datetime, datetime]:
    try:
        start = datetime.strptime(month, "%Y-%m").replace(tzinfo=TIMEZONE)
    except ValueError as e:
        raise ConfigError(f"Miesiąc w formacie RRRR-MM, np. 2026-08 (podano: {month})") from e
    next_month = start.replace(year=start.year + start.month // 12, month=start.month % 12 + 1)
    return start, next_month - timedelta(seconds=1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ksef", description="Faktury z KSeF")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "ustaw-haslo", help="zapisz hasło do klucza certyfikatu w systemowym sejfie"
    ).set_defaults(func=cmd_set_password)
    sub.add_parser("zaloguj", help="sprawdź logowanie do KSeF certyfikatem").set_defaults(
        func=cmd_login
    )
    download = sub.add_parser("pobierz", help="pobierz faktury zakupowe z miesiąca jako PDF")
    download.add_argument(
        "month",
        nargs="?",
        help="miesiąc wystawienia: numer (np. 08) albo RRRR-MM; bez podania program zapyta",
    )
    download.add_argument(
        "--otworz", dest="open_folder", action="store_true", help="otwórz folder po pobraniu"
    )
    download.set_defaults(func=cmd_download)

    args = parser.parse_args()
    try:
        args.func(args)
    except (ConfigError, CredentialsError, KsefError) as e:
        print(f"Błąd: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
