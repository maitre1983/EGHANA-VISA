import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { toast } from "sonner";
import { RefreshCw, Activity, CheckCircle2, XCircle, CreditCard, Bitcoin, MessageSquareText } from "lucide-react";
import { fmtDateTime, PageHeader } from "../lib/adminUi";
import { PaymentDiagnostics } from "../components/PaymentDiagnostics";

const META = {
    hubtel: { label: "Hubtel — card payments", icon: CreditCard },
    nowpayments: { label: "NowPayments — crypto", icon: Bitcoin },
    hubtel_sms: { label: "Hubtel — SMS alerts", icon: MessageSquareText },
};

export default function AdminHealth() {
    const [data, setData] = useState(null);
    const [busy, setBusy] = useState(false);

    const load = async () => {
        const { data } = await api.get("/admin/health");
        setData(data);
    };
    const checkNow = async () => {
        setBusy(true);
        try { await api.post("/admin/health/check"); await load(); toast.success("Check completed"); }
        catch { toast.error("Check failed"); }
        setBusy(false);
    };
    useEffect(() => { load(); }, []);
    if (!data) return <div className="p-10">Loading…</div>;
    const latest = data.latest;

    return (
        <div className="p-6 md:p-10 max-w-6xl" data-testid="admin-health-page">
            <PageHeader title="Payment Monitoring" subtitle="Automatic check every 15 minutes. Admins get an email (and SMS if enabled) when a gateway goes down or comes back.">
                <button onClick={checkNow} disabled={busy} data-testid="health-check-now" className="inline-flex items-center gap-2 text-sm bg-ghana-green text-white px-4 py-2 rounded-md hover:bg-ghana-green-dark disabled:opacity-60">
                    <RefreshCw size={14} className={busy ? "animate-spin" : ""} /> Check now
                </button>
            </PageHeader>
            <div className="mt-4 text-xs text-slate-500" data-testid="health-last-checked">Last check: {latest ? fmtDateTime(latest.checked_at) : "never — click “Check now”"}</div>
            <div className="mt-6 grid md:grid-cols-3 gap-4">
                {(latest?.results || []).map((r) => <GatewayCard key={r.gateway} r={r} uptime={data.uptime_pct[r.gateway]} />)}
            </div>
            <div className="mt-6 grid md:grid-cols-3 gap-4">
                <Stat label="Payments confirmed (24h)" value={data.payments_24h.paid} testid="health-paid-24h" />
                <Stat label="Payments failed (24h)" value={data.payments_24h.failed} testid="health-failed-24h" warn={data.payments_24h.failed > 0} />
                <Stat label="Last confirmed payment" value={data.last_paid ? fmtDateTime(data.last_paid.paid_at) : "—"} sub={data.last_paid?.tracking_no} testid="health-last-paid" small />
            </div>
            <PendingVerifications />
            <PaymentDiagnostics />
            <History history={data.history} />
        </div>
    );
}

const PendingVerifications = () => {
    const [rows, setRows] = useState([]);
    const load = () => api.get("/admin/payment-verifications").then(({ data }) => setRows(data)).catch(() => {});
    useEffect(() => { load(); }, []);
    const verify = async (t) => {
        try {
            const { data } = await api.post(`/admin/applications/${t}/verify-payment`);
            data.state === "verified" ? toast.success(`${t} confirmed paid by Hubtel`) : toast.message(`${t}: ${data.state}`);
        } catch (e) { toast.error(e?.response?.data?.detail || "Verification failed"); }
        load();
    };
    return (
        <div className="mt-8 bg-white rounded-xl border border-black/10 p-6" data-testid="pending-verifications">
            <div className="font-heading font-semibold">Hubtel payments awaiting verification</div>
            <p className="text-xs text-slate-500 mt-1">Live card payments are only marked paid after Hubtel's status API confirms them. Unconfirmed ones are retried automatically every 15 minutes.</p>
            {rows.length === 0 && <div className="mt-3 text-sm text-slate-500" data-testid="pending-verifications-empty">Nothing pending.</div>}
            <div className="mt-3 divide-y divide-black/5">
                {rows.map((r) => (
                    <div key={r.tracking_no} className="py-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm" data-testid={`pending-verification-${r.tracking_no}`}>
                        <span className="font-mono">{r.tracking_no}</span>
                        <span>{r.full_name}</span>
                        <span className="text-slate-500">{r.amount_charged} {r.payment_currency}</span>
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-ghana-gold/20">{r.payment_verification?.state}</span>
                        <span className="text-xs text-slate-400 truncate max-w-xs" title={r.payment_verification?.last_error || ""}>{r.payment_verification?.last_error}</span>
                        <button onClick={() => verify(r.tracking_no)} data-testid={`verify-payment-${r.tracking_no}`} className="ml-auto text-xs border border-black/10 px-3 py-1.5 rounded-md hover:bg-slate-50">Verify now</button>
                    </div>
                ))}
            </div>
        </div>
    );
};

