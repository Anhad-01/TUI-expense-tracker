from __future__ import annotations

import re
from pathlib import Path

from .categorize import categorize
from .db import parse_display_date
from .models import ClosingBalance, Transaction


DATE_RE = re.compile(r"^\d{2}[-/]\d{2}[-/]\d{4}$")


def _require_pdfplumber() -> object:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "PDF import requires pdfplumber. Install with: "
            "python3 -m pip install -r requirements.txt"
        ) from exc
    return pdfplumber


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_amount(value: object) -> float | None:
    text = normalize_text(value).replace(",", "")
    if not text:
        return None
    return float(text)


def statement_date_to_display(value: str) -> str:
    return parse_display_date(value.replace("-", "/"))


def simplify_transaction(value: str) -> str:
    text = normalize_text(value)
    parts = [part.strip() for part in text.split("/")]
    if len(parts) >= 4 and parts[2] and parts[3]:
        return parts[3]
    return text


def extract_transactions_from_pdf(
    pdf_path: Path | str,
    password: str | None = None,
) -> list[Transaction]:
    transactions, _ = extract_statement_from_pdf(pdf_path, password=password)
    return transactions


def extract_statement_from_pdf(
    pdf_path: Path | str,
    password: str | None = None,
) -> tuple[list[Transaction], list[ClosingBalance]]:
    pdfplumber = _require_pdfplumber()
    source = Path(pdf_path)
    scanner = StatementScanner(source.name)
    with pdfplumber.open(source, password=password or "") as pdf:
        for page in pdf.pages[1:]:
            for table in page.extract_tables() or []:
                scanner.consume_table(table)
                if scanner.done:
                    return scanner.transactions, scanner.closing_balances
    return scanner.transactions, scanner.closing_balances


class StatementScanner:
    def __init__(self, statement_file: str) -> None:
        self.statement_file = statement_file
        self.in_statement_table = False
        self.done = False
        self.row_number = 0
        self.last_txn_date: str | None = None
        self.transactions: list[Transaction] = []
        self.closing_balances: list[ClosingBalance] = []

    def consume_table(self, table: list[list[object]]) -> None:
        for raw_row in table:
            cells = [normalize_text(cell) for cell in raw_row if cell is not None][:6]
            if len(cells) < 6:
                continue
            marker = cells[1].lower()
            if not self.in_statement_table:
                if "opening balance" in marker:
                    self.in_statement_table = True
                continue
            if "closing balance" in marker:
                self.add_closing_balance(cells)
                self.done = True
                return
            transaction = self.row_to_transaction(cells)
            if transaction:
                self.transactions.append(transaction)

    def row_to_transaction(self, cells: list[str]) -> Transaction | None:
        txn_date = cells[0]
        if not DATE_RE.match(txn_date):
            return None
        transaction = simplify_transaction(cells[1])
        if not transaction:
            return None
        self.row_number += 1
        self.last_txn_date = statement_date_to_display(txn_date)
        return Transaction(
            txn_date=self.last_txn_date,
            transaction=transaction,
            debit=parse_amount(cells[2]),
            credit=parse_amount(cells[3]),
            category=categorize(transaction),
            mode="UPI",
            statement_file=self.statement_file,
            pdf_row_number=self.row_number,
        )

    def add_closing_balance(self, cells: list[str]) -> None:
        if not self.last_txn_date:
            return
        balance = parse_amount(cells[4])
        if balance is None:
            return
        day, month, year = self.last_txn_date.split("/")
        self.closing_balances.append(
            ClosingBalance(
                month=f"{year}-{month}",
                closing_balance=balance,
                statement_file=self.statement_file,
            )
        )



