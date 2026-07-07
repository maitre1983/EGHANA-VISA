import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { DollarSign, TrendingUp, Zap } from "lucide-react";

export default function AdminAnalytics() {
    const [kpi, setKpi] = useState(null);
    useEffect(() => { api.get("/admin/kpis").then(({ data }) => setKpi(data)); }, []);
    if (!kpi) return <div className="p-10">Loading…</div>;

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

            <div className="mt-10 grid md:grid-cols-3 gap-4">
                <StatCard label="Total applications" v={kpi.total} />
                <StatCard label="Submitted" v={kpi.submitted} />
                <StatCard label="In Progress" v={kpi.in_progress} />
                <StatCard label="Done" v={kpi.done} />
            </div>
        </div>
    );
}

const StatCard = ({ label, v }) => (
    <div className="bg-white border border-black/10 rounded-xl p-5">
        <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">{label}</div>
        <div className="mt-2 font-heading text-3xl font-bold">{v}</div>
    </div>
);
