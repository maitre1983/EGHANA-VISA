"""Read-only aggregation of financial transactions across every existing
payment source. Never writes, never modifies balances, never duplicates.

Three sources merged into one normalized shape:
  1. applications.payment_status=="paid" → authoritative confirmed revenue
  2. hubtel_callbacks                    → raw Hubtel attempts (incl. failed)
  3. crypto_payments                     → raw NOWPayments attempts

Dedup strategy: when a callback shares its provider_reference with an
application already surfaced as "paid", the application wins (it's the
reconciled truth) and the callback is suppressed to avoid double-counting.
Orphan callbacks (no matching application) are surfaced with status
"unmatched" so admins see them but totals skip them.
"""
from __future__ import annotations

from typing import Any, Iterable
from datetime import datetime, timezone


# -------- Normalization helpers --------

def _iso_of(doc: dict, *candidates: str) -> str | None:
    for k in candidates:
        v = doc.get(k)
        if v:
            return v if isinstance(v, str) else v.isoformat()
    return None


def _normalize_app(a: dict) -> dict | None:
    """Confirmed payments live on the application doc itself."""
    if a.get("payment_status") != "paid":
        return None
    ref = a.get("payment_transaction_id") or a.get("tracking_no")
    method = (a.get("payment_method") or "").lower()
    # Infer provider from stored payment_method; conservative fallback.
    if "hubtel" in method:
        provider = "hubtel"
    elif "nowpayments" in method or "usdt" in method or "crypto" in method:
        provider = "nowpayments"
    elif "crypto" in (a.get("payment_type") or "").lower():
        provider = "nowpayments"
    else:
        # Legacy records without payment_method — infer from reference prefix.
        r = (ref or "").upper()
        if r.startswith("TX-"):
            provider = "hubtel"
        elif r.startswith("NP-"):
            provider = "nowpayments"
        else:
            provider = "unknown"
    return {
        "id": f"app:{a.get('tracking_no')}:{ref}",
        "source": "application",
        "date": _iso_of(a, "paid_at", "updated_at", "created_at"),
        "provider": provider,
        "provider_reference": ref,
        "tracking_no": a.get("tracking_no"),
        "customer_name": a.get("full_name"),
        "customer_email": a.get("email"),
        "amount": float(a.get("amount_usd") or 0),
        "currency": "USD",
        "network": None,
        "status": "paid",
        "audit_only": False,
        "payment_method_label": a.get("payment_method") or "",
    }


def _normalize_hubtel_cb(cb: dict) -> dict:
    """Hubtel server-to-server callback. Shape varies per Hubtel version —
    we read defensively from well-known keys."""
    payload = cb.get("payload") or cb.get("body") or {}
    data = payload.get("Data") or payload.get("data") or {}
    status_raw = (cb.get("status") or payload.get("Status") or data.get("Status") or "").lower()
    status = {
        "success": "paid", "paid": "paid",
        "failed": "failed", "cancelled": "failed", "declined": "failed",
        "expired": "expired",
        "pending": "pending",
    }.get(status_raw, status_raw or "pending")
    ref = (
        cb.get("provider_reference")
        or cb.get("transaction_id")
        or data.get("TransactionId")
        or data.get("ClientReference")
        or payload.get("ClientReference")
        or cb.get("id")
    )
    amount = data.get("Amount") or payload.get("Amount") or cb.get("amount")
    currency = data.get("Currency") or payload.get("Currency") or cb.get("currency") or "GHS"
    tracking = cb.get("tracking_no") or data.get("ClientReference") or payload.get("ClientReference")
    return {
        "id": f"hubtel:{ref}",
        "source": "hubtel_callback",
        "date": _iso_of(cb, "created_at", "received_at"),
        "provider": "hubtel",
        "provider_reference": ref,
        "tracking_no": tracking,
        "customer_name": cb.get("customer_name"),
        "customer_email": cb.get("customer_email"),
        "amount": float(amount or 0),
        "currency": currency,
        "network": None,
        "status": status,
        "payment_method_label": "Hubtel",
    }


