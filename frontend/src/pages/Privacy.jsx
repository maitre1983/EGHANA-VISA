import React from "react";

const SECTIONS = [
    ["Data controller", "eghanavisa.com (e.GHANA Visa Services), reachable via the WhatsApp number displayed on the site."],
    ["What we collect", "Passport information, contact details, travel dates, profession, and identity documents (face photo, passport pages, flight tickets). Payment card data is processed by Hubtel and never touches our servers."],
    ["Purpose", "Data is collected exclusively for the purpose of preparing and transmitting your Ghana visa application, communicating status updates, and complying with legal obligations."],
    ["Legal basis (GDPR)", "The processing is based on the performance of a contract (Art. 6.1.b GDPR) and on our legitimate interest in fraud prevention (Art. 6.1.f)."],
    ["Retention", "Application data is retained for 24 months for legal, tax and audit reasons, then securely deleted."],
    ["Your rights", "Under GDPR and the Ghana Data Protection Act 2012 you have the right to access, rectify, port, or request deletion of your data. Contact us via WhatsApp to exercise these rights."],
    ["Security", "All uploads are encrypted at rest. Passwords are hashed with bcrypt. Admin access is protected by JWT and multi-factor where enabled."],
    ["Cookies", "We use only strictly necessary cookies to keep your session alive during payment. No tracking cookies."],
];

export default function Privacy() {
    return (
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Legal</div>
            <h1 className="mt-2 text-3xl md:text-5xl font-heading font-bold">Privacy Policy</h1>
            <p className="mt-3 text-slate-600">GDPR + Ghana Data Protection Act 2012 compliant.</p>
            <div className="mt-10 space-y-6 bg-white rounded-xl border border-black/10 p-8 shadow-sm">
                {SECTIONS.map(([t, b], i) => (
                    <div key={`privacy-${t}`}>
                        <h2 className="font-heading text-xl font-semibold">{i + 1}. {t}</h2>
                        <p className="mt-2 text-slate-700 leading-relaxed">{b}</p>
                    </div>
                ))}
            </div>
        </div>
    );
}
