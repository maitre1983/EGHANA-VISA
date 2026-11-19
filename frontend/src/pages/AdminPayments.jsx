import React, { useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import { toast } from "sonner";
import {
    RefreshCw, Search, Calendar, Download, Eye, X,
    CheckCircle2, Clock, XCircle, AlertTriangle, Undo2, HelpCircle, Copy,
} from "lucide-react";

// GMT = UTC for Ghana (no DST). Shared formatter.
const _DATE = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const _TIME = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
const fmtDate = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    return `${_DATE.format(d)} — ${_TIME.format(d)} GMT`;
};

const STATUS_META = {
    paid:          { label: "Paid",          icon: CheckCircle2, cls: "bg-ghana-green text-white" },
    pending:       { label: "Pending",       icon: Clock,        cls: "bg-ghana-gold text-ghana-black" },
    failed:        { label: "Failed",        icon: XCircle,      cls: "bg-ghana-red text-white" },
    expired:       { label: "Expired",       icon: AlertTriangle,cls: "bg-slate-500 text-white" },
    refunded:      { label: "Refunded",      icon: Undo2,        cls: "bg-indigo-500 text-white" },
    unmatched:     { label: "Unmatched",     icon: HelpCircle,   cls: "bg-orange-500 text-white" },
    deduplicated:  { label: "Deduplicated",  icon: Copy,         cls: "bg-slate-300 text-slate-700" },
};

const PROVIDERS = [
    { key: "", label: "All providers" },
    { key: "hubtel", label: "Hubtel" },
    { key: "nowpayments", label: "NOWPayments" },
    { key: "unknown", label: "Unknown" },
];

const STATUSES = [
    { key: "", label: "All (hide audit-only)" },
    { key: "paid", label: "Paid" },
    { key: "pending", label: "Pending" },
    { key: "failed", label: "Failed" },
    { key: "expired", label: "Expired" },
    { key: "refunded", label: "Refunded" },
    { key: "unmatched", label: "Unmatched" },
    { key: "deduplicated", label: "Deduplicated (audit only)" },
];

