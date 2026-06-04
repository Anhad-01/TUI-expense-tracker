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
            with Horizontal(classes="toolbar"):
                yield Input(placeholder="Date dd/mm/yyyy", id="manual_date")
                yield Input(placeholder="Transaction", id="manual_transaction")
                yield Input(placeholder="Withdrawal", id="manual_withdrawal")
                yield Input(placeholder="Deposit", id="manual_deposit")
                yield Button("Add", id="add_manual")
            yield Static("", id="status")
            yield DataTable(id="transactions")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#transactions", DataTable)
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
        self.refresh_table()

    def refresh_table(self) -> None:
        table = self.query_one("#transactions", DataTable)
        table.clear()
        for row in self.db.fetch_transactions():
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

    def action_refresh(self) -> None:
        self.refresh_table()
        self.set_status("Refreshed.")

    def action_export(self) -> None:
        path = self.db.export_csv("expense_tracker_export.csv")
        self.set_status(f"Exported {path}.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "import_pdf":
            self.import_pdf()
        elif event.button.id == "add_manual":
            self.add_manual()

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
        self.refresh_table()
        self.set_status(f"Extracted {len(rows)} rows. Inserted {inserted}; skipped {skipped}.")

    def add_manual(self) -> None:
        date = self.query_one("#manual_date", Input).value.strip()
        transaction = self.query_one("#manual_transaction", Input).value.strip()
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
                    category=categorize(transaction),
                    source="manual",
                )
            )
        except Exception as exc:
            self.set_status(f"Manual entry failed: {exc}")
            return
        self.refresh_table()
        self.set_status("Inserted manual transaction." if inserted else "Skipped duplicate.")

    def on_unmount(self) -> None:
        self.db.close()
