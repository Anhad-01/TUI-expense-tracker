# Expense Tracker

An offline, terminal-based expense tracker that extracts transactions from password-protected bank statement PDFs, categorises them via regex, stores them in SQLite, and provides a TUI for viewing/analysis.

## Idea

Bank statements arrive as password-protected PDFs via email. This tool:

1. Opens the PDF (with optional password) using `pdfplumber`
2. Scans all tables across all pages, detecting opening/closing balance markers
3. Extracts date, description, debit, credit from each row
4. Simplifies UPI transaction strings (e.g. `UPI/P2M/.../Merchant Name/...` → `Merchant Name`)
5. Auto-categorises using keyword rules
6. Stores transactions and monthly closing balances in SQLite with SHA-256 hash deduplication
7. Exposes everything via a `textual` TUI and a CLI

All processing is offline. No telemetry, no network calls.

## Methodology

### Layered architecture

| Layer | File | Responsibility |
|---|---|---|
| Models | `models.py` | `Transaction` and `ClosingBalance` dataclasses |
| PDF extraction | `pdf_pipeline.py` | `pdfplumber` table parsing, `StatementScanner` state machine |
| Categorisation | `categorize.py` | Regex rules → category labels |
| Storage | `db.py` | SQLite schema, insert, dedup, filter, analysis queries, CSV export |
| CLI | `main.py` | `argparse` entry point with 5 subcommands |
| TUI | `tui.py` | `textual` dashboard with import, entry, filter, analysis panels |

### Data flow

```
PDF → pdfplumber → StatementScanner → Transaction/ClosingBalance → categorize()
                                                                      ↓
                                                                  ExpenseDB.insert_*()
                                                                      ↓
                                                                  SQLite (transactions, closing_balances)
                                                                      ↓
                                                            TUI DataTable / CLI list / CSV export
```

### Deduplication

Each transaction is hashed (SHA-256) on `txn_date|description|debit|credit|mode|statement_file|pdf_row_number`. The `row_hash` column has a `UNIQUE` constraint, so re-importing the same PDF silently skips duplicates. `pdf_row_number` prevents false duplicates when the same merchant sends the same amount twice on the same day.

## Progress

```
* cf01324 update database columns
* 2ab2198 fix: update hashing logic to prevent false duplicates
*   98d911d Merge branch 'no-prune' — update categories, remove pruning step
|\
| * dddae4f feat: remove pruning step to prevent data leakage
* | 116dbb6 update categories
|/
* 779b26a fix: extract entries from subsequent pages of statement
| * 34ed3ee feat: remove pdf pruning step
|/
* 368ff6f feat: add hard delete option, db filter, sql query option
* 580c911 first commit
```

### Milestones

- **`580c911`** — Project scaffold: models, db schema, pdf extraction, CLI, basic TUI
- **`368ff6f`** — Hard delete, category/date/text filters, SQL query runner, CSV export
- **`779b26a`** — Fixed extraction for multi-page statements: phantom `None` cells filtered out, first 6 real columns used
- **`dddae4f`** — Removed `pikepdf` pruning step; pipeline now reads original PDFs directly
- **`98d911d`** — Merged category updates and pruning removal
- **`2ab2198`** — Added `pdf_row_number` to hash to prevent false dedup collisions
- **`cf01324`** — Schema migration: `withdrawals/deposits/balance/other_information/source` → `debit/credit/mode`; added `closing_balances` table; renamed TUI columns; PDF imports set `mode='UPI'`

### What's implemented (✓) and what's planned (○)

| Feature | Status |
|---|---|
| PDF transaction extraction | ✓ |
| Regex categorisation (11 categories) | ✓ |
| SQLite storage with dedup | ✓ |
| Monthly closing balance tracking | ✓ |
| TUI with import, manual entry, filters, SQL runner | ✓ |
| CSV export | ✓ |
| Expenditure analysis (monthly balances, category spend, costliest tx) | ✓ |
| CLI (upload-pdf, add, list, export-csv, tui) | ✓ |
| IMAP email auto-download | ○ |
| systemd timer scheduling | ○ |
| `pikepdf` password decryption | ○ (removed — pdfplumber handles passwords natively) |

fix by kilo: updated TUI top panel row layout for digital PDF imports, cash manual entries, and filter search controls.
feat by kilo: added plotext-based unicode bar graphs for monthly closing balance, overall category spend, and monthly category spend in the analysis panel.
fix by kilo: simplified analysis graphs to compact unicode horizontal bars and added category spend sections for all months plus overall spend.
