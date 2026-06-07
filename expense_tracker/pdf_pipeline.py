from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .categorize import categorize
from .db import parse_display_date
from .models import Transaction


DATE_RE = re.compile(r"^\d{2}[-/]\d{2}[-/]\d{4}$")


def _require_pdf_deps() -> tuple[object, object]:
    try:
        import pdfplumber
        import pikepdf
    except ImportError as exc:
        raise RuntimeError(
            "PDF import requires pikepdf and pdfplumber. Install with: "
            "python3 -m pip install -r requirements.txt"
        ) from exc
    return pikepdf, pdfplumber


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


def is_pruned_pdf(path: Path) -> bool:
    return path.stem.endswith(".pruned") or ".pruned." in path.name


def create_pruned_pdf(
    pdf_path: Path | str,
    password: str | None = None,
    output_dir: Path | str | None = None,
) -> Path:
    pikepdf, _ = _require_pdf_deps()
    source = Path(pdf_path)
    if is_pruned_pdf(source):
        return source
    if output_dir is None:
        output_dir = source.parent / ".pruned"
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.stem}.pruned.pdf"
    if target.exists():
        return target
    with pikepdf.open(source, password=password or "") as pdf:
        if len(pdf.pages) > 2:
            del pdf.pages[-1]
            del pdf.pages[0]
        pdf.save(target)
    return target


def extract_transactions_from_pdf(
    pdf_path: Path | str,
    password: str | None = None,
    prune: bool = True,
) -> list[Transaction]:
    _, pdfplumber = _require_pdf_deps()
    source = Path(pdf_path)
    statement_path = create_pruned_pdf(source, password=password) if prune else source
    transactions: list[Transaction] = []
    with pdfplumber.open(statement_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                transactions.extend(_transactions_from_table(table, source.name))
    return transactions


def _transactions_from_table(table: list[list[object]], statement_file: str) -> list[Transaction]:
    rows: list[Transaction] = []
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
            )
        )
    return rows


def extract_transactions_via_secure_temp(
    pdf_path: Path | str,
    password: str | None = None,
) -> list[Transaction]:
    with tempfile.TemporaryDirectory(prefix="expense-tracker-") as temp_dir:
        pruned = create_pruned_pdf(pdf_path, password=password, output_dir=temp_dir)
        return extract_transactions_from_pdf(pruned, password=None, prune=False)

