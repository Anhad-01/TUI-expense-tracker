from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path

from .categorize import categorize
from .models import ClosingBalance, Transaction


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
        "" if tx.debit is None else f"{tx.debit:.2f}",
        "" if tx.credit is None else f"{tx.credit:.2f}",
        tx.mode.strip(),
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
                debit REAL,
                credit REAL,
                category TEXT NOT NULL,
                mode TEXT NOT NULL,
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
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS closing_balances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                closing_balance REAL NOT NULL,
                statement_file TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(month, statement_file)
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_closing_balances_month ON closing_balances(month)"
        )
        self.conn.commit()

    def insert_transaction(self, tx: Transaction) -> bool:
        txn_date = parse_display_date(tx.txn_date)
        normalized = Transaction(
            txn_date=txn_date,
            transaction=tx.transaction.strip(),
            debit=amount_to_db(tx.debit),
            credit=amount_to_db(tx.credit),
            category=(tx.category or categorize(tx.transaction)).strip(),
            mode=(tx.mode or "cash").strip(),
            statement_file=(tx.statement_file or "").strip(),
            pdf_row_number=tx.pdf_row_number,
        )
        row_hash = make_row_hash(normalized)
        try:
            self.conn.execute(
                """
                INSERT INTO transactions (
                    txn_date, txn_date_sort, "transaction", debit, credit,
                    category, mode, statement_file, pdf_row_number, row_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized.txn_date,
                    date_sort_key(normalized.txn_date),
                    normalized.transaction,
                    normalized.debit,
                    normalized.credit,
                    normalized.category,
                    normalized.mode,
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

    def insert_closing_balance(self, balance: ClosingBalance) -> bool:
        try:
            self.conn.execute(
                """
                INSERT INTO closing_balances (month, closing_balance, statement_file)
                VALUES (?, ?, ?)
                ON CONFLICT(month, statement_file) DO UPDATE SET
                    closing_balance = excluded.closing_balance
                """,
                (balance.month, balance.closing_balance, balance.statement_file),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def insert_closing_balances(self, balances: list[ClosingBalance]) -> int:
        saved = 0
        for balance in balances:
            if self.insert_closing_balance(balance):
                saved += 1
        return saved

    def clear_transactions(self) -> int:
        cursor = self.conn.execute("DELETE FROM transactions")
        self.conn.execute("DELETE FROM closing_balances")
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
            clauses.append('"transaction" LIKE ?')
            needle = f"%{text}%"
            params.append(needle)
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

    def monthly_closing_balances(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT month, closing_balance
                FROM closing_balances
                ORDER BY month
                """
            )
        )

    def category_spend(self, month: str | None = None) -> list[sqlite3.Row]:
        where = "WHERE debit IS NOT NULL AND debit > 0"
        params: list[object] = []
        if month:
            where += " AND substr(txn_date_sort, 1, 7) = ?"
            params.append(month)
        return list(
            self.conn.execute(
                f"""
                SELECT category, SUM(debit) AS total
                FROM transactions
                {where}
                GROUP BY category
                ORDER BY total DESC
                """,
                params,
            )
        )

    def months_with_transactions(self) -> list[str]:
        return [
            row["month"]
            for row in self.conn.execute(
                """
                SELECT DISTINCT substr(txn_date_sort, 1, 7) AS month
                FROM transactions
                ORDER BY month DESC
                """
            )
        ]

    def costliest_transaction(self, month: str | None = None) -> sqlite3.Row | None:
        where = "WHERE debit IS NOT NULL"
        params: list[object] = []
        if month:
            where += " AND substr(txn_date_sort, 1, 7) = ?"
            params.append(month)
        return self.conn.execute(
            f"""
            SELECT *
            FROM transactions
            {where}
            ORDER BY debit DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

    def export_csv(self, output_path: Path | str) -> Path:
        path = Path(output_path)
        rows = self.fetch_transactions()
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "Txn Date",
                    "Transaction",
                    "Debit",
                    "Credit",
                    "Category",
                    "Mode",
                    "Statement File",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["txn_date"],
                        row["transaction"],
                        row["debit"] if row["debit"] is not None else "",
                        row["credit"] if row["credit"] is not None else "",
                        row["category"],
                        row["mode"],
                        row["statement_file"],
                    ]
                )
        return path
