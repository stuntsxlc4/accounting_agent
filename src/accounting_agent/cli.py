import argparse
import sys
from getpass import getpass

from accounting_agent.config import ConfigError, load_config
from accounting_agent.credentials import CredentialsError, load_private_key, set_key_password


def cmd_set_password() -> None:
    config = load_config()
    password = getpass(f"Hasło do klucza {config.key_path.name}: ")
    load_private_key(config.key_path, password)
    set_key_password(password)
    print("Hasło poprawne, zapisane w systemowym sejfie.")


COMMANDS = {
    "ustaw-haslo": (cmd_set_password, "zapisz hasło do klucza certyfikatu w systemowym sejfie"),
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="ksef", description="Faktury z KSeF")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (_, help_text) in COMMANDS.items():
        sub.add_parser(name, help=help_text)
    args = parser.parse_args()

    try:
        COMMANDS[args.command][0]()
    except (ConfigError, CredentialsError) as e:
        print(f"Błąd: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
