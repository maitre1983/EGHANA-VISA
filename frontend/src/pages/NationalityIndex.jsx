import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { NATIONALITY_LIST, REGIONS, NATIONALITY_COUNT } from "../data/nationalityData";

/**
 * Index of all nationality landing pages. Serves as:
 * - SEO hub (interlinks 150+ country pages)
 * - Human-usable A-Z directory
 * - Sitemap seed
 */
export default function NationalityIndex() {
    const [q, setQ] = useState("");
    const [region, setRegion] = useState("All");

    useEffect(() => {
        document.title = `Ghana Visa by Nationality — ${NATIONALITY_COUNT}+ Countries | eGhanaVisa`;
        let m = document.querySelector('meta[name="description"]');
        if (!m) { m = document.createElement("meta"); m.name = "description"; document.head.appendChild(m); }
        m.setAttribute("content", `Ghana Visa requirements for ${NATIONALITY_COUNT}+ nationalities. Country-by-country guide covering eligibility, documents, processing time, fees and ECOWAS exemptions.`);
        return () => { document.title = "e.GHANA Visa — Fast Ghana Visa On Arrival"; };
    }, []);

    const filtered = useMemo(() => {
        const ql = q.trim().toLowerCase();
        return NATIONALITY_LIST.filter((n) => {
            if (region !== "All" && n.region !== region) return false;
            if (!ql) return true;
            return n.country.toLowerCase().includes(ql) || n.demonym.toLowerCase().includes(ql) || n.iso2.toLowerCase().includes(ql);
        });
    }, [q, region]);

    const grouped = useMemo(() => {
        const g = {};
        for (const n of filtered) (g[n.region] = g[n.region] || []).push(n);
        for (const r of Object.keys(g)) g[r].sort((a, b) => a.country.localeCompare(b.country));
        return g;
    }, [filtered]);

    return (
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Country directory</div>
            <h1 className="mt-2 text-3xl md:text-5xl font-heading font-bold" data-testid="nationality-index-h1">Ghana Visa by Nationality</h1>
            <p className="mt-4 text-lg text-slate-600 max-w-3xl">
                Choose your passport country to view the visa requirements, processing options and step-by-step guide tailored to your nationality. Covering <strong>{NATIONALITY_COUNT}+ countries</strong> including all ECOWAS-exempt nations.
            </p>

            {/* Filters */}
            <div className="mt-8 flex flex-col md:flex-row gap-3 md:items-center">
                <div className="relative flex-1">
                    <Search size={16} className="absolute left-3 top-3 text-slate-400" />
                    <input
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        placeholder="Search country, demonym or ISO code…"
                        data-testid="nationality-search"
                        className="w-full pl-9 pr-3 py-2.5 border border-black/10 rounded-md text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none"
                    />
                </div>
                <div className="flex gap-1.5 flex-wrap">
                    <button onClick={() => setRegion("All")} data-testid="region-All" className={`text-xs px-3 py-1.5 rounded-md ${region === "All" ? "bg-ghana-black text-white" : "border border-black/10 hover:bg-slate-50"}`}>All ({NATIONALITY_COUNT})</button>
                    {REGIONS.map((r) => (
                        <button key={r} onClick={() => setRegion(r)} data-testid={`region-${r.replace(/\s+/g, "-")}`} className={`text-xs px-3 py-1.5 rounded-md ${region === r ? "bg-ghana-black text-white" : "border border-black/10 hover:bg-slate-50"}`}>{r}</button>
                    ))}
                </div>
            </div>

            {/* Groups */}
            <div className="mt-10 space-y-10">
                {Object.entries(grouped).map(([r, list]) => (
                    <section key={r}>
                        <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-3">{r} <span className="text-slate-400">· {list.length}</span></div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                            {list.map((n) => (
                                <Link
                                    key={n.slug}
                                    to={`/visa-for-${n.slug}`}
                                    data-testid={`nat-link-${n.slug}`}
                                    className="group flex items-center gap-3 p-3 border border-black/5 rounded-lg hover:border-ghana-green hover:bg-ghana-green/5 transition-colors"
                                >
                                    <span className="text-2xl leading-none" aria-hidden>{n.flag}</span>
                                    <div className="min-w-0">
                                        <div className="text-sm font-medium text-ghana-black truncate">{n.country}</div>
                                        <div className="text-[11px] text-slate-500 truncate">
                                            {n.ecowas ? <span className="text-ghana-green font-semibold">ECOWAS exempt</span> : `${n.demonym} · ${n.iso2}`}
                                        </div>
                                    </div>
                                </Link>
                            ))}
                        </div>
                    </section>
                ))}
                {filtered.length === 0 && (
                    <div className="text-center py-12 text-slate-500 text-sm">No countries match your search.</div>
                )}
            </div>
        </div>
    );
}