def _normalize_crypto(p: dict) -> dict:
    status_raw = (p.get("payment_status") or p.get("status") or "").lower()
    status = {
        "finished": "paid", "confirmed": "paid",
        "failed": "failed", "expired": "expired", "refunded": "refunded",
        "waiting": "pending", "pending": "pending", "confirming": "pending",
        "sending": "pending", "partially_paid": "pending",
    }.get(status_raw, status_raw or "pending")
    return {
        "id": f"nowpayments:{p.get('invoice_id') or p.get('payment_id')}",
        "source": "crypto_payments",
        "date": _iso_of(p, "updated_at", "created_at"),
        "provider": "nowpayments",
        "provider_reference": p.get("invoice_id") or p.get("payment_id"),
        "tracking_no": p.get("tracking_no"),
        "customer_name": p.get("customer_name"),
        "customer_email": p.get("customer_email"),
        "amount": float(p.get("pay_amount") or p.get("amount") or 0),
        "currency": (p.get("pay_currency") or p.get("currency") or "USDT").upper(),
        "network": p.get("network") or p.get("pay_currency_network"),
        "status": status,
        "payment_method_label": f"NOWPayments ({(p.get('network') or '').upper() or 'crypto'})".strip(),
    }


# -------- Public API --------

async def list_transactions(
    db,
    *,
    provider: str = "",
    status: str = "",
    search: str = "",
    from_date: str = "",
    to_date: str = "",
) -> list[dict]:
    """Return every known transaction, de-duplicated and reconciled.

    Rules:
      - Confirmed payments on `applications` are the authoritative source.
      - Raw callbacks for the same provider_reference are suppressed.
      - Orphan callbacks (no matching application) are surfaced as
        status="unmatched" so nothing is ever hidden.
    """
    # 1. Confirmed payments from applications
    app_txs: list[dict] = []
    async for a in db.applications.find({"payment_status": "paid"}, {"_id": 0}):
        norm = _normalize_app(a)
        if norm:
            app_txs.append(norm)
    confirmed_refs = {t["provider_reference"] for t in app_txs if t.get("provider_reference")}
    known_trackings = {t["tracking_no"] for t in app_txs if t.get("tracking_no")}

    # 2. Hubtel callback trail (adds failed/expired/orphans + audit-only dupes)
    hubtel_txs: list[dict] = []
    async for cb in db.hubtel_callbacks.find({}, {"_id": 0}):
        n = _normalize_hubtel_cb(cb)
        is_duplicate = bool(n["provider_reference"]) and n["provider_reference"] in confirmed_refs
        if is_duplicate:
            # Preserve the callback so admins can still audit the raw event,
            # but mark it audit-only so it never contributes to revenue totals.
            n["audit_only"] = True
            n["status"] = "deduplicated"
        else:
            n["audit_only"] = False
            if not n.get("tracking_no") or n["tracking_no"] not in known_trackings:
                if n["status"] == "paid":
                    n["status"] = "unmatched"
        hubtel_txs.append(n)

    # 3. Crypto callback trail
    crypto_txs: list[dict] = []
    async for p in db.crypto_payments.find({}, {"_id": 0}):
        n = _normalize_crypto(p)
        is_duplicate = bool(n["provider_reference"]) and n["provider_reference"] in confirmed_refs
        if is_duplicate:
            n["audit_only"] = True
            n["status"] = "deduplicated"
        else:
            n["audit_only"] = False
            if not n.get("tracking_no") or n["tracking_no"] not in known_trackings:
                if n["status"] == "paid":
                    n["status"] = "unmatched"
        crypto_txs.append(n)

    merged = app_txs + hubtel_txs + crypto_txs

    # -------- Apply filters (in-memory — datasets are small) --------
    p = (provider or "").lower().strip()
    if p:
        merged = [t for t in merged if t["provider"] == p]
    st = (status or "").lower().strip()
    if st:
        merged = [t for t in merged if t["status"] == st]
    s = (search or "").lower().strip()
    if s:
        def _hit(t: dict) -> bool:
            for k in ("provider_reference", "tracking_no", "customer_name", "customer_email"):
                v = (t.get(k) or "")
                if s in str(v).lower():
                    return True
            return False
        merged = [t for t in merged if _hit(t)]
    if from_date:
        lo = f"{from_date.strip()}T00:00:00+00:00"
        merged = [t for t in merged if (t.get("date") or "") >= lo]
    if to_date:
        hi = f"{to_date.strip()}T23:59:59.999999+00:00"
        merged = [t for t in merged if (t.get("date") or "") <= hi]

    # Newest first, nulls last.
    merged.sort(key=lambda t: t.get("date") or "", reverse=True)
    return merged


