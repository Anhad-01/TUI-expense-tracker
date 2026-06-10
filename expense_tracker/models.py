from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Transaction:
    txn_date: str
    transaction: str
    debit: float | None = None
    credit: float | None = None
    category: str = "Uncategorized"
    mode: str = "manual"
    statement_file: str = ""
    pdf_row_number: int = 0
