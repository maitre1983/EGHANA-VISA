import React, { useEffect, useState, useMemo } from "react";
import api from "../lib/api";
import { Eye, Play, CheckCircle2, X, RefreshCw, Search, Calendar, ArrowUpDown } from "lucide-react";
import { toast } from "sonner";

const FILTERS = [
    { key: "all", label: "All" },
    { key: "submitted", label: "Submitted" },
    { key: "in_progress", label: "In Progress" },
    { key: "done", label: "Done" },
];

// Ghana sits on GMT+0 year-round (no DST), so UTC = GMT. Format as
// "19 Nov 2026 — 14:35 GMT" using a locale-stable formatter to avoid
// SSR/client drift and avoid pulling in moment/dayjs.
const _FMT_DATE = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const _FMT_TIME = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
function _fmt(iso) {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    return `${_FMT_DATE.format(d)} — ${_FMT_TIME.format(d)} GMT`;
}
// Returns { text, fallback }. `fallback` is true for legacy records where
// no definitive submitted_at exists — we show the creation date but flag it
// as unconfirmed so it is never presented as a definitive submission.
export function submittedAtDisplay(app) {
    if (!app) return { text: "—", fallback: false };
    if (app.submitted_at) return { text: _fmt(app.submitted_at), fallback: false };
    if (app.created_at) return { text: _fmt(app.created_at), fallback: true };
    return { text: "—", fallback: false };
}

