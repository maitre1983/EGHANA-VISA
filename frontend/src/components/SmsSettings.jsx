import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { toast } from "sonner";
import { Save, Send } from "lucide-react";
import { fmtDateTime } from "../lib/adminUi";

const EVENTS = [
    ["new_submission", "New application submitted"],
    ["payment_success", "Payment confirmed"],
    ["ticket_escalated", "Ticket escalated by Abena"],
];
const input = "mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none";

export const SmsSettings = ({ initial, onReload }) => {
    const toForm = (c) => ({ ...c, client_secret: "", numbersText: (c.admin_numbers || []).join("\n") });
    const [f, setF] = useState(toForm(initial));
    const [log, setLog] = useState([]);
    const [busy, setBusy] = useState(false);
    useEffect(() => setF(toForm(initial)), [initial]);
    const loadLog = () => api.get("/admin/sms-log").then(({ data }) => setLog(data)).catch(() => {});
    useEffect(() => { loadLog(); }, []);
    const set = (k, v) => setF((o) => ({ ...o, [k]: v }));

    const save = async () => {
        try {
            await api.post("/admin/settings/sms", {
                enabled: f.enabled, client_id: f.client_id, client_secret: f.client_secret, sender_id: f.sender_id,
                admin_numbers: f.numbersText.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean), events: f.events || {},
            });
            toast.success("SMS settings saved"); onReload();
        } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    };
    const test = async () => {
        setBusy(true);
        try {
            const { data } = await api.post("/admin/sms/test");
            data.ok ? toast.success("Test SMS sent") : toast.error(`Hubtel refused: ${data.results?.[0]?.error || "unknown error"}`);
        } catch (e) { toast.error(e?.response?.data?.detail || "Test failed"); }
        setBusy(false); loadLog();
    };

    return (
        <div className="space-y-6">
            <div className="bg-white rounded-xl border border-black/10 p-6 space-y-4" data-testid="sms-settings">
                <div className="font-heading font-semibold">Hubtel SMS alerts for admins</div>
                <p className="text-xs text-slate-500 -mt-2">Use the SMS Client ID / Secret from your Hubtel dashboard (Develop → API keys → SMS) — they differ from the payment keys. The Sender ID must be approved by Hubtel (max 11 characters).</p>
                <label className="inline-flex items-center gap-3 cursor-pointer">
                    <input type="checkbox" checked={!!f.enabled} onChange={(e) => set("enabled", e.target.checked)} data-testid="sms-enabled" className="w-4 h-4 accent-ghana-green" />
                    <span className="text-sm font-medium">Send SMS alerts</span>
                </label>
                <div className="grid md:grid-cols-3 gap-4">
                    <Field label="SMS Client ID"><input value={f.client_id || ""} onChange={(e) => set("client_id", e.target.value)} data-testid="sms-client-id" className={input} /></Field>
                    <Field label={`SMS Client Secret ${initial.client_secret_set ? "(saved — leave empty to keep)" : ""}`}>
                        <input type="password" value={f.client_secret} onChange={(e) => set("client_secret", e.target.value)} data-testid="sms-client-secret" className={input} placeholder={initial.client_secret_set ? "••••••••" : ""} />
                    </Field>
                    <Field label="Sender ID"><input value={f.sender_id || ""} maxLength={11} onChange={(e) => set("sender_id", e.target.value)} data-testid="sms-sender-id" className={input} placeholder="eGhanaVisa" /></Field>
                </div>
                <Field label="Admin phone numbers (one per line, international format)">
                    <textarea rows={3} value={f.numbersText} onChange={(e) => set("numbersText", e.target.value)} data-testid="sms-numbers" className={`${input} font-mono`} placeholder="+233241234567" />
                </Field>
                <div>
                    <div className="text-xs uppercase tracking-wider text-slate-600 font-medium">Send an SMS when…</div>
                    <div className="mt-2 flex flex-wrap gap-5">
                        {EVENTS.map(([k, label]) => (
                            <label key={k} className="inline-flex items-center gap-2 text-sm">
                                <input type="checkbox" checked={!!f.events?.[k]} onChange={(e) => set("events", { ...f.events, [k]: e.target.checked })} data-testid={`sms-event-${k}`} className="accent-ghana-green" /> {label}
                            </label>
                        ))}
                    </div>
                    <div className="text-xs text-slate-500 mt-2">Gateway outages from Payment Monitoring are also sent by SMS when alerts are on.</div>
                </div>
                <div className="flex gap-2">
                    <button onClick={save} data-testid="sms-save" className="bg-ghana-green text-white px-4 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark"><Save size={14} /> Save</button>
                    <button onClick={test} disabled={busy} data-testid="sms-test" className="border border-black/10 px-4 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-slate-50 disabled:opacity-50"><Send size={14} /> {busy ? "Sending…" : "Send test SMS"}</button>
                </div>
            </div>
            <SmsLog log={log} />
        </div>
    );
};

const Field = ({ label, children }) => (
    <div><label className="text-xs uppercase tracking-wider text-slate-600 font-medium">{label}</label>{children}</div>
);

const SmsLog = ({ log }) => (
    <div className="bg-white rounded-xl border border-black/10 p-6" data-testid="sms-log">
        <div className="font-heading font-semibold">Recent SMS</div>
        {log.length === 0 && <div className="mt-3 text-sm text-slate-500">No SMS sent yet.</div>}
        <div className="mt-3 divide-y divide-black/5">
            {log.map((l) => (
                <div key={l.id} className="py-2.5 text-sm flex flex-wrap gap-x-4 gap-y-1 items-center">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${l.ok ? "bg-ghana-green/10 text-ghana-green" : "bg-ghana-red/10 text-ghana-red"}`}>{l.ok ? "Sent" : "Failed"}</span>
                    <span className="text-slate-500 text-xs">{fmtDateTime(l.created_at)}</span>
                    <span className="font-mono text-xs">{l.to}</span>
                    <span className="text-slate-600 truncate max-w-md">{l.content}</span>
                    {l.error && <span className="text-xs text-ghana-red truncate max-w-xs" title={l.error}>{l.error}</span>}
                </div>
            ))}
        </div>
    </div>
);
