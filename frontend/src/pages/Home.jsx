import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ShieldCheck, Clock, FileText, Sparkles, ArrowRight, CheckCircle2 } from "lucide-react";
import api from "../lib/api";

export default function Home() {
    const [config, setConfig] = useState(null);
    useEffect(() => { api.get("/config").then(({ data }) => setConfig(data)).catch(() => {}); }, []);

    return (
        <div>
            {/* Hero */}
            <section className="relative overflow-hidden bg-white">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 md:py-28 grid md:grid-cols-2 gap-12 items-center">
                    <div className="animate-fade-up">
                        <div className="inline-flex items-center gap-2 bg-ghana-green/10 text-ghana-green px-3 py-1 rounded-full text-xs font-semibold tracking-widest uppercase">
                            <span className="w-1.5 h-1.5 rounded-full bg-ghana-green animate-pulse" />
                            Official Portal · e-Visa Ready
                        </div>
                        <h1 className="mt-6 text-4xl sm:text-5xl lg:text-6xl font-heading font-bold tracking-tight text-ghana-black leading-[1.05]">
                            Your <span className="text-ghana-green">Ghana</span> visa,<br />
                            <span className="text-ghana-red">approved</span> in as little as <span className="text-ghana-black">48 hours</span>.
                        </h1>
                        <p className="mt-6 text-lg text-slate-600 max-w-lg">
                            Skip the queue at Kotoka Airport. Apply online, upload your documents and receive your Visa On Arrival by email.
                        </p>
                        <div className="mt-8 flex flex-wrap gap-3">
                            <Link
                                to="/apply"
                                data-testid="hero-apply-cta"
                                className="inline-flex items-center gap-2 bg-ghana-green text-white px-6 py-3.5 rounded-md font-medium hover:bg-ghana-green-dark transition-colors"
                            >
                                Start Application <ArrowRight size={16} />
                            </Link>
                            <Link
                                to="/track"
                                data-testid="hero-track-cta"
                                className="inline-flex items-center gap-2 bg-white text-ghana-black px-6 py-3.5 rounded-md font-medium border border-black/10 hover:bg-slate-50 transition-colors"
                            >
                                Track My Visa
                            </Link>
                        </div>
                        <div className="mt-10 grid grid-cols-3 gap-6 max-w-md">
                            {[
                                { k: "150+", v: "Countries" },
                                { k: "48h", v: "Express" },
                                { k: "100%", v: "Secure" },
                            ].map((s) => (
                                <div key={s.v}>
                                    <div className="font-heading text-3xl font-bold text-ghana-black">{s.k}</div>
                                    <div className="text-xs uppercase tracking-widest text-slate-500 mt-1">{s.v}</div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Right: Visa card mock hero visual */}
                    <div className="relative animate-fade-up">
                        <div className="absolute -top-6 -right-6 w-64 h-64 rounded-full bg-ghana-gold/30 blur-3xl" />
                        <div className="absolute -bottom-6 -left-6 w-64 h-64 rounded-full bg-ghana-green/20 blur-3xl" />
                        <div className="relative bg-white rounded-2xl border border-black/10 shadow-xl overflow-hidden">
                            <div className="ghana-stripe h-2" />
                            <img
                                src="https://images.unsplash.com/photo-1707209210229-a32ec4b62b51?crop=entropy&cs=srgb&fm=jpg&q=80&w=900"
                                alt="Accra, Ghana"
                                className="w-full h-72 object-cover"
                                loading="lazy"
                            />
                            <div className="p-6">
                                <div className="flex items-center gap-3 text-xs uppercase tracking-widest text-slate-500 mb-2">
                                    <div className="black-star scale-50" /> <span>Akwaaba — Welcome home</span>
                                </div>
                                <h3 className="font-heading text-xl font-semibold">Ghana Visa On Arrival</h3>
                                <p className="text-sm text-slate-600 mt-2">Fully electronic. Delivered by email. Valid at all Ghanaian entry points.</p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Trust bar */}
            <section className="border-y border-black/5 bg-slate-50">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 grid grid-cols-2 md:grid-cols-4 gap-6">
                    {[
                        { icon: <ShieldCheck size={20} />, t: "Encrypted uploads" },
                        { icon: <Clock size={20} />, t: "48h Express" },
                        { icon: <FileText size={20} />, t: "Third-party portal" },
                        { icon: <Sparkles size={20} />, t: "AI-assisted (Ama)" },
                    ].map((x) => (
                        <div key={x.t} className="flex items-center gap-3 text-sm text-slate-700">
                            <div className="w-10 h-10 rounded-lg bg-white border border-black/5 flex items-center justify-center text-ghana-green">{x.icon}</div>
                            <span className="font-medium">{x.t}</span>
                        </div>
                    ))}
                </div>
            </section>

            {/* How it works */}
            <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
                <div className="max-w-2xl">
                    <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Process</div>
                    <h2 className="mt-3 text-3xl md:text-4xl font-heading font-bold">Three steps. That's it.</h2>
                    <p className="mt-4 text-slate-600">A modern, transparent workflow — no queues, no paperwork nightmares.</p>
                </div>

                <div className="mt-14 grid md:grid-cols-3 gap-6">
                    {[
                        { n: "01", t: "Fill the application", d: "Enter your passport details, travel dates and profession. Upload your face photo, passport and flight ticket." },
                        { n: "02", t: "Pay by Visa card", d: "Secure Hubtel payment gateway. Get an instant tracking number the moment payment succeeds." },
                        { n: "03", t: "Receive your visa", d: "Track your application live. Your approved e-Visa is delivered straight to your email inbox." },
                    ].map((s, i) => (
                        <div key={s.n} className="group relative bg-white rounded-xl border border-black/10 p-8 hover:shadow-md transition-shadow">
                            <div className="font-heading font-bold text-5xl text-ghana-black/10 group-hover:text-ghana-green/30 transition-colors">{s.n}</div>
                            <h3 className="mt-2 font-heading text-xl font-semibold">{s.t}</h3>
                            <p className="mt-3 text-sm text-slate-600 leading-relaxed">{s.d}</p>
                            {i < 2 && <div className="hidden md:block absolute top-1/2 -right-3 w-6 border-t-2 border-dashed border-ghana-gold" />}
                        </div>
                    ))}
                </div>
            </section>

            {/* Visa types */}
            <section className="bg-white py-24">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex items-end justify-between flex-wrap gap-6 mb-14">
                        <div>
                            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Visa Types</div>
                            <h2 className="mt-3 text-3xl md:text-4xl font-heading font-bold">Choose your Ghana visa</h2>
                        </div>
                        <Link to="/prices" className="text-sm font-medium text-ghana-black inline-flex items-center gap-1 hover:gap-2 transition-all" data-testid="home-see-prices">See all prices <ArrowRight size={14} /></Link>
                    </div>
                    <div className="grid md:grid-cols-3 gap-6">
                        {(config?.visa_types || []).map((v) => (
                            <div key={v.code} className={`relative rounded-xl border p-8 transition-all ${v.active ? "border-black/10 bg-white hover:-translate-y-1 hover:shadow-lg" : "border-black/5 bg-slate-50"}`}>
                                {!v.active && <span className="absolute top-4 right-4 text-[10px] uppercase tracking-widest bg-ghana-gold text-ghana-black px-2 py-1 rounded font-bold">Coming Soon</span>}
                                <h3 className="font-heading text-2xl font-semibold">{v.name_en}</h3>
                                <div className="mt-4 flex items-baseline gap-1">
                                    <span className="font-heading text-4xl font-bold text-ghana-green">${v.price_usd}</span>
                                    <span className="text-sm text-slate-500">USD</span>
                                </div>
                                <ul className="mt-6 space-y-2 text-sm text-slate-700">
                                    <li className="flex items-center gap-2"><CheckCircle2 size={14} className="text-ghana-green" /> {v.days} days validity</li>
                                    <li className="flex items-center gap-2"><CheckCircle2 size={14} className="text-ghana-green" /> Regular · {v.processing_time_label || "5–7 business days"}</li>
                                    {v.express_available !== false && (
                                        <li className="flex items-center gap-2"><CheckCircle2 size={14} className="text-ghana-green" /> Express +${config?.express_surcharge_usd} · 48–72h</li>
                                    )}
                                    {v.requires_presence && (
                                        <li className="flex items-center gap-2 text-ghana-red"><CheckCircle2 size={14} className="text-ghana-red" /> Presence in Ghana required</li>
                                    )}
                                </ul>
                                {v.active ? (
                                    <Link to="/apply" className="mt-6 inline-flex items-center gap-2 bg-ghana-black text-white px-5 py-2.5 rounded-md text-sm font-medium hover:bg-ghana-black/90 transition-colors" data-testid={`home-select-${v.code}`}>
                                        Apply <ArrowRight size={14} />
                                    </Link>
                                ) : (
                                    <button disabled className="mt-6 inline-flex items-center gap-2 bg-slate-200 text-slate-500 px-5 py-2.5 rounded-md text-sm font-medium cursor-not-allowed">Unavailable</button>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Discover Ghana — tourism showcase */}
            <section className="bg-slate-50 py-24 overflow-hidden">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="max-w-2xl">
                        <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Discover Ghana</div>
                        <h2 className="mt-3 text-3xl md:text-4xl font-heading font-bold">A country of gold, kente and a thousand stories</h2>
                        <p className="mt-4 text-slate-600">From the Kwame Nkrumah Mausoleum to the great Ashanti kingdom, from Cape Coast to the world's finest cocoa fields — Ghana welcomes you with the warmest "Akwaaba".</p>
                    </div>

                    <div className="mt-14 grid md:grid-cols-2 lg:grid-cols-4 gap-6">
                        {[
                            {
                                title: "Kwame Nkrumah",
                                subtitle: "Independence & Pan-African vision",
                                img: "https://images.unsplash.com/photo-1568025848823-86404cd04ad1?crop=entropy&cs=srgb&fm=jpg&q=80&w=800",
                                text: "Visit the mausoleum of Ghana's first president — the man who set Africa on the road to independence.",
                            },
                            {
                                title: "Ashanti Kingdom",
                                subtitle: "Kumasi · Golden Stool",
                                img: "https://images.pexels.com/photos/6567674/pexels-photo-6567674.jpeg?auto=compress&cs=tinysrgb&w=800",
                                text: "Step into a living kingdom of kente cloth, royal drums and the sacred Golden Stool at Manhyia Palace.",
                            },
                            {
                                title: "Gold Coast Castles",
                                subtitle: "Cape Coast · Elmina",
                                img: "https://images.unsplash.com/photo-1707209210229-a32ec4b62b51?crop=entropy&cs=srgb&fm=jpg&q=80&w=800",
                                text: "Walk the UNESCO-listed castles of the Gold Coast — a solemn, powerful chapter of world history.",
                            },
                            {
                                title: "World-class Cocoa",
                                subtitle: "Farm-to-bar chocolate",
                                img: "https://images.unsplash.com/photo-1606312619070-d48b4c652a52?crop=entropy&cs=srgb&fm=jpg&q=80&w=800",
                                text: "Ghana grows some of the world's finest cocoa. Meet the farmers and taste single-origin Ghanaian chocolate.",
                            },
                        ].map((c) => (
                            <div key={c.title} className="group bg-white rounded-xl overflow-hidden border border-black/10 hover:shadow-lg transition-shadow" data-testid={`discover-${c.title.split(" ")[0].toLowerCase()}`}>
                                <div className="relative h-48 overflow-hidden">
                                    <img src={c.img} alt={c.title} loading="lazy" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                                    <div className="absolute inset-0 bg-gradient-to-t from-ghana-black/60 to-transparent" />
                                    <div className="absolute bottom-3 left-4 right-4">
                                        <div className="text-[10px] uppercase tracking-widest text-ghana-gold font-bold">{c.subtitle}</div>
                                        <div className="font-heading text-lg font-bold text-white">{c.title}</div>
                                    </div>
                                </div>
                                <div className="p-5">
                                    <p className="text-sm text-slate-600 leading-relaxed">{c.text}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Taste of Ghana */}
            <section className="bg-white py-24">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="grid md:grid-cols-2 gap-14 items-center">
                        <div className="relative order-2 md:order-1">
                            <div className="absolute -top-4 -left-4 w-40 h-40 rounded-full bg-ghana-red/20 blur-3xl" />
                            <div className="absolute -bottom-4 -right-4 w-40 h-40 rounded-full bg-ghana-gold/30 blur-3xl" />
                            <div className="relative grid grid-cols-2 gap-4">
                                <img
                                    src="https://images.unsplash.com/photo-1604909052743-94e838986d24?crop=entropy&cs=srgb&fm=jpg&q=80&w=700"
                                    alt="Jollof rice"
                                    loading="lazy"
                                    className="rounded-xl w-full h-56 object-cover shadow-lg"
                                />
                                <img
                                    src="https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?crop=entropy&cs=srgb&fm=jpg&q=80&w=700"
                                    alt="African plantain"
                                    loading="lazy"
                                    className="rounded-xl w-full h-56 object-cover shadow-lg mt-8"
                                />
                                <img
                                    src="https://images.unsplash.com/photo-1567982047351-76b6f93e38ee?crop=entropy&cs=srgb&fm=jpg&q=80&w=700"
                                    alt="Grilled tilapia"
                                    loading="lazy"
                                    className="rounded-xl w-full h-56 object-cover shadow-lg"
                                />
                                <img
                                    src="https://images.unsplash.com/photo-1516684732162-798a0062be99?crop=entropy&cs=srgb&fm=jpg&q=80&w=700"
                                    alt="Ghanaian market spices"
                                    loading="lazy"
                                    className="rounded-xl w-full h-56 object-cover shadow-lg mt-8"
                                />
                            </div>
                        </div>
                        <div className="order-1 md:order-2">
                            <div className="text-xs uppercase tracking-[0.25em] text-ghana-red font-semibold">A taste of Ghana</div>
                            <h2 className="mt-3 text-3xl md:text-4xl font-heading font-bold">Come hungry. Leave in love.</h2>
                            <p className="mt-4 text-slate-600">Ghanaian cuisine is bold, spicy and generous. From the legendary <em>Jollof rice</em> — the pride of Accra — to smoked tilapia straight from the coast, every plate tells a story.</p>
                            <ul className="mt-8 grid grid-cols-2 gap-3 text-sm">
                                {[
                                    ["Jollof rice", "The West-African icon"],
                                    ["Waakye", "Rice & beans, weekend classic"],
                                    ["Banku & Tilapia", "Fermented corn dough + grilled fish"],
                                    ["Fufu & light soup", "Cassava · plantain · goat"],
                                    ["Red Red", "Bean stew with fried plantain"],
                                    ["Kelewele", "Spicy fried plantain snack"],
                                    ["Kenkey", "Steamed corn dumpling"],
                                    ["Chinchinga", "Suya-style street kebabs"],
                                ].map(([dish, sub]) => (
                                    <li key={dish} className="p-3 rounded-lg border border-black/5 bg-slate-50">
                                        <div className="font-heading font-semibold text-ghana-black">{dish}</div>
                                        <div className="text-xs text-slate-500 mt-0.5">{sub}</div>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </div>
            </section>

            {/* Departure compliance warning banner */}
            <section className="bg-ghana-black text-white py-16">
                <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
                    <div className="inline-flex items-center gap-2 bg-ghana-red/20 text-ghana-red px-3 py-1 rounded-full text-xs uppercase tracking-widest font-semibold">Important</div>
                    <h3 className="mt-4 font-heading text-2xl md:text-3xl font-semibold">Respect your declared departure date</h3>
                    <p className="mt-4 text-white/70">
                        The Ghana Immigration Service has full authority under Ghanaian law to detain, fine or deport travellers who exceed their declared departure date.
                        <span className="text-ghana-gold"> The traveller bears sole responsibility.</span>
                    </p>
                </div>
            </section>
        </div>
    );
}
