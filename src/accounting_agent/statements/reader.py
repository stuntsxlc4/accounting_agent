from pathlib import Path

import pdfplumber

from accounting_agent.statements.alior import is_alior, parse_alior
from accounting_agent.statements.erste import is_erste, parse_erste
from accounting_agent.statements.models import Statement, StatementError
from accounting_agent.statements.unicredit import is_unicredit, parse_unicredit

PARSERS = [
    (is_alior, parse_alior),
    (is_erste, parse_erste),
    (is_unicredit, parse_unicredit),
]


class ScannedStatementError(StatementError):
    pass


def read_statement(path: Path) -> Statement:
    """Odczytuje wyciąg PDF i sprawdza zgodność sald."""
    with pdfplumber.open(path) as pdf:
        first_page = pdf.pages[0].extract_text() or ""
    if not first_page.strip():
        raise ScannedStatementError(f"{path.name}: skan bez tekstu, nie da się odczytać")
    for matches, parse in PARSERS:
        if matches(first_page):
            statement = parse(path)
            statement.validate()
            return statement
    raise StatementError(f"{path.name}: nieznany bank lub układ wyciągu")
