from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Transaction:
    txn_date: str
    transaction: str
    debit: float | None = None
    credit: float | None = None
    category: str = "Uncategorized"
    mode: str = "cash"
    statement_file: str = ""
    pdf_row_number: int = 0


@dataclass(frozen=True)
class ClosingBalance:
    month: str
    closing_balance: float
    statement_file: str = ""