def compute_summary(txs: Iterable[dict]) -> dict:
    """Totals broken down by (provider, currency) — never cross-currency sum.

    Only status==paid feeds the confirmed-revenue totals. All other statuses
    are reported as counts so admins can see them without inflating revenue.
    """
    by_bucket: dict[tuple[str, str], float] = {}
    counts: dict[str, int] = {"paid": 0, "pending": 0, "failed": 0, "expired": 0, "refunded": 0, "unmatched": 0, "deduplicated": 0}
    for t in txs:
        counts[t["status"]] = counts.get(t["status"], 0) + 1
        # Skip audit-only duplicates and any non-paid status for revenue.
        if t.get("audit_only") or t["status"] != "paid":
            continue
        key = (t["provider"], (t["currency"] or "USD").upper())
        by_bucket[key] = by_bucket.get(key, 0.0) + float(t.get("amount") or 0)
    return {
        "confirmed_revenue": [
            {"provider": prov, "currency": cur, "amount": round(amt, 2)}
            for (prov, cur), amt in sorted(by_bucket.items())
        ],
        "status_counts": counts,
        "total_transactions": sum(counts.values()),
    }


def _safe_cell(v: Any) -> Any:
    """CSV-injection / spreadsheet-formula protection.

    If the value is a string that starts with one of `= + - @ \t \r`,
    Excel / LibreOffice / Google Sheets will interpret it as a formula.
    Malicious user-supplied data could therefore exfiltrate information
    or trigger DDE. Prefix with a single quote to force text interpretation.
    Numeric / boolean / None values pass through unchanged so totals keep
    working in the generated spreadsheet."""
    if isinstance(v, str) and v and v[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def to_csv(txs: list[dict]) -> str:
    """CSV export. One column per normalized field, header-stable.
    Values are sanitised against CSV injection."""
    import csv, io
    buf = io.StringIO()
    fields = [
        "date", "provider", "provider_reference", "tracking_no",
        "customer_name", "customer_email", "amount", "currency",
        "network", "status", "audit_only", "payment_method_label", "source",
    ]
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for t in txs:
        w.writerow({k: _safe_cell(t.get(k, "")) for k in fields})
    return buf.getvalue()


def to_xlsx(txs: list[dict]) -> bytes:
    """Professional Excel (.xlsx) export.

    Produces a workbook with:
      • Sheet 1 "Transactions" — every normalized row with:
          - Styled header, frozen top row, autoFilter, auto column widths
          - Status-colour-coded status cells
          - `audit_only` flag preserved so auditors can see deduplicated callbacks
          - CSV-injection protection on every string cell
      • Sheet 2 "Summary" — confirmed revenue grouped by (provider, currency),
        with Excel SUMIFS formulas that excludes audit_only rows.
    Returns the raw .xlsx bytes."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    import io

    wb = Workbook()

    # ---------- Sheet 1: Transactions ----------
    ws = wb.active
    ws.title = "Transactions"
    headers = [
        ("Date", "date"),
        ("Client", "customer_name"),
        ("Email", "customer_email"),
        ("Tracking #", "tracking_no"),
        ("Amount", "amount"),
        ("Currency", "currency"),
        ("Provider", "provider"),
        ("Network", "network"),
        ("Reference", "provider_reference"),
        ("Status", "status"),
        ("Audit only", "audit_only"),
        ("Payment method", "payment_method_label"),
        ("Source", "source"),
    ]
    thin = Side(style="thin", color="E2E8F0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill("solid", fgColor="0E7D3B")  # Ghana green
    header_align = Alignment(horizontal="left", vertical="center", wrap_text=False)

    for col_idx, (label, _) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = border

    status_fills = {
        "paid":          PatternFill("solid", fgColor="0E7D3B"),
        "pending":       PatternFill("solid", fgColor="F4C542"),
        "failed":        PatternFill("solid", fgColor="CE1126"),
        "expired":       PatternFill("solid", fgColor="94A3B8"),
        "refunded":      PatternFill("solid", fgColor="6366F1"),
        "unmatched":     PatternFill("solid", fgColor="F97316"),
        "deduplicated":  PatternFill("solid", fgColor="CBD5E1"),
    }
    status_font_white = Font(color="FFFFFF", bold=True, size=10)
    status_font_dark = Font(color="0F172A", bold=True, size=10)

    for row_idx, t in enumerate(txs, start=2):
        for col_idx, (_, key) in enumerate(headers, 1):
            raw = t.get(key)
            if key == "amount":
                val = float(raw or 0)
            elif key == "audit_only":
                val = bool(raw)
            else:
                val = _safe_cell(raw if raw is not None else "")
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.border = border
            if key == "amount":
                cell.number_format = "#,##0.00"
                cell.alignment = Alignment(horizontal="right")
            if key == "status":
                fill = status_fills.get(str(raw))
                if fill:
                    cell.fill = fill
                    cell.font = status_font_white if raw in ("paid","failed","refunded","unmatched") else status_font_dark
                    cell.alignment = Alignment(horizontal="center")

    # Column widths tailored to content
    widths = {
        "A": 24, "B": 22, "C": 28, "D": 20, "E": 12, "F": 10,
        "G": 14, "H": 10, "I": 28, "J": 14, "K": 11, "L": 28, "M": 18,
    }
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    # Freeze header + enable autoFilter so admins can sort/filter in Excel
    ws.freeze_panes = "A2"
    last_col_letter = get_column_letter(len(headers))
    last_row = max(2, len(txs) + 1)
    ws.auto_filter.ref = f"A1:{last_col_letter}{last_row}"

    # ---------- Sheet 2: Summary ----------
    s = wb.create_sheet("Summary")
    s["A1"] = "Confirmed revenue by provider × currency"
    s["A1"].font = Font(bold=True, size=13)
    s["A1"].alignment = Alignment(vertical="center")
    s.row_dimensions[1].height = 22

    s["A3"] = "Provider"; s["B3"] = "Currency"; s["C3"] = "Confirmed amount"; s["D3"] = "Transactions"
    for c in ("A3", "B3", "C3", "D3"):
        s[c].font = header_font
        s[c].fill = header_fill
        s[c].alignment = header_align

    summary = compute_summary(txs)
    row = 4
    for item in summary["confirmed_revenue"]:
        s.cell(row=row, column=1, value=item["provider"])
        s.cell(row=row, column=2, value=item["currency"])
        c_amt = s.cell(row=row, column=3, value=item["amount"])
        c_amt.number_format = "#,##0.00"
        # Count paid tx for this (provider, currency) — formula over Sheet 1
        s.cell(row=row, column=4,
               value=f'=COUNTIFS(Transactions.G:G,"{item["provider"]}",Transactions.F:F,"{item["currency"]}",Transactions.J:J,"paid",Transactions.K:K,FALSE)')
        row += 1

    # Status counts block
    s.cell(row=row + 1, column=1, value="Status counts").font = Font(bold=True)
    row += 2
    for k, v in summary["status_counts"].items():
        s.cell(row=row, column=1, value=k)
        s.cell(row=row, column=2, value=v)
        row += 1

    s.column_dimensions["A"].width = 18
    s.column_dimensions["B"].width = 12
    s.column_dimensions["C"].width = 18
    s.column_dimensions["D"].width = 14

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
