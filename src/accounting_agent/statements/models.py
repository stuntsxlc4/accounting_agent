from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path


class StatementError(Exception):
    pass


@dataclass
class Transaction:
    booking_date: date
    amount: Decimal  # ujemna = obciążenie, dodatnia = uznanie
    lines: list[str] = field(default_factory=list)
    operation_date: date | None = None
    counterparty: str = ""
    balance_after: Decimal | None = None

    @property
    def is_debit(self) -> bool:
        return self.amount < 0

    @property
    def text(self) -> str:
        return " ".join(" ".join(self.lines).split())


@dataclass
class Statement:
    bank: str
    path: Path
    account: str = ""
    currency: str = "PLN"
    period_from: date | None = None
    period_to: date | None = None
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    transactions: list[Transaction] = field(default_factory=list)

    def validate(self) -> None:
        """Saldo początkowe + operacje = saldo końcowe, także po każdej operacji."""
        if self.opening_balance is None or self.closing_balance is None:
            raise StatementError(f"{self.path.name}: nie znaleziono sald wyciągu")
        balance = self.opening_balance
        for t in self.transactions:
            balance += t.amount
            if t.balance_after is not None and balance != t.balance_after:
                raise StatementError(
                    f"{self.path.name}: saldo po operacji z {t.booking_date} ({t.text[:60]}…) "
                    f"wynosi {t.balance_after}, a wyliczone {balance}"
                )
        if balance != self.closing_balance:
            raise StatementError(
                f"{self.path.name}: saldo końcowe {self.closing_balance}, wyliczone {balance}"
            )
