import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Search, CheckCircle2, Clock, FileText } from "lucide-react";
import api from "../lib/api";

const STATUSES = [
    { key: "submitted", label: "Submitted", desc: "We've received your application and payment." },
    { key: "in_progress", label: "In Progress", desc: "Ghana Immigration is reviewing your file." },
    { key: "done", label: "Done", desc: "Approved — your e-Visa is on its way to your inbox." },
];

export default function Track() {
    const [search] = useSearchParams();
    const [number, setNumber] = useState(search.get("number") || "");
    const [result, setResult] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const doTrack = async (e) => {
        e?.preventDefault();
        if (!number) return;
        setLoading(true); setError(""); setResult(null);
        try {
            const { data } = await api.get(`/track/${number.trim()}`);
            setResult(data);
        } catch (err) {
            setError("Application not found. Please double-check your tracking number.");
        } finally { setLoading(false); }
    };

    useEffect(() => { if (search.get("number")) doTrack(); /* eslint-disable-next-line */ }, []);

    const currentIdx = result ? STATUSES.findIndex((s) => s.key === result.status) : -1;

    return (
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Tracking</div>
            <h1 className="mt-2 text-3xl md:text-4xl font-heading font-bold">Track your application</h1>
            <p className="mt-3 text-slate-600">Enter the tracking number we sent to your email.</p>

            <form onSubmit={doTrack} className="mt-8 flex flex-col sm:flex-row gap-3">
                <div className="flex-1 relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                    <input
                        value={number}
                        onChange={(e) => setNumber(e.target.value.toUpperCase())}
                        placeholder="GH-2026-XXXXXX"
                        data-testid="track-input"
                        className="w-full pl-10 pr-4 py-3.5 rounded-md border border-black/10 focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none bg-white font-mono"
                    />
                </div>
                <button type="submit" data-testid="track-btn" disabled={loading || !number}
                    className="bg-ghana-green text-white px-6 py-3.5 rounded-md text-sm font-medium hover:bg-ghana-green-dark transition-colors disabled:opacity-50">
                    {loading ? "Searching…" : "Track"}
                </button>
            </form>

            {error && <div className="mt-6 text-sm text-ghana-red" data-testid="track-error">{error}</div>}

            {result && (
                <div className="mt-10 bg-white border border-black/10 rounded-xl p-8 shadow-sm" data-testid="track-result">
                    <div className="flex items-start justify-between gap-4 flex-wrap">
                        <div>
                            <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Application</div>
                            <div className="font-heading text-2xl font-bold mt-1">{result.tracking_no}</div>
                            <div className="text-sm text-slate-600 mt-1">{result.visa_name} · {result.processing === "express" ? "Express" : "Regular"}</div>
                        </div>
                        <span className={`px-3 py-1.5 rounded-full text-xs uppercase tracking-widest font-bold ${
                            result.status === "done" ? "bg-ghana-green text-white" :
                            result.status === "in_progress" ? "bg-ghana-gold text-ghana-black" :
                            "bg-ghana-black text-white"
                        }`}>{result.status.replace("_", " ")}</span>
                    </div>

                    <div className="mt-10 relative border-l-2 border-slate-200 ml-4 space-y-8">
                        {STATUSES.map((s, i) => {
                            const active = i <= currentIdx;
                            const current = i === currentIdx;
                            const ts = result[`${s.key === "submitted" ? "paid" : s.key}_at`];
                            return (
                                <div key={s.key} className="relative pl-8">
                                    <div className={`absolute -left-[9px] top-0 w-4 h-4 rounded-full border-2 border-white ${current ? "bg-ghana-gold" : active ? "bg-ghana-green" : "bg-slate-300"}`} />
                                    <div className="font-heading font-semibold flex items-center gap-2">
                                        {s.label}
                                        {current && <span className="text-[10px] uppercase tracking-widest bg-ghana-gold text-ghana-black px-2 py-0.5 rounded font-bold">Current</span>}
                                    </div>
                                    <div className="text-sm text-slate-500">{s.desc}</div>
                                    {ts && <div className="text-xs text-slate-400 mt-1">{new Date(ts).toLocaleString()}</div>}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}
