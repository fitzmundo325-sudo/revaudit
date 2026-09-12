# Revolving Fund Expense Tracker (Flask)

A Flask + SQLite web app converted from the "Revolving Expenses Database With
Dashboard" Google Sheet. It replicates the sheet's structure:

- **Dashboard** — key metrics, expenses-by-account-type per unit, and a
  month-by-month summary for the selected year (mirrors the "Expense
  Dashboard Summary" tab, auto-calculated from the ledgers).
- **9 unit ledgers** — Sir Q Expense, Management, Cluster1–Cluster6, and
  Internal Audit. Each is a full CRUD expense ledger (Payee, Branch,
  Transaction Date, Particulars, Ref#, Account Title, TIN, Address, Amount),
  matching the original per-unit sheets.
- Account titles: Transportation & Travel, Meal Allowance, Employees Housing
  Allowance, Water, Miscellaneous.

The database is seeded once from `seed_data.json` (194 transactions
extracted from the July 2026 data in the uploaded workbook, totalling
₱52,013.41 — matching the sheet's grand total).

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 — it redirects to the dashboard. Default login:
`Jenny` / `jenny_081226` (role: Auditor) · `Queben` / `qjdc.cfi` (General Manager) · `admin` / `admin123` (Admin — manages users at /admin/users)

## Structure

```
app.py                 # Entry point: from revfund import create_app
revfund/
  __init__.py          # App factory: config, .env, secrets, db, cache, login
                       # manager, maintenance mode, idle timeout, error handlers
  models.py            # User, Expense, AuditLog, SystemSecret, MaintenanceMode
  auth.py              # Blueprint: login / logout (role-based)
  views.py             # Blueprint: dashboard, unit ledgers, CRUD, import/export,
                       # audit log viewer
  api_handles.py       # Blueprint: /apis/expenses, /apis/units, /apis/accounts
  audit.py             # Tamper-evident hash-chained audit logging
seed_data.json          # One-time seed data extracted from the original xlsx
templates/
  base.html              # Layout / navbar (role-aware sidebar)
  login.html             # Sign-in page
  dashboard.html          # Dashboard (KPIs + summary tables)
  ledger.html             # Per-unit ledger with add/edit/delete modals
  entry_fields.html       # Shared form fields for add/edit
  audit_logs.html         # Admin: audit trail with tamper detection
  maintenance.html        # Maintenance-mode page
instance/
  revfund.db              # SQLite database (created automatically on first run)
```

## Foundation (ported from the CFI count system)

- Flask app-factory + blueprint package layout.
- `flask-login` auth with user roles (Admin, Viewer, ...). New users default to
  `Admin`; the `role` column is added to existing databases automatically.
- `.env` support: `REVFUND_SECRET_KEY` (falls back to a key persisted in the
  `system_secret` table) and `SESSION_IDLE_TIMEOUT_SECONDS` (default 15 min).
- Additive SQLite migrations (`_ensure_*_columns()` PRAGMA helpers) — existing
  data is never dropped.
- Tamper-evident audit log (SHA-256 hash chain) for logins, CRUD, imports and
  application errors; verified on the Audit Logs page.
- Maintenance mode, idle-session auto-logout, presence tracking, Flask-Caching.

## Notes / next steps

- Amounts and dates are editable per entry through the ledger page (pencil
  icon to edit, trash icon to delete, "Add Entry" button to add new rows).
- `/export/<unit>.csv` downloads a CSV of that unit's ledger.
- `/api/expenses?unit=<unit>` returns JSON for all entries (optionally
  filtered by unit) if you want to wire up another frontend.
- If you want authentication/roles (e.g. only accounting staff can edit),
  or multi-year data entry beyond July 2026, let me know and I can add it.
