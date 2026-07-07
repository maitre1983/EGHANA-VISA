import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { DollarSign, TrendingUp, Zap, Bitcoin, CreditCard } from "lucide-react";

export default function AdminAnalytics() {
    const [kpi, setKpi] = useState(null);
    const [crypto, setCrypto] = useState([]);
    useEffect(() => {
        api.get("/admin/kpis").then(({ data }) => setKpi(data));
        api.get("/admin/crypto-payments").then(({ data }) => setCrypto(data)).catch(() => {});
    }, []);
    if (!kpi) return <div className="p-10">Loading…</div>;

    const cryptoPaid = crypto.filter((c) => c.payment_status === "finished").length;
    const hubtelPaid = Math.max(0, kpi.total - cryptoPaid);

    const cards = [
        { icon: <DollarSign />, l: "Total revenue", v: `$${kpi.revenue_usd.toLocaleString()}`, c: "bg-ghana-green text-white" },
        { icon: <TrendingUp />, l: "Average per application", v: `$${kpi.avg_usd.toLocaleString()}`, c: "bg-white" },
        { icon: <Zap />, l: "Express upgrades", v: kpi.express_count, c: "bg-ghana-gold/40" },
    ];

    return (
        <div className="p-6 md:p-10">
            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Command Center</div>
            <h1 className="mt-1 font-heading text-3xl font-bold">Analytics</h1>

            <div className="mt-8 grid md:grid-cols-3 gap-4">
                {cards.map((c) => (
                    <div key={c.l} className={`rounded-xl border border-black/10 p-6 ${c.c}`} data-testid={`analytics-${c.l.toLowerCase().replace(/\s/g, "-")}`}>
                        <div className="opacity-70">{c.icon}</div>
                        <div className="mt-4 text-xs uppercase tracking-widest opacity-70 font-semibold">{c.l}</div>
                        <div className="mt-1 font-heading text-4xl font-bold">{c.v}</div>
                    </div>
                ))}
            </div>

            <div className="mt-10 grid md:grid-cols-4 gap-4">
                <StatCard label="Total applications" v={kpi.total} />
                <StatCard label="Submitted" v={kpi.submitted} />
                <StatCard label="In Progress" v={kpi.in_progress} />
                <StatCard label="Done" v={kpi.done} />
            </div>

            <div className="mt-10 bg-white border border-black/10 rounded-xl p-6" data-testid="analytics-payment-split">
                <div className="font-heading font-semibold mb-4">Payment method split</div>
                <div className="grid md:grid-cols-2 gap-4">
                    <SplitBox icon={<CreditCard size={18} />} label="Hubtel (Visa card)" v={hubtelPaid} tint="bg-ghana-green/10 text-ghana-green" />
                    <SplitBox icon={<Bitcoin size={18} />} label="USDT (crypto)" v={cryptoPaid} tint="bg-emerald-50 text-emerald-600" />
                </div>
            </div>

            {crypto.length > 0 && (
                <div className="mt-6 bg-white border border-black/10 rounded-xl p-6" data-testid="analytics-crypto-list">
                    <div className="font-heading font-semibold mb-4">Crypto transactions</div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="bg-slate-50 text-left text-xs uppercase tracking-widest text-slate-500">
                                <tr>
                                    <th className="px-3 py-2">Payment ID</th>
                                    <th className="px-3 py-2">Tracking</th>
                                    <th className="px-3 py-2">Network</th>
                                    <th className="px-3 py-2">Amount</th>
                                    <th className="px-3 py-2">Received</th>
                                    <th className="px-3 py-2">Status</th>
                                    <th className="px-3 py-2">Created</th>
                                </tr>
                            </thead>
                            <tbody>
                                {crypto.map((c) => (
                                    <tr key={c.payment_id} className="border-t border-black/5" data-testid={`crypto-row-${c.payment_id}`}>
                                        <td className="px-3 py-2 font-mono">{c.payment_id}</td>
                                        <td className="px-3 py-2 font-mono">{c.tracking_no}</td>
                                        <td className="px-3 py-2 uppercase">{c.network}</td>
                                        <td className="px-3 py-2">{c.pay_amount} {c.pay_currency}</td>
                                        <td className="px-3 py-2">{c.actually_paid || "—"}</td>
                                        <td className="px-3 py-2">
                                            <span className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded font-bold ${
                                                c.payment_status === "finished" ? "bg-ghana-green text-white" :
                                                c.payment_status === "failed" || c.payment_status === "expired" ? "bg-ghana-red text-white" :
                                                "bg-ghana-gold text-ghana-black"
                                            }`}>{c.payment_status}</span>
                                        </td>
                                        <td className="px-3 py-2 text-xs text-slate-500">{new Date(c.created_at).toLocaleString()}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}

const StatCard = ({ label, v }) => (
    <div className="bg-white border border-black/10 rounded-xl p-5">
        <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">{label}</div>
        <div className="mt-2 font-heading text-3xl font-bold">{v}</div>
    </div>
);

const SplitBox = ({ icon, label, v, tint }) => (
    <div className="border border-black/5 rounded-lg p-5 flex items-center gap-4">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${tint}`}>{icon}</div>
        <div>
            <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">{label}</div>
            <div className="font-heading text-2xl font-bold">{v}</div>
        </div>
    </div>
);
