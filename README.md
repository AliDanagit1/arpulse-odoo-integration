# ARPulse — Simple Odoo Accounts Receivable Integration

ARPulse is a deliberately small finance integration for an interview demonstration.
It reads posted, unpaid customer invoices from Odoo 20 through the JSON-2 API,
maps them into an accounts-receivable aging view, and writes a collection note
plus a follow-up activity back to the selected Odoo invoice.

## The integration flow

1. FastAPI authenticates to Odoo using a bearer API key.
2. It reads `account.move` customer invoices with `search_read`.
3. The service maps Odoo fields into aging buckets and risk levels.
4. The browser displays receivables KPIs, DSO, aging, and top debtors using
   Odoo's actual company currency rather than a hardcoded currency.
5. **Log follow-up** calls `message_post` and `activity_schedule` on the invoice.

Mock mode has the same interface but never calls Odoo. The UI labels mock mode
clearly so it cannot be confused with a successful live connection.

## Windows PowerShell — run locally

```powershell
cd C:\path\to\arpulse
py --version
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>.

If PowerShell blocks activation, run this once in the same window:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## First run: safe mock demo

Keep this in `.env`:

```dotenv
MOCK_ODOO=true
ODOO_URL=https://aspireapplication.odoo.com
ODOO_DB=
ODOO_API_KEY=
CACHE_TTL=60
ODOO_TIMEOUT=15
REPORTING_CURRENCY=LBP
USD_TO_LBP_RATE=89500
```

Expected status badge: `Demo data · mock mode`.

## Live Odoo 20 mode

Create an API key in the Odoo user account, then change `.env`:

```dotenv
MOCK_ODOO=false
ODOO_URL=https://aspireapplication.odoo.com
ODOO_DB=
ODOO_API_KEY=put_the_odoo_api_key_here
CACHE_TTL=60
ODOO_TIMEOUT=15
REPORTING_CURRENCY=LBP
USD_TO_LBP_RATE=89500
```

Restart Uvicorn. Never commit `.env`; it is excluded by `.gitignore` and
`.dockerignore`. A normal Odoo login password is not the JSON-2 bearer API key.

## Verify the application

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
Invoke-RestMethod http://127.0.0.1:8000/api/status
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard
pytest -q
```

Expected results:

- `/healthz`: `{ "status": "ok" }`
- mock `/api/status`: `connected=true`, `mode=mock`
- live `/api/status`: `connected=true`, `mode=json2`, and the Odoo user name
- bad/missing API key: a clear disconnected status; the app does not silently fake success
- `pytest`: all tests pass

For the live write test, choose a harmless test invoice and click **Log follow-up**
once. In Odoo, open that invoice and verify both the internal note in the chatter
and the scheduled To Do activity. This does not email the customer and does not
post, pay, cancel, or delete an accounting entry.

## What to say in the interview

> ARPulse is a small two-way Odoo finance integration. It authenticates through
> Odoo 20's JSON-2 API, reads posted open customer invoices, maps ERP records into
> receivables aging and DSO metrics, and writes a controlled follow-up note and
> activity back to the invoice. I kept mock mode explicit, secrets in environment
> variables, added timeouts and structured errors, validated inputs, escaped ERP
> text in the UI, and added a duplicate-click guard. The same design transfers to
> NetSuite: replace the Odoo adapter with NetSuite REST records while keeping the
> mapping, service, validation, UI, and monitoring boundaries.

## Honest limitations

- The ten-minute duplicate guard and cache are in memory; a multi-instance production
  deployment would use Redis or a database.
- DSO is a simplified demonstration calculation using open receivables and the last
  90 days of posted invoice sales.
- USD invoices are converted into the LBP reporting currency using
  \`USD_TO_LBP_RATE\`. Update this environment value when the approved business
  rate changes. The original invoice currency and amount remain visible.
- The follow-up action creates an internal Odoo note and activity; it does not send
  an email to a customer.
- This demo has no user login. Do not expose the live write endpoint publicly without
  authentication or private access controls.

## Docker

```powershell
docker build -t arpulse .
docker run --rm -p 8000:8000 --env-file .env arpulse
```

For the interview, prove the local live integration first. Deployment is secondary;
AWS App Runner is the simplest fit for this existing Dockerfile once access protection
is added.
