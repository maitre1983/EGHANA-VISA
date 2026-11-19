import React, { useEffect, useState } from "react";
import { X, Cookie, ShieldCheck } from "lucide-react";
import { readConsent, hasChosen, writeConsent, acceptAll, rejectNonEssential } from "../lib/consent";

const CATEGORIES = [
    {
        key: "essential",
        title: "Essential Cookies",
        pill: "Always active",
        locked: true,
        desc: "Required for the website to function — secure sessions, form submissions and remembering your progress through the application. These cannot be turned off.",
    },
    {
        key: "analytics",
        title: "Analytics Cookies",
        desc: "Anonymous visitor statistics we use to understand which pages help travelers and where they get stuck. Includes our own first-party analytics and, if configured, Google Analytics 4 & Microsoft Clarity.",
    },
    {
        key: "marketing",
        title: "Marketing Cookies",
        desc: "Only used if we later enable advertising or remarketing. Currently off by default and no ad networks are loaded.",
    },
    {
        key: "functional",
        title: "Functional Cookies",
        desc: "Remembers your preferences such as language, layout and interface settings so the site feels the same on each visit.",
    },
];

export default function CookieConsent() {
    const [visible, setVisible] = useState(false);
    const [detailsOpen, setDetailsOpen] = useState(false);
    const [choices, setChoices] = useState({ essential: true, analytics: false, marketing: false, functional: false });

    useEffect(() => {
        // Show banner only on first visit
        if (!hasChosen()) setVisible(true);
        const existing = readConsent();
        if (existing) setChoices(existing);

        const openHandler = () => {
            const cur = readConsent() || { essential: true, analytics: false, marketing: false, functional: false };
            setChoices(cur);
            setDetailsOpen(true);
            setVisible(true);
        };
        window.addEventListener("egv:consent-open", openHandler);
        return () => window.removeEventListener("egv:consent-open", openHandler);
    }, []);

    const finish = (fn) => { fn(); setVisible(false); setDetailsOpen(false); };
    const saveCustom = () => finish(() => writeConsent(choices));

    if (!visible) return null;

    return (
        <div className="fixed inset-x-0 bottom-0 z-[70] px-4 pb-4 md:pb-6" data-testid="cookie-consent">
            <div className="max-w-5xl mx-auto rounded-2xl shadow-2xl border border-black/10 bg-white overflow-hidden">
                {!detailsOpen ? (
                    <div className="p-5 md:p-6 grid md:grid-cols-[auto_1fr_auto] gap-5 items-center">
                        <div className="w-12 h-12 rounded-full bg-ghana-gold/20 text-ghana-black flex items-center justify-center">
                            <Cookie size={22} />
                        </div>
                        <div>
                            <div className="font-heading font-semibold text-base text-ghana-black">We value your privacy</div>
                            <p className="text-sm text-slate-600 mt-1 leading-relaxed">
                                We use cookies to improve your browsing experience and collect anonymous statistics that help us improve our services. You can accept or refuse non-essential cookies at any time.
                            </p>
                        </div>
                        <div className="flex flex-col md:flex-row gap-2 md:items-center">
                            <button
                                data-testid="consent-reject"
                                onClick={() => finish(rejectNonEssential)}
                                className="text-sm px-4 py-2.5 border border-black/10 rounded-md hover:bg-slate-50 whitespace-nowrap"
                            >
                                Reject non-essential
                            </button>
                            <button
                                data-testid="consent-customize"
                                onClick={() => setDetailsOpen(true)}
                                className="text-sm px-4 py-2.5 border border-black/10 rounded-md hover:bg-slate-50 whitespace-nowrap"
                            >
                                Customize
                            </button>
                            <button
                                data-testid="consent-accept-all"
                                onClick={() => finish(acceptAll)}
                                className="text-sm px-4 py-2.5 bg-ghana-green text-white rounded-md hover:bg-ghana-green-dark font-medium whitespace-nowrap"
                            >
                                Accept all
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="p-5 md:p-6 max-h-[80vh] overflow-y-auto">
                        <div className="flex items-start justify-between gap-4 mb-4">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-full bg-ghana-gold/20 flex items-center justify-center"><ShieldCheck size={18} /></div>
                                <div>
                                    <div className="font-heading font-semibold text-base">Cookie preferences</div>
                                    <div className="text-xs text-slate-500">Choose which categories you allow. You can change this any time from the footer.</div>
                                </div>
                            </div>
                            <button onClick={() => { setDetailsOpen(false); if (hasChosen()) setVisible(false); }} data-testid="consent-close" className="text-slate-400 hover:text-ghana-black"><X size={20} /></button>
                        </div>
                        <div className="space-y-3">
                            {CATEGORIES.map((c) => (
                                <div key={c.key} className="border border-black/10 rounded-lg p-4">
                                    <div className="flex items-start justify-between gap-4">
                                        <div>
                                            <div className="font-heading font-semibold text-sm text-ghana-black">{c.title}</div>
                                            <p className="text-xs text-slate-600 mt-1 leading-relaxed">{c.desc}</p>
                                        </div>
                                        {c.locked ? (
                                            <span className="text-[10px] uppercase tracking-widest bg-ghana-green/10 text-ghana-green-dark px-2 py-1 rounded-full font-semibold whitespace-nowrap">Always active</span>
                                        ) : (
                                            <label className="inline-flex items-center cursor-pointer shrink-0">
                                                <input
                                                    type="checkbox"
                                                    className="sr-only"
                                                    checked={Boolean(choices[c.key])}
                                                    onChange={(e) => setChoices((old) => ({ ...old, [c.key]: e.target.checked }))}
                                                    data-testid={`consent-toggle-${c.key}`}
                                                />
                                                <span className={`relative w-11 h-6 rounded-full transition-colors ${choices[c.key] ? "bg-ghana-green" : "bg-slate-300"}`}>
                                                    <span className={`absolute top-0.5 ${choices[c.key] ? "left-5" : "left-0.5"} w-5 h-5 bg-white rounded-full transition-all`} />
                                                </span>
                                            </label>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="mt-5 flex flex-col md:flex-row gap-2 md:justify-end">
                            <button
                                data-testid="consent-reject-2"
                                onClick={() => finish(rejectNonEssential)}
                                className="text-sm px-4 py-2.5 border border-black/10 rounded-md hover:bg-slate-50"
                            >
                                Reject non-essential
                            </button>
                            <button
                                data-testid="consent-save"
                                onClick={saveCustom}
                                className="text-sm px-4 py-2.5 border border-ghana-green text-ghana-green rounded-md hover:bg-ghana-green/5 font-medium"
                            >
                                Save preferences
                            </button>
                            <button
                                data-testid="consent-accept-all-2"
                                onClick={() => finish(acceptAll)}
                                className="text-sm px-4 py-2.5 bg-ghana-green text-white rounded-md hover:bg-ghana-green-dark font-medium"
                            >
                                Accept all
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