export default function AdminDashboard() {
    const [kpi, setKpi] = useState(null);
    const [apps, setApps] = useState([]);
    const [filter, setFilter] = useState("all");
    const [selected, setSelected] = useState(null);
    const [loading, setLoading] = useState(false);
    const [search, setSearch] = useState("");
    const [fromDate, setFromDate] = useState("");
    const [toDate, setToDate] = useState("");
    const [sortAsc, setSortAsc] = useState(false); // false = newest first (DB default)
    const [page, setPage] = useState(1);
    const PAGE_SIZE = 100;

    const load = async () => {
        setLoading(true);
        try {
            const [k, a] = await Promise.all([
                api.get("/admin/kpis"),
                api.get("/admin/applications", {
                    params: {
                        status: filter,
                        search: search.trim() || undefined,
                        from_date: fromDate || undefined,
                        to_date: toDate || undefined,
                        page,
                        page_size: PAGE_SIZE,
                    },
                }),
            ]);
            setKpi(k.data); setApps(a.data);
        } finally { setLoading(false); }
    };

    useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter, page]);

    // Debounced search/date — local only, no new network until typing stops.
    useEffect(() => {
        setPage(1);  // any new filter resets pagination
        const t = setTimeout(() => { load(); }, 350);
        return () => clearTimeout(t);
        // eslint-disable-next-line
    }, [search, fromDate, toDate]);

    const displayed = useMemo(() => {
        // Backend already returns newest-first. Reverse locally only when user asks oldest-first.
        return sortAsc ? [...apps].reverse() : apps;
    }, [apps, sortAsc]);

    const resetFilters = () => { setSearch(""); setFromDate(""); setToDate(""); };

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

            {/* Search + date range toolbar */}
            <div className="mt-4 bg-white rounded-xl border border-black/10 p-3 flex flex-col md:flex-row gap-3 md:items-center">
                <div className="relative flex-1 min-w-[220px]">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search by name, email or tracking number…"
                        data-testid="dashboard-search"
                        className="w-full pl-9 pr-3 py-2 border border-black/10 rounded-md text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none"
                    />
                </div>
                <div className="flex gap-2 items-center text-sm">
                    <Calendar size={14} className="text-slate-400" />
                    <input
                        type="date"
                        value={fromDate}
                        onChange={(e) => setFromDate(e.target.value)}
                        data-testid="dashboard-from-date"
                        aria-label="From date"
                        className="px-2 py-2 border border-black/10 rounded-md focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none"
                    />
                    <span className="text-slate-400">→</span>
                    <input
                        type="date"
                        value={toDate}
                        onChange={(e) => setToDate(e.target.value)}
                        data-testid="dashboard-to-date"
                        aria-label="To date"
                        className="px-2 py-2 border border-black/10 rounded-md focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none"
                    />
                </div>
                {(search || fromDate || toDate) && (
                    <button onClick={resetFilters} data-testid="dashboard-reset-filters" className="text-xs text-slate-500 hover:text-ghana-red underline underline-offset-2">Reset</button>
                )}
                <div className="text-xs text-slate-500 md:ml-auto whitespace-nowrap" data-testid="dashboard-result-count">
                    {loading ? "Loading…" : `${displayed.length} result${displayed.length === 1 ? "" : "s"}${displayed.length >= PAGE_SIZE ? " (page " + page + ")" : ""}`}
                </div>
                <div className="flex items-center gap-1 text-xs">
                    <button
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page <= 1 || loading}
                        data-testid="dashboard-page-prev"
                        className="px-2 py-1 border border-black/10 rounded hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                        aria-label="Previous page"
                    >←</button>
                    <span className="font-mono text-slate-500">pg {page}</span>
                    <button
                        onClick={() => setPage((p) => p + 1)}
                        disabled={loading || displayed.length < PAGE_SIZE}
                        data-testid="dashboard-page-next"
                        className="px-2 py-1 border border-black/10 rounded hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                        aria-label="Next page"
                    >→</button>
                </div>
            </div>

            {/* Table */}
            <div className="mt-4 bg-white rounded-xl border border-black/10 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 text-left text-xs uppercase tracking-widest text-slate-500">
                            <tr>
                                <th className="px-4 py-3 font-semibold">Tracking</th>
                                <th className="px-4 py-3 font-semibold">
                                    <button
                                        onClick={() => setSortAsc((v) => !v)}
                                        data-testid="dashboard-sort-submitted"
                                        className="inline-flex items-center gap-1 uppercase tracking-widest text-xs font-semibold hover:text-ghana-green"
                                        title={sortAsc ? "Sort newest first" : "Sort oldest first"}
                                    >
                                        Submitted At <ArrowUpDown size={11} />
                                    </button>
                                </th>
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
                            {displayed.map((a) => (
                                <tr key={a.tracking_no} className="border-t border-black/5" data-testid={`row-${a.tracking_no}`}>
                                    <td className="px-4 py-3 font-mono">{a.tracking_no}</td>
                                    <td className="px-4 py-3 whitespace-nowrap text-slate-600" data-testid={`submitted-at-${a.tracking_no}`}>
                                        {(() => {
                                            const d = submittedAtDisplay(a);
                                            return (
                                                <span className="inline-flex items-center gap-2">
                                                    <span className={d.fallback ? "text-slate-500" : ""}>{d.text}</span>
                                                    {d.fallback && (
                                                        <span
                                                            title="Legacy record — created date shown because no definitive submission timestamp was captured"
                                                            className="text-[9px] uppercase tracking-widest font-semibold text-slate-400 italic border border-slate-200 rounded px-1.5 py-0.5"
                                                            data-testid={`submitted-at-fallback-${a.tracking_no}`}
                                                        >created</span>
                                                    )}
                                                </span>
                                            );
                                        })()}
                                    </td>
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
                            {displayed.length === 0 && (
                                <tr><td colSpan="11" className="text-center py-12 text-slate-500 text-sm">{loading ? "Loading…" : (search || fromDate || toDate) ? "No applications match these filters." : "No applications yet."}</td></tr>
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
                            {(() => {
                                const d = submittedAtDisplay(selected);
                                return (
                                    <KV
                                        k={d.fallback ? "Created at (no definitive submission timestamp)" : "Submitted at"}
                                        v={d.text}
                                    />
                                );
                            })()}
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
