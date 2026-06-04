from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Transaction:
    txn_date: str
    transaction: str
    withdrawals: float | None = None
    deposits: float | None = None
    balance: float | None = None
    other_information: str = ""
    category: str = "Uncategorized"
    source: str = "manual"
    statement_file: str = ""