const GatewayCard = ({ r, uptime }) => {
    const m = META[r.gateway] || { label: r.gateway, icon: Activity };
    const Icon = m.icon;
    const up = r.status === "up";
    return (
        <div className={`bg-white rounded-xl border p-5 ${up ? "border-black/10" : "border-ghana-red"}`} data-testid={`gateway-card-${r.gateway}`}>
            <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-2 font-medium text-sm"><Icon size={16} /> {m.label}</span>
                <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${up ? "bg-ghana-green text-white" : "bg-ghana-red text-white"}`} data-testid={`gateway-status-${r.gateway}`}>
                    {up ? <CheckCircle2 size={12} /> : <XCircle size={12} />} {up ? "Operational" : "Down"}
                </span>
            </div>
            <div className="mt-4 flex items-baseline gap-4">
                <div><div className="font-heading text-2xl font-bold">{r.latency_ms}<span className="text-sm font-normal text-slate-500"> ms</span></div><div className="text-xs text-slate-500">response time</div></div>
                {uptime !== undefined && <div><div className="font-heading text-2xl font-bold">{uptime}%</div><div className="text-xs text-slate-500">uptime (recent checks)</div></div>}
            </div>
            <div className="mt-3 text-xs text-slate-500 font-mono truncate" title={r.detail}>{r.detail} · {r.mode}</div>
        </div>
    );
};

const Stat = ({ label, value, sub, testid, warn, small }) => (
    <div className="bg-white rounded-xl border border-black/10 p-5" data-testid={testid}>
        <div className="text-xs uppercase tracking-wider text-slate-500">{label}</div>
        <div className={`mt-2 font-heading font-bold ${small ? "text-base" : "text-3xl"} ${warn ? "text-ghana-red" : ""}`}>{value}</div>
        {sub && <div className="text-xs font-mono text-slate-500 mt-1">{sub}</div>}
    </div>
);

const History = ({ history }) => (
    <div className="mt-8 bg-white rounded-xl border border-black/10 p-6" data-testid="health-history">
        <div className="font-heading font-semibold">Recent checks</div>
        {history.length === 0 && <div className="mt-3 text-sm text-slate-500">No history yet.</div>}
        <div className="mt-4 space-y-3">
            {["hubtel", "nowpayments", "hubtel_sms"].map((g) => {
                const points = [...history].reverse().map((h) => h.results.find((r) => r.gateway === g)).filter(Boolean);
                if (!points.length) return null;
                return (
                    <div key={g} className="flex items-center gap-3">
                        <div className="w-44 text-sm text-slate-600 shrink-0">{META[g].label}</div>
                        <div className="flex gap-0.5 flex-wrap">
                            {points.map((p, i) => <span key={i} title={`${p.status} · ${p.latency_ms}ms`} className={`w-2 h-6 rounded-sm ${p.status === "up" ? "bg-ghana-green" : "bg-ghana-red"}`} />)}
                        </div>
                    </div>
                );
            })}
        </div>
    </div>
);
