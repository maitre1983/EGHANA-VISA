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

    # 2. Hubtel callback trail (adds failed/expired/orphans)
    hubtel_txs: list[dict] = []
    async for cb in db.hubtel_callbacks.find({}, {"_id": 0}):
        n = _normalize_hubtel_cb(cb)
        if n["provider_reference"] and n["provider_reference"] in confirmed_refs:
            continue  # already covered by the confirmed application row
        if not n.get("tracking_no") or n["tracking_no"] not in known_trackings:
            # keep status for pending/failed/expired, otherwise label orphan
            if n["status"] == "paid":
                n["status"] = "unmatched"
        hubtel_txs.append(n)

    # 3. Crypto callback trail
    crypto_txs: list[dict] = []
    async for p in db.crypto_payments.find({}, {"_id": 0}):
        n = _normalize_crypto(p)
        if n["provider_reference"] and n["provider_reference"] in confirmed_refs:
            continue
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
    counts: dict[str, int] = {"paid": 0, "pending": 0, "failed": 0, "expired": 0, "refunded": 0, "unmatched": 0}
    for t in txs:
        counts[t["status"]] = counts.get(t["status"], 0) + 1
        if t["status"] != "paid":
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


def to_csv(txs: list[dict]) -> str:
    """CSV export. One column per normalized field, header-stable."""
    import csv, io
    buf = io.StringIO()
    fields = [
        "date", "provider", "provider_reference", "tracking_no",
        "customer_name", "customer_email", "amount", "currency",
        "network", "status", "payment_method_label", "source",
    ]
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for t in txs:
        w.writerow({k: t.get(k, "") for k in fields})
    return buf.getvalue()
