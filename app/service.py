import datetime as dt

BUCKETS = [("current", "Current"), ("1-30", "1–30 days"), ("31-60", "31–60 days"),
           ("61-90", "61–90 days"), ("90+", "90+ days")]


def bucket_of(d):
    return "current" if d <= 0 else "1-30" if d <= 30 else "31-60" if d <= 60 else "61-90" if d <= 90 else "90+"


def risk_of(d):
    return "low" if d <= 0 else "medium" if d <= 30 else "high" if d <= 90 else "critical"


def convert_amount(amount, source_currency, reporting_currency="LBP", usd_to_lbp_rate=89500.0):
    source, target = (source_currency or "").upper(), reporting_currency.upper()
    if source == target:
        return round(amount, 2)
    if source == "USD" and target == "LBP":
        return round(amount * usd_to_lbp_rate, 2)
    if source == "LBP" and target == "USD":
        return round(amount / usd_to_lbp_rate, 2)
    return None


def sales_total(rows, reporting_currency="LBP", usd_to_lbp_rate=89500.0):
    total = 0
    for r in rows:
        c = r.get("currency_id")
        converted = convert_amount(r.get("amount_total", 0), c[1] if c else "",
                                   reporting_currency, usd_to_lbp_rate)
        if converted is not None:
            total += converted
    return round(total, 2)


def normalize(rows, today=None, reporting_currency="LBP", usd_to_lbp_rate=89500.0):
    today, out = today or dt.date.today(), []
    for r in rows:
        if not r.get("invoice_date_due"):
            continue
        d = (today - dt.date.fromisoformat(r["invoice_date_due"])).days
        p, c = r.get("partner_id"), r.get("currency_id")
        cc, company = r.get("company_currency_id"), r.get("company_id")
        currency = c[1] if c else ""
        reporting_amount = convert_amount(r["amount_residual"], currency,
                                          reporting_currency, usd_to_lbp_rate)
        out.append({"id": r["id"], "number": r["name"], "partner_id": p[0] if p else 0,
                    "customer": p[1] if p else "-", "issued": r["invoice_date"],
                    "due": r["invoice_date_due"], "days_overdue": max(0, d),
                    "amount": r["amount_residual"], "amount_company": r["amount_residual_signed"],
                    "currency": currency,
                    "amount_reporting": reporting_amount,
                    "reporting_currency": reporting_currency,
                    "usd_to_lbp_rate": usd_to_lbp_rate,
                    "company_currency": cc[1] if cc else (c[1] if c else ""),
                    "company_id": company[0] if company else 0,
                    "company": company[1] if company else "",
                    "bucket": bucket_of(d), "risk": risk_of(d)})
    return out


def dashboard(invs, sales90):
    companies = sorted({i["company"] for i in invs if i.get("company")})
    converted = [i for i in invs if i["amount_reporting"] is not None]
    total = sum(i["amount_reporting"] for i in converted)
    od = [i for i in invs if i["days_overdue"] > 0]
    converted_od = [i for i in od if i["amount_reporting"] is not None]
    over = sum(i["amount_reporting"] for i in converted_od)
    aging = [{"key": k, "label": l,
              "count": sum(1 for i in invs if i["bucket"] == k),
              "amount": round(sum(i["amount_reporting"] for i in converted
                                  if i["bucket"] == k), 2)}
             for k, l in BUCKETS]
    deb = {}
    for i in od:
        x = deb.setdefault(i["partner_id"], {"partner_id": i["partner_id"], "customer": i["customer"],
                                              "overdue": 0, "invoices": 0, "max_days": 0})
        if i["amount_reporting"] is not None:
            x["overdue"] = round(x["overdue"] + i["amount_reporting"], 2)
        x["invoices"] += 1
        x["max_days"] = max(x["max_days"], i["days_overdue"])
    for x in deb.values():
        x["risk"] = risk_of(x["max_days"])
    return {"total_receivable": round(total, 2), "total_overdue": round(over, 2),
            "overdue_pct": round(over / total * 100, 1) if total else 0,
            "dso": round(total / sales90 * 90, 1) if sales90 else None,
            "currency": invs[0]["reporting_currency"] if invs else "LBP",
            "usd_to_lbp_rate": invs[0]["usd_to_lbp_rate"] if invs else None,
            "mixed_currency": False,
            "unconverted_count": len(invs) - len(converted),
            "companies": companies,
            "open_count": len(invs), "overdue_count": len(od), "aging": aging,
            "top_debtors": sorted(deb.values(), key=lambda x: -x["overdue"])[:8]}
