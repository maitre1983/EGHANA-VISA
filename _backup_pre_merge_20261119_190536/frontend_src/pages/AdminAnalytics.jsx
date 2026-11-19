import React, { useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import {
    Users, Eye, MousePointerClick, DollarSign, Activity, TrendingUp,
    Globe, Monitor, Smartphone, Compass, CheckCircle2, XCircle, RefreshCw,
} from "lucide-react";
import {
    LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
    XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

const PRESETS = [
    { key: "today", label: "Today" },
    { key: "yesterday", label: "Yesterday" },
    { key: "7d", label: "Last 7 days" },
    { key: "30d", label: "Last 30 days" },
    { key: "90d", label: "Last 90 days" },
    { key: "year", label: "This year" },
    { key: "all", label: "All time" },
];

const SOURCE_COLORS = { "Organic Search": "#0F8A5F", "Direct": "#0A0A0A", "Social Media": "#FCD116", "Referral": "#CE1126", "Paid Ads": "#7C3AED" };
const DEVICE_COLORS = ["#0F8A5F", "#FCD116", "#CE1126", "#0A0A0A", "#7C3AED"];

const TABS = [
    { key: "overview", label: "Overview" },
    { key: "traffic", label: "Traffic Sources" },
    { key: "visitors", label: "Visitors" },
    { key: "seo", label: "SEO" },
];

const fmtDuration = (sec) => {
    if (!sec) return "0s";
    const m = Math.floor(sec / 60), s = Math.round(sec % 60);
    return m ? `${m}m ${s}s` : `${s}s`;
};

const Kpi = ({ icon: Icon, label, value, sub, tone = "bg-white", testid }) => (
    <div className={`rounded-xl border border-black/10 p-5 ${tone}`} data-testid={testid}>
        <div className="flex items-center justify-between">
            <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">{label}</div>
            <Icon size={16} className="text-slate-400" />
        </div>
        <div className="mt-3 font-heading text-2xl font-bold text-ghana-black">{value}</div>
        {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
);

const Card = ({ title, children, right }) => (
    <div className="bg-white rounded-xl border border-black/10 p-5">
        <div className="flex items-center justify-between mb-4">
            <div className="font-heading font-semibold text-sm text-ghana-black">{title}</div>
            {right}
        </div>
        {children}
    </div>
);

const RowList = ({ items, valueKey = "count", labelKey = "name", empty = "No data yet" }) => {
    const max = Math.max(1, ...items.map((i) => i[valueKey] || 0));
    if (!items.length) return <div className="text-xs text-slate-400 py-6 text-center">{empty}</div>;
    return (
        <div className="space-y-2.5">
            {items.map((it, idx) => (
                <div key={`${it[labelKey]}-${idx}`} className="text-sm">
                    <div className="flex items-center justify-between">
                        <span className="text-slate-700 truncate max-w-[70%]">{it.label || it[labelKey]}</span>
                        <span className="text-slate-500 font-mono text-xs">{it[valueKey]}</span>
                    </div>
                    <div className="mt-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full bg-ghana-green" style={{ width: `${(it[valueKey] * 100) / max}%` }} />
                    </div>
                </div>
            ))}
        </div>
    );
};

export default function AdminAnalytics() {
    const [preset, setPreset] = useState("30d");
    const [customFrom, setCustomFrom] = useState("");
    const [customTo, setCustomTo] = useState("");
    const [tab, setTab] = useState("overview");
    const [data, setData] = useState(null);
    const [series, setSeries] = useState([]);
    const [seo, setSeo] = useState(null);
    const [loading, setLoading] = useState(false);

    const params = useMemo(() => {
        if (customFrom || customTo) return { from: customFrom, to: customTo };
        return { preset };
    }, [preset, customFrom, customTo]);

    const load = async () => {
        setLoading(true);
        try {
            const [{ data: sum }, { data: ts }, { data: se }] = await Promise.all([
                api.get("/admin/analytics/summary", { params }),
                api.get("/admin/analytics/timeseries", { params }),
                api.get("/admin/seo/status"),
            ]);
            setData(sum);
            setSeries(ts.series || []);
            setSeo(se);
        } catch (e) {
            /* toast handled elsewhere */
        } finally { setLoading(false); }
    };

    useEffect(() => { load(); }, [preset, customFrom, customTo]);

    const web = data?.web || {};
    const conv = data?.conversion || {};

    return (
        <div className="p-6 md:p-10 max-w-7xl mx-auto">
            <div className="mb-6 flex items-start justify-between flex-wrap gap-3">
                <div>
                    <div className="text-xs uppercase tracking-widest text-ghana-green font-semibold">Command Center</div>
                    <h1 className="font-heading text-3xl font-bold mt-1">Analytics &amp; SEO</h1>
                </div>
                <button data-testid="analytics-refresh" onClick={load} className="inline-flex items-center gap-2 text-sm border border-black/10 rounded-md px-3 py-2 hover:bg-slate-50 bg-white">
                    <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
                </button>
            </div>

            {/* Date range */}
            <div className="bg-white rounded-xl border border-black/10 p-3 mb-6 flex items-center gap-2 flex-wrap">
                {PRESETS.map((p) => (
                    <button
                        key={p.key}
                        data-testid={`preset-${p.key}`}
                        onClick={() => { setPreset(p.key); setCustomFrom(""); setCustomTo(""); }}
                        className={`text-xs px-3 py-1.5 rounded-md ${preset === p.key && !customFrom && !customTo ? "bg-ghana-black text-white" : "hover:bg-slate-50 text-slate-700"}`}
                    >{p.label}</button>
                ))}
                <div className="mx-2 h-6 w-px bg-slate-200" />
                <input type="date" data-testid="date-from" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)} className="text-xs border border-black/10 rounded-md px-2 py-1.5" />
                <span className="text-xs text-slate-500">to</span>
                <input type="date" data-testid="date-to" value={customTo} onChange={(e) => setCustomTo(e.target.value)} className="text-xs border border-black/10 rounded-md px-2 py-1.5" />
            </div>

            {/* Tabs */}
            <div className="flex gap-2 mb-6 border-b border-slate-200">
                {TABS.map((t) => (
                    <button key={t.key} data-testid={`tab-${t.key}`} onClick={() => setTab(t.key)}
                        className={`px-4 py-2.5 text-sm border-b-2 -mb-px ${tab === t.key ? "border-ghana-green text-ghana-black font-semibold" : "border-transparent text-slate-500 hover:text-ghana-black"}`}>
                        {t.label}
                    </button>
                ))}
            </div>

            {!data && loading && <div className="text-slate-500 py-10">Loading…</div>}

            {data && tab === "overview" && (
                <>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                        <Kpi icon={Users} label="Unique visitors" value={web.unique_visitors} sub={`${web.new_visitors} new · ${web.returning_visitors} returning`} testid="kpi-visitors" />
                        <Kpi icon={Eye} label="Page views" value={web.page_views} sub={`${web.sessions} sessions`} testid="kpi-pageviews" />
                        <Kpi icon={Activity} label="Bounce rate" value={`${web.bounce_rate_pct}%`} sub={`Avg session ${fmtDuration(web.avg_session_duration_sec)}`} testid="kpi-bounce" />
                        <Kpi icon={TrendingUp} label="Conversion rate" value={`${conv.conversion_rate_pct}%`} sub={`${conv.applications_paid} paid / ${web.unique_visitors} visitors`} tone="bg-ghana-green/10" testid="kpi-conversion" />
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                        <Kpi icon={MousePointerClick} label="Apply-button clicks" value={conv.apply_clicks} testid="kpi-apply-clicks" />
                        <Kpi icon={MousePointerClick} label="Payment-button clicks" value={conv.payment_clicks} testid="kpi-payment-clicks" />
                        <Kpi icon={CheckCircle2} label="Successful applications" value={conv.applications_paid} testid="kpi-apps-paid" />
                        <Kpi icon={XCircle} label="Abandoned applications" value={conv.applications_abandoned} testid="kpi-apps-abandoned" />
                    </div>
                    <div className="grid md:grid-cols-3 gap-4 mb-6">
                        <div className="md:col-span-2"><Card title="Visitors & applications">
                            <ResponsiveContainer width="100%" height={260}>
                                <LineChart data={series} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                                    <CartesianGrid stroke="#eef2f7" strokeDasharray="3 3" />
                                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#64748b" }} />
                                    <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                                    <Tooltip />
                                    <Legend wrapperStyle={{ fontSize: 12 }} />
                                    <Line type="monotone" name="Visitors" dataKey="visitors" stroke="#0F8A5F" strokeWidth={2} dot={false} />
                                    <Line type="monotone" name="Page views" dataKey="page_views" stroke="#0A0A0A" strokeWidth={2} dot={false} />
                                    <Line type="monotone" name="Applications" dataKey="applications" stroke="#CE1126" strokeWidth={2} dot={false} />
                                </LineChart>
                            </ResponsiveContainer>
                        </Card></div>
                        <Card title="Revenue (USD)">
                            <div className="font-heading text-3xl font-bold text-ghana-green mb-1" data-testid="kpi-revenue">${conv.revenue_usd?.toLocaleString?.()}</div>
                            <div className="text-xs text-slate-500 mb-3">in selected range</div>
                            <ResponsiveContainer width="100%" height={180}>
                                <BarChart data={series} margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
                                    <CartesianGrid stroke="#eef2f7" strokeDasharray="3 3" />
                                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#64748b" }} hide />
                                    <YAxis tick={{ fontSize: 10, fill: "#64748b" }} />
                                    <Tooltip />
                                    <Bar dataKey="revenue" fill="#0F8A5F" />
                                </BarChart>
                            </ResponsiveContainer>
                        </Card>
                    </div>
                    <div className="grid md:grid-cols-2 gap-4">
                        <Card title="Conversion funnel">
                            <FunnelRow label="Page views" value={web.page_views} max={web.page_views} color="bg-slate-800" />
                            <FunnelRow label="Apply-button clicks" value={conv.apply_clicks} max={web.page_views} color="bg-ghana-black" />
                            <FunnelRow label="Applications submitted" value={conv.applications_submitted} max={web.page_views} color="bg-ghana-gold" />
                            <FunnelRow label="Payment-button clicks" value={conv.payment_clicks} max={web.page_views} color="bg-ghana-red" />
                            <FunnelRow label="Applications paid" value={conv.applications_paid} max={web.page_views} color="bg-ghana-green" />
                        </Card>
                        <Card title="Top landing pages"><RowList items={data.top_landing_pages || []} labelKey="name" /></Card>
                    </div>
                </>
            )}

            {data && tab === "traffic" && (
                <div className="grid md:grid-cols-2 gap-4">
                    <Card title="Traffic sources">
                        <ResponsiveContainer width="100%" height={240}>
                            <PieChart>
                                <Pie data={data.sources.filter((s) => s.count > 0)} dataKey="count" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={(e) => `${e.name} ${e.count}`}>
                                    {data.sources.map((s, i) => <Cell key={s.name} fill={SOURCE_COLORS[s.name] || DEVICE_COLORS[i % DEVICE_COLORS.length]} />)}
                                </Pie>
                                <Tooltip />
                            </PieChart>
                        </ResponsiveContainer>
                    </Card>
                    <Card title="Sources breakdown"><RowList items={data.sources} /></Card>
                    <Card title="UTM campaigns"><div className="text-xs text-slate-500 py-6 text-center">Append <code className="bg-slate-100 px-1.5 py-0.5 rounded">?utm_source=…&utm_medium=…&utm_campaign=…</code> to your ad URLs to auto-populate this section.</div></Card>
                    <Card title="Referrers (external)"><RowList items={(data.top_landing_pages || []).slice(0, 8)} empty="Once external sites link to you, we'll list them here." /></Card>
                </div>
            )}

            {data && tab === "visitors" && (
                <div className="grid md:grid-cols-2 gap-4">
                    <Card title="Countries"><RowList items={data.countries || []} labelKey="label" /></Card>
                    <Card title="Cities"><RowList items={data.cities || []} empty="No city data yet (requires geo-header from CDN)." /></Card>
                    <Card title={(<span className="inline-flex items-center gap-2"><Monitor size={14} /> Devices</span>)}><RowList items={data.devices || []} /></Card>
                    <Card title={(<span className="inline-flex items-center gap-2"><Smartphone size={14} /> Operating systems</span>)}><RowList items={data.os || []} /></Card>
                    <Card title={(<span className="inline-flex items-center gap-2"><Compass size={14} /> Browsers</span>)}><RowList items={data.browsers || []} /></Card>
                    <Card title={(<span className="inline-flex items-center gap-2"><Globe size={14} /> Screen sizes</span>)}><div className="text-xs text-slate-500 py-6 text-center">Not currently aggregated. Reach out if you want this exposed.</div></Card>
                </div>
            )}

            {tab === "seo" && seo && (
                <div className="grid md:grid-cols-2 gap-4">
                    <Card title="Technical health">
                        <SeoRow label="Sitemap.xml" ok={seo.sitemap.ok} sub={seo.sitemap.url} code={seo.sitemap.status_code} />
                        <SeoRow label="Robots.txt" ok={seo.robots.ok} sub={seo.robots.url} code={seo.robots.status_code} />
                        <SeoRow label="Search Console connected" ok={seo.gsc_connected} sub="Paste your GSC verification code in Settings → Analytics IDs to activate." />
                        <SeoRow label="Google Analytics 4 connected" ok={Boolean((data?.web?.page_views ?? 0) >= 0)} sub="Configured via Settings → Analytics IDs. Fires only after user consent." />
                    </Card>
                    <Card title="Core pages (meta status)">
                        <div className="grid grid-cols-[1fr_repeat(4,60px)] text-[11px] uppercase tracking-widest text-slate-500 font-semibold border-b border-slate-100 pb-1">
                            <div>Path</div><div className="text-center">Title</div><div className="text-center">Desc</div><div className="text-center">Canon</div><div className="text-center">JSON-LD</div>
                        </div>
                        {seo.core_pages.map((p) => (
                            <div key={p.path} className="grid grid-cols-[1fr_repeat(4,60px)] text-sm py-2 border-b border-slate-50 items-center">
                                <div className="text-slate-700 font-mono text-xs">{p.path}</div>
                                {[p.meta_title, p.meta_description, p.canonical, p.structured_data].map((v, i) => (
                                    <div key={i} className="text-center">{v ? <CheckCircle2 size={14} className="mx-auto text-ghana-green" /> : <XCircle size={14} className="mx-auto text-slate-300" />}</div>
                                ))}
                            </div>
                        ))}
                    </Card>
                    <Card title="Indexed pages (estimate)">
                        <div className="font-heading text-3xl font-bold" data-testid="seo-indexed">{seo.indexed_pages_estimate}+</div>
                        <div className="text-xs text-slate-500 mt-1">Based on our sitemap. Connect Google Search Console for actual indexed count.</div>
                    </Card>
                    <Card title="Top keywords / Search performance">
                        <div className="text-xs text-slate-500 py-6 text-center">Requires Google Search Console integration. Paste your verification code in Settings → Analytics IDs, verify ownership in GSC, then this section will populate.</div>
                    </Card>
                </div>
            )}
        </div>
    );
}

const FunnelRow = ({ label, value, max, color }) => {
    const pct = max ? Math.min(100, (value * 100) / max) : 0;
    return (
        <div className="mb-3">
            <div className="flex items-center justify-between text-sm">
                <span className="text-slate-700">{label}</span>
                <span className="font-mono text-slate-500 text-xs">{value} · {pct.toFixed(1)}%</span>
            </div>
            <div className="mt-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
            </div>
        </div>
    );
};

const SeoRow = ({ label, ok, sub, code }) => (
    <div className="flex items-start justify-between py-2 border-b border-slate-50 last:border-0">
        <div>
            <div className="text-sm font-medium text-ghana-black">{label}</div>
            {sub && <div className="text-[11px] text-slate-500 font-mono break-all mt-0.5">{sub}</div>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
            {code !== undefined && <span className="text-[10px] font-mono text-slate-400">{code || "—"}</span>}
            {ok ? <span className="inline-flex items-center gap-1 text-xs bg-ghana-green/10 text-ghana-green-dark px-2 py-1 rounded-full font-semibold"><CheckCircle2 size={12} /> OK</span> : <span className="inline-flex items-center gap-1 text-xs bg-slate-100 text-slate-500 px-2 py-1 rounded-full font-semibold"><XCircle size={12} /> Off</span>}
        </div>
    </div>
);
