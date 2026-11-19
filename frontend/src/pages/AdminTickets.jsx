import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { toast } from "sonner";
import { RefreshCw, MessageSquare, Send, CheckCircle2, RotateCcw, Mail, Bot, User } from "lucide-react";
import { fmtDateTime, PageHeader } from "../lib/adminUi";

const FILTERS = [["open", "Open"], ["resolved", "Resolved"], ["", "All"]];

export default function AdminTickets() {
    const [filter, setFilter] = useState("open");
    const [tickets, setTickets] = useState([]);
    const [selected, setSelected] = useState(null);
    const [loading, setLoading] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const { data } = await api.get("/admin/support-tickets", { params: filter ? { status: filter } : {} });
            setTickets(data);
        } catch { toast.error("Could not load tickets"); }
        setLoading(false);
    };
    useEffect(() => { load(); setSelected(null); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

    return (
        <div className="p-6 md:p-10 max-w-7xl" data-testid="admin-tickets-page">
            <PageHeader title="Abena Tickets" subtitle="Questions the AI assistant escalated to your team.">
                <button onClick={load} data-testid="tickets-refresh" className="inline-flex items-center gap-2 text-sm bg-white border border-black/10 px-3 py-2 rounded-md hover:bg-slate-50">
                    <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
                </button>
            </PageHeader>
            <div className="mt-6 flex gap-2">
                {FILTERS.map(([k, label]) => (
                    <button key={k || "all"} onClick={() => setFilter(k)} data-testid={`tickets-filter-${k || "all"}`}
                        className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${filter === k ? "bg-ghana-black text-white" : "bg-white border border-black/10 text-slate-600 hover:text-ghana-black"}`}>
                        {label}
                    </button>
                ))}
            </div>
            <div className="mt-6 grid lg:grid-cols-[380px_1fr] gap-6">
                <TicketList tickets={tickets} selectedId={selected?.id} onSelect={setSelected} />
                {selected ? <TicketDetail key={selected.id} ticket={selected} onChanged={() => { load(); setSelected(null); }} />
                    : <div className="bg-white rounded-xl border border-dashed border-black/15 p-10 text-center text-sm text-slate-500" data-testid="ticket-empty-detail">Select a ticket to read and reply.</div>}
            </div>
        </div>
    );
}

const TicketList = ({ tickets, selectedId, onSelect }) => (
    <div className="bg-white rounded-xl border border-black/10 divide-y divide-black/5 max-h-[70vh] overflow-y-auto" data-testid="tickets-list">
        {tickets.length === 0 && <div className="p-8 text-sm text-slate-500 text-center" data-testid="tickets-empty">No tickets here.</div>}
        {tickets.map((t) => (
            <button key={t.id} onClick={() => onSelect(t)} data-testid={`ticket-row-${t.id}`}
                className={`w-full text-left p-4 transition-colors ${selectedId === t.id ? "bg-ghana-green/5" : "hover:bg-slate-50"}`}>
                <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-sm truncate">{t.customer_name || t.customer_email || "Anonymous visitor"}</span>
                    <StatusPill status={t.status} />
                </div>
                <div className="mt-1 text-sm text-slate-600 line-clamp-2">{t.question}</div>
                <div className="mt-2 text-xs text-slate-400">{fmtDateTime(t.created_at)}</div>
            </button>
        ))}
    </div>
);

const StatusPill = ({ status }) => (
    <span className={`text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full ${status === "open" ? "bg-ghana-gold text-ghana-black" : "bg-ghana-green text-white"}`}>{status}</span>
);

const TicketDetail = ({ ticket, onChanged }) => {
    const [reply, setReply] = useState(ticket.admin_reply || "");
    const [messages, setMessages] = useState([]);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        api.get(`/admin/support-tickets/${ticket.id}/conversation`).then(({ data }) => setMessages(data.messages)).catch(() => {});
    }, [ticket.id]);

    const send = async () => {
        if (!reply.trim()) return;
        setBusy(true);
        try {
            const { data } = await api.post(`/admin/support-tickets/${ticket.id}/reply`, { reply, close: true });
            toast.success(data.emailed ? "Reply sent by email and ticket resolved" : "Reply saved (no customer email on file)");
            onChanged();
        } catch (e) { toast.error(e?.response?.data?.detail || "Reply failed"); }
        setBusy(false);
    };
    const setStatus = async (status) => {
        await api.post(`/admin/support-tickets/${ticket.id}/status`, { status });
        toast.success(status === "open" ? "Ticket reopened" : "Ticket resolved");
        onChanged();
    };

    return (
        <div className="bg-white rounded-xl border border-black/10 p-6 space-y-5" data-testid="ticket-detail">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <div className="font-heading text-lg font-semibold" data-testid="ticket-detail-name">{ticket.customer_name || "Anonymous visitor"}</div>
                    <div className="text-sm text-slate-500 flex items-center gap-1.5"><Mail size={13} /> {ticket.customer_email || "No email provided"}</div>
                    {ticket.tracking_no && <div className="text-xs font-mono text-slate-500 mt-1">{ticket.tracking_no}</div>}
                </div>
                {ticket.status === "open"
                    ? <button onClick={() => setStatus("resolved")} data-testid="ticket-mark-resolved" className="text-sm inline-flex items-center gap-1.5 border border-black/10 px-3 py-1.5 rounded-md hover:bg-slate-50"><CheckCircle2 size={14} /> Mark resolved</button>
                    : <button onClick={() => setStatus("open")} data-testid="ticket-reopen" className="text-sm inline-flex items-center gap-1.5 border border-black/10 px-3 py-1.5 rounded-md hover:bg-slate-50"><RotateCcw size={14} /> Reopen</button>}
            </div>
            <Conversation messages={messages} ticket={ticket} />
            {ticket.admin_reply && <div className="text-xs text-slate-500">Last reply by {ticket.admin_email || "admin"} · {fmtDateTime(ticket.admin_replied_at)}</div>}
            <div>
                <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Your reply</label>
                <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={5} data-testid="ticket-reply-input"
                    className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none"
                    placeholder="Write the answer the traveller will receive by email…" />
                <button onClick={send} disabled={busy || !reply.trim()} data-testid="ticket-reply-send"
                    className="mt-3 bg-ghana-green text-white px-4 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark disabled:opacity-50">
                    <Send size={14} /> {busy ? "Sending…" : "Send reply & resolve"}
                </button>
            </div>
        </div>
    );
};

const Conversation = ({ messages, ticket }) => {
    const rows = messages.length ? messages : [{ user_message: ticket.question, ai_reply: ticket.ai_reply, created_at: ticket.created_at }];
    return (
        <div className="bg-slate-50 rounded-lg p-4 space-y-3 max-h-80 overflow-y-auto" data-testid="ticket-conversation">
            <div className="text-xs uppercase tracking-wider text-slate-500 font-medium flex items-center gap-1.5"><MessageSquare size={12} /> Chat history</div>
            {rows.map((m, i) => (
                <div key={i} className="space-y-2">
                    <Bubble icon={User} who="Visitor" text={m.user_message} />
                    <Bubble icon={Bot} who="Abena" text={m.ai_reply} ai />
                </div>
            ))}
        </div>
    );
};

const Bubble = ({ icon: Icon, who, text, ai }) => (
    <div className={`flex gap-2 ${ai ? "" : "flex-row-reverse text-right"}`}>
        <span className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${ai ? "bg-ghana-green text-white" : "bg-ghana-black text-white"}`}><Icon size={13} /></span>
        <div className={`rounded-lg px-3 py-2 text-sm max-w-[85%] whitespace-pre-line ${ai ? "bg-white border border-black/5" : "bg-ghana-black/90 text-white"}`}>
            <div className="text-[10px] uppercase tracking-wider opacity-60 mb-0.5">{who}</div>{text}
        </div>
    </div>
);
