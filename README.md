# Expense Tracker

Manual-first offline expense tracker for bank statement PDFs and cash entries.

## Setup

```bash
python3 -m pip install -r requirements.txt
```

## Commands

```bash
python3 -m expense_tracker.main tui
python3 -m expense_tracker.main upload-pdf statements/feb2026.pdf --password '<pdf-password>'
python3 -m expense_tracker.main add --date 15/02/2026 --transaction Cash --withdrawals 100
python3 -m expense_tracker.main list
python3 -m expense_tracker.main export-csv expense_tracker_export.csv
```

Dates are stored and displayed as `dd/mm/yyyy`. Query order is newest date first,
then newest inserted row first for entries on the same date.

The TUI supports manual categories, filtered transaction views, hard database
clear, and direct SQL execution against the SQLite database.

PDF pruning writes derived files under `.pruned/` and reuses an existing pruned
copy. Files already named as pruned PDFs are not pruned again.
