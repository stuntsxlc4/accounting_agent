import argparse
import sys
from getpass import getpass

from accounting_agent.config import ConfigError, load_config
from accounting_agent.credentials import (
    CredentialsError,
    get_key_password,
    load_private_key,
    set_key_password,
)
from accounting_agent.ksef import KsefClient, KsefError


def cmd_set_password() -> None:
    config = load_config()
    password = getpass(f"Hasło do klucza {config.key_path.name}: ")
    load_private_key(config.key_path, password)
    set_key_password(password)
    print("Hasło poprawne, zapisane w systemowym sejfie.")


def cmd_login() -> None:
    config = load_config()
    key = load_private_key(config.key_path, get_key_password())
    with KsefClient(config.ksef_env) as client:
        session = client.authenticate(config.nip, config.cert_path.read_text(), key)
        print(f"Zalogowano do KSeF ({config.ksef_env}) w kontekście NIP {config.nip}.")
        print(f"Token dostępowy ważny do {session.access.valid_until.astimezone():%Y-%m-%d %H:%M}.")
        client.close_session(session)
        print("Sesja zamknięta.")


COMMANDS = {
    "ustaw-haslo": (cmd_set_password, "zapisz hasło do klucza certyfikatu w systemowym sejfie"),
    "zaloguj": (cmd_login, "sprawdź logowanie do KSeF certyfikatem"),
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="ksef", description="Faktury z KSeF")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (_, help_text) in COMMANDS.items():
        sub.add_parser(name, help=help_text)
    args = parser.parse_args()

    try:
        COMMANDS[args.command][0]()
    except (ConfigError, CredentialsError, KsefError) as e:
        print(f"Błąd: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
