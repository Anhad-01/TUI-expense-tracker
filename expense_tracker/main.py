from __future__ import annotations

import argparse
from pathlib import Path

from .categorize import categorize
from .db import DEFAULT_DB_PATH, ExpenseDB
from .models import Transaction
from .pdf_pipeline import extract_transactions_from_pdf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="expense-tracker")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    upload = sub.add_parser("upload-pdf", help="Extract and import a local statement PDF")
    upload.add_argument("pdf_path")
    upload.add_argument("--password", default=None)

    manual = sub.add_parser("add", help="Add one manual transaction")
    manual.add_argument("--date", required=True, help="dd/mm/yyyy")
    manual.add_argument("--transaction", required=True)
    manual.add_argument("--debit", type=float)
    manual.add_argument("--credit", type=float)
    manual.add_argument("--category", default=None)

    sub.add_parser("list", help="List transactions")

    export = sub.add_parser("export-csv", help="Export transactions to CSV")
    export.add_argument("output_path")

    sub.add_parser("tui", help="Open the terminal UI")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = ExpenseDB(args.db)
    try:
        try:
            if args.command == "upload-pdf":
                rows = extract_transactions_from_pdf(Path(args.pdf_path), password=args.password)
                inserted, skipped = db.insert_many(rows)
                print(f"Extracted {len(rows)} rows. Inserted {inserted}; skipped duplicates {skipped}.")
            elif args.command == "add":
                category = args.category or categorize(args.transaction)
                inserted = db.insert_transaction(
                    Transaction(
                        txn_date=args.date,
                        transaction=args.transaction,
                        debit=args.debit,
                        credit=args.credit,
                        category=category,
                        mode="cash",
                    )
                )
                print("Inserted manual transaction." if inserted else "Skipped duplicate transaction.")
            elif args.command == "list":
                for row in db.fetch_transactions():
                    print(
                        f"{row['txn_date']} | {row['transaction']} | "
                        f"D:{row['debit'] or ''} C:{row['credit'] or ''} | "
                        f"{row['category']} | {row['mode']}"
                    )
            elif args.command == "export-csv":
                print(f"Exported {db.export_csv(args.output_path)}")
            elif args.command == "tui":
                try:
                    from .tui import ExpenseTrackerApp
                except ImportError as exc:
                    raise RuntimeError(
                        "TUI requires textual. Install with: python3 -m pip install -r requirements.txt"
                    ) from exc
                ExpenseTrackerApp(args.db).run()
        except Exception as exc:
            print(f"Error: {exc}")
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(run())
