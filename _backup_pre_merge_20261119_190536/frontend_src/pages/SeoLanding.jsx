import React, { useEffect } from "react";
import { Link, useLocation, Navigate } from "react-router-dom";
import { ArrowRight, ChevronLeft } from "lucide-react";
import { SEO_PAGES } from "../data/seoPages";

/**
 * Dynamic SEO landing page — one component serves any SEO_PAGES entry.
 * Slug is derived from location.pathname to keep routes explicit for SEO.
 */
export default function SeoLanding() {
    const { pathname } = useLocation();
    const slug = pathname.replace(/^\/+/, "").split("/")[0];
    const page = SEO_PAGES[slug];

    useEffect(() => {
        if (!page) return;
        document.title = page.title;
        let m = document.querySelector('meta[name="description"]');
        if (!m) { m = document.createElement("meta"); m.name = "description"; document.head.appendChild(m); }
        m.setAttribute("content", page.description);
        return () => { document.title = "e.GHANA Visa — Fast Ghana Visa On Arrival"; };
    }, [page]);

    if (!page) return <Navigate to="/" replace />;

    // Schema.org FAQPage JSON-LD
    const faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": page.sections.map((s) => ({
            "@type": "Question",
            "name": s.h,
            "acceptedAnswer": { "@type": "Answer", "text": s.p },
        })),
    };

    return (
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
            <Link to="/" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-ghana-black mb-6" data-testid="seo-back">
                <ChevronLeft size={16} /> Home
            </Link>
            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Guide</div>
            <h1 className="mt-2 text-3xl md:text-5xl font-heading font-bold" data-testid="seo-h1">{page.h1}</h1>
            <p className="mt-4 text-lg text-slate-600">{page.intro}</p>

            <div className="mt-10 space-y-6">
                {page.sections.map((s) => (
                    <section key={s.h} className="bg-white border border-black/10 rounded-xl p-6">
                        <h2 className="font-heading text-xl font-semibold">{s.h}</h2>
                        <p className="mt-2 text-slate-700 leading-relaxed">{s.p}</p>
                    </section>
                ))}
            </div>

            <div className="mt-10 flex flex-col sm:flex-row gap-3">
                <Link to="/apply" data-testid="seo-cta-apply" className="inline-flex items-center gap-2 bg-ghana-green text-white px-6 py-3.5 rounded-md font-medium hover:bg-ghana-green-dark transition-colors">
                    {page.cta} <ArrowRight size={16} />
                </Link>
                <Link to="/faq" className="inline-flex items-center gap-2 bg-white text-ghana-black px-6 py-3.5 rounded-md font-medium border border-black/10 hover:bg-slate-50">
                    See full FAQ
                </Link>
            </div>

            {/* Internal linking */}
            <div className="mt-10 border-t border-black/5 pt-6">
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-3">Related guides</div>
                <div className="flex flex-wrap gap-2">
                    {Object.keys(SEO_PAGES).filter((k) => k !== slug).slice(0, 6).map((k) => (
                        <Link key={k} to={`/${k}`} className="text-xs bg-slate-100 hover:bg-slate-200 text-ghana-black px-3 py-1.5 rounded-full transition-colors">
                            {SEO_PAGES[k].h1}
                        </Link>
                    ))}
                </div>
            </div>

            {/* Compliance disclaimer */}
            <div className="mt-10 text-xs text-slate-500 bg-slate-50 border border-black/5 rounded-md px-4 py-3">
                <strong>Independent third-party assistance:</strong> eGhanaVisa.com is not affiliated with the Government of Ghana, the Ghana Immigration Service or the Ministry of Foreign Affairs.
            </div>

            <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faq) }} />
        </div>
    );
}
