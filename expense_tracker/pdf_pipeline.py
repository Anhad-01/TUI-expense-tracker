from __future__ import annotations

import re
from pathlib import Path

from .categorize import categorize
from .db import parse_display_date
from .models import Transaction


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
    pdfplumber = _require_pdfplumber()
    source = Path(pdf_path)
    transactions: list[Transaction] = []
    row_number = 0
    with pdfplumber.open(source, password=password or "") as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                batch, row_number = _transactions_from_table(table, source.name, row_number)
                transactions.extend(batch)
    return transactions


def _transactions_from_table(
    table: list[list[object]], statement_file: str, start_row: int = 0
) -> tuple[list[Transaction], int]:
    rows: list[Transaction] = []
    row_number = start_row
    for raw_row in table:
        cells = [normalize_text(cell) for cell in raw_row if cell is not None][:6]
        if len(cells) < 6:
            continue
        txn_date = cells[0]
        transaction_raw = cells[1]
        if not DATE_RE.match(txn_date):
            continue
        transaction = simplify_transaction(transaction_raw)
        if not transaction or transaction.lower() in {"opening balance", "closing balance"}:
            continue
        row_number += 1
        rows.append(
            Transaction(
                txn_date=statement_date_to_display(txn_date),
                transaction=transaction,
                withdrawals=parse_amount(cells[2]),
                deposits=parse_amount(cells[3]),
                balance=parse_amount(cells[4]),
                other_information=cells[5],
                category=categorize(transaction),
                source="pdf",
                statement_file=statement_file,
                pdf_row_number=row_number,
            )
        )
    return rows, row_number




