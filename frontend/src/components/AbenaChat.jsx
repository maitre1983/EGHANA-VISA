import React, { useEffect, useRef, useState } from "react";
import { MessageCircle, X, Send, LifeBuoy } from "lucide-react";
import api from "../lib/api";
import { log } from "../lib/log";

export default function AbenaChat() {
    const [open, setOpen] = useState(false);
    const [messages, setMessages] = useState([
        { id: "welcome", role: "ai", text: "Akwaaba! I'm Abena, your Ghana Visa assistant. Ask me about prices, processing times, required documents or tracking — and I'll transfer you to a human agent if anything needs a personal touch." },
    ]);
    const [input, setInput] = useState("");
    const [busy, setBusy] = useState(false);
    const [sessionId, setSessionId] = useState(null);
    const [contactEmail, setContactEmail] = useState("");
    const [contactName, setContactName] = useState("");
    const [needsContact, setNeedsContact] = useState(false);
    const listRef = useRef(null);

    useEffect(() => {
        if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
    }, [messages, open]);

    const send = async () => {
        const msg = input.trim();
        if (!msg || busy) return;
        const userId = `u-${Date.now()}`;
        setMessages((m) => [...m, { id: userId, role: "user", text: msg }]);
        setInput("");
        setBusy(true);
        try {
            const { data } = await api.post("/chat", {
                message: msg,
                session_id: sessionId,
                contact_email: contactEmail || undefined,
                contact_name: contactName || undefined,
            });
            setSessionId(data.session_id);
            setMessages((m) => [...m, {
                id: `a-${Date.now()}`, role: "ai", text: data.reply,
                escalated: Boolean(data.escalated),
                ticketId: data.ticket_id || null,
            }]);
            if (data.escalated && !contactEmail) setNeedsContact(true);
        } catch (err) {
            log.warn("Abena chat error:", err?.message || err);
            setMessages((m) => [...m, { id: `err-${Date.now()}`, role: "ai", text: "Sorry, I'm having trouble reaching my brain. Please try again or contact us on WhatsApp." }]);
        } finally { setBusy(false); }
    };

    return (
        <>
            <button
                data-testid="abena-open"
                onClick={() => setOpen((o) => !o)}
                className="fixed bottom-4 right-[5.5rem] md:bottom-6 md:right-24 w-14 h-14 rounded-full shadow-xl ring-2 ring-white z-50 flex items-center justify-center transition-transform hover:scale-105"
                style={{ background: "#0A0A0A", color: "#FCD116" }}
                aria-label="Open Abena chat"
            >
                {open ? <X size={22} /> : <MessageCircle size={22} />}
            </button>

            {open && (
                <div
                    data-testid="abena-window"
                    className="fixed bottom-24 right-4 md:bottom-24 md:right-24 w-[360px] max-w-[92vw] h-[520px] max-h-[calc(100vh-8rem)] md:max-h-[calc(100vh-7rem)] bg-white rounded-xl shadow-2xl overflow-hidden z-50 flex flex-col border border-black/10"
                >
                    <div className="bg-ghana-black text-white px-4 py-3 flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full ghana-stripe flex items-center justify-center text-ghana-black font-heading font-extrabold text-sm">A</div>
                        <div>
                            <div className="font-heading font-semibold text-sm">Abena</div>
                            <div className="text-[10px] uppercase tracking-widest text-ghana-gold">AI Support · Live 24/7</div>
                        </div>
                    </div>

                    {needsContact && (
                        <div className="bg-ghana-gold/10 border-b border-ghana-gold/40 px-3 py-2 text-xs" data-testid="abena-contact-form">
                            <div className="text-ghana-black mb-1.5"><strong>An admin will follow up.</strong> Leave your email so we can reach you:</div>
                            <div className="flex gap-1.5">
                                <input value={contactName} onChange={(e) => setContactName(e.target.value)} placeholder="Name" data-testid="abena-contact-name"
                                    className="flex-1 border border-black/10 rounded px-2 py-1 text-xs" />
                                <input value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} placeholder="Email" data-testid="abena-contact-email"
                                    className="flex-1 border border-black/10 rounded px-2 py-1 text-xs" />
                                <button onClick={() => setNeedsContact(false)} className="text-ghana-black hover:underline">Done</button>
                            </div>
                        </div>
                    )}

                    <div ref={listRef} className="flex-1 overflow-y-auto p-3 space-y-2 bg-slate-50">
                        {messages.map((m) => (
                            <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                                <div className={`max-w-[85%] text-sm px-3 py-2 rounded-lg ${m.role === "user" ? "bg-ghana-green text-white rounded-br-sm" : "bg-white text-ghana-black rounded-bl-sm border border-black/5"}`}>
                                    {m.text}
                                    {m.escalated && (
                                        <div className="mt-2 flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-ghana-red font-semibold" data-testid="abena-escalated-badge">
                                            <LifeBuoy size={12} /> Transferred to human · Ticket {m.ticketId ? m.ticketId.slice(0, 8) : ""}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                        {busy && <div className="text-xs text-slate-500 pl-2">Abena is typing…</div>}
                    </div>

                    <div className="p-3 bg-white border-t border-black/5 flex gap-2">
                        <input
                            data-testid="abena-input"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && send()}
                            placeholder="Ask Abena a question…"
                            className="flex-1 border border-black/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ghana-green"
                        />
                        <button data-testid="abena-send" onClick={send} disabled={busy} className="bg-ghana-green text-white rounded-md px-3 py-2 hover:bg-ghana-green-dark transition-colors disabled:opacity-50">
                            <Send size={16} />
                        </button>
                    </div>
                </div>
            )}
        </>
    );
}
