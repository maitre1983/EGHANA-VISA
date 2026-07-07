import React, { useEffect, useRef, useState } from "react";
import { MessageCircle, X, Send } from "lucide-react";
import api from "../lib/api";

export default function AmaChat() {
    const [open, setOpen] = useState(false);
    const [messages, setMessages] = useState([
        { role: "ai", text: "Akwaaba! I'm Ama, your Ghana Visa assistant. Ask me about prices, processing times, required documents or tracking." },
    ]);
    const [input, setInput] = useState("");
    const [busy, setBusy] = useState(false);
    const [sessionId, setSessionId] = useState(null);
    const listRef = useRef(null);

    useEffect(() => {
        if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
    }, [messages, open]);

    const send = async () => {
        const msg = input.trim();
        if (!msg || busy) return;
        setMessages((m) => [...m, { role: "user", text: msg }]);
        setInput("");
        setBusy(true);
        try {
            const { data } = await api.post("/chat", { message: msg, session_id: sessionId });
            setSessionId(data.session_id);
            setMessages((m) => [...m, { role: "ai", text: data.reply }]);
        } catch {
            setMessages((m) => [...m, { role: "ai", text: "Sorry, I'm having trouble reaching my brain. Please try again." }]);
        } finally {
            setBusy(false);
        }
    };

    return (
        <>
            <button
                data-testid="ama-open"
                onClick={() => setOpen((o) => !o)}
                className="fixed bottom-24 right-6 md:bottom-6 md:right-24 w-14 h-14 rounded-full shadow-xl z-50 flex items-center justify-center transition-transform hover:scale-105"
                style={{ background: "#0A0A0A", color: "#FCD116" }}
                aria-label="Open Ama chat"
            >
                {open ? <X size={22} /> : <MessageCircle size={22} />}
            </button>

            {open && (
                <div
                    data-testid="ama-window"
                    className="fixed bottom-40 right-6 md:bottom-24 md:right-24 w-[350px] max-w-[92vw] h-[480px] bg-white rounded-xl shadow-2xl overflow-hidden z-50 flex flex-col border border-black/10"
                >
                    <div className="bg-ghana-black text-white px-4 py-3 flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full ghana-stripe flex items-center justify-center text-ghana-black font-heading font-extrabold text-sm">A</div>
                        <div>
                            <div className="font-heading font-semibold text-sm">Ama</div>
                            <div className="text-[10px] uppercase tracking-widest text-ghana-gold">Ghana Visa Assistant</div>
                        </div>
                    </div>
                    <div ref={listRef} className="flex-1 overflow-y-auto p-3 space-y-2 bg-slate-50">
                        {messages.map((m, i) => (
                            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                                <div
                                    className={`max-w-[80%] text-sm px-3 py-2 rounded-lg ${
                                        m.role === "user"
                                            ? "bg-ghana-green text-white rounded-br-sm"
                                            : "bg-white text-ghana-black rounded-bl-sm border border-black/5"
                                    }`}
                                >
                                    {m.text}
                                </div>
                            </div>
                        ))}
                        {busy && <div className="text-xs text-slate-500 pl-2">Ama is typing…</div>}
                    </div>
                    <div className="p-3 bg-white border-t border-black/5 flex gap-2">
                        <input
                            data-testid="ama-input"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && send()}
                            placeholder="Ask Ama a question…"
                            className="flex-1 border border-black/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ghana-green"
                        />
                        <button
                            data-testid="ama-send"
                            onClick={send}
                            disabled={busy}
                            className="bg-ghana-green text-white rounded-md px-3 py-2 hover:bg-ghana-green-dark transition-colors disabled:opacity-50"
                        >
                            <Send size={16} />
                        </button>
                    </div>
                </div>
            )}
        </>
    );
}
