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

const SEC = { prices: "Visa Prices", types: "Visa Types", methods: "Payment Methods", hubtel: "Hubtel API", nowpayments: "NowPayments (USDT)", other: "WhatsApp & AI" };

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
    const saveAI = async (v) => { await api.post("/admin/settings/ai-model", { ai_model: v }); toast.success("Saved"); reload(); };
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
                        <Card title="WhatsApp support number (used by Ama)">
                            <TextRow initial={s.whatsapp_admin} onSave={saveWhatsapp} testid="whatsapp" placeholder="+233..." />
                        </Card>
                        <Card title="AI model for Ama chat">
                            <SelectRow initial={s.ai_model} options={AI_MODELS} onSave={saveAI} testid="ai-model" />
                        </Card>
                    </>
                )}
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

const HubtelForm = ({ initial, onSave }) => {    const [f, setF] = useState(initial);
    const set = (k, v) => setF((old) => ({ ...old, [k]: v }));
    return (
        <div className="bg-white rounded-xl border border-black/10 p-6 space-y-4">
            <div className="font-heading font-semibold">Hubtel Configuration</div>
            <ToggleRow active={f.sandbox} onChange={(v) => set("sandbox", v)} testid="hubtel-sandbox" />
            <div className="text-xs text-slate-500 -mt-2">Sandbox mode simulates payments. Turn off once real API keys are configured below.</div>
            <div className="grid md:grid-cols-2 gap-4">
                {[
                    ["api_id", "API ID"],
                    ["api_key", "API Key"],
                    ["merchant_account_id", "Merchant Account ID"],
                    ["callback_url", "Callback URL"],
                    ["return_url", "Return URL"],
                    ["outbound_proxy_url", "Outbound static IP proxy URL (optional, e.g. Fixie)"],
                ].map(([k, label]) => (
                    <div key={k}>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">{label}</label>
                        <input value={f[k] || ""} onChange={(e) => set(k, e.target.value)} data-testid={`hubtel-${k}`}
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                    </div>
                ))}
            </div>
            <button onClick={() => onSave(f)} data-testid="hubtel-save" className="bg-ghana-green text-white px-5 py-2.5 rounded-md text-sm font-medium inline-flex items-center gap-2 hover:bg-ghana-green-dark"><Save size={14} /> Save Hubtel</button>
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

