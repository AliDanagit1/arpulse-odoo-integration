import datetime as dt
import random

import httpx


class OdooError(Exception):
    def __init__(self, code, msg, status=502):
        super().__init__(msg)
        self.code, self.status = code, status


FIELDS = ["id", "name", "partner_id", "invoice_date", "invoice_date_due",
          "amount_residual", "amount_residual_signed", "currency_id",
          "company_currency_id", "company_id"]
OPEN = [["move_type", "=", "out_invoice"], ["state", "=", "posted"],
        ["payment_state", "in", ["not_paid", "partial"]]]


class Json2Client:
    """Odoo JSON-2 API: POST /json/2/<model>/<method>, bearer API key, named args."""
    mode = "json2"

    def __init__(self, url, key, db="", timeout=15.0):
        self.url = url.rstrip("/")
        self.h = {"Authorization": f"bearer {key}", "Content-Type": "application/json"}
        self.timeout = timeout
        if db:
            self.h["X-Odoo-Database"] = db

    def call(self, model, method, **kw):
        try:
            r = httpx.post(
                f"{self.url}/json/2/{model}/{method}",
                json=kw,
                headers=self.h,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise OdooError("ODOO_UNAVAILABLE", f"Cannot reach Odoo: {e}")
        if r.status_code in (401, 403):
            raise OdooError("ODOO_AUTH", "Odoo rejected the API key / user rights")
        if r.status_code >= 400:
            try:
                detail = r.json().get("message", r.text[:300])
            except ValueError:
                detail = r.text[:300]
            raise OdooError("ODOO_REJECTED", detail)
        try:
            return r.json()
        except ValueError:
            raise OdooError("ODOO_INVALID_RESPONSE", "Odoo returned invalid JSON")

    def open_invoices(self):
        return self.call("account.move", "search_read", domain=OPEN, fields=FIELDS, limit=2000)

    def sales_90d(self):
        since = (dt.date.today() - dt.timedelta(days=90)).isoformat()
        return self.call("account.move", "search_read",
                         fields=["amount_total", "currency_id", "amount_total_signed",
                                 "company_currency_id"], limit=5000,
                         domain=[["move_type", "=", "out_invoice"], ["state", "=", "posted"],
                                 ["invoice_date", ">=", since]])

    def remind(self, inv_id, body, days):
        msg = self.call("account.move", "message_post", ids=[inv_id], body=body,
                        message_type="comment", subtype_xmlid="mail.mt_note")
        deadline = (dt.date.today() + dt.timedelta(days=days)).isoformat()
        self.call("account.move", "activity_schedule", ids=[inv_id],
                  act_type_xmlid="mail.mail_activity_data_todo",
                  summary="Follow up on payment", date_deadline=deadline)
        return {"message_id": msg, "deadline": deadline}

    def status(self):
        u = self.call("res.users", "search_read", domain=[], fields=["name"], limit=1)
        return {"connected": True, "mode": self.mode, "user": u[0]["name"] if u else None}


class MockClient:
    """Offline fake with the same interface, for demos and tests."""
    mode = "mock"

    def __init__(self):
        r, t = random.Random(7), dt.date.today()
        names = ["Apex Global Logistics", "Meridian Health", "Horizon Cloud", "Sterling & Hayes",
                 "Vanguard Tech", "Bluefin Dynamics", "CyberNetics", "Crestline Capital",
                 "Northwind Traders", "Cedar Foods", "Phoenicia Trading", "Levant Retail"]
        self.rows, self.notes = [], []
        for i in range(1, 41):
            p = r.randrange(12)
            due = t - dt.timedelta(days=r.choice([-25, -10, 5, 15, 40, 70, 95, 130]) + r.randint(-4, 4))
            amt = round(r.uniform(800, 25000), 2)
            self.rows.append({"id": i, "name": f"INV/2026/{i:04d}", "partner_id": [p + 1, names[p]],
                              "invoice_date": (due - dt.timedelta(days=30)).isoformat(),
                              "invoice_date_due": due.isoformat(), "amount_residual": amt,
                              "amount_residual_signed": amt, "currency_id": [1, "USD"]})

    def open_invoices(self):
        return list(self.rows)

    def sales_90d(self):
        return [{"amount_total": round(r["amount_residual"] * 1.4, 2),
                 "amount_total_signed": round(r["amount_residual"] * 1.4, 2),
                 "currency_id": r["currency_id"],
                 "company_currency_id": r["currency_id"]}
                for r in self.rows]

    def remind(self, inv_id, body, days):
        self.notes.append((inv_id, body))
        return {"message_id": len(self.notes),
                "deadline": (dt.date.today() + dt.timedelta(days=days)).isoformat()}

    def status(self):
        return {"connected": True, "mode": self.mode, "user": "Mock User"}
