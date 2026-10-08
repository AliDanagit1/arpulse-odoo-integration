import html
import logging
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import service
from .config import settings
from .odoo import Json2Client, MockClient, OdooError

app = FastAPI(title="ARPulse")
log = logging.getLogger("arpulse")
_client, _cache, _last = None, {}, {}
TEMPLATES = {
    "friendly": "Friendly reminder: invoice {n} ({amt} {cur}) was due on {due}. Please arrange payment.",
    "firm": "Invoice {n} ({amt} {cur}) is {days} days overdue (due {due}). Please pay immediately.",
    "final": "FINAL NOTICE: invoice {n} ({amt} {cur}) is {days} days overdue. Escalation follows if unpaid.",
}


def client():
    global _client
    if _client is None:
        if settings.mock_odoo:
            log.warning("ARPulse is running in MOCK mode; no Odoo calls will be made")
            _client = MockClient()
        elif not (settings.odoo_url and settings.odoo_api_key):
            raise OdooError(
                "ODOO_CONFIG",
                "Live mode requires ODOO_URL and ODOO_API_KEY",
                status=503,
            )
        else:
            _client = Json2Client(
                settings.odoo_url,
                settings.odoo_api_key,
                settings.odoo_db,
                settings.odoo_timeout,
            )
    return _client


def data(refresh=False):
    c = _cache.get("d")
    if refresh or not c or time.time() - c[0] > settings.cache_ttl:
        cl = client()
        invs = service.normalize(cl.open_invoices(),
                                 reporting_currency=settings.reporting_currency,
                                 usd_to_lbp_rate=settings.usd_to_lbp_rate)
        sales90 = service.sales_total(cl.sales_90d(), settings.reporting_currency,
                                      settings.usd_to_lbp_rate)
        c = _cache["d"] = (time.time(), invs, sales90)
    return c


@app.exception_handler(OdooError)
async def odoo_error(_, e: OdooError):
    return JSONResponse({"error": {"code": e.code, "message": str(e)}}, status_code=e.status)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/status")
def status():
    try:
        return client().status()
    except OdooError as e:
        return {"connected": False, "mode": "live", "error": {"code": e.code, "message": str(e)}}


@app.get("/api/dashboard")
def dashboard(refresh: bool = False):
    _, invs, s90 = data(refresh)
    return service.dashboard(invs, s90)


@app.get("/api/invoices")
def invoices(
    bucket: Literal["", "current", "1-30", "31-60", "61-90", "90+"] = "",
    risk: Literal["", "low", "medium", "high", "critical"] = "",
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
):
    items = [i for i in data()[1]
             if (not bucket or i["bucket"] == bucket) and (not risk or i["risk"] == risk)
             and (not q or q.lower() in (i["number"] + i["customer"]).lower())]
    items.sort(key=lambda i: (-(i["amount_reporting"] or 0), -i["days_overdue"]))
    s = (max(page, 1) - 1) * page_size
    return {"items": items[s:s + page_size], "total": len(items), "page": page, "page_size": page_size}


class Reminder(BaseModel):
    template: Literal["friendly", "firm", "final"] = "friendly"
    note: str = ""
    followup_days: int = 3


@app.post("/api/invoices/{inv_id}/reminder")
def reminder(inv_id: int, body: Reminder):
    inv = next((i for i in data()[1] if i["id"] == inv_id), None)
    if not inv:
        raise HTTPException(409, "Invoice is not open (or not found)")
    if len(body.note) > 500 or not 0 <= body.followup_days <= 30:
        raise HTTPException(422, "Note must be at most 500 characters and follow-up must be 0-30 days")
    if time.time() - _last.get(inv_id, 0) < 600:
        raise HTTPException(429, "A reminder was already sent for this invoice in the last 10 minutes")
    text = TEMPLATES[body.template].format(n=inv["number"], amt=f"{inv['amount']:,.2f}", cur=inv["currency"],
                                           due=inv["due"], days=inv["days_overdue"])
    html_body = f"<p>{html.escape(text)}</p>" + (f"<p>{html.escape(body.note)}</p>" if body.note else "")
    res = client().remind(inv_id, html_body, max(0, body.followup_days))
    log.info("Odoo follow-up created for invoice_id=%s", inv_id)
    _last[inv_id] = time.time()
    _cache.clear()
    return {"invoice_id": inv_id, "activity_scheduled": True, **res}


app.mount("/", StaticFiles(directory="frontend", html=True), name="ui")
