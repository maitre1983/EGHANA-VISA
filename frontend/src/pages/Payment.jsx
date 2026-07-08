import React, { useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CreditCard, Bitcoin, ShieldCheck, CheckCircle2, Loader2, Copy, Clock } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { log } from "../lib/log";

export default function Payment() {
    const { tracking } = useParams();
    const nav = useNavigate();
    const [config, setConfig] = useState(null);
    const [loading, setLoading] = useState(false);
    const [sandboxTx, setSandboxTx] = useState(null);
    const [crypto, setCrypto] = useState(null); // active USDT payment state
    const pollRef = useRef(null);

    // Fetch site config once on mount — no deps intentionally
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { api.get("/config").then(({ data }) => setConfig(data)); }, []);
    // Cleanup poll interval on unmount
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

    const startPayment = async () => {
        setLoading(true);
        try {
            const { data } = await api.post("/payments/initiate", { tracking_no: tracking });
            if (data.sandbox) setSandboxTx(data);
            else window.location.href = data.checkout_url;
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Payment initiation failed");
        } finally { setLoading(false); }
    };

    const confirmSandbox = async (success) => {
        setLoading(true);
        try {
            await api.post("/payments/confirm", { tracking_no: tracking, success });
            if (success) nav(`/success/${tracking}`); else toast.error("Payment marked as failed");
        } finally { setLoading(false); }
    };

    const startCrypto = async (network) => {
        setLoading(true);
        try {
            const { data } = await api.post("/payments/crypto/initiate", { tracking_no: tracking, network });
            setCrypto(data);
            // Poll every 15s
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = setInterval(async () => {
                try {
                    const { data: st } = await api.get(`/payments/crypto/status/${data.payment_id}`);
                    setCrypto((c) => ({ ...c, ...st }));
                    if (st.internal_status === "paid") {
                        clearInterval(pollRef.current);
                        toast.success("Payment received!");
                        nav(`/success/${tracking}`);
                    } else if (st.internal_status === "failed") {
                        clearInterval(pollRef.current);
                        toast.error("Payment failed or expired");
                    }
                } catch (err) {
                    log.warn("Crypto status poll failed (will retry):", err?.message || err);
                }
            }, 15000);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Crypto payment initiation failed");
        } finally { setLoading(false); }
    };

    const cryptoActive = (code) => (config?.payment_methods || []).find((p) => p.code === code)?.active;
    const cryptoConfigured = config?.nowpayments_configured;
    const hubtelActive = cryptoActive("hubtel_visa");
    const discountPct = Number(config?.usdt_discount_pct || 0);

    return (
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Payment</div>
            <h1 className="mt-2 text-3xl md:text-4xl font-heading font-bold">Complete your payment</h1>
            <p className="mt-3 text-slate-600">Tracking number: <span className="font-heading font-semibold" data-testid="payment-tracking">{tracking}</span></p>

            {config?.hubtel_sandbox && (
                <div className="mt-6 bg-ghana-gold/20 border border-ghana-gold text-ghana-black rounded-md px-4 py-3 text-sm flex items-center gap-2" data-testid="payment-sandbox-banner">
                    <ShieldCheck size={16} /> Payment gateway in <strong>SANDBOX</strong> mode. No real charges.
                </div>
            )}

            {/* If a crypto payment is active, show the deposit panel */}
            {crypto ? (
                <CryptoDepositPanel crypto={crypto} tracking={tracking} onCancel={() => { clearInterval(pollRef.current); setCrypto(null); }} />
            ) : (
                <div className="mt-8 space-y-4">
                    {/* Hubtel */}
                    <div className={`bg-white rounded-xl border ${hubtelActive ? "border-black/10" : "border-black/5 opacity-60"} p-6`}>
                        <div className="flex items-center justify-between gap-4 flex-wrap">
                            <div className="flex items-center gap-4">
                                <div className="w-12 h-12 rounded-lg bg-ghana-green/10 flex items-center justify-center text-ghana-green"><CreditCard size={22} /></div>
                                <div>
                                    <div className="font-heading font-semibold">Visa Card (via Hubtel)</div>
                                    <div className="text-xs text-slate-500">Secure card checkout · SSL encrypted</div>
                                </div>
                            </div>
                            <button onClick={startPayment} disabled={!hubtelActive || loading} data-testid="payment-hubtel-btn"
                                className="bg-ghana-green text-white px-6 py-2.5 rounded-md text-sm font-medium hover:bg-ghana-green-dark transition-colors disabled:opacity-50 inline-flex items-center gap-2">
                                {loading ? <Loader2 className="animate-spin" size={14} /> : null} Pay now
                            </button>
                        </div>
                    </div>

                    {/* USDT — visible only when active AND configured */}
                    {[
                        { code: "usdt_trc20", network: "trc20", label: "USDT (TRC20 · TRON)", desc: "Low fees, ~1 min settlement" },
                        { code: "usdt_bep20", network: "bep20", label: "USDT (BEP20 · BSC)", desc: "Low fees, ~30 sec settlement" },
                    ].map((m) => {
                        const active = cryptoActive(m.code);
                        const visible = active; // toggle governs visibility (simulation fills the gap when unconfigured)
                        const isSimulation = active && !cryptoConfigured;
                        const comingSoon = !active;
                        return (
                            <div key={m.code} className={`bg-white rounded-xl border ${visible ? "border-black/10" : "border-black/5 opacity-60"} p-6 relative`}>
                                {visible && discountPct > 0 && (
                                    <span className="absolute -top-3 -right-3 bg-ghana-red text-white text-[11px] font-bold uppercase tracking-widest px-3 py-1 rounded-full shadow-md" data-testid={`${m.code}-discount-badge`}>
                                        Save {discountPct}%
                                    </span>
                                )}
                                <div className="flex items-center justify-between gap-4 flex-wrap">
                                    <div className="flex items-center gap-4">
                                        <div className="w-12 h-12 rounded-lg bg-emerald-50 flex items-center justify-center text-emerald-600"><Bitcoin size={22} /></div>
                                        <div>
                                            <div className="font-heading font-semibold flex items-center gap-2">
                                                {m.label}
                                                {comingSoon && <span className="text-[10px] uppercase tracking-widest bg-ghana-gold/40 text-ghana-black px-2 py-0.5 rounded font-bold">Coming Soon</span>}
                                                {isSimulation && <span className="text-[10px] uppercase tracking-widest bg-ghana-gold text-ghana-black px-2 py-0.5 rounded font-bold" data-testid={`${m.code}-simulation-badge`}>Sandbox</span>}
                                            </div>
                                            <div className="text-xs text-slate-500">
                                                {m.desc}
                                                {visible && discountPct > 0 && <span className="ml-2 text-ghana-green font-semibold">· {discountPct}% off applied automatically</span>}
                                            </div>
                                        </div>
                                    </div>
                                    <button onClick={() => startCrypto(m.network)} disabled={!visible || loading} data-testid={`payment-${m.code}-btn`}
                                        className="bg-emerald-600 text-white px-6 py-2.5 rounded-md text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50 inline-flex items-center gap-2">
                                        {loading ? <Loader2 className="animate-spin" size={14} /> : null} Pay with USDT
                                    </button>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Sandbox modal for Hubtel */}
            {sandboxTx && (
                <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-8" data-testid="payment-sandbox-modal">
                        <div className="w-14 h-14 rounded-full bg-ghana-gold/30 flex items-center justify-center mx-auto"><CreditCard className="text-ghana-black" /></div>
                        <h3 className="mt-4 font-heading text-xl font-semibold text-center">Hubtel Sandbox Checkout</h3>
                        <p className="mt-2 text-sm text-slate-600 text-center">Simulate a card payment for transaction <span className="font-mono">{sandboxTx.transaction_id}</span>.</p>
                        <div className="mt-6 grid grid-cols-2 gap-3">
                            <button onClick={() => confirmSandbox(false)} data-testid="sandbox-fail" className="border border-black/10 rounded-md py-2.5 text-sm hover:bg-slate-50">Simulate failure</button>
                            <button onClick={() => confirmSandbox(true)} data-testid="sandbox-success" className="bg-ghana-green text-white rounded-md py-2.5 text-sm font-medium hover:bg-ghana-green-dark inline-flex items-center justify-center gap-2">
                                <CheckCircle2 size={14} /> Simulate success
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function CryptoDepositPanel({ crypto, tracking, onCancel }) {
    const nav = useNavigate();
    const [simLoading, setSimLoading] = React.useState(false);
    const copy = (val) => { navigator.clipboard.writeText(String(val)); toast.success("Copied"); };
    const networkText = crypto.network === "trc20" ? "TRON (TRC20)" : "Binance Smart Chain (BEP20)";
    const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(crypto.pay_address || "")}`;

    const simulateFinish = async (success) => {
        setSimLoading(true);
        try {
            await api.post(`/payments/crypto/simulate-finish/${crypto.payment_id}`, { success });
            if (success) {
                toast.success("Simulated payment received");
                nav(`/success/${tracking}`);
            } else {
                toast.error("Simulated failure applied");
                onCancel();
            }
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Simulation failed");
        } finally { setSimLoading(false); }
    };

    return (
        <div className="mt-8 bg-white rounded-xl border border-emerald-200 p-8 shadow-sm" data-testid="crypto-deposit">
            {crypto.simulated && (
                <div className="mb-6 bg-ghana-gold/20 border border-ghana-gold text-ghana-black rounded-md px-4 py-3 text-sm flex items-center gap-2" data-testid="crypto-sandbox-banner">
                    <ShieldCheck size={16} /> USDT gateway in <strong>SANDBOX</strong> mode. This address is fake — no funds will move.
                </div>
            )}
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                    <div className="text-xs uppercase tracking-widest text-emerald-700 font-semibold">Awaiting deposit</div>
                    <h2 className="mt-1 font-heading text-2xl font-bold">Send USDT · {networkText}</h2>
                </div>
                <span className="text-[10px] uppercase tracking-widest bg-emerald-100 text-emerald-800 px-2 py-1 rounded font-bold">
                    Status: {crypto.payment_status || "waiting"}
                </span>
            </div>

            <div className="mt-6 grid md:grid-cols-[180px_1fr] gap-6 items-center">
                <img src={qrUrl} alt="Deposit QR" className="w-[180px] h-[180px] rounded-lg border border-black/5" />
                <div className="space-y-4">
                    <Kv label="Amount to send" value={<span className="font-heading font-bold text-2xl">{crypto.pay_amount} <span className="text-sm text-slate-500 uppercase">{crypto.pay_currency}</span></span>} onCopy={() => copy(crypto.pay_amount)} />
                    <Kv label="Deposit address" mono value={crypto.pay_address} onCopy={() => copy(crypto.pay_address)} />
                    <Kv label="Network" value={<span className="font-semibold">{networkText}</span>} />
                </div>
            </div>

            <div className="mt-6 rounded-md bg-ghana-red/5 border border-ghana-red/30 p-4 text-sm text-ghana-black" data-testid="crypto-warning">
                <strong className="text-ghana-red">⚠ Send only USDT on the {networkText} network.</strong> Any other coin or network will be permanently lost.
            </div>

            {crypto.simulated ? (
                <div className="mt-6 grid grid-cols-2 gap-3">
                    <button onClick={() => simulateFinish(false)} disabled={simLoading} data-testid="crypto-sim-fail"
                        className="border border-black/10 rounded-md py-2.5 text-sm hover:bg-slate-50 disabled:opacity-50">Simulate failure</button>
                    <button onClick={() => simulateFinish(true)} disabled={simLoading} data-testid="crypto-sim-success"
                        className="bg-emerald-600 text-white rounded-md py-2.5 text-sm font-medium hover:bg-emerald-700 inline-flex items-center justify-center gap-2 disabled:opacity-50">
                        {simLoading ? <Loader2 className="animate-spin" size={14} /> : <CheckCircle2 size={14} />} Simulate payment received
                    </button>
                </div>
            ) : (
                <div className="mt-6 flex items-center gap-2 text-xs text-slate-500">
                    <Clock size={14} className="animate-pulse" />
                    We check the blockchain automatically every 15 seconds. This page will refresh once the payment is confirmed.
                </div>
            )}

            <button onClick={onCancel} className="mt-4 text-xs text-slate-500 underline hover:text-ghana-black" data-testid="crypto-cancel">Cancel and choose another method</button>
        </div>
    );
}

function Kv({ label, value, mono, onCopy }) {
    return (
        <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">{label}</div>
            <div className={`mt-0.5 flex items-center gap-2 ${mono ? "font-mono text-sm break-all" : ""}`}>
                <div className="flex-1 min-w-0">{value}</div>
                {onCopy && <button onClick={onCopy} className="p-1.5 rounded hover:bg-slate-100"><Copy size={14} /></button>}
            </div>
        </div>
    );
}
