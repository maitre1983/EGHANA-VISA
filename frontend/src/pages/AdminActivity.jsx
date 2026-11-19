import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { toast } from "sonner";
import { RefreshCw, Search, ChevronLeft, ChevronRight } from "lucide-react";
import { fmtDateTime, PageHeader } from "../lib/adminUi";

const LABELS = [
    [/^\/api\/admin\/login$/, "Signed in"],
    [/^\/api\/admin\/credentials$/, "Changed login credentials"],
    [/^\/api\/admin\/applications\/[^/]+\/status$/, "Changed application status"],
    [/^\/api\/admin\/applications\/[^/]+\/documents\//, "Viewed applicant document"],
    [/^\/api\/admin\/applications\/[^/]+$/, "Deleted application"],
    [/^\/api\/admin\/transactions\.(csv|xlsx)$/, "Exported transactions"],
    [/^\/api\/admin\/settings\/([^/]+)/, (m) => `Updated setting: ${m[1].replace(/-/g, " ")}`],
    [/^\/api\/admin\/email-templates$/, "Edited email template"],
    [/^\/api\/admin\/email\/test$/, "Sent test email"],
    [/^\/api\/admin\/sms\/test$/, "Sent test SMS"],
    [/^\/api\/admin\/support-tickets\/[^/]+\/reply$/, "Replied to Abena ticket"],
    [/^\/api\/admin\/support-tickets\/[^/]+\/status$/, "Changed ticket status"],
    [/^\/api\/admin\/health\/check$/, "Ran gateway health check"],
    [/^\/api\/admin\/cleanup\//, "Data cleanup"],
    [/^\/api\/admin\/storage\/test$/, "Tested storage"],
];

const describe = (path) => {
    for (const [re, l] of LABELS) {
        const m = path.match(re);
        if (m) return typeof l === "function" ? l(m) : l;
    }
    return path.replace("/api/admin/", "");
};

export default function AdminActivity() {
    const [data, setData] = useState({ items: [], total: 0, admins: [] });
    const [search, setSearch] = useState("");
    const [admin, setAdmin] = useState("");
    const [onlyFailed, setOnlyFailed] = useState(false);
    const [page, setPage] = useState(1);
    const [open, setOpen] = useState(null);
    const pageSize = 50;

    const load = async () => {
        try {
            const { data } = await api.get("/admin/audit-log", { params: { search, admin_email: admin, only_failed: onlyFailed, page, page_size: pageSize } });
            setData(data);
        } catch { toast.error("Could not load activity"); }
    };
    useEffect(() => { load(); }, [admin, onlyFailed, page]); // eslint-disable-line react-hooks/exhaustive-deps
    const pages = Math.max(1, Math.ceil(data.total / pageSize));

    return (
        <div className="p-6 md:p-10 max-w-7xl" data-testid="admin-activity-page">
            <PageHeader title="Activity Log" subtitle="Every change made in the Command Center — who, what and when.">
                <button onClick={load} data-testid="activity-refresh" className="inline-flex items-center gap-2 text-sm bg-white border border-black/10 px-3 py-2 rounded-md hover:bg-slate-50"><RefreshCw size={14} /> Refresh</button>
            </PageHeader>
            <div className="mt-6 flex flex-wrap gap-3 items-center">
                <form onSubmit={(e) => { e.preventDefault(); setPage(1); load(); }} className="relative">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter by action (e.g. settings, tracking no)" data-testid="activity-search"
                        className="pl-9 pr-3 py-2 w-80 border border-black/10 rounded-md text-sm bg-white focus:border-ghana-green outline-none" />
                </form>
                <select value={admin} onChange={(e) => { setAdmin(e.target.value); setPage(1); }} data-testid="activity-admin-filter" className="border border-black/10 rounded-md px-3 py-2 text-sm bg-white">
                    <option value="">All admins</option>
                    {data.admins.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
                <label className="inline-flex items-center gap-2 text-sm text-slate-600">
                    <input type="checkbox" checked={onlyFailed} onChange={(e) => { setOnlyFailed(e.target.checked); setPage(1); }} data-testid="activity-only-failed" /> Failed actions only
                </label>
                <span className="text-sm text-slate-500 ml-auto" data-testid="activity-total">{data.total} entries</span>
            </div>
            <div className="mt-4 bg-white rounded-xl border border-black/10 overflow-x-auto">
                <table className="w-full text-sm" data-testid="activity-table">
                    <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                        <tr><th className="text-left p-3">When</th><th className="text-left p-3">Admin</th><th className="text-left p-3">Action</th><th className="text-left p-3">Result</th><th className="text-left p-3">IP</th></tr>
                    </thead>
                    <tbody className="divide-y divide-black/5">
                        {data.items.length === 0 && <tr><td colSpan={5} className="p-8 text-center text-slate-500">No activity yet.</td></tr>}
                        {data.items.map((it) => <Row key={it.id} it={it} open={open === it.id} onToggle={() => setOpen(open === it.id ? null : it.id)} />)}
                    </tbody>
                </table>
            </div>
            <div className="mt-4 flex items-center justify-end gap-2 text-sm">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid="activity-prev" className="p-2 border border-black/10 rounded-md bg-white disabled:opacity-40"><ChevronLeft size={14} /></button>
                <span data-testid="activity-page">Page {page} / {pages}</span>
                <button disabled={page >= pages} onClick={() => setPage(page + 1)} data-testid="activity-next" className="p-2 border border-black/10 rounded-md bg-white disabled:opacity-40"><ChevronRight size={14} /></button>
            </div>
        </div>
    );
}

const Row = ({ it, open, onToggle }) => (
    <>
        <tr onClick={onToggle} className="hover:bg-slate-50 cursor-pointer" data-testid={`activity-row-${it.id}`}>
            <td className="p-3 whitespace-nowrap text-slate-600">{fmtDateTime(it.created_at)}</td>
            <td className="p-3">{it.admin_email || "—"}</td>
            <td className="p-3"><div className="font-medium">{describe(it.path)}</div><div className="text-xs text-slate-400 font-mono">{it.method} {it.path}</div></td>
            <td className="p-3"><span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${it.success ? "bg-ghana-green/10 text-ghana-green" : "bg-ghana-red/10 text-ghana-red"}`}>{it.success ? "OK" : "Failed"} · {it.status_code}</span></td>
            <td className="p-3 text-xs font-mono text-slate-500">{it.ip || "—"}</td>
        </tr>
        {open && (
            <tr><td colSpan={5} className="bg-slate-50 p-4">
                <pre className="text-xs font-mono whitespace-pre-wrap break-all" data-testid="activity-details">{it.details ? JSON.stringify(it.details, null, 2) : "No details"}{it.query ? `\n\nquery: ${it.query}` : ""}</pre>
            </td></tr>
        )}
    </>
);
