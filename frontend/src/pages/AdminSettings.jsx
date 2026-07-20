import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { toast } from "sonner";
import { Save } from "lucide-react";

const AI_MODELS = [
    "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gemini-3-flash-preview",
];

const SEC = { prices: "Visa Prices", types: "Visa Types", methods: "Payment Methods", hubtel: "Hubtel API", fx: "Exchange Rate", nowpayments: "NowPayments (USDT)", storage: "Storage (R2)", other: "WhatsApp & AI", analytics: "Analytics IDs", danger: "Danger Zone" };

export default function AdminSettings() {
    const [tab, setTab] = useState("prices");
    const [s, setS] = useState(null);

    const reload = async () => {
        const { data } = await api.get("/admin/settings");
        setS(data);
    };
    useEffect(() => { reload(); }, []);
    if (!s) return <div className="p-10">Loading…</div>;

    const savePrice = async (code, price) => {
        await api.post("/admin/settings/visa-price", { code, price_usd: parseFloat(price) });
        toast.success("Price saved"); reload();
    };
    const saveSurcharge = async (price) => {
        await api.post("/admin/settings/express-surcharge", { price_usd: parseFloat(price) });
        toast.success("Surcharge saved"); reload();
    };
    const toggleVisa = async (code, active) => {
        try { await api.post("/admin/settings/visa-toggle", { code, active }); toast.success("Updated"); reload(); }
        catch (e) { toast.error(e?.response?.data?.detail || "Update failed"); }
    };
    const togglePayment = async (code, active) => {
        await api.post("/admin/settings/payment-toggle", { code, active }); toast.success("Updated"); reload();
    };
    const saveHubtel = async (payload) => {
        await api.post("/admin/settings/hubtel", payload); toast.success("Hubtel saved"); reload();
    };
    const saveNowpayments = async (payload) => {
        await api.post("/admin/settings/nowpayments", payload); toast.success("NowPayments saved"); reload();
    };
    const testNowpayments = async () => {
        try {
            const { data } = await api.post("/admin/settings/nowpayments/test");
            toast.success(`Connection OK · ${data.mode} · TRC20:${data.usdttrc20_supported ? "✓" : "✗"} · BEP20:${data.usdtbsc_supported ? "✓" : "✗"}`);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Test failed");
        }
    };
    const saveWhatsapp = async (v) => { await api.post("/admin/settings/whatsapp", { whatsapp_admin: v }); toast.success("Saved"); reload(); };
    const saveWhatsappPublic = async (payload) => {
        await api.post("/admin/settings/whatsapp-public", payload);
        toast.success("Saved"); reload();
    };
    const saveBackofficeUrl = async (v) => {
        await api.post("/admin/settings/admin-backoffice-url", { admin_backoffice_url: v });
        toast.success("Saved"); reload();
    };
    const saveAdditionalEmails = async (list) => {
        try {
            await api.post("/admin/settings/additional-admin-emails", { additional_admin_emails: list });
            toast.success("Additional admin emails saved"); reload();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Save failed");
        }
    };
    const saveAI = async (v) => { await api.post("/admin/settings/ai-model", { ai_model: v }); toast.success("Saved"); reload(); };
    const saveAdminEmail = async (v) => {
        try {
            await api.post("/admin/settings/admin-notification-email", { admin_notification_email: v });
            toast.success("Admin notification email saved");
            reload();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Save failed");
        }
    };
    const saveUpload = async (v) => { await api.post("/admin/settings/upload-limit", { max_upload_mb: parseInt(v, 10) }); toast.success("Saved"); reload(); };

    return (
        <div className="p-6 md:p-10 max-w-5xl">
            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Command Center</div>
            <h1 className="mt-1 font-heading text-3xl font-bold">Settings</h1>

            <div className="mt-8 flex gap-2 flex-wrap border-b border-black/10">
                {Object.entries(SEC).map(([key, label]) => (
                    <button key={key} onClick={() => setTab(key)} data-testid={`settings-tab-${key}`}
                        className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${tab === key ? "border-ghana-green text-ghana-green" : "border-transparent text-slate-600 hover:text-ghana-black"}`}>
                        {label}
                    </button>
                ))}
            </div>

            <div className="mt-8 space-y-6">
                {tab === "prices" && (
                    <>
                        {s.visa_types.map((v) => (
                            <Card key={v.code} title={v.name_en}>
                                <PriceRow initial={v.price_usd} onSave={(p) => savePrice(v.code, p)} testid={`price-${v.code}`} />
                            </Card>
                        ))}
                        <Card title="Express Processing Surcharge (USD)">
                            <PriceRow initial={s.express_surcharge_usd} onSave={saveSurcharge} testid="price-surcharge" />
                        </Card>
                        <Card title="Max upload size (MB)">
                            <NumberRow initial={s.max_upload_mb} onSave={saveUpload} testid="max-upload" />
                        </Card>
                    </>
                )}
                {tab === "types" && s.visa_types.map((v) => (
                    <Card key={v.code} title={v.name_en}>
                        <ToggleRow active={v.active} disabled={v.always_active} onChange={(x) => toggleVisa(v.code, x)} testid={`toggle-visa-${v.code}`} />
                        {v.always_active && <div className="text-xs text-slate-500 mt-2">Always active — cannot be disabled.</div>}
                    </Card>
                ))}
                {tab === "methods" && s.payment_methods.map((m) => (
                    <Card key={m.code} title={m.name}>
                        <ToggleRow active={m.active} onChange={(x) => togglePayment(m.code, x)} testid={`toggle-pay-${m.code}`} />
                    </Card>
                ))}
                {tab === "hubtel" && <HubtelForm initial={s.hubtel} onSave={saveHubtel} />}
                {tab === "nowpayments" && <NowPaymentsForm initial={s.nowpayments || {}} onSave={saveNowpayments} onTest={testNowpayments} discountPct={s.usdt_discount_pct || 0} onSaveDiscount={async (pct) => { await api.post("/admin/settings/usdt-discount", { pct }); toast.success("Discount saved"); reload(); }} />}
                {tab === "other" && (
                    <>
                        <Card title="WhatsApp support number (used by Abena)">
                            <TextRow initial={s.whatsapp_admin} onSave={saveWhatsapp} testid="whatsapp" placeholder="+233..." />
                        </Card>
                        <Card title="AI model for Abena chat">
                            <SelectRow initial={s.ai_model} options={AI_MODELS} onSave={saveAI} testid="ai-model" />
                        </Card>
                        <Card title="Admin notification email (new applications & payments)">
                            <TextRow
                                initial={s.admin_notification_email || ""}
                                onSave={saveAdminEmail}
                                testid="admin-notification-email"
                                placeholder="ops@example.com (leave empty to disable)"
                            />
                            <div className="text-xs text-slate-500 mt-2">Sent when a new application is submitted AND when its payment succeeds. Leave empty to disable internal notifications.</div>
                        </Card>
                        <Card title="Additional admin recipients (CC on every notification)">
                            <AdditionalEmailsEditor
                                initial={s.additional_admin_emails || []}
                                onSave={saveAdditionalEmails}
                            />
                            <div className="text-xs text-slate-500 mt-2">Extra addresses that receive the same admin notifications (new submission + payment success). One per row.</div>
                        </Card>
                        <Card title="Back-office link included in admin emails">
                            <TextRow
                                initial={s.admin_backoffice_url || ""}
                                onSave={saveBackofficeUrl}
                                testid="admin-backoffice-url"
                                placeholder="https://eghanavisa.com/admin/dashboard"
                            />
                            <div className="text-xs text-slate-500 mt-2">Base URL used to build the &quot;Open Back Office&quot; button in admin notification emails. The tracking number is appended automatically as a query param.</div>
                        </Card>
                        <Card title="Public WhatsApp widget (visible on every page)">
                            <WhatsappPublicEditor
                                initial={{
                                    whatsapp_public_number: s.whatsapp_public_number || "",
                                    whatsapp_public_message: s.whatsapp_public_message || "",
                                    whatsapp_agent_name: s.whatsapp_agent_name || "",
                                    whatsapp_agent_avatar_url: s.whatsapp_agent_avatar_url || "",
                                    whatsapp_agent_status_text: s.whatsapp_agent_status_text || "",
                                    whatsapp_teaser_message: s.whatsapp_teaser_message || "",
                                }}
                                onSave={saveWhatsappPublic}
                            />
                            <div className="text-xs text-slate-500 mt-2">A conversational widget appears at the bottom-right of every public page. Tapping it opens a chat preview with the agent name, avatar, status, and a teaser message. The green CTA opens WhatsApp with the pre-filled message.</div>
                        </Card>
                    </>
                )}
                {tab === "analytics" && <AnalyticsIdsForm initial={s} onReload={reload} />}
                {tab === "storage" && <R2StorageForm initial={s} onReload={reload} />}
                {tab === "fx" && <FxForm initial={s} onReload={reload} />}
                {tab === "danger" && <DangerZone onReload={reload} />}
            </div>
        </div>
    );
}

const Card = ({ title, children }) => (
    <div className="bg-white rounded-xl border border-black/10 p-6">
        <div className="font-heading font-semibold">{title}</div>
        <div className="mt-4">{children}</div>
    </div>
);

const PriceRow = ({ initial, onSave, testid }) => {
    const [v, setV] = useState(initial);
    useEffect(() => setV(initial), [initial]);
    return (
        <div className="flex gap-2">
            <input type="number" step="0.01" value={v} onChange={(e) => setV(e.target.value)} data-testid={testid}
                className="flex-1 border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
            <button onClick={() => onSave(v)} data-testid={`${testid}-save`} className="bg-ghana-green text-white px-4 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark"><Save size={14} /> Save</button>
        </div>
    );
};
const NumberRow = PriceRow;
const TextRow = ({ initial, onSave, testid, placeholder }) => {
    const [v, setV] = useState(initial);
    useEffect(() => setV(initial), [initial]);
    return (
        <div className="flex gap-2">
            <input value={v} placeholder={placeholder} onChange={(e) => setV(e.target.value)} data-testid={testid}
                className="flex-1 border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
            <button onClick={() => onSave(v)} data-testid={`${testid}-save`} className="bg-ghana-green text-white px-4 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark"><Save size={14} /> Save</button>
        </div>
    );
};

const AdditionalEmailsEditor = ({ initial, onSave }) => {
    // Editable list of comma/newline-separated emails.
    const toText = (arr) => (arr || []).join("\n");
    const [text, setText] = useState(toText(initial));
    useEffect(() => setText(toText(initial)), [initial]);
    const save = () => {
        const list = text.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
        onSave(list);
    };
    return (
        <div className="flex flex-col gap-2">
            <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                data-testid="additional-admin-emails"
                rows={3}
                placeholder="ops-alerts@example.com&#10;another@example.com"
                className="w-full border border-black/10 rounded-md px-3 py-2.5 text-sm font-mono focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none"
            />
            <div>
                <button onClick={save} data-testid="additional-admin-emails-save" className="bg-ghana-green text-white px-4 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark"><Save size={14} /> Save list</button>
            </div>
        </div>
    );
};

const WhatsappPublicEditor = ({ initial, onSave }) => {
    const [f, setF] = useState(initial);
    useEffect(() => setF(initial), [initial]);
    const set = (k, v) => setF((old) => ({ ...old, [k]: v }));
    const FIELDS = [
        ["whatsapp_public_number", "Number (international format)", "+233202794825", "input"],
        ["whatsapp_public_message", "Pre-filled message sent to WhatsApp", "Hello, I need assistance regarding my Ghana Visa application.", "textarea"],
        ["whatsapp_agent_name", "Agent display name", "Ama · Ghana Visa Support", "input"],
        ["whatsapp_agent_avatar_url", "Agent avatar URL (optional — leave empty to use initials)", "https://…/avatar.jpg", "input"],
        ["whatsapp_agent_status_text", "Status line (e.g. Online · Replies within 5 min)", "Online · Replies within 5 minutes", "input"],
        ["whatsapp_teaser_message", "Teaser message shown inside the widget bubble", "Hi there! 👋 Have a question about your Ghana visa? Chat with us on WhatsApp — we're here to help.", "textarea"],
    ];
    return (
        <div className="flex flex-col gap-3">
            {FIELDS.map(([k, label, placeholder, kind]) => (
                <div key={k}>
                    <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">{label}</label>
                    {kind === "textarea" ? (
                        <textarea
                            value={f[k] || ""}
                            onChange={(e) => set(k, e.target.value)}
                            data-testid={k.replace(/_/g, "-")}
                            rows={2}
                            placeholder={placeholder}
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none"
                        />
                    ) : (
                        <input
                            value={f[k] || ""}
                            onChange={(e) => set(k, e.target.value)}
                            data-testid={k.replace(/_/g, "-")}
                            placeholder={placeholder}
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none"
                        />
                    )}
                </div>
            ))}
            <div>
                <button onClick={() => onSave(f)} data-testid="whatsapp-public-save" className="bg-ghana-green text-white px-4 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark"><Save size={14} /> Save WhatsApp widget</button>
            </div>
        </div>
    );
};

const SelectRow = ({ initial, options, onSave, testid }) => {
    const [v, setV] = useState(initial);
    useEffect(() => setV(initial), [initial]);
    return (
        <div className="flex gap-2">
            <select value={v} onChange={(e) => setV(e.target.value)} data-testid={testid}
                className="flex-1 border border-black/10 rounded-md px-3 py-2.5 text-sm bg-white focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none">
                {options.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
            <button onClick={() => onSave(v)} data-testid={`${testid}-save`} className="bg-ghana-green text-white px-4 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark"><Save size={14} /> Save</button>
        </div>
    );
};

const ToggleRow = ({ active, disabled, onChange, testid }) => (
    <label className={`inline-flex items-center gap-3 ${disabled ? "opacity-60" : "cursor-pointer"}`}>
        <span className={`relative w-11 h-6 rounded-full transition-colors ${active ? "bg-ghana-green" : "bg-slate-300"}`}>
            <span className={`absolute top-0.5 ${active ? "left-5" : "left-0.5"} w-5 h-5 bg-white rounded-full transition-all`} />
        </span>
        <input type="checkbox" className="hidden" checked={active} disabled={disabled} onChange={(e) => onChange(e.target.checked)} data-testid={testid} />
        <span className="text-sm font-medium">{active ? "Active" : "Inactive"}</span>
    </label>
);

const HubtelForm = ({ initial, onSave }) => {
    const [f, setF] = useState(initial);
    const set = (k, v) => setF((old) => ({ ...old, [k]: v }));
    const base = (process.env.REACT_APP_BACKEND_URL || window.location.origin).replace(/\/$/, "");
    const officialCallback = `${base}/api/webhooks/hubtel`;
    const officialReturn = `${base}/payment/return`;
    const officialCancel = `${base}/payment/cancelled`;
    const copy = (v) => { navigator.clipboard.writeText(v); toast.success("Copied"); };

    return (
        <div className="bg-white rounded-xl border border-black/10 p-6 space-y-4">
            <div className="font-heading font-semibold">Hubtel Configuration</div>
            <ToggleRow active={f.sandbox} onChange={(v) => set("sandbox", v)} testid="hubtel-sandbox" />
            <div className="text-xs text-slate-500 -mt-2">Sandbox mode simulates payments. Turn off once real API keys are configured below.</div>

            {/* Explicit warning when admin has picked PRODUCTION but credentials are missing */}
            {!f.sandbox && (["api_id", "api_key", "merchant_account_id"].some((k) => !String(f[k] || "").trim())) && (
                <div className="bg-ghana-red/10 border border-ghana-red text-ghana-red rounded-md px-4 py-3 text-sm" data-testid="hubtel-missing-warning">
                    <div className="font-semibold">⚠ Production mode is ON but Hubtel credentials are incomplete</div>
                    <div className="mt-1 text-xs">
                        Missing: <strong>{["api_id", "api_key", "merchant_account_id"].filter((k) => !String(f[k] || "").trim()).join(", ")}</strong>.
                        Card payments will return HTTP 503 to customers until these are filled in — no silent sandbox fallback.
                    </div>
                </div>
            )}

            <div className="border-t border-black/5 pt-4">
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-2">Production URLs — copy these into your Hubtel dashboard</div>
                {[
                    ["Callback URL (server-to-server)", officialCallback, "hubtel-official-callback"],
                    ["Return URL (customer redirect after payment)", officialReturn, "hubtel-official-return"],
                    ["Cancellation URL (customer clicks cancel)", officialCancel, "hubtel-official-cancel"],
                ].map(([label, val, tid]) => (
                    <div key={tid} className="mb-3">
                        <div className="text-[11px] uppercase tracking-wider text-slate-600 font-medium">{label}</div>
                        <div className="flex gap-2 mt-1">
                            <input readOnly value={val} data-testid={tid}
                                className="flex-1 bg-slate-50 border border-black/10 rounded-md px-3 py-2 text-xs font-mono text-slate-700" />
                            <button type="button" onClick={() => copy(val)} className="border border-black/10 px-3 py-2 rounded-md text-xs hover:bg-slate-50">Copy</button>
                        </div>
                    </div>
                ))}
                <div className="text-[11px] text-slate-500 mt-1">
                    <strong>Callback URL</strong> is a secure backend endpoint used only for Hubtel → server payment notifications. It is what updates the application status after payment.<br />
                    <strong>Return URL</strong> is the customer-facing page shown after checkout — display only, does <em>not</em> change payment state.
                </div>
            </div>

            <div className="grid md:grid-cols-2 gap-4 border-t border-black/5 pt-4">
                {[
                    ["api_id", "API ID"],
                    ["api_key", "API Key"],
                    ["merchant_account_id", "Merchant Account ID"],
                    ["callback_url", "Callback URL (paste from above)"],
                    ["return_url", "Return URL (paste from above)"],
                    ["cancellation_url", "Cancellation URL (paste from above)"],
                ].map(([k, label]) => (
                    <div key={k}>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">{label}</label>
                        <input value={f[k] || ""} onChange={(e) => set(k, e.target.value)} data-testid={`hubtel-${k}`}
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                    </div>
                ))}
            </div>
            <div className="flex gap-2 flex-wrap">
                <button onClick={() => onSave(f)} data-testid="hubtel-save" className="bg-ghana-green text-white px-5 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark"><Save size={14} /> Save Hubtel</button>
                <button
                    type="button"
                    onClick={() => setF((old) => ({ ...old, callback_url: officialCallback, return_url: officialReturn, cancellation_url: officialCancel }))}
                    data-testid="hubtel-autofill-urls"
                    className="border border-black/10 px-5 py-2.5 rounded-md text-sm font-medium hover:bg-slate-50"
                >
                    Auto-fill URLs from above
                </button>
            </div>
        </div>
    );
};

const NowPaymentsForm = ({ initial, onSave, onTest, discountPct, onSaveDiscount }) => {
    const [f, setF] = useState({
        sandbox: initial.sandbox ?? true,
        api_key: initial.api_key || "",
        ipn_secret: initial.ipn_secret || "",
        sandbox_api_key: initial.sandbox_api_key || "",
        sandbox_ipn_secret: initial.sandbox_ipn_secret || "",
    });
    const [pct, setPct] = useState(discountPct || 0);
    useEffect(() => { setPct(discountPct || 0); }, [discountPct]);
    const set = (k, v) => setF((old) => ({ ...old, [k]: v }));
    const callbackUrl = `${(process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "")}/api/webhooks/nowpayments`;
    const configured = f.sandbox
        ? (f.sandbox_api_key && f.sandbox_ipn_secret)
        : (f.api_key && f.ipn_secret);

    return (
        <div className="bg-white rounded-xl border border-black/10 p-6 space-y-4">
            <div className="flex items-center justify-between gap-2 flex-wrap">
                <div>
                    <div className="font-heading font-semibold">NowPayments Configuration (USDT TRC20/BEP20)</div>
                    <div className="text-xs text-slate-500 mt-0.5">Get keys at nowpayments.io → Store Settings.</div>
                </div>
                {!configured && (
                    <span className="text-[10px] uppercase tracking-widest bg-ghana-red/10 text-ghana-red px-2 py-1 rounded font-bold" data-testid="np-required-badge">Configuration required</span>
                )}
            </div>

            <ToggleRow active={f.sandbox} onChange={(v) => set("sandbox", v)} testid="np-sandbox" />
            <div className="text-xs text-slate-500 -mt-2">Sandbox uses <span className="font-mono">api-sandbox.nowpayments.io</span>. Production uses <span className="font-mono">api.nowpayments.io</span>.</div>

            <div className="border-t border-black/5 pt-4">
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-2">IPN Callback URL (copy into your NowPayments dashboard)</div>
                <div className="flex gap-2">
                    <input readOnly value={callbackUrl} data-testid="np-callback-url"
                        className="flex-1 bg-slate-50 border border-black/10 rounded-md px-3 py-2 text-xs font-mono text-slate-700" />
                    <button type="button" onClick={() => { navigator.clipboard.writeText(callbackUrl); toast.success("Copied"); }}
                        className="border border-black/10 px-3 py-2 rounded-md text-xs hover:bg-slate-50">Copy</button>
                </div>
            </div>

            <div className="grid md:grid-cols-2 gap-4 pt-4 border-t border-black/5">
                <div>
                    <div className="text-xs uppercase tracking-widest text-emerald-700 font-semibold mb-2">Sandbox credentials</div>
                    <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Sandbox API Key</label>
                    <input value={f.sandbox_api_key} onChange={(e) => set("sandbox_api_key", e.target.value)} data-testid="np-sandbox-key"
                        className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                    <label className="text-xs uppercase tracking-wider text-slate-600 font-medium mt-3 block">Sandbox IPN Secret</label>
                    <input value={f.sandbox_ipn_secret} onChange={(e) => set("sandbox_ipn_secret", e.target.value)} data-testid="np-sandbox-ipn"
                        className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                </div>
                <div>
                    <div className="text-xs uppercase tracking-widest text-ghana-red font-semibold mb-2">Production credentials</div>
                    <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Production API Key</label>
                    <input value={f.api_key} onChange={(e) => set("api_key", e.target.value)} data-testid="np-prod-key"
                        className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                    <label className="text-xs uppercase tracking-wider text-slate-600 font-medium mt-3 block">Production IPN Secret</label>
                    <input value={f.ipn_secret} onChange={(e) => set("ipn_secret", e.target.value)} data-testid="np-prod-ipn"
                        className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                </div>
            </div>

            <div className="pt-4 border-t border-black/5 flex gap-2 flex-wrap">
                <button onClick={() => onSave(f)} data-testid="np-save" className="bg-ghana-green text-white px-5 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark"><Save size={14} /> Save NowPayments</button>
                <button onClick={onTest} data-testid="np-test" className="border border-black/10 px-5 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-slate-50">Test connection</button>
            </div>

            <div className="pt-4 border-t border-black/5">
                <div className="font-heading font-semibold mb-1">USDT payment discount</div>
                <div className="text-xs text-slate-500 mb-3">Boost crypto adoption by offering a small discount on USDT payments (0–50%). Applied automatically at checkout, before the NowPayments payment is created.</div>
                <div className="flex items-center gap-2 max-w-xs">
                    <input type="number" step="0.1" min="0" max="50" value={pct} onChange={(e) => setPct(e.target.value)} data-testid="usdt-discount-input"
                        className="flex-1 border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                    <span className="font-heading font-semibold text-lg">%</span>
                    <button onClick={() => onSaveDiscount(parseFloat(pct) || 0)} data-testid="usdt-discount-save" className="bg-ghana-green text-white px-4 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark"><Save size={14} /> Save</button>
                </div>
            </div>
        </div>
    );
};



const AnalyticsIdsForm = ({ initial, onReload }) => {
    const [f, setF] = useState({
        ga4_measurement_id: initial?.ga4_measurement_id || "",
        gsc_verification: initial?.gsc_verification || "",
        clarity_project_id: initial?.clarity_project_id || "",
    });
    const set = (k, v) => setF((old) => ({ ...old, [k]: v }));
    const save = async () => {
        try {
            await api.post("/admin/settings/analytics-ids", f);
            toast.success("Analytics IDs saved");
            onReload();
        } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    };
    const rows = [
        { k: "ga4_measurement_id", label: "Google Analytics 4 — Measurement ID", ph: "G-XXXXXXXXXX", note: "Found in Google Analytics → Admin → Data Streams. GA4 loads only after user accepts Analytics cookies." },
        { k: "gsc_verification", label: "Google Search Console — verification code", ph: "abcdef123456...", note: "Copy the content value from the HTML meta-tag verification method in GSC. Injected as a passive <meta> tag (not a cookie)." },
        { k: "clarity_project_id", label: "Microsoft Clarity — Project ID", ph: "abcdef1234", note: "From Clarity dashboard → Settings → Setup. Loads only after user accepts Analytics cookies." },
    ];
    return (
        <div className="bg-white rounded-xl border border-black/10 p-6 space-y-5">
            <div className="font-heading font-semibold">Analytics &amp; SEO integrations</div>
            <p className="text-xs text-slate-500 -mt-2">Paste your IDs below. Scripts are loaded on the public site only after the visitor accepts the Analytics cookie category (GDPR-compliant).</p>
            {rows.map((r) => (
                <div key={r.k}>
                    <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">{r.label}</label>
                    <input value={f[r.k]} onChange={(e) => set(r.k, e.target.value)} data-testid={`analytics-${r.k}`} placeholder={r.ph}
                        className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none font-mono" />
                    <div className="text-[11px] text-slate-500 mt-1">{r.note}</div>
                </div>
            ))}
            <button onClick={save} data-testid="analytics-ids-save" className="bg-ghana-green text-white px-5 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark"><Save size={14} /> Save analytics IDs</button>
        </div>
    );
};

const DangerZone = ({ onReload }) => {
    const [preview, setPreview] = useState(null);
    const [confirmWipe, setConfirmWipe] = useState("");
    const [busy, setBusy] = useState(false);

    const runPreview = async () => {
        setBusy(true);
        try {
            const { data } = await api.get("/admin/cleanup/preview");
            setPreview(data);
        } catch (e) { toast.error(e?.response?.data?.detail || "Preview failed"); }
        finally { setBusy(false); }
    };
    const runCleanTests = async () => {
        if (!window.confirm(`Delete ${preview?.count ?? "?"} test applications and their payment/log records? This cannot be undone.`)) return;
        setBusy(true);
        try {
            const { data } = await api.post("/admin/cleanup/test-data");
            toast.success(`Removed ${data.deleted.applications} test applications`);
            setPreview(null); onReload();
        } catch (e) { toast.error(e?.response?.data?.detail || "Cleanup failed"); }
        finally { setBusy(false); }
    };
    const runWipeAll = async () => {
        if (confirmWipe !== "DELETE ALL") { toast.error('Type exactly "DELETE ALL" to confirm.'); return; }
        setBusy(true);
        try {
            const { data } = await api.post("/admin/cleanup/wipe-all", { confirm: confirmWipe });
            const total = Object.values(data.deleted).reduce((a, b) => a + b, 0);
            toast.success(`Wiped ${total} records across ${Object.keys(data.deleted).length} collections`);
            setConfirmWipe(""); setPreview(null); onReload();
        } catch (e) { toast.error(e?.response?.data?.detail || "Wipe failed"); }
        finally { setBusy(false); }
    };

    return (
        <div className="space-y-5">
            <div className="bg-white border border-ghana-gold/50 rounded-xl p-6 space-y-4">
                <div>
                    <div className="font-heading font-semibold text-lg text-ghana-black">Safe cleanup — test applications only</div>
                    <p className="text-xs text-slate-600 mt-1">Removes applications matching test heuristics (obvious dummy emails/names/passport numbers). Preview first, then confirm. Admin settings, email templates and user accounts are preserved.</p>
                </div>
                <div className="flex gap-2 flex-wrap">
                    <button onClick={runPreview} disabled={busy} data-testid="cleanup-preview" className="border border-black/10 px-4 py-2 rounded-md text-sm hover:bg-slate-50">Preview test records</button>
                    <button onClick={runCleanTests} disabled={busy || !preview || preview.count === 0} data-testid="cleanup-run" className="bg-ghana-gold text-ghana-black px-4 py-2 rounded-md text-sm font-medium hover:bg-ghana-gold/90 disabled:opacity-40">Delete {preview?.count ?? "…"} test records</button>
                </div>
                {preview && (
                    <div className="mt-2 border border-black/10 rounded-lg overflow-hidden">
                        <div className="bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-widest">{preview.count} matches</div>
                        <div className="max-h-72 overflow-y-auto">
                            {preview.items.length === 0 && <div className="p-6 text-center text-sm text-slate-500">No test-looking records found. Clean!</div>}
                            {preview.items.map((it) => (
                                <div key={it.tracking_no} className="grid grid-cols-[110px_1fr_1fr] gap-2 px-3 py-2 text-xs border-t border-slate-100">
                                    <span className="font-mono text-ghana-black">{it.tracking_no}</span>
                                    <span className="truncate">{it.full_name}</span>
                                    <span className="truncate text-slate-500">{it.email}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            <div className="bg-white border-2 border-ghana-red rounded-xl p-6 space-y-4">
                <div>
                    <div className="font-heading font-semibold text-lg text-ghana-red">Nuclear cleanup — wipe everything</div>
                    <p className="text-xs text-slate-600 mt-1">Deletes <strong>all</strong> applications, payment records, callbacks, email logs, chat sessions and analytics events. Only use this once before go-live or if instructed. Admin accounts, visa prices, email templates and integration keys remain intact.</p>
                </div>
                <div>
                    <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Type <code className="bg-slate-100 px-1.5 py-0.5 rounded">DELETE ALL</code> to confirm</label>
                    <div className="flex gap-2 mt-1.5">
                        <input value={confirmWipe} onChange={(e) => setConfirmWipe(e.target.value)} data-testid="danger-confirm" placeholder="DELETE ALL"
                            className="flex-1 border border-ghana-red/40 rounded-md px-3 py-2.5 text-sm focus:border-ghana-red focus:ring-1 focus:ring-ghana-red outline-none font-mono" />
                        <button onClick={runWipeAll} disabled={busy || confirmWipe !== "DELETE ALL"} data-testid="danger-wipe" className="bg-ghana-red text-white px-5 py-2.5 rounded-md text-sm font-medium hover:brightness-110 disabled:opacity-40">Wipe all data</button>
                    </div>
                </div>
            </div>
        </div>
    );
};

const R2StorageForm = ({ initial, onReload }) => {
    const cur = initial?.r2 || {};
    const [f, setF] = useState({
        enabled: cur.enabled ?? true,
        account_id: cur.account_id || "",
        bucket: cur.bucket || "",
        access_key_id: cur.access_key_id || "",
        secret_access_key: "",  // never re-populated (masked server-side)
        cdn_domain: cur.cdn_domain || "https://cdn.eghanavisa.com",
        env_prefix: cur.env_prefix || "",
        signed_url_ttl: cur.signed_url_ttl || 900,
    });
    const set = (k, v) => setF((old) => ({ ...old, [k]: v }));
    const [status, setStatus] = useState(null);
    const [testResult, setTestResult] = useState(null);
    const [busy, setBusy] = useState(false);

    const reloadStatus = async () => {
        try {
            const { data } = await api.get("/admin/storage/status");
            setStatus(data);
        } catch (e) { /* ignore */ }
    };
    useEffect(() => { reloadStatus(); }, []);

    const save = async () => {
        setBusy(true);
        try {
            await api.post("/admin/settings/r2", f);
            toast.success("R2 configuration saved");
            setF((old) => ({ ...old, secret_access_key: "" }));
            onReload(); reloadStatus();
        } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
        finally { setBusy(false); }
    };
    const test = async () => {
        setBusy(true); setTestResult(null);
        try {
            const { data } = await api.post("/admin/storage/test");
            setTestResult(data);
            if (data.ok) toast.success("R2 connection successful");
            else toast.error(`R2 test failed: ${data.detail || "unknown"}`);
        } catch (e) {
            const detail = e?.response?.data?.detail || e.message;
            setTestResult({ ok: false, detail });
            toast.error(`Test error: ${detail}`);
        } finally { setBusy(false); }
    };

    const secretHint = cur.secret_access_key && !f.secret_access_key ? `Currently: ${cur.secret_access_key} (leave empty to keep)` : "";

    return (
        <div className="space-y-5">
            {/* Live status card */}
            {status && (
                <div className="bg-white border border-black/10 rounded-xl p-5 grid md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">Active backend</div>
                        <div className={`font-heading font-bold mt-1 ${status.active_backend?.startsWith("r2") ? "text-ghana-green" : "text-slate-600"}`} data-testid="r2-active-backend">{status.active_backend}</div>
                    </div>
                    <div>
                        <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">Environment</div>
                        <div className="font-mono mt-1" data-testid="r2-env">{status.env_prefix} <span className="text-xs text-slate-400">(detected: {status.env_detected})</span></div>
                    </div>
                    <div>
                        <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">Bucket</div>
                        <div className="font-mono mt-1">{status.bucket || <span className="text-slate-400 italic">not configured</span>}</div>
                    </div>
                    <div>
                        <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">Signed URL TTL</div>
                        <div className="font-mono mt-1">{status.signed_url_ttl}s ({Math.round(status.signed_url_ttl / 60)}m)</div>
                    </div>
                </div>
            )}

            <div className="bg-white border border-black/10 rounded-xl p-6 space-y-4">
                <div className="flex items-center justify-between">
                    <div>
                        <div className="font-heading font-semibold">Cloudflare R2 credentials</div>
                        <p className="text-xs text-slate-500 mt-1">Files uploaded via <code className="bg-slate-100 px-1 rounded">POST /api/applications/&#123;tn&#125;/documents</code> are stored privately in R2 and served via short-lived signed URLs. Nothing hardcoded — everything read from this form.</p>
                    </div>
                    <ToggleRow active={f.enabled} onChange={(v) => set("enabled", v)} testid="r2-enabled" />
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                    <div>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Account ID</label>
                        <input value={f.account_id} onChange={(e) => set("account_id", e.target.value)} data-testid="r2-account-id" placeholder="32-char hex from Cloudflare R2 → Overview"
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm font-mono focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                    </div>
                    <div>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Bucket name</label>
                        <input value={f.bucket} onChange={(e) => set("bucket", e.target.value)} data-testid="r2-bucket" placeholder="eghanavisa"
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm font-mono focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                    </div>
                    <div>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Access Key ID</label>
                        <input value={f.access_key_id} onChange={(e) => set("access_key_id", e.target.value)} data-testid="r2-access-key-id"
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm font-mono focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                    </div>
                    <div>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Secret Access Key</label>
                        <input value={f.secret_access_key} onChange={(e) => set("secret_access_key", e.target.value)} data-testid="r2-secret-access-key" type="password" placeholder={secretHint || "Enter secret (write-only)"}
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm font-mono focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                        {secretHint && <div className="text-[11px] text-slate-500 mt-1">{secretHint}</div>}
                    </div>
                    <div>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">CDN custom domain</label>
                        <input value={f.cdn_domain} onChange={(e) => set("cdn_domain", e.target.value)} data-testid="r2-cdn-domain" placeholder="https://cdn.eghanavisa.com"
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm font-mono focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                        <div className="text-[11px] text-slate-500 mt-1">Optional. When set, signed URLs are generated against this host. Configure the domain in Cloudflare → R2 → Bucket → Settings → Custom Domains (keep &quot;Restrict Access&quot; enabled).</div>
                    </div>
                    <div>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Environment prefix</label>
                        <input value={f.env_prefix} onChange={(e) => set("env_prefix", e.target.value)} data-testid="r2-env-prefix" placeholder="(leave empty for auto: production / preview / development)"
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm font-mono focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                    </div>
                    <div>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Signed URL TTL (seconds)</label>
                        <input value={f.signed_url_ttl} onChange={(e) => set("signed_url_ttl", parseInt(e.target.value || "0", 10))} data-testid="r2-signed-url-ttl" type="number" min="60" max="86400"
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm font-mono focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                        <div className="text-[11px] text-slate-500 mt-1">Default 900 (15 min). Min 60s, max 86400s (24h).</div>
                    </div>
                </div>

                <div className="flex gap-2 flex-wrap">
                    <button onClick={save} disabled={busy} data-testid="r2-save" className="bg-ghana-green text-white px-5 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark disabled:opacity-50">
                        <Save size={14} /> Save R2 configuration
                    </button>
                    <button onClick={test} disabled={busy} data-testid="r2-test" className="border border-ghana-green text-ghana-green px-5 py-2.5 rounded-md text-sm font-medium hover:bg-ghana-green/5 disabled:opacity-50">
                        Test R2 connection
                    </button>
                </div>

                {testResult && (
                    <div className={`mt-2 p-3 rounded-lg text-sm font-mono ${testResult.ok ? "bg-ghana-green/5 border border-ghana-green/30 text-ghana-green-dark" : "bg-ghana-red/5 border border-ghana-red/30 text-ghana-red"}`} data-testid="r2-test-result">
                        {testResult.ok ? (
                            <div>
                                <div className="font-semibold">✔ R2 connection OK</div>
                                <div className="mt-1 text-xs">Bucket: <strong>{testResult.bucket}</strong> · Env: <strong>{testResult.env_prefix}</strong> · TTL: <strong>{testResult.signed_url_ttl}s</strong>{testResult.cdn_domain ? ` · CDN: ${testResult.cdn_domain}` : ""}</div>
                            </div>
                        ) : (
                            <div>
                                <div className="font-semibold">✘ R2 connection failed</div>
                                <div className="mt-1 text-xs">{testResult.detail}</div>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Folder layout reference */}
            <div className="bg-white border border-black/10 rounded-xl p-5">
                <div className="font-heading font-semibold text-sm mb-2">Folder layout inside the bucket</div>
                <pre className="text-[11px] font-mono bg-slate-50 rounded-md p-3 leading-relaxed overflow-x-auto">{`{env}/applicants/{tracking_no}/photos/…
{env}/applicants/{tracking_no}/passports/…
{env}/applicants/{tracking_no}/supporting-documents/…
{env}/payments/{tracking_no}/…
{env}/invoices/{tracking_no}/…
{env}/exports/{yyyy-mm-dd}/…`}</pre>
                <div className="text-[11px] text-slate-500 mt-2">Bucket must stay private. Downloads are served exclusively via short-lived pre-signed URLs. When an application (or the Danger Zone wipe) deletes records, the corresponding R2 folder is purged automatically.</div>
            </div>
        </div>
    );
};


const FxForm = ({ initial, onReload }) => {
    const cur = initial?.fx || { provider: "open_er_api", manual_rate: 0, buffer_pct: 0, cache_seconds: 900 };
    const [f, setF] = useState(cur);
    const [providers, setProviders] = useState([]);
    const [live, setLive] = useState(null);
    const [busy, setBusy] = useState(false);
    const set = (k, v) => setF((old) => ({ ...old, [k]: v }));

    useEffect(() => {
        (async () => {
            try {
                const [{ data: p }, { data: l }] = await Promise.all([
                    api.get("/admin/fx/providers"),
                    api.get("/admin/fx/live"),
                ]);
                setProviders(p.providers || []);
                setLive(l);
            } catch (e) { /* ignore */ }
        })();
    }, []);

    const save = async () => {
        setBusy(true);
        try {
            await api.post("/admin/settings/fx", f);
            toast.success("Exchange-rate configuration saved");
            const { data: l } = await api.get("/admin/fx/live"); setLive(l);
            onReload();
        } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
        finally { setBusy(false); }
    };
    const refresh = async () => {
        setBusy(true);
        try {
            const { data: l } = await api.get("/admin/fx/live"); setLive(l);
            if (l.ok) toast.success(`Live rate: 1 USD = ${l.rate} GHS`);
            else toast.error(l.detail || "Failed to fetch rate");
        } finally { setBusy(false); }
    };

    return (
        <div className="space-y-5">
            {live && (
                <div className={`rounded-xl border p-5 ${live.ok ? "bg-ghana-green/5 border-ghana-green/40" : "bg-ghana-red/5 border-ghana-red/40"}`}>
                    {live.ok ? (
                        <div className="grid md:grid-cols-4 gap-4 text-sm">
                            <div>
                                <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">Current rate</div>
                                <div className="font-heading font-bold text-2xl text-ghana-green-dark mt-1" data-testid="fx-live-rate">1 USD = {live.rate} GHS</div>
                            </div>
                            <div>
                                <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">Applied (with buffer)</div>
                                <div className="font-mono mt-1">{live.buffered_rate} <span className="text-slate-500 text-xs">(+{live.buffer_pct}%)</span></div>
                            </div>
                            <div>
                                <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">Provider</div>
                                <div className="mt-1">{live.provider}</div>
                            </div>
                            <div>
                                <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">$100 = ?</div>
                                <div className="font-mono mt-1">{live.sample_100_usd_to_ghs} GHS</div>
                            </div>
                            <div className="md:col-span-4 text-[11px] text-slate-500">Source: <a href={live.source_url} target="_blank" rel="noreferrer" className="underline">{live.source_url}</a> · Fetched {live.fetched_at} · {live.from_cache ? "from cache" : "fresh"}</div>
                        </div>
                    ) : (
                        <div className="text-sm text-ghana-red"><strong>✘ Rate unavailable:</strong> {live.detail}</div>
                    )}
                </div>
            )}

            <div className="bg-white border border-black/10 rounded-xl p-6 space-y-4">
                <div className="font-heading font-semibold">USD → GHS conversion for Hubtel checkout</div>
                <p className="text-xs text-slate-500 -mt-2">Applied automatically before every Hubtel checkout. All visa prices remain stored in USD; only the amount sent to Hubtel is converted. Every payment record persists the original USD amount, the charged GHS amount, the rate used and the timestamp for reconciliation.</p>

                <div className="grid md:grid-cols-2 gap-4">
                    <div>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Provider</label>
                        <select value={f.provider} onChange={(e) => set("provider", e.target.value)} data-testid="fx-provider"
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm bg-white focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none">
                            {providers.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Manual rate (used when provider = Manual, or as fallback)</label>
                        <input type="number" step="0.0001" value={f.manual_rate} onChange={(e) => set("manual_rate", parseFloat(e.target.value || "0"))} data-testid="fx-manual-rate"
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm font-mono focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                    </div>
                    <div>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Buffer % (safety margin for intraday drift)</label>
                        <input type="number" step="0.1" min="0" max="10" value={f.buffer_pct} onChange={(e) => set("buffer_pct", parseFloat(e.target.value || "0"))} data-testid="fx-buffer-pct"
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm font-mono focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                        <div className="text-[11px] text-slate-500 mt-1">e.g. 1% covers small overnight FX drift. Max 10%.</div>
                    </div>
                    <div>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Cache TTL (seconds)</label>
                        <input type="number" min="60" max="86400" value={f.cache_seconds} onChange={(e) => set("cache_seconds", parseInt(e.target.value || "0", 10))} data-testid="fx-cache-seconds"
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm font-mono focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                        <div className="text-[11px] text-slate-500 mt-1">Default 900s (15 min). We don&apos;t hit the FX API on every checkout.</div>
                    </div>
                </div>

                <div className="flex gap-2 flex-wrap">
                    <button onClick={save} disabled={busy} data-testid="fx-save" className="bg-ghana-green text-white px-5 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark disabled:opacity-50">
                        <Save size={14} /> Save FX configuration
                    </button>
                    <button onClick={refresh} disabled={busy} data-testid="fx-refresh" className="border border-ghana-green text-ghana-green px-5 py-2.5 rounded-md text-sm font-medium hover:bg-ghana-green/5 disabled:opacity-50">
                        Refresh live rate
                    </button>
                </div>
            </div>
        </div>
    );
};

