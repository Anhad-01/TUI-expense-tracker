from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path

from .categorize import categorize
from .models import Transaction


DEFAULT_DB_PATH = Path("expense_tracker.sqlite3")


def parse_display_date(value: str) -> str:
    parts = value.strip().replace("-", "/").split("/")
    if len(parts) != 3:
        raise ValueError("date must be dd/mm/yyyy")
    day, month, year = (part.zfill(2) for part in parts)
    if len(year) != 4:
        raise ValueError("date year must be yyyy")
    return f"{day}/{month}/{year}"


def date_sort_key(value: str) -> str:
    day, month, year = parse_display_date(value).split("/")
    return f"{year}-{month}-{day}"


def amount_to_db(value: float | str | None) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    return float(value)


def make_row_hash(tx: Transaction) -> str:
    parts = [
        parse_display_date(tx.txn_date),
        tx.transaction.strip(),
        "" if tx.withdrawals is None else f"{tx.withdrawals:.2f}",
        "" if tx.deposits is None else f"{tx.deposits:.2f}",
        "" if tx.balance is None else f"{tx.balance:.2f}",
        tx.other_information.strip(),
        tx.source.strip(),
        tx.statement_file.strip(),
        str(tx.pdf_row_number),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class ExpenseDB:
    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                txn_date TEXT NOT NULL,
                txn_date_sort TEXT NOT NULL,
                "transaction" TEXT NOT NULL,
                withdrawals REAL,
                deposits REAL,
                balance REAL,
                other_information TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL,
                source TEXT NOT NULL,
                statement_file TEXT NOT NULL DEFAULT '',
                pdf_row_number INTEGER NOT NULL DEFAULT 0,
                row_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_sort ON transactions(txn_date_sort DESC, id DESC)"
        )
        self.conn.commit()

    def insert_transaction(self, tx: Transaction) -> bool:
        txn_date = parse_display_date(tx.txn_date)
        normalized = Transaction(
            txn_date=txn_date,
            transaction=tx.transaction.strip(),
            withdrawals=amount_to_db(tx.withdrawals),
            deposits=amount_to_db(tx.deposits),
            balance=amount_to_db(tx.balance),
            other_information=(tx.other_information or "").strip(),
            category=(tx.category or categorize(tx.transaction)).strip(),
            source=(tx.source or "manual").strip(),
            statement_file=(tx.statement_file or "").strip(),
            pdf_row_number=tx.pdf_row_number,
        )
        row_hash = make_row_hash(normalized)
        try:
            self.conn.execute(
                """
                INSERT INTO transactions (
                    txn_date, txn_date_sort, "transaction", withdrawals, deposits, balance,
                    other_information, category, source, statement_file, pdf_row_number, row_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized.txn_date,
                    date_sort_key(normalized.txn_date),
                    normalized.transaction,
                    normalized.withdrawals,
                    normalized.deposits,
                    normalized.balance,
                    normalized.other_information,
                    normalized.category,
                    normalized.source,
                    normalized.statement_file,
                    normalized.pdf_row_number,
                    row_hash,
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def insert_many(self, transactions: list[Transaction]) -> tuple[int, int]:
        inserted = 0
        skipped = 0
        for tx in transactions:
            if self.insert_transaction(tx):
                inserted += 1
            else:
                skipped += 1
        return inserted, skipped

    def clear_transactions(self) -> int:
        cursor = self.conn.execute("DELETE FROM transactions")
        self.conn.commit()
        return cursor.rowcount

    def fetch_transactions(
        self,
        category: str | None = None,
        text: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[object] = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if text:
            clauses.append('("transaction" LIKE ? OR other_information LIKE ?)')
            needle = f"%{text}%"
            params.extend([needle, needle])
        if start_date:
            clauses.append("txn_date_sort >= ?")
            params.append(date_sort_key(start_date))
        if end_date:
            clauses.append("txn_date_sort <= ?")
            params.append(date_sort_key(end_date))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return list(
            self.conn.execute(
                f"""
                SELECT * FROM transactions
                {where}
                ORDER BY txn_date_sort DESC, id DESC
                """,
                params,
            )
        )

    def categories(self) -> list[str]:
        return [
            row["category"]
            for row in self.conn.execute(
                "SELECT DISTINCT category FROM transactions ORDER BY category"
            )
        ]

    def run_sql(self, query: str) -> tuple[list[str], list[sqlite3.Row], int]:
        cursor = self.conn.execute(query)
        if cursor.description:
            columns = [column[0] for column in cursor.description]
            return columns, list(cursor.fetchall()), cursor.rowcount
        self.conn.commit()
        return [], [], cursor.rowcount

    def export_csv(self, output_path: Path | str) -> Path:
        path = Path(output_path)
        rows = self.fetch_transactions()
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "Txn Date",
                    "Transaction",
                    "Withdrawals",
                    "Deposits",
                    "Balance",
                    "Other Information",
                    "Category",
                    "Source",
                    "Statement File",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["txn_date"],
                    row["transaction"],
                        row["withdrawals"] if row["withdrawals"] is not None else "",
                        row["deposits"] if row["deposits"] is not None else "",
                        row["balance"] if row["balance"] is not None else "",
                        row["other_information"],
                        row["category"],
                        row["source"],
                        row["statement_file"],
                    ]
                )
        return path
