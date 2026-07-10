import React, { useEffect, useMemo } from "react";
import { Link, useLocation, Navigate } from "react-router-dom";
import { ArrowRight, ChevronLeft, CheckCircle2, XCircle, Clock, FileText, Camera, Plane, ShieldCheck } from "lucide-react";
import { NATIONALITY_BY_SLUG, NATIONALITY_LIST } from "../data/nationalityData";
import { trackEvent } from "../lib/analytics";

/**
 * Dynamic nationality landing page — /visa-for-{slug}
 * One component per country, generated from the NATIONALITY_LIST dataset.
 * ECOWAS states render a distinct "You do NOT need a visa" experience.
 */
export default function NationalityLanding() {
    const { pathname } = useLocation();
    // pathname looks like "/visa-for-us-citizens" — strip the prefix.
    const slug = pathname.replace(/^\/visa-for-/, "");
    const data = NATIONALITY_BY_SLUG[slug];

    // Deterministic set of "related" nationalities (same region, different slug)
    const related = useMemo(() => {
        if (!data) return [];
        return NATIONALITY_LIST
            .filter((n) => n.region === data.region && n.slug !== data.slug)
            .slice(0, 6);
    }, [data]);

    useEffect(() => {
        if (!data) return;
        const title = data.ecowas
            ? `Ghana Visa for ${data.demonym} Citizens — ECOWAS Exempt | eGhanaVisa`
            : `Ghana Visa for ${data.demonym} Citizens (${data.iso2}) — Apply Online | eGhanaVisa`;
        const description = data.ecowas
            ? `${data.country} is an ECOWAS member state. ${data.demonym} citizens do not need a visa to enter Ghana. Full guide, entry requirements and stay duration.`
            : `Apply online for a Ghana Visa as a ${data.demonym} citizen (${data.country}, ${data.iso2}). Required documents, processing time, fees, embassy details and step-by-step guide.`;
        document.title = title;
        let m = document.querySelector('meta[name="description"]');
        if (!m) { m = document.createElement("meta"); m.name = "description"; document.head.appendChild(m); }
        m.setAttribute("content", description);

        // Canonical
        let canon = document.querySelector('link[rel="canonical"]');
        if (!canon) { canon = document.createElement("link"); canon.rel = "canonical"; document.head.appendChild(canon); }
        canon.setAttribute("href", `https://eghanavisa.com/visa-for-${data.slug}`);

        return () => {
            document.title = "e.GHANA Visa — Fast Ghana Visa On Arrival";
            if (canon) canon.remove();
        };
    }, [data]);

    if (!data) return <Navigate to="/visa-by-nationality" replace />;

    // Schema.org JSON-LD
    const ld = {
        "@context": "https://schema.org",
        "@type": data.ecowas ? "Article" : "TravelAction",
        "name": `Ghana Visa for ${data.demonym} Citizens`,
        "description": `Complete guide for ${data.demonym} nationals travelling from ${data.country} to Ghana.`,
        "areaServed": { "@type": "Country", "name": "Ghana" },
        "provider": { "@type": "Organization", "name": "eGhanaVisa (independent assistance)" },
    };

    const heading = data.ecowas
        ? `Ghana Visa for ${data.demonym} Citizens — ECOWAS Exempt`
        : `Ghana Visa for ${data.demonym} Citizens`;

    return (
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
            <Link to="/visa-by-nationality" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-ghana-black mb-6" data-testid="nationality-back">
                <ChevronLeft size={16} /> All nationalities
            </Link>

            <div className="flex items-start gap-4 mb-4">
                <div className="text-6xl leading-none" aria-hidden data-testid="nationality-flag">{data.flag}</div>
                <div>
                    <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Ghana Visa Guide · {data.region}</div>
                    <h1 className="mt-1 text-3xl md:text-5xl font-heading font-bold" data-testid="nationality-h1">{heading}</h1>
                </div>
            </div>

            {data.ecowas ? <EcowasBanner data={data} /> : <NonEcowasBanner />}

            <div className="mt-10 grid md:grid-cols-2 gap-4">
                <FactCard icon={<Clock size={18} />} label="Processing time" value={data.ecowas ? "No visa needed — enter on your passport" : "Regular 5–7 days · Express 48–72h"} />
                <FactCard icon={<FileText size={18} />} label="Passport requirement" value="Valid 6+ months from arrival · at least 2 blank pages" />
                <FactCard icon={<Camera size={18} />} label="Photo requirement" value={data.ecowas ? "N/A — no visa application" : "Face photo · white background · no glasses"} />
                <FactCard icon={<Plane size={18} />} label="Common departure airport" value={data.airport} />
            </div>

            {!data.ecowas && (
                <>
                    <section className="mt-10 bg-white border border-black/10 rounded-xl p-6">
                        <h2 className="font-heading text-xl font-semibold">Do {data.demonym} citizens need a visa for Ghana?</h2>
                        <p className="mt-2 text-slate-700 leading-relaxed">
                            Yes. <strong>{data.country}</strong> is not an ECOWAS member state, so <strong>{data.demonym} passport holders</strong> require a valid Ghana visa before travelling.
                            The modern route is the online Ghana eVisa, which is fully digital and delivered by email once approved. Our service assists you end-to-end: document review, application submission and secure payment.
                        </p>
                    </section>

                    <section className="mt-4 bg-white border border-black/10 rounded-xl p-6">
                        <h2 className="font-heading text-xl font-semibold">Required documents (from {data.country})</h2>
                        <ul className="mt-3 space-y-2 text-slate-700 text-sm">
                            <li className="flex gap-2"><CheckCircle2 size={16} className="text-ghana-green shrink-0 mt-0.5" /> Colour scan of your {data.demonym} passport data page — must remain valid at least 6 months after your intended departure from Ghana.</li>
                            <li className="flex gap-2"><CheckCircle2 size={16} className="text-ghana-green shrink-0 mt-0.5" /> Recent face photograph on a plain white background, no glasses, no head covering (unless religious).</li>
                            <li className="flex gap-2"><CheckCircle2 size={16} className="text-ghana-green shrink-0 mt-0.5" /> Return or onward flight ticket (departure from your city of residence typically routed through {data.airport}).</li>
                            <li className="flex gap-2"><CheckCircle2 size={16} className="text-ghana-green shrink-0 mt-0.5" /> Confirmation of accommodation in Ghana (hotel booking, invitation letter or host address).</li>
                            <li className="flex gap-2"><CheckCircle2 size={16} className="text-ghana-green shrink-0 mt-0.5" /> Yellow fever vaccination certificate (mandatory upon entry, not before application submission).</li>
                        </ul>
                    </section>

                    <section className="mt-4 bg-white border border-black/10 rounded-xl p-6">
                        <h2 className="font-heading text-xl font-semibold">Processing time &amp; fees for {data.demonym} applicants</h2>
                        <div className="grid sm:grid-cols-3 gap-3 mt-3">
                            {[
                                { t: "Regular", d: "5–7 business days", p: "$350 (Tourist) · $500 (Business)" },
                                { t: "Priority", d: "3 business days", p: "+$25" },
                                { t: "Express", d: "48–72 hours", p: "+$50" },
                            ].map((tier) => (
                                <div key={tier.t} className="border border-black/5 rounded-lg p-4">
                                    <div className="font-heading font-semibold">{tier.t}</div>
                                    <div className="text-xs text-slate-500 mt-1">{tier.d}</div>
                                    <div className="text-sm text-ghana-green font-semibold mt-2">{tier.p}</div>
                                </div>
                            ))}
                        </div>
                        <p className="mt-4 text-xs text-slate-500">Prices displayed in USD. Payment accepted by Visa card (Hubtel) or USDT (TRC20/BEP20).</p>
                    </section>

                    <section className="mt-4 bg-white border border-black/10 rounded-xl p-6">
                        <h2 className="font-heading text-xl font-semibold">How {data.demonym} travellers apply</h2>
                        <ol className="mt-3 space-y-2 text-slate-700 text-sm list-decimal list-inside">
                            <li>Fill our online form — select Tourist or Business, choose your processing tier.</li>
                            <li>Upload your {data.demonym} passport scan, photo and flight ticket.</li>
                            <li>Pay securely in USD (card or USDT with 10% discount).</li>
                            <li>Receive your tracking number instantly and check status any time on the Track page.</li>
                            <li>Get your approved e-Visa by email — print it and travel with your passport.</li>
                        </ol>
                    </section>
                </>
            )}

            <div className="mt-10 flex flex-col sm:flex-row gap-3">
                {!data.ecowas && (
                    <Link
                        to="/apply"
                        onClick={() => trackEvent("apply_click", { source: "nationality-cta", slug: data.slug })}
                        data-testid="nationality-cta-apply"
                        className="inline-flex items-center gap-2 bg-ghana-green text-white px-6 py-3.5 rounded-md font-medium hover:bg-ghana-green-dark transition-colors"
                    >
                        Apply as a {data.demonym} citizen <ArrowRight size={16} />
                    </Link>
                )}
                <Link to="/faq" className="inline-flex items-center gap-2 bg-white text-ghana-black px-6 py-3.5 rounded-md font-medium border border-black/10 hover:bg-slate-50">
                    See full FAQ
                </Link>
                <Link to="/prices" className="inline-flex items-center gap-2 bg-white text-ghana-black px-6 py-3.5 rounded-md font-medium border border-black/10 hover:bg-slate-50">
                    View all prices
                </Link>
            </div>

            <div className="mt-12 border-t border-black/5 pt-6">
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-3">Also for travellers from {data.region}</div>
                <div className="flex flex-wrap gap-2" data-testid="nationality-related">
                    {related.map((n) => (
                        <Link key={n.slug} to={`/visa-for-${n.slug}`} className="text-xs bg-slate-100 hover:bg-slate-200 text-ghana-black px-3 py-1.5 rounded-full transition-colors inline-flex items-center gap-1.5">
                            <span aria-hidden>{n.flag}</span> {n.demonym}
                        </Link>
                    ))}
                </div>
            </div>

            <div className="mt-10 text-xs text-slate-500 bg-slate-50 border border-black/5 rounded-md px-4 py-3">
                <strong>Independent third-party assistance:</strong> eGhanaVisa.com is not affiliated with the Government of Ghana, the Ghana Immigration Service or any Ghanaian embassy. We assist travellers with their visa application in exchange for a service fee.
            </div>

            <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(ld) }} />
        </div>
    );
}

