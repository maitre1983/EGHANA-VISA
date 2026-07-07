import React from "react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "../components/ui/accordion";

const FAQS = [
    { q: "Who needs a Ghana Visa On Arrival?", a: "Any traveller who is not a citizen of one of the 16 ECOWAS West African nations must obtain a Ghana visa to enter the country. This includes tourists, business travellers and transit passengers." },
    { q: "How long does processing take?", a: "Regular processing takes 5 to 7 business days. Express processing is completed within 48 to 72 hours and includes a surcharge." },
    { q: "What documents do I need?", a: "You need a face photo on a white background (no glasses), a clear copy of your passport data page, a photograph of your passport cover, and your flight ticket or booking confirmation. Files must be JPEG, PNG or PDF." },
    { q: "How will I receive my visa?", a: "Your electronic visa is delivered to the email address provided in the application. Print a copy and travel with your passport — that's it." },
    { q: "How do I track my application?", a: "Every application receives a unique tracking number in the format GH-YYYY-XXXXXX. Enter it on our Track page to see the current status: Submitted → In Progress → Done." },
    { q: "What happens if I stay beyond my declared departure date?", a: "Under Ghanaian law, the Ghana Immigration Service is fully entitled to detain, fine or deport travellers who exceed their declared departure date. e.GHANA Visa Services declines all responsibility — the traveller bears sole responsibility." },
    { q: "Which payment methods are accepted?", a: "At launch we accept Visa cards through Hubtel's secure gateway. USDT (TRC20 and BEP20) crypto payments are coming soon and can be enabled by our team." },
    { q: "What is your refund policy?", a: "Applications that are cancelled before review by Immigration may be refunded. Once your file is being processed or approved, the fee is non-refundable, in line with standard visa services practice." },
];

export default function FAQ() {
    return (
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Help</div>
            <h1 className="mt-2 text-3xl md:text-5xl font-heading font-bold">Frequently asked questions</h1>
            <p className="mt-3 text-slate-600">Everything you need to know about the Ghana Visa On Arrival application.</p>

            <div className="mt-10">
                <Accordion type="single" collapsible className="space-y-3">
                    {FAQS.map((f, i) => (
                        <AccordionItem key={i} value={`item-${i}`} className="bg-white border border-black/10 rounded-xl px-5 data-[state=open]:border-ghana-green" data-testid={`faq-item-${i}`}>
                            <AccordionTrigger className="font-heading text-left font-semibold hover:no-underline py-5">{f.q}</AccordionTrigger>
                            <AccordionContent className="text-slate-700 leading-relaxed pb-5">{f.a}</AccordionContent>
                        </AccordionItem>
                    ))}
                </Accordion>
            </div>
        </div>
    );
}
