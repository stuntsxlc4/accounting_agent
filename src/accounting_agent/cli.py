import argparse
import sys
from datetime import date, datetime, timedelta
from getpass import getpass
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
from accounting_agent.naming import invoice_filename
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
    if config.output_dir is None:
        raise ConfigError("Brak OUTPUT_DIR w .env")
    config.output_dir.mkdir(parents=True, exist_ok=True)
    date_from, date_to = _month_range(args.month)

    with KsefClient(config.ksef_env) as client:
        session = _authenticate(client, config)
        try:
            invoices = client.query_purchase_invoices(session, date_from, date_to)
            print(f"Faktur zakupowych w {args.month}: {len(invoices)}")
            saved = 0
            for meta in invoices:
                name = invoice_filename(
                    date.fromisoformat(meta["issueDate"]),
                    meta["invoiceNumber"],
                    meta["seller"].get("name") or "",
                    meta["invoiceType"],
                )
                path = config.output_dir / name
                if path.exists():
                    print(f"  pominięto (już jest): {path.name}")
                    continue
                xml = client.get_invoice_xml(session, meta["ksefNumber"])
                render_invoice_pdf(parse_invoice(xml, meta["ksefNumber"]), path)
                saved += 1
                print(f"  zapisano: {path.name}")
        finally:
            client.close_session(session)
    print(f"Zapisano {saved} nowych plików w {config.output_dir}")


def _authenticate(client: KsefClient, config: Config) -> Session:
    key = load_private_key(config.key_path, get_key_password())
    return client.authenticate(config.nip, config.cert_path.read_text(), key)


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
    download.add_argument("month", metavar="RRRR-MM", help="miesiąc wystawienia, np. 2026-08")
    download.set_defaults(func=cmd_download)

    args = parser.parse_args()
    try:
        args.func(args)
    except (ConfigError, CredentialsError, KsefError) as e:
        print(f"Błąd: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
