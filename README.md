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

Then open http://localhost:5000 — it redirects to the dashboard.

## Structure

```
app.py                 # Flask app, models, routes
seed_data.json          # One-time seed data extracted from the original xlsx
templates/
  base.html              # Layout / navbar
  dashboard.html          # Dashboard (KPIs + summary tables)
  ledger.html             # Per-unit ledger with add/edit/delete modals
  entry_fields.html       # Shared form fields for add/edit
instance/
  revfund.db              # SQLite database (created automatically on first run)
```

## Notes / next steps

- Amounts and dates are editable per entry through the ledger page (pencil
  icon to edit, trash icon to delete, "Add Entry" button to add new rows).
- `/export/<unit>.csv` downloads a CSV of that unit's ledger.
- `/api/expenses?unit=<unit>` returns JSON for all entries (optionally
  filtered by unit) if you want to wire up another frontend.
- If you want authentication/roles (e.g. only accounting staff can edit),
  or multi-year data entry beyond July 2026, let me know and I can add it.
