import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { Eye, Play, CheckCircle2, X, RefreshCw } from "lucide-react";
import { toast } from "sonner";

const FILTERS = [
    { key: "all", label: "All" },
    { key: "submitted", label: "Submitted" },
    { key: "in_progress", label: "In Progress" },
    { key: "done", label: "Done" },
];

export default function AdminDashboard() {
    const [kpi, setKpi] = useState(null);
    const [apps, setApps] = useState([]);
    const [filter, setFilter] = useState("all");
    const [selected, setSelected] = useState(null);
    const [loading, setLoading] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const [k, a] = await Promise.all([api.get("/admin/kpis"), api.get("/admin/applications", { params: { status: filter } })]);
            setKpi(k.data); setApps(a.data);
        } finally { setLoading(false); }
    };

    useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter]);

    const setStatus = async (tracking, status) => {
        try {
            await api.post(`/admin/applications/${tracking}/status`, { status });
            toast.success(`Marked as ${status.replace("_", " ")}`);
            load();
            if (selected?.tracking_no === tracking) {
                const { data } = await api.get(`/admin/applications/${tracking}`); setSelected(data);
            }
        } catch (e) { toast.error(e?.response?.data?.detail || "Update failed"); }
    };

    const view = async (tracking) => {
        const { data } = await api.get(`/admin/applications/${tracking}`);
        setSelected(data);
    };

    return (
        <div className="p-6 md:p-10">
            <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                    <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Command Center</div>
                    <h1 className="mt-1 font-heading text-3xl font-bold">Dashboard</h1>
                </div>
                <button onClick={load} className="inline-flex items-center gap-2 border border-black/10 bg-white px-4 py-2 rounded-md text-sm hover:bg-slate-50" data-testid="dashboard-refresh"><RefreshCw size={14} /> Refresh</button>
            </div>

            {/* KPIs */}
            <div className="mt-8 grid grid-cols-2 md:grid-cols-5 gap-4">
                {[
                    { l: "Applications", v: kpi?.total ?? 0, c: "bg-ghana-black text-white" },
                    { l: "Submitted", v: kpi?.submitted ?? 0, c: "bg-white" },
                    { l: "In Progress", v: kpi?.in_progress ?? 0, c: "bg-ghana-gold/40" },
                    { l: "Done", v: kpi?.done ?? 0, c: "bg-ghana-green/10" },
                    { l: "Revenue (USD)", v: `$${kpi?.revenue_usd ?? 0}`, c: "bg-white border-l-4 border-ghana-red" },
                ].map((k) => (
                    <div key={k.l} className={`rounded-xl border border-black/10 p-5 ${k.c}`} data-testid={`kpi-${k.l.toLowerCase().replace(/\s/g, "-")}`}>
                        <div className="text-xs uppercase tracking-widest opacity-70 font-semibold">{k.l}</div>
                        <div className="mt-2 font-heading text-3xl font-bold">{k.v}</div>
                    </div>
                ))}
            </div>

            {/* Filter tabs */}
            <div className="mt-10 flex gap-2 flex-wrap">
                {FILTERS.map((f) => (
                    <button key={f.key} onClick={() => setFilter(f.key)} data-testid={`filter-${f.key}`}
                        className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${filter === f.key ? "bg-ghana-black text-white" : "bg-white border border-black/10 text-ghana-black hover:bg-slate-50"}`}>
                        {f.label}
                    </button>
                ))}
            </div>

            {/* Table */}
            <div className="mt-4 bg-white rounded-xl border border-black/10 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 text-left text-xs uppercase tracking-widest text-slate-500">
                            <tr>
                                <th className="px-4 py-3 font-semibold">Tracking</th>
                                <th className="px-4 py-3 font-semibold">Name</th>
                                <th className="px-4 py-3 font-semibold">Passport</th>
                                <th className="px-4 py-3 font-semibold">Email</th>
                                <th className="px-4 py-3 font-semibold">Visa</th>
                                <th className="px-4 py-3 font-semibold">Proc.</th>
                                <th className="px-4 py-3 font-semibold">Arrival</th>
                                <th className="px-4 py-3 font-semibold">Departure</th>
                                <th className="px-4 py-3 font-semibold">Status</th>
                                <th className="px-4 py-3 font-semibold text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {apps.map((a) => (
                                <tr key={a.tracking_no} className="border-t border-black/5" data-testid={`row-${a.tracking_no}`}>
                                    <td className="px-4 py-3 font-mono">{a.tracking_no}</td>
                                    <td className="px-4 py-3">{a.full_name}</td>
                                    <td className="px-4 py-3">{a.passport_number}</td>
                                    <td className="px-4 py-3 truncate max-w-[180px]">{a.email}</td>
                                    <td className="px-4 py-3">{a.visa_name}</td>
                                    <td className="px-4 py-3">{a.processing}</td>
                                    <td className="px-4 py-3">{a.arrival_date}</td>
                                    <td className="px-4 py-3">{a.departure_date}</td>
                                    <td className="px-4 py-3">
                                        <span className={`text-[10px] uppercase tracking-widest px-2 py-1 rounded font-bold ${
                                            a.status === "done" ? "bg-ghana-green text-white" :
                                            a.status === "in_progress" ? "bg-ghana-gold text-ghana-black" :
                                            "bg-slate-800 text-white"
                                        }`}>{a.status.replace("_", " ")}</span>
                                    </td>
                                    <td className="px-4 py-3 text-right space-x-1">
                                        {a.status === "submitted" && (
                                            <button onClick={() => setStatus(a.tracking_no, "in_progress")} data-testid={`btn-inprogress-${a.tracking_no}`} className="inline-flex items-center gap-1 text-xs bg-ghana-gold text-ghana-black px-2 py-1 rounded font-semibold hover:bg-ghana-gold-dark"><Play size={12} /> In Progress</button>
                                        )}
                                        {a.status === "in_progress" && (
                                            <button onClick={() => setStatus(a.tracking_no, "done")} data-testid={`btn-done-${a.tracking_no}`} className="inline-flex items-center gap-1 text-xs bg-ghana-green text-white px-2 py-1 rounded font-semibold hover:bg-ghana-green-dark"><CheckCircle2 size={12} /> Done</button>
                                        )}
                                        <button onClick={() => view(a.tracking_no)} data-testid={`btn-view-${a.tracking_no}`} className="inline-flex items-center gap-1 text-xs border border-black/10 px-2 py-1 rounded hover:bg-slate-50"><Eye size={12} /> View</button>
                                    </td>
                                </tr>
                            ))}
                            {apps.length === 0 && (
                                <tr><td colSpan="10" className="text-center py-12 text-slate-500 text-sm">{loading ? "Loading…" : "No applications yet."}</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Detail modal */}
            {selected && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-start md:items-center justify-center p-4 overflow-y-auto">
                    <div className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full my-8" data-testid="detail-modal">
                        <div className="flex items-center justify-between p-6 border-b border-black/5">
                            <div>
                                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Application</div>
                                <div className="font-heading text-xl font-bold">{selected.tracking_no}</div>
                            </div>
                            <button onClick={() => setSelected(null)} data-testid="detail-close" className="p-2 rounded hover:bg-slate-100"><X size={18} /></button>
                        </div>
                        <div className="p-6 grid md:grid-cols-2 gap-4 text-sm">
                            <KV k="Name" v={selected.full_name} />
                            <KV k="Email" v={selected.email} />
                            <KV k="Phone" v={selected.phone} />
                            <KV k="Profession" v={selected.profession} />
                            <KV k="Passport" v={`${selected.passport_number} (${selected.passport_type})`} />
                            <KV k="Passport country" v={selected.passport_country} />
                            <KV k="Passport expiry" v={selected.passport_expiry} />
                            <KV k="Travelling from" v={selected.travelling_from} />
                            <KV k="Arrival" v={selected.arrival_date} />
                            <KV k="Departure" v={selected.departure_date} />
                            <KV k="Visa" v={selected.visa_name} />
                            <KV k="Processing" v={selected.processing} />
                            <KV k="Amount" v={`$${selected.amount_usd}`} />
                            <KV k="Status" v={selected.status} />
                        </div>
                        <div className="px-6 pb-6">
                            <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-2">Documents</div>
                            <div className="grid sm:grid-cols-2 gap-2">
                                {Object.entries(selected.documents || {}).map(([type, ref]) => (
                                    <a key={type} href={`#`} onClick={async (e) => {
                                        e.preventDefault();
                                        const token = localStorage.getItem("egv_admin_token");
                                        const url = `${api.defaults.baseURL}/admin/applications/${selected.tracking_no}/documents/${type}`;
                                        const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
                                        const blob = await res.blob();
                                        window.open(URL.createObjectURL(blob), "_blank");
                                    }} data-testid={`doc-${type}`} className="text-sm border border-black/10 rounded-md px-3 py-2 hover:bg-slate-50 truncate">📎 {type} — {ref.original_filename}</a>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

const KV = ({ k, v }) => (
    <div>
        <div className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">{k}</div>
        <div className="font-medium mt-0.5">{v}</div>
    </div>
);
