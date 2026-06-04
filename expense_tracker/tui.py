from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from .categorize import categorize
from .db import ExpenseDB
from .models import Transaction
from .pdf_pipeline import extract_transactions_from_pdf


class ExpenseTrackerApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    .toolbar {
        height: 3;
        padding: 0 1;
    }
    Input {
        width: 1fr;
    }
    Button {
        width: 14;
    }
    #status {
        height: 1;
        padding: 0 1;
    }
    DataTable {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("e", "export", "Export CSV"),
        ("c", "clear_filters", "Clear Filters"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self.db = ExpenseDB(db_path)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal(classes="toolbar"):
                yield Input(placeholder="PDF path", id="pdf_path")
                yield Input(placeholder="PDF password", password=True, id="pdf_password")
                yield Button("Import PDF", id="import_pdf")
                yield Button("Clear DB", id="clear_db")
            with Horizontal(classes="toolbar"):
                yield Input(placeholder="Date dd/mm/yyyy", id="manual_date")
                yield Input(placeholder="Transaction", id="manual_transaction")
                yield Input(placeholder="Category", id="manual_category")
                yield Input(placeholder="Withdrawal", id="manual_withdrawal")
                yield Input(placeholder="Deposit", id="manual_deposit")
                yield Button("Add", id="add_manual")
            with Horizontal(classes="toolbar"):
                yield Input(placeholder="Filter category", id="filter_category")
                yield Input(placeholder="From dd/mm/yyyy", id="filter_start")
                yield Input(placeholder="To dd/mm/yyyy", id="filter_end")
                yield Input(placeholder="Search text", id="filter_text")
                yield Button("Filter", id="apply_filter")
            with Horizontal(classes="toolbar"):
                yield Input(placeholder='SQL query, e.g. SELECT * FROM transactions WHERE category = "Food"', id="sql_query")
                yield Button("Run SQL", id="run_sql")
            yield Static("", id="status")
            yield DataTable(id="transactions")
        yield Footer()

    def on_mount(self) -> None:
        self.show_transactions()

    def set_transaction_columns(self) -> None:
        table = self.query_one("#transactions", DataTable)
        table.clear(columns=True)
        table.add_columns(
            "Date",
            "Transaction",
            "Withdrawal",
            "Deposit",
            "Balance",
            "Category",
            "Source",
            "Other",
        )

    def show_transactions(
        self,
        category: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        text: str | None = None,
    ) -> None:
        self.set_transaction_columns()
        self.refresh_table()

    def refresh_table(self) -> None:
        table = self.query_one("#transactions", DataTable)
        table.clear()
        for row in self.db.fetch_transactions(
            category=self.input_value("filter_category"),
            start_date=self.input_value("filter_start"),
            end_date=self.input_value("filter_end"),
            text=self.input_value("filter_text"),
        ):
            table.add_row(
                row["txn_date"],
                row["transaction"],
                "" if row["withdrawals"] is None else f"{row['withdrawals']:.2f}",
                "" if row["deposits"] is None else f"{row['deposits']:.2f}",
                "" if row["balance"] is None else f"{row['balance']:.2f}",
                row["category"],
                row["source"],
                row["other_information"],
            )

    def set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def input_value(self, selector_id: str) -> str | None:
        value = self.query_one(f"#{selector_id}", Input).value.strip()
        return value or None

    def action_refresh(self) -> None:
        self.show_transactions()
        self.set_status("Refreshed.")

    def action_clear_filters(self) -> None:
        for selector_id in ("filter_category", "filter_start", "filter_end", "filter_text"):
            self.query_one(f"#{selector_id}", Input).value = ""
        self.show_transactions()
        self.set_status("Filters cleared.")

    def action_export(self) -> None:
        path = self.db.export_csv("expense_tracker_export.csv")
        self.set_status(f"Exported {path}.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "import_pdf":
            self.import_pdf()
        elif event.button.id == "add_manual":
            self.add_manual()
        elif event.button.id == "clear_db":
            self.clear_db()
        elif event.button.id == "apply_filter":
            self.apply_filter()
        elif event.button.id == "run_sql":
            self.run_sql()

    def import_pdf(self) -> None:
        pdf_path = self.query_one("#pdf_path", Input).value.strip()
        password = self.query_one("#pdf_password", Input).value or None
        if not pdf_path:
            self.set_status("Enter a PDF path.")
            return
        try:
            rows = extract_transactions_from_pdf(Path(pdf_path), password=password)
            inserted, skipped = self.db.insert_many(rows)
        except Exception as exc:
            self.set_status(f"Import failed: {exc}")
            return
        self.show_transactions()
        self.set_status(f"Extracted {len(rows)} rows. Inserted {inserted}; skipped {skipped}.")

    def add_manual(self) -> None:
        date = self.query_one("#manual_date", Input).value.strip()
        transaction = self.query_one("#manual_transaction", Input).value.strip()
        manual_category = self.query_one("#manual_category", Input).value.strip()
        withdrawal = self.query_one("#manual_withdrawal", Input).value.strip()
        deposit = self.query_one("#manual_deposit", Input).value.strip()
        if not date or not transaction:
            self.set_status("Manual entry needs date and transaction.")
            return
        try:
            inserted = self.db.insert_transaction(
                Transaction(
                    txn_date=date,
                    transaction=transaction,
                    withdrawals=float(withdrawal) if withdrawal else None,
                    deposits=float(deposit) if deposit else None,
                    category=manual_category or categorize(transaction),
                    source="manual",
                )
            )
        except Exception as exc:
            self.set_status(f"Manual entry failed: {exc}")
            return
        self.show_transactions()
        self.set_status("Inserted manual transaction." if inserted else "Skipped duplicate.")

    def clear_db(self) -> None:
        deleted = self.db.clear_transactions()
        self.show_transactions()
        self.set_status(f"Hard deleted {deleted} rows.")

    def apply_filter(self) -> None:
        try:
            self.show_transactions()
        except Exception as exc:
            self.set_status(f"Filter failed: {exc}")
            return
        self.set_status("Filtered.")

    def run_sql(self) -> None:
        query = self.query_one("#sql_query", Input).value.strip()
        if not query:
            self.set_status("Enter SQL query.")
            return
        try:
            columns, rows, changed = self.db.run_sql(query)
        except Exception as exc:
            self.set_status(f"SQL failed: {exc}")
            return
        if columns:
            self.show_sql_results(columns, rows)
            self.set_status(f"SQL returned {len(rows)} rows.")
        else:
            self.show_transactions()
            self.set_status(f"SQL changed {changed} rows.")

    def show_sql_results(self, columns: list[str], rows: list[object]) -> None:
        table = self.query_one("#transactions", DataTable)
        table.clear(columns=True)
        table.add_columns(*columns)
        for row in rows:
            table.add_row(*["" if row[column] is None else str(row[column]) for column in columns])

    def on_unmount(self) -> None:
        self.db.close()
