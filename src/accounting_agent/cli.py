import argparse
import sys
from getpass import getpass
from pathlib import Path

from accounting_agent.config import ConfigError, load_config
from accounting_agent.credentials import CredentialsError, load_private_key, set_key_password
from accounting_agent.ksef import KsefClient, KsefError
from accounting_agent.matching import EXPECTS_INVOICE
from accounting_agent.services import (
    authenticate,
    download_invoices,
    open_path,
    parse_month,
    reconcile,
)


def cmd_set_password(args: argparse.Namespace) -> None:
    config = load_config()
    password = getpass(f"Hasło do klucza {config.key_path.name}: ")
    load_private_key(config.key_path, password)
    set_key_password(password)
    print("Hasło poprawne, zapisane w systemowym sejfie.")


def cmd_login(args: argparse.Namespace) -> None:
    config = load_config()
    with KsefClient(config.ksef_env) as client:
        session = authenticate(client, config)
        print(f"Zalogowano do KSeF ({config.ksef_env}) w kontekście NIP {config.nip}.")
        print(f"Token dostępowy ważny do {session.access.valid_until.astimezone():%Y-%m-%d %H:%M}.")
        client.close_session(session)
        print("Sesja zamknięta.")


def cmd_download(args: argparse.Namespace) -> None:
    config = load_config()
    month = parse_month(args.month) if args.month else _ask_month("pobrać faktury")
    result = download_invoices(config, month, _print_progress)
    print(f"Faktur w KSeF: {len(result.invoices)}, nowych plików: {result.saved}")
    print(f"Folder: {result.folder}")
    if args.open_folder:
        open_path(result.folder)


def cmd_reconcile(args: argparse.Namespace) -> None:
    config = load_config()
    month = parse_month(args.month) if args.month else _ask_month("porównać wyciągi")
    folder = Path(args.statements) if args.statements else None
    result = reconcile(config, month, folder, _print_progress)

    for message in result.unreadable:
        print(f"Nie odczytano: {message}")
    expecting = [d for d in result.debits if d.kind in EXPECTS_INVOICE]
    print(f"Odczytane wyciągi: {len(result.statements)} (salda zgodne)")
    print(f"Faktur zakupowych w KSeF z 12 miesięcy: {result.invoice_count}")
    print(f"Obciążeń: {len(result.debits)}, w tym przelewów i płatności kartą: {len(expecting)}")
    print(f"  z fakturą: {sum(1 for d in expecting if d.invoice)}")
    print(f"  BRAK FAKTURY: {sum(1 for d in expecting if not d.invoice)}")
    print(f"Faktury z miesiąca bez płatności na wyciągach: {len(result.unpaid)}")
    for status in sorted({u.status for u in result.unpaid}):
        print(f"  {status}: {sum(1 for u in result.unpaid if u.status == status)}")
    print(f"Zestawienie: {result.report}")
    if args.open_folder:
        open_path(result.folder)


def _print_progress(message: str, done: int | None = None, total: int | None = None) -> None:
    print(f"  [{done}/{total}] {message}" if total else f"  {message}")


def _ask_month(action: str) -> str:
    while True:
        text = input(f"Z którego miesiąca {action}? Podaj numer (01–12): ")
        try:
            return parse_month(text)
        except ConfigError:
            print("To nie jest numer miesiąca. Wpisz liczbę od 01 do 12, np. 09 to wrzesień.")


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

    reconcile_cmd = sub.add_parser(
        "porownaj", help="porównaj faktury z wyciągami bankowymi (Excel)"
    )
    reconcile_cmd.add_argument(
        "month", nargs="?", help="miesiąc wyciągów: numer (np. 08) albo RRRR-MM"
    )
    reconcile_cmd.add_argument(
        "--wyciagi",
        dest="statements",
        help="folder z wyciągami PDF (domyślnie Obrazy › … › Wyciągi)",
    )
    reconcile_cmd.add_argument(
        "--otworz", dest="open_folder", action="store_true", help="otwórz folder po porównaniu"
    )
    reconcile_cmd.set_defaults(func=cmd_reconcile)

    args = parser.parse_args()
    try:
        args.func(args)
    except (ConfigError, CredentialsError, KsefError) as e:
        print(f"Błąd: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