const EcowasBanner = ({ data }) => (
    <div className="mt-6 bg-ghana-green/10 border border-ghana-green text-ghana-green-dark rounded-lg px-5 py-4 flex items-start gap-3" data-testid="ecowas-banner">
        <CheckCircle2 size={20} className="shrink-0 mt-0.5" />
        <div className="text-sm leading-relaxed">
            <strong>Great news — no Ghana visa required.</strong> {data.country} is one of the 16 ECOWAS member states. Under the ECOWAS free-movement protocol, {data.demonym} citizens can enter Ghana with a valid national passport or ECOWAS travel certificate for up to 90 days without a visa.
        </div>
    </div>
);

const NonEcowasBanner = () => (
    <div className="mt-6 bg-ghana-gold/15 border border-ghana-gold text-ghana-black rounded-lg px-5 py-4 flex items-start gap-3">
        <ShieldCheck size={20} className="shrink-0 mt-0.5 text-ghana-green" />
        <div className="text-sm leading-relaxed">
            <strong>Ghana visa required.</strong> Apply online in a few minutes — we handle the paperwork and deliver the approved e-Visa to your inbox.
        </div>
    </div>
);

const FactCard = ({ icon, label, value }) => (
    <div className="bg-white border border-black/10 rounded-xl p-5">
        <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-slate-500 font-semibold">
            <span className="text-ghana-green">{icon}</span> {label}
        </div>
        <div className="mt-2 text-sm text-ghana-black font-medium">{value}</div>
    </div>
);
