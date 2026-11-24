import React, { useEffect, useMemo, useRef, useState } from "react";
import { MessageCircle, X, Send, LifeBuoy } from "lucide-react";
import api from "../lib/api";
import { log } from "../lib/log";
import { AbenaMessage } from "./AbenaMessage";
import { abenaLang, abenaCopy } from "./abenaCopy";

export default function AbenaChat() {
    const lang = useMemo(abenaLang, []);
    const t = abenaCopy(lang);
    const [open, setOpen] = useState(false);
    const [messages, setMessages] = useState([{ id: "welcome", role: "ai", text: t.welcome }]);
    const [input, setInput] = useState("");
    const [busy, setBusy] = useState(false);
    const [sessionId, setSessionId] = useState(null);
    const [contactEmail, setContactEmail] = useState("");
    const [contactName, setContactName] = useState("");
    const [needsContact, setNeedsContact] = useState(false);
    const listRef = useRef(null);
    const lastRef = useRef(null);

    useEffect(() => {
        const last = messages[messages.length - 1];
        if (last?.role === "ai" && lastRef.current) lastRef.current.scrollIntoView({ block: "start", behavior: "smooth" });
        else if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
    }, [messages, open, busy]);

    const send = async () => {
        const msg = input.trim();
        if (!msg || busy) return;
        setMessages((m) => [...m, { id: `u-${Date.now()}`, role: "user", text: msg }]);
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
                escalated: Boolean(data.escalated), ticketId: data.ticket_id || null,
            }]);
            if (data.escalated && !contactEmail) setNeedsContact(true);
        } catch (err) {
            log.warn("Abena chat error:", err?.message || err);
            setMessages((m) => [...m, { id: `err-${Date.now()}`, role: "ai", text: t.error }]);
        } finally { setBusy(false); }
    };

    return (
        <>
            <button
                data-testid="abena-open"
                onClick={() => setOpen((o) => !o)}
                className="fixed bottom-4 right-[5.5rem] md:bottom-6 md:right-24 w-14 h-14 rounded-full shadow-xl ring-2 ring-white z-50 flex items-center justify-center transition-transform hover:scale-105"
                style={{ background: "#0A0A0A", color: "#FCD116" }}
                aria-label={open ? t.close : t.open}
            >
                {open ? <X size={22} /> : <MessageCircle size={22} />}
            </button>

            {open && (
                <div
                    data-testid="abena-window"
                    role="dialog"
                    aria-label="ABENA"
                    className="fixed z-50 flex flex-col bg-white rounded-2xl shadow-2xl overflow-hidden border border-black/10 inset-x-2 bottom-20 h-[calc(100dvh-6.5rem)] max-h-[600px] sm:inset-x-auto sm:right-4 sm:w-[400px] md:right-24 md:bottom-24 md:h-[600px] md:max-h-[calc(100dvh-7.5rem)]"
                >
                    <div className="bg-ghana-black text-white px-4 py-3 flex items-center gap-3 shrink-0">
                        <div className="w-9 h-9 rounded-full ghana-stripe flex items-center justify-center text-ghana-black font-heading font-extrabold text-sm">A</div>
                        <div className="flex-1 min-w-0">
                            <div className="font-heading font-semibold text-sm tracking-wide">ABENA</div>
                            <div className="text-[10px] uppercase tracking-widest text-ghana-gold" data-testid="abena-subtitle">{t.subtitle}</div>
                        </div>
                        <button onClick={() => setOpen(false)} aria-label={t.close} data-testid="abena-close" className="p-1.5 rounded-full hover:bg-white/10 transition-colors">
                            <X size={18} />
                        </button>
                    </div>

                    {needsContact && (
                        <div className="bg-ghana-gold/10 border-b border-ghana-gold/40 px-3 py-2 text-xs shrink-0" data-testid="abena-contact-form">
                            <div className="text-ghana-black mb-1.5"><strong>{t.contactTitle}</strong> {t.contactText}</div>
                            <div className="flex gap-1.5">
                                <input value={contactName} onChange={(e) => setContactName(e.target.value)} placeholder={t.name} data-testid="abena-contact-name"
                                    className="flex-1 min-w-0 border border-black/10 rounded px-2 py-1.5 text-base sm:text-xs" />
                                <input type="email" value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} placeholder={t.email} data-testid="abena-contact-email"
                                    className="flex-1 min-w-0 border border-black/10 rounded px-2 py-1.5 text-base sm:text-xs" />
                                <button onClick={() => setNeedsContact(false)} data-testid="abena-contact-done" className="text-ghana-black font-semibold px-1 hover:underline">{t.done}</button>
                            </div>
                        </div>
                    )}

                    <div ref={listRef} data-testid="abena-messages" className="flex-1 overflow-y-auto overscroll-contain px-3 py-4 space-y-3 bg-slate-50">
                        {messages.map((m, i) => (
                            <div key={m.id} ref={i === messages.length - 1 ? lastRef : null} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                                <div className={`max-w-[88%] text-[14px] leading-relaxed px-3.5 py-2.5 rounded-2xl break-words ${m.role === "user" ? "bg-ghana-green text-white rounded-br-md" : "bg-white text-slate-800 rounded-bl-md border border-black/5 shadow-sm"}`}>
                                    <AbenaMessage text={m.text} user={m.role === "user"} />
                                    {m.escalated && (
                                        <div className="mt-2 flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-ghana-red font-semibold" data-testid="abena-escalated-badge">
                                            <LifeBuoy size={12} /> {t.transferred} {m.ticketId ? m.ticketId.slice(0, 8) : ""}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                        {busy && <div className="text-xs text-slate-500 pl-2" data-testid="abena-typing">{t.typing}</div>}
                    </div>

                    <div className="p-3 bg-white border-t border-black/5 flex gap-2 shrink-0">
                        <input
                            data-testid="abena-input"
                            value={input}
                            maxLength={1500}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && send()}
                            placeholder={t.placeholder}
                            className="flex-1 min-w-0 border border-black/10 rounded-full px-4 py-2 text-base sm:text-sm focus:outline-none focus:ring-1 focus:ring-ghana-green"
                        />
                        <button data-testid="abena-send" onClick={send} disabled={busy} aria-label={t.send} className="bg-ghana-green text-white rounded-full w-10 h-10 flex items-center justify-center shrink-0 hover:bg-ghana-green-dark transition-colors disabled:opacity-50">
                            <Send size={16} />
                        </button>
                    </div>
                </div>
            )}
        </>
    );
}
