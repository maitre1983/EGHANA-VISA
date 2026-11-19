import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { CheckCircle2 } from "lucide-react";

export default function Prices() {
    const [config, setConfig] = useState(null);
    useEffect(() => { api.get("/config").then(({ data }) => setConfig(data)); }, []);

    return (
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Pricing</div>
            <h1 className="mt-2 text-3xl md:text-5xl font-heading font-bold">Transparent pricing</h1>
            <p className="mt-3 text-slate-600 max-w-xl">All prices in USD. Express processing surcharge: <strong>+${config?.express_surcharge_usd || 0}</strong>.</p>

            <div className="mt-10 grid md:grid-cols-3 gap-6">
                {(config?.visa_types || []).map((v) => (
                    <div key={v.code} className={`relative rounded-2xl border p-8 ${v.active ? "border-black/10 bg-white" : "border-black/5 bg-slate-50"}`}>
                        {!v.active && <span className="absolute top-4 right-4 text-[10px] uppercase tracking-widest bg-ghana-gold text-ghana-black px-2 py-1 rounded font-bold">Coming Soon</span>}
                        <div className="h-1 w-16 ghana-stripe-h rounded-sm mb-6" />
                        <h3 className="font-heading text-2xl font-semibold">{v.name_en}</h3>
                        <div className="mt-4 flex items-baseline gap-1">
                            <span className="font-heading text-5xl font-bold text-ghana-black">${v.price_usd}</span>
                            <span className="text-sm text-slate-500">USD</span>
                        </div>
                        <ul className="mt-6 space-y-2 text-sm text-slate-700">
                            <li className="flex items-center gap-2"><CheckCircle2 size={14} className="text-ghana-green" /> {v.days} days validity</li>
                            <li className="flex items-center gap-2"><CheckCircle2 size={14} className="text-ghana-green" /> Regular · {v.processing_time_label || "5–7 business days"}</li>
                            {v.express_available !== false && (
                                <li className="flex items-center gap-2"><CheckCircle2 size={14} className="text-ghana-gold-dark" /> Express +${config?.express_surcharge_usd} · 48–72h</li>
                            )}
                            {v.requires_presence && (
                                <li className="flex items-center gap-2 text-ghana-red"><CheckCircle2 size={14} className="text-ghana-red" /> Presence in Ghana required</li>
                            )}
                            <li className="flex items-center gap-2"><CheckCircle2 size={14} className="text-ghana-green" /> Delivered by email</li>
                        </ul>
                        {v.active ? (
                            <Link to="/apply" data-testid={`prices-select-${v.code}`} className="mt-8 inline-flex items-center gap-2 bg-ghana-black text-white px-5 py-2.5 rounded-md text-sm font-medium hover:bg-ghana-black/90 transition-colors">Apply now</Link>
                        ) : (
                            <button disabled className="mt-8 bg-slate-200 text-slate-500 px-5 py-2.5 rounded-md text-sm font-medium cursor-not-allowed">Not available</button>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
