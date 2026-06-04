# Expense Tracker Automation Pipeline - Architecture & Implementation Guide

## 1. Objective
Develop an automated, fully offline, and secure pipeline to extract expenditure data from monthly bank/credit card statements received via email. The system will process password-protected PDFs, extract specific tabular data, categorize transactions, and store them in a local SQLite database. A Terminal User Interface (TUI) will provide data visualization, manual entry capabilities, and file export for LibreOffice.

## 2. Core Requirements & Constraints
* **Zero Telemetry/Offline Processing:** After the initial IMAP download of the PDF, no external APIs or network calls are permitted. All processing (decryption, OCR/extraction, categorization) must occur locally.
* **Security:** Email credentials must use App Passwords stored in environment variables or system keyring. No hardcoded credentials. Passwords for PDFs should be managed securely.
* **Data Integrity:** The database must handle deduplication to prevent duplicate entries if the script is run multiple times.
* **Extensibility:** Support manual PDF uploads and manual row entries (for cash transactions).
* **Export:** Generate clean CSV or XLSX files on demand for LibreOffice compatibility.

## 3. Technology Stack
* **Language:** Python 3.x
* **Ingestion:** `imaplib` (Standard Library)
* **PDF Manipulation:** `pikepdf` (C++ qpdf wrapper for lossless decryption and page stripping)
* **Data Extraction:** `pdfplumber` (Offline tabular data extraction)
* **Database:** `sqlite3` (Standard Library)
* **Categorization:** `re` (Regex-based keyword filtering)
* **TUI Framework:** `textual`
* **OS/Scheduling:** Fedora Linux / `systemd` timers

## 4. Phase-by-Phase Implementation Plan

### Phase 1: Local PDF Processing Engine (Core Extraction)
**Objective:** Handle the decryption and extraction of tabular data from a local PDF.
**Tasks:**
1.  **Decryption & Pruning (`pikepdf`):**
    * Load a password-protected PDF.
    * Create a decrypted copy in memory or a secure temporary directory (`/tmp`).
    * Strip the first and last pages.
2.  **Table Extraction (`pdfplumber`):**
    * Open the pruned, decrypted PDF.
    * Identify the target table coordinates or rely on line parsing.
    * Extract rows into a structured format (e.g., list of dictionaries representing Date, Description, Amount, Reference Number).
3.  **Data Cleanup:** Write utility functions to strip whitespaces, format dates uniformly (ISO 8601), and cast numerical strings to floats.

### Phase 2: Database & Business Logic (Storage & Categorization)
**Objective:** Store extracted data reliably and apply automatic categorization.
**Tasks:**
1.  **Schema Design (`sqlite3`):**
    * Create a `transactions` table with columns: `id` (Primary Key), `date`, `description`, `amount`, `category`, `source` (Auto/Manual), `hash` (Unique identifier).
    * The `hash` column should be an MD5/SHA256 hash of Date + Description + Amount to enforce `UNIQUE` constraints and prevent duplicate inserts.
2.  **Categorization Engine:**
    * Create a dictionary mapping keywords/regex patterns to categories (e.g., `(?i).*AMAZON.*` -> `e-commerce`, `(?i).*ZOMATO.*` -> `food`).
    * Write a function that applies these rules to the description field before insertion.
3.  **Database Interface Class:** Implement methods for `insert_transaction`, `fetch_all`, `fetch_by_category`, and `export_to_csv`.

### Phase 3: Automated Ingestion Pipeline (Email Fetching)
**Objective:** Automatically retrieve the monthly statement.
**Tasks:**
1.  **IMAP Connection (`imaplib`):** Connect to `imap.gmail.com` using SSL.
2.  **Search & Fetch:** Search the inbox for `(UNSEEN FROM "sender@example.com" SUBJECT "Statement Subject")`.
3.  **Download:** Parse the email payload, extract the PDF attachment, and save it to a designated processing directory.
4.  **Flagging:** Mark the email as read (`\Seen`) to avoid reprocessing. Close the connection.
5.  **Integration:** Pass the downloaded file path to the Phase 1 Engine.

### Phase 4: Terminal User Interface (TUI) & Manual Operations
**Objective:** Provide a graphical interface within the terminal using `textual`.
**Tasks:**
1.  **Dashboard:** Build a main screen displaying a `DataTable` widget populated from the SQLite database.
2.  **Filters:** Add input fields or dropdowns to filter the table by category or date range.
3.  **Manual Entry Form:** Create a modal dialogue with input fields to manually add cash transactions.
4.  **Manual Upload Action:** Create a file picker or text input prompt to supply a local PDF path to the Phase 1 Engine, bypassing the IMAP module.
5.  **Export Action:** Add a keybind to trigger the CSV/XLSX export function for LibreOffice.

### Phase 5: System Integration & Scheduling
**Objective:** Automate execution on the Fedora host.
**Tasks:**
1.  **CLI Entry Points:** Use `argparse` or `click` to define execution modes: e.g., `python main.py --daemon` (runs IMAP + Processing) vs `python main.py --tui` (opens the interface).
2.  **Systemd Service:** Write a `~/.config/systemd/user/expense-tracker.service` file to execute the daemon command.
3.  **Systemd Timer:** Write a corresponding `.timer` file configured with `OnCalendar=*-*-05 10:00:00` (e.g., 5th of every month) and `Persistent=true`.

## 5. Directives for Coding Agents
* Implement strict error handling, particularly around missing IMAP attachments, incorrect PDF passwords, and database locking exceptions.
* Prioritize secure handling of intermediate files. Decrypted PDFs should not persist on disk after processing.
* Keep the architecture highly modular. The parsing logic must be completely decoupled from the IMAP fetching logic to ensure the manual upload feature works seamlessly.
