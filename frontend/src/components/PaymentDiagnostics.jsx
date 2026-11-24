import React, { useState } from "react";
import api from "../lib/api";
import { toast } from "sonner";
import { Stethoscope } from "lucide-react";

const fmt = (v) => {
    if (v && typeof v === "object" && "http_status" in v) {
        if (v.http_status === 403 && !v.responseCode) return "HTTP 403 – server IP not authorised by Hubtel";
        if (v.http_status === 401) return "HTTP 401 – Hubtel credentials rejected";
        if (v.http_status === null) return `No response – ${v.error || "network error"}`;
        return `HTTP ${v.http_status} · ${v.responseCode || ""} ${v.message || ""}${v.data ? " · " + JSON.stringify(v.data) : ""}`;
    }
    if (v && typeof v === "object") return JSON.stringify(v, (k, x) => (x && typeof x === "object" && "http_status" in x ? fmt(x) : x));
    return v === "" || v === null || v === undefined ? "—" : String(v);
};

const Line = ({ k, v, testid }) => (
    <div className="flex gap-3 text-sm py-1" data-testid={testid}>
        <span className="w-56 shrink-0 text-slate-500">{k}</span>
        <span className="font-mono break-all">{fmt(v)}</span>
    </div>
);

export const PaymentDiagnostics = () => {
    const [refs, setRefs] = useState("");
    const [res, setRes] = useState(null);
    const [busy, setBusy] = useState(false);
    const run = async () => {
        setBusy(true);
        try {
            const { data } = await api.post("/admin/payments/diagnostics", { tracking_nos: refs.split(/[\s,]+/).filter(Boolean) });
            setRes(data);
        } catch (e) { toast.error(e?.response?.data?.detail || "Diagnostics failed"); }
        setBusy(false);
    };
    const h = res?.hubtel;
    const n = res?.nowpayments;
    return (
        <div className="mt-8 bg-white rounded-xl border border-black/10 p-6" data-testid="payment-diagnostics">
            <div className="font-heading font-semibold">Payment diagnostics (read-only)</div>
            <p className="text-xs text-slate-500 mt-1">Checks the server's outgoing IP, Hubtel credentials and IP authorisation, and NOWPayments keys. Optionally looks up tracking numbers at Hubtel. Nothing is modified.</p>
            <div className="mt-3 flex gap-2">
                <input value={refs} onChange={(e) => setRefs(e.target.value)} placeholder="Tracking numbers to reconcile (optional, comma separated)"
                    data-testid="diagnostics-refs" className="flex-1 border border-black/10 rounded-md px-3 py-2 text-sm" />
                <button onClick={run} disabled={busy} data-testid="diagnostics-run" className="inline-flex items-center gap-2 text-sm bg-ghana-black text-white px-4 py-2 rounded-md disabled:opacity-60">
                    <Stethoscope size={14} /> {busy ? "Running…" : "Run diagnostics"}
                </button>
            </div>
            {res && (
                <div className="mt-4 divide-y divide-black/5" data-testid="diagnostics-result">
                    <Line k="Server outgoing IP" v={res.egress_ip} testid="diag-egress-ip" />
                    {res.egress_ip_via_hubtel_proxy && <Line k="IP via Hubtel proxy" v={res.egress_ip_via_hubtel_proxy} />}
                    <Line k="Public base URL" v={res.public_base_url} />
                    <Line k="Hubtel mode" v={h.mode} testid="diag-hubtel-mode" />
                    <Line k="Hubtel credentials" v={h.credentials_present} />
                    <Line k="Callback URL" v={h.callback_url} />
                    <Line k="Return URL" v={h.return_url} />
                    <Line k="Cancellation URL" v={h.cancellation_url} />
                    <Line k="Hubtel status API probe" v={h.status_api_probe} testid="diag-hubtel-probe" />
                    {Object.entries(h.references || {}).map(([ref, r]) => <Line key={ref} k={`Reconcile ${ref}`} v={r} />)}
                    <Line k="NOWPayments mode" v={n.mode} testid="diag-np-mode" />
                    <Line k="NOWPayments IPN URL" v={n.ipn_url} />
                    <Line k="NOWPayments live keys" v={n.live_keys} testid="diag-np-live" />
                    <Line k="NOWPayments sandbox keys" v={n.sandbox_keys} />
                </div>
            )}
        </div>
    );
};
