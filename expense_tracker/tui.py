from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from .categorize import categorize
from .db import ExpenseDB
from .models import Transaction
from .pdf_pipeline import extract_statement_from_pdf


class ExpenseTrackerApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    .top {
        height: 10;
    }
    .panel {
        border: round $accent;
        padding: 0 1;
    }
    #digital_panel {
        width: 24%;
    }
    #cash_panel {
        width: 38%;
    }
    #filter_panel {
        width: 38%;
    }
    .toolbar {
        height: 3;
        padding: 0 1;
    }
    .buttons {
        height: 3;
        padding: 0 1;
        content-align: center middle;
    }
    .sqlbar {
        height: 3;
        padding: 0 1;
    }
    .bottom {
        height: 1fr;
    }
    #table_panel {
        width: 58%;
        border: round $accent;
        padding: 0 1;
    }
    #analysis_panel {
        width: 42%;
        border: round $accent;
        padding: 0 1;
        overflow-y: auto;
    }
    Input {
        width: auto;
        min-width: 8;
    }
    Button {
        width: auto;
        min-width: 10;
    }
    #sql_query {
        width: 1fr;
    }
    #status {
        height: 1;
        padding: 0 1;
    }
    DataTable {
        height: 1fr;
    }
    #analysis {
        height: auto;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("e", "export", "Export CSV"),
        ("c", "clear_filters", "Clear Filters"),
        ("q", "quit", "Quit"),
    ]
    MAX_TRANSACTION_DISPLAY_LENGTH = 25

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self.db = ExpenseDB(db_path)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal(classes="top"):
                with Vertical(classes="panel", id="digital_panel"):
                    yield Static("Add digital transactions")
                    with Horizontal(classes="toolbar"):
                        yield Input(placeholder="PDF path", id="pdf_path")
                    with Horizontal(classes="toolbar"):
                        yield Input(placeholder="password", password=True, id="pdf_password")
                        yield Button("Import PDF", id="import_pdf")
                with Vertical(classes="panel", id="cash_panel"):
                    yield Static("Add Cash Transactions")
                    with Horizontal(classes="toolbar"):
                        yield Input(placeholder="Date", id="manual_date")
                        yield Input(placeholder="Transaction", id="manual_transaction")
                    with Horizontal(classes="toolbar"):
                        yield Input(placeholder="Debit", id="manual_debit")
                        yield Input(placeholder="Credit", id="manual_credit")
                        yield Button("Add transaction", id="add_manual")
                with Vertical(classes="panel", id="filter_panel"):
                    yield Static("Filter Search")
                    with Horizontal(classes="toolbar"):
                        yield Input(placeholder="Category", id="filter_category")
                        yield Input(placeholder="From", id="filter_start")
                        yield Input(placeholder="To", id="filter_end")
                    with Horizontal(classes="toolbar"):
                        yield Input(placeholder="Search text", id="filter_text")
                        yield Button("Filter", id="apply_filter")
            with Horizontal(classes="sqlbar"):
                yield Input(
                    placeholder='SQL query, e.g. SELECT * FROM transactions WHERE category = "Food"',
                    id="sql_query",
                )
                yield Button("Run SQL", id="run_sql")
                yield Button("Clear DB", id="clear_db")
            yield Static("", id="status")
            with Horizontal(classes="bottom"):
                with Vertical(id="table_panel"):
                    yield Static("Transaction database")
                    yield DataTable(id="transactions")
                with Vertical(id="analysis_panel"):
                    yield Static("Expenditure analysis")
                    yield Static("", id="analysis")
        yield Footer()

    def on_mount(self) -> None:
        self.show_transactions()

    def set_transaction_columns(self) -> None:
        table = self.query_one("#transactions", DataTable)
        table.clear(columns=True)
        table.add_columns("Date", "Transaction", "Debit", "Credit", "Category", "Mode")

    def show_transactions(self) -> None:
        self.set_transaction_columns()
        self.refresh_table()
        self.refresh_analysis()

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
                self.display_value(row["transaction"], self.MAX_TRANSACTION_DISPLAY_LENGTH),
                "" if row["debit"] is None else f"{row['debit']:.2f}",
                "" if row["credit"] is None else f"{row['credit']:.2f}",
                row["category"],
                row["mode"],
            )

    def refresh_analysis(self) -> None:
        self.query_one("#analysis", Static).update(self.build_analysis_text())

    def set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def input_value(self, selector_id: str) -> str | None:
        value = self.query_one(f"#{selector_id}", Input).value.strip()
        return value or None

    def action_refresh(self) -> None:
        self.show_transactions()
        self.set_status("Refreshed.")

    def action_clear_filters(self) -> None:
        for selector_id in (
            "filter_category",
            "filter_start",
            "filter_end",
            "filter_text",
        ):
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
            rows, balances = extract_statement_from_pdf(Path(pdf_path), password=password)
            inserted, skipped = self.db.insert_many(rows)
            self.db.insert_closing_balances(balances)
        except Exception as exc:
            self.set_status(f"Import failed: {exc}")
            return
        self.show_transactions()
        self.set_status(
            f"Rows {len(rows)}. Inserted {inserted}. Skipped {skipped}. Balances {len(balances)}."
        )

    def add_manual(self) -> None:
        date = self.query_one("#manual_date", Input).value.strip()
        transaction = self.query_one("#manual_transaction", Input).value.strip()
        debit = self.query_one("#manual_debit", Input).value.strip()
        credit = self.query_one("#manual_credit", Input).value.strip()
        if not date or not transaction:
            self.set_status("Manual entry needs date and transaction.")
            return
        try:
            inserted = self.db.insert_transaction(
                Transaction(
                    txn_date=date,
                    transaction=transaction,
                    debit=float(debit) if debit else None,
                    credit=float(credit) if credit else None,
                    category=categorize(transaction),
                    mode="manual",
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
            self.refresh_analysis()
            self.set_status(f"SQL returned {len(rows)} rows.")
        else:
            self.show_transactions()
            self.set_status(f"SQL changed {changed} rows.")

    def show_sql_results(self, columns: list[str], rows: list[object]) -> None:
        table = self.query_one("#transactions", DataTable)
        table.clear(columns=True)
        table.add_columns(*columns)
        for row in rows:
            table.add_row(
                *[
                    self.display_value(
                        row[column],
                        self.MAX_TRANSACTION_DISPLAY_LENGTH
                        if str(column).lower() == "transaction"
                        else None,
                    )
                    for column in columns
                ]
            )

    def display_value(self, value: object, max_length: int | None = None) -> str:
        if value is None:
            return ""
        text = str(value)
        if max_length is not None and len(text) > max_length:
            return f"{text[: max_length - 1]}…"
        return text

    def build_analysis_text(self) -> str:
        lines = [
            "Monthly closing balance",
            self.render_monthly_closing_balance(),
            "",
            "Category wise expenditure overall",
            self.render_category_spend(None),
            "",
            "Category wise expenditure by month",
            self.render_category_spend_by_month(),
            "",
            "Costliest expenditure by month",
            self.render_costliest_expenditure_by_month(),
        ]
        return "\n".join(lines)

    def render_monthly_closing_balance(self) -> str:
        rows = self.db.monthly_closing_balances()
        if not rows:
            return "No closing balance data."
        labels = [row["month"] for row in rows]
        values = [float(row["closing_balance"]) for row in rows]
        return self.render_value_bars(labels, values, max_abs=True)

    def render_category_spend(self, month: str | None) -> str:
        rows = self.db.category_spend(month)
        if not rows:
            return "No debit data."
        return self.render_category_rows(rows)

    def render_category_spend_by_month(self) -> str:
        months = self.db.months_with_transactions()
        if not months:
            return "No transaction months."
        sections = []
        for month in months:
            rows = self.db.category_spend(month)
            if not rows:
                continue
            sections.append(month)
            sections.append(self.render_category_rows(rows))
        return "\n\n".join(sections) if sections else "No debit data."

    def render_category_rows(self, rows: list[object]) -> str:
        labels = [row["category"] for row in rows]
        values = [float(row["total"]) for row in rows]
        total = sum(values) or 1
        bar_lines = self.render_value_bars(labels, values)
        legend = "\n".join(
            f"{'':>{16}} {row['total']:.2f} ({row['total'] / total:.1%})"
            for row in rows
        )
        return "\n".join([bar_lines, legend])

    def render_value_bars(
        self,
        labels: list[str],
        values: list[float],
        width: int = 24,
        max_abs: bool = False,
    ) -> str:
        if not values:
            return "No data."
        scale = max(abs(value) for value in values) if max_abs else max(values)
        if scale <= 0:
            return "No data."
        lines = []
        for label, value in zip(labels, values):
            filled = int(round(abs(value) / scale * width))
            bar = "█" * filled if value >= 0 else "░" * filled
            lines.append(f"{self.short_label(label):<16} {bar} {value:.2f}")
        return "\n".join(lines)

    def short_label(self, label: str, max_length: int = 16) -> str:
        return label if len(label) <= max_length else f"{label[: max_length - 1]}…"

    def render_costliest_expenditure_by_month(self) -> str:
        months = self.db.months_with_transactions()
        if not months:
            return "No transaction months."
        sections = []
        for month in months:
            row = self.db.costliest_transaction(month)
            if not row:
                continue
            sections.append(
                f"{month}\n{row['txn_date']} | {self.display_value(row['transaction'], self.MAX_TRANSACTION_DISPLAY_LENGTH)} | {row['category']} | {row['debit']:.2f}"
            )
        return "\n\n".join(sections) if sections else "No debit data."

    def on_unmount(self) -> None:
        self.db.close()
