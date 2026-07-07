import React from "react";

const TERMS = [
    ["Purpose", "eghanavisa.com facilitates the completion and submission of Ghana Visa On Arrival applications. e.GHANA Visa Services is a private facilitator and is not an agency of the Government of the Republic of Ghana."],
    ["Applicant responsibility", "Applicants are fully responsible for the accuracy of the information they provide. Incorrect or misleading information may result in the rejection of the application without refund."],
    ["Processing times", "Regular processing takes 5–7 business days. Express processing takes 48–72 hours. These delays are indicative and depend on the Ghana Immigration Service which has final authority."],
    ["Fees & refunds", "Fees paid cover the visa facilitation service. Once an application has entered processing, fees are non-refundable. Fees do not guarantee the issuance of a visa."],
    ["Departure date compliance", "The traveller is responsible for respecting the declared departure date. Any overstay is subject to sanctions under Ghanaian law (detention, fines, deportation)."],
    ["Data protection", "Personal data is processed in line with our Privacy Policy, GDPR and the Ghana Data Protection Act 2012. Documents are encrypted and accessible only by authorised staff."],
    ["Liability", "e.GHANA Visa Services is not liable for decisions taken by the Ghana Immigration Service, delays caused by third parties, or any missed travel resulting therefrom."],
    ["Contact", "Any question about these terms may be submitted through the WhatsApp support number provided on the site."],
];

export default function Terms() {
    return (
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Legal</div>
            <h1 className="mt-2 text-3xl md:text-5xl font-heading font-bold">Terms & Conditions</h1>
            <p className="mt-3 text-slate-600">Please read carefully before submitting an application.</p>
            <div className="mt-10 space-y-6 bg-white rounded-xl border border-black/10 p-8 shadow-sm">
                {TERMS.map(([title, body], i) => (
                    <div key={i}>
                        <h2 className="font-heading text-xl font-semibold">{i + 1}. {title}</h2>
                        <p className="mt-2 text-slate-700 leading-relaxed">{body}</p>
                    </div>
                ))}
            </div>
        </div>
    );
}
