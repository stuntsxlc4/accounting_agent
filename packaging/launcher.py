"""Punkt startowy paczki PyInstaller (program okienkowy Faktury KSeF)."""

import os
import sys

# Program okienkowy nie ma konsoli: sys.stdout i sys.stderr są wtedy None, a część bibliotek
# zakłada, że istnieją. Komunikaty trafiają do dziennika zdarzeń aplikacji.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

if "--self-check" in sys.argv:
    from accounting_agent.selfcheck import run  # noqa: E402

    sys.exit(run())

from accounting_agent.desktop import main  # noqa: E402

main()