export default function AdminPayments() {
    const [data, setData] = useState({ transactions: [], summary: { confirmed_revenue: [], status_counts: {}, total_transactions: 0 } });
    const [loading, setLoading] = useState(false);
    const [search, setSearch] = useState("");
    const [provider, setProvider] = useState("");
    const [status, setStatus] = useState("");
    const [fromDate, setFromDate] = useState("");
    const [toDate, setToDate] = useState("");
    const [selected, setSelected] = useState(null);
    const [selectedRaw, setSelectedRaw] = useState(null);
    const [sortKey, setSortKey] = useState("date");
    const [sortDir, setSortDir] = useState("desc");

    const load = async () => {
        setLoading(true);
        try {
            const { data: resp } = await api.get("/admin/transactions", {
                params: {
                    provider: provider || undefined,
                    status: status || undefined,
                    search: search.trim() || undefined,
                    from_date: fromDate || undefined,
                    to_date: toDate || undefined,
                },
            });
            setData(resp);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Failed to load transactions");
        } finally { setLoading(false); }
    };

    useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
    useEffect(() => {
        const t = setTimeout(() => { load(); }, 300);
        return () => clearTimeout(t);
        // eslint-disable-next-line
    }, [search, provider, status, fromDate, toDate]);

    const openDetail = async (tx) => {
        setSelected(tx);
        setSelectedRaw(null);
        try {
            const { data: d } = await api.get(`/admin/transactions/${encodeURIComponent(tx.id)}`);
            setSelectedRaw(d);
        } catch (_e) {
            setSelectedRaw({ raw: null, application: null });
        }
    };

    const exportFile = async (format) => {
        try {
            const token = localStorage.getItem("egv_admin_token");
            const ext = format === "xlsx" ? "xlsx" : "csv";
            const url = new URL(`${api.defaults.baseURL}/admin/transactions.${ext}`);
            const qs = { provider, status, search: search.trim(), from_date: fromDate, to_date: toDate };
            Object.entries(qs).forEach(([k, v]) => { if (v) url.searchParams.set(k, v); });
            const res = await fetch(url.toString(), { headers: { Authorization: `Bearer ${token}` } });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const blob = await res.blob();
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = `eghanavisa-transactions-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.${ext}`;
            document.body.appendChild(a); a.click(); a.remove();
            toast.success(`${ext.toUpperCase()} exported`);
        } catch (e) {
            toast.error(`Export failed: ${e.message}`);
        }
    };
    const exportCsv = () => exportFile("csv");
    const exportXlsx = () => exportFile("xlsx");

    const sorted = useMemo(() => {
        // Hide deduplicated callbacks from the main view unless the admin
        // explicitly asks for them via the Status filter — they still exist
        // for audit but must never inflate the visible count.
        const base = (status === "deduplicated")
            ? data.transactions
            : data.transactions.filter((t) => t.status !== "deduplicated");
        const list = [...base];
        const dir = sortDir === "asc" ? 1 : -1;
        list.sort((a, b) => {
            const va = a[sortKey] ?? "";
            const vb = b[sortKey] ?? "";
            if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
            return String(va).localeCompare(String(vb)) * dir;
        });
        return list;
    }, [data.transactions, sortKey, sortDir, status]);

    const toggleSort = (key) => {
        if (sortKey === key) { setSortDir(sortDir === "asc" ? "desc" : "asc"); }
        else { setSortKey(key); setSortDir("desc"); }
    };

    const resetFilters = () => { setSearch(""); setProvider(""); setStatus(""); setFromDate(""); setToDate(""); };

    const activeFilters = !!(search || provider || status || fromDate || toDate);

    return (
        <div className="p-6 md:p-10">
            <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                    <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Command Center</div>
                    <h1 className="mt-1 font-heading text-3xl font-bold">Payments — Transactions</h1>
                    <p className="text-sm text-slate-500 mt-1">Unified read-only view of every Hubtel and NOWPayments transaction. Confirmed revenue is reconciled from the applications collection.</p>
                </div>
                <div className="flex gap-2">
                    <button onClick={load} data-testid="payments-refresh" className="inline-flex items-center gap-2 border border-black/10 bg-white px-4 py-2 rounded-md text-sm hover:bg-slate-50"><RefreshCw size={14} /> Refresh</button>
                    <button onClick={exportCsv} data-testid="payments-export-csv" className="inline-flex items-center gap-2 border border-black/10 bg-white px-4 py-2 rounded-md text-sm hover:bg-slate-50"><Download size={14} /> Export CSV</button>
                    <button onClick={exportXlsx} data-testid="payments-export-xlsx" className="inline-flex items-center gap-2 bg-ghana-green text-white px-4 py-2 rounded-md text-sm hover:bg-ghana-green-dark font-semibold"><Download size={14} /> Export Excel</button>
                </div>
            </div>

            {/* Financial summary — split by (provider, currency), never summed across currencies */}
            <div className="mt-8">
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-3">Confirmed revenue (by provider × currency)</div>
                {data.summary.confirmed_revenue.length === 0 ? (
                    <div className="bg-white border border-dashed border-black/10 rounded-xl px-6 py-8 text-sm text-slate-500" data-testid="revenue-empty">No confirmed revenue in the current filter window.</div>
                ) : (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {data.summary.confirmed_revenue.map((r, idx) => (
                            <div key={idx} data-testid={`revenue-${r.provider}-${r.currency}`} className="bg-white rounded-xl border border-black/10 p-5">
                                <div className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">{r.provider}</div>
                                <div className="mt-2 font-heading text-2xl font-bold">{r.amount.toLocaleString()} <span className="text-base font-medium text-slate-500">{r.currency}</span></div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Status counts */}
                <div className="mt-3 grid grid-cols-3 md:grid-cols-6 gap-2 text-xs">
                    {Object.entries(data.summary.status_counts).map(([k, v]) => (
                        <div key={k} data-testid={`count-${k}`} className="bg-white border border-black/10 rounded-md px-3 py-2 flex items-center justify-between">
                            <span className="text-slate-500 capitalize">{k}</span>
                            <span className="font-bold font-mono">{v}</span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Filters toolbar */}
            <div className="mt-6 bg-white rounded-xl border border-black/10 p-3 flex flex-col lg:flex-row gap-3 lg:items-center">
                <div className="relative flex-1 min-w-[220px]">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search by reference, tracking, client name or email…"
                        data-testid="payments-search"
                        className="w-full pl-9 pr-3 py-2 border border-black/10 rounded-md text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none"
                    />
                </div>
                <select value={provider} onChange={(e) => setProvider(e.target.value)} data-testid="payments-provider-filter" className="px-3 py-2 text-sm border border-black/10 rounded-md focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none">
                    {PROVIDERS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
                </select>
                <select value={status} onChange={(e) => setStatus(e.target.value)} data-testid="payments-status-filter" className="px-3 py-2 text-sm border border-black/10 rounded-md focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none">
                    {STATUSES.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
                </select>
                <div className="flex gap-2 items-center text-sm">
                    <Calendar size={14} className="text-slate-400" />
                    <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} data-testid="payments-from-date" aria-label="From date" className="px-2 py-2 border border-black/10 rounded-md focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                    <span className="text-slate-400">→</span>
                    <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} data-testid="payments-to-date" aria-label="To date" className="px-2 py-2 border border-black/10 rounded-md focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                </div>
                {activeFilters && (
                    <button onClick={resetFilters} data-testid="payments-reset-filters" className="text-xs text-slate-500 hover:text-ghana-red underline underline-offset-2">Reset</button>
                )}
                <div className="text-xs text-slate-500 lg:ml-auto whitespace-nowrap" data-testid="payments-result-count">
                    {loading ? "Loading…" : `${sorted.length} transaction${sorted.length === 1 ? "" : "s"}`}
                </div>
            </div>

            {/* Table */}
            <div className="mt-4 bg-white rounded-xl border border-black/10 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 text-left text-xs uppercase tracking-widest text-slate-500">
                            <tr>
                                <Th label="Date" sortKey="date" active={sortKey === "date"} dir={sortDir} onClick={toggleSort} />
                                <Th label="Client" sortKey="customer_name" active={sortKey === "customer_name"} dir={sortDir} onClick={toggleSort} />
                                <Th label="Tracking" sortKey="tracking_no" active={sortKey === "tracking_no"} dir={sortDir} onClick={toggleSort} />
                                <Th label="Amount" sortKey="amount" active={sortKey === "amount"} dir={sortDir} onClick={toggleSort} align="right" />
                                <Th label="Currency" sortKey="currency" active={sortKey === "currency"} dir={sortDir} onClick={toggleSort} />
                                <Th label="Provider" sortKey="provider" active={sortKey === "provider"} dir={sortDir} onClick={toggleSort} />
                                <th className="px-4 py-3 font-semibold">Network</th>
                                <Th label="Reference" sortKey="provider_reference" active={sortKey === "provider_reference"} dir={sortDir} onClick={toggleSort} />
                                <Th label="Status" sortKey="status" active={sortKey === "status"} dir={sortDir} onClick={toggleSort} />
                                <th className="px-4 py-3 font-semibold text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sorted.map((t) => {
                                const meta = STATUS_META[t.status] || STATUS_META.pending;
                                const Icon = meta.icon;
                                return (
                                    <tr key={t.id} className="border-t border-black/5" data-testid={`tx-row-${t.id}`}>
                                        <td className="px-4 py-3 whitespace-nowrap text-slate-600">{fmtDate(t.date)}</td>
                                        <td className="px-4 py-3">{t.customer_name || <span className="text-slate-400 italic">—</span>}</td>
                                        <td className="px-4 py-3 font-mono text-xs">{t.tracking_no || <span className="text-slate-400 italic">—</span>}</td>
                                        <td className="px-4 py-3 text-right font-mono">{(t.amount || 0).toLocaleString()}</td>
                                        <td className="px-4 py-3">{t.currency}</td>
                                        <td className="px-4 py-3 capitalize">{t.provider}</td>
                                        <td className="px-4 py-3 text-slate-500">{t.network || "—"}</td>
                                        <td className="px-4 py-3 font-mono text-xs truncate max-w-[180px]" title={t.provider_reference}>{t.provider_reference}</td>
                                        <td className="px-4 py-3">
                                            <span className={`inline-flex items-center gap-1 text-[10px] uppercase tracking-widest px-2 py-1 rounded font-bold ${meta.cls}`}>
                                                <Icon size={10} /> {meta.label}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-right">
                                            <button onClick={() => openDetail(t)} data-testid={`tx-view-${t.id}`} className="inline-flex items-center gap-1 text-xs border border-black/10 px-2 py-1 rounded hover:bg-slate-50"><Eye size={12} /> View</button>
                                        </td>
                                    </tr>
                                );
                            })}
                            {sorted.length === 0 && (
                                <tr><td colSpan="10" className="text-center py-12 text-slate-500 text-sm">{loading ? "Loading…" : activeFilters ? "No transactions match these filters." : "No transactions yet."}</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Detail modal */}
            {selected && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-start md:items-center justify-center p-4 overflow-y-auto">
                    <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full my-8" data-testid="tx-detail-modal">
                        <div className="flex items-center justify-between p-6 border-b border-black/5">
                            <div>
                                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Transaction</div>
                                <div className="font-heading text-xl font-bold font-mono">{selected.provider_reference}</div>
                            </div>
                            <button onClick={() => { setSelected(null); setSelectedRaw(null); }} data-testid="tx-detail-close" className="p-2 rounded hover:bg-slate-100"><X size={18} /></button>
                        </div>
                        <div className="p-6 grid md:grid-cols-2 gap-4 text-sm">
                            <KV k="Date" v={fmtDate(selected.date)} />
                            <KV k="Status" v={selected.status} />
                            <KV k="Provider" v={selected.provider} />
                            <KV k="Payment method" v={selected.payment_method_label || "—"} />
                            <KV k="Amount" v={`${(selected.amount || 0).toLocaleString()} ${selected.currency}`} />
                            <KV k="Network" v={selected.network || "—"} />
                            <KV k="Tracking" v={selected.tracking_no || "— (unmatched)"} />
                            <KV k="Source" v={selected.source} />
                            <KV k="Customer" v={selected.customer_name || "—"} />
                            <KV k="Email" v={selected.customer_email || "—"} />
                        </div>
                        {selectedRaw?.application && (
                            <div className="px-6 pb-4">
                                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-2">Linked application</div>
                                <div className="bg-slate-50 rounded-lg px-4 py-3 text-xs grid sm:grid-cols-2 gap-1">
                                    <div><span className="text-slate-500">Visa:</span> {selectedRaw.application.visa_name}</div>
                                    <div><span className="text-slate-500">Status:</span> {selectedRaw.application.status}</div>
                                    <div><span className="text-slate-500">Arrival:</span> {selectedRaw.application.arrival_date}</div>
                                    <div><span className="text-slate-500">Departure:</span> {selectedRaw.application.departure_date}</div>
                                </div>
                            </div>
                        )}
                        <div className="px-6 pb-6">
                            <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-2">Raw source document</div>
                            <pre className="bg-slate-900 text-slate-100 text-[11px] rounded-lg p-4 overflow-auto max-h-[300px]" data-testid="tx-raw-json">{selectedRaw === null ? "Loading…" : JSON.stringify(selectedRaw.raw, null, 2) || "(none)"}</pre>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

const Th = ({ label, sortKey, active, dir, onClick, align }) => (
    <th className={`px-4 py-3 font-semibold ${align === "right" ? "text-right" : ""}`}>
        <button onClick={() => onClick(sortKey)} className={`uppercase tracking-widest text-xs font-semibold inline-flex items-center gap-1 ${active ? "text-ghana-green" : "hover:text-ghana-green"}`} data-testid={`payments-sort-${sortKey}`}>
            {label}
            <span className="text-[9px]">{active ? (dir === "asc" ? "▲" : "▼") : "↕"}</span>
        </button>
    </th>
);

const KV = ({ k, v }) => (
    <div>
        <div className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">{k}</div>
        <div className="font-medium mt-0.5 break-all">{v}</div>
    </div>
);
