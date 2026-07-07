import React, { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { CreditCard, Bitcoin, ShieldCheck, CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";

export default function Payment() {
    const { tracking } = useParams();
    const [search] = useSearchParams();
    const nav = useNavigate();
    const [config, setConfig] = useState(null);
    const [loading, setLoading] = useState(false);
    const [sandboxTx, setSandboxTx] = useState(null);

    useEffect(() => { api.get("/config").then(({ data }) => setConfig(data)); }, []);

    const startPayment = async () => {
        setLoading(true);
        try {
            const { data } = await api.post("/payments/initiate", { tracking_no: tracking });
            if (data.sandbox) {
                setSandboxTx(data);
            } else {
                window.location.href = data.checkout_url;
            }
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Payment initiation failed");
        } finally {
            setLoading(false);
        }
    };

    const confirmSandbox = async (success) => {
        setLoading(true);
        try {
            await api.post("/payments/confirm", { tracking_no: tracking, success });
            if (success) nav(`/success/${tracking}`); else toast.error("Payment marked as failed");
        } finally { setLoading(false); }
    };

    const hubtelActive = (config?.payment_methods || []).find((p) => p.code === "hubtel_visa")?.active;

    return (
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Payment</div>
            <h1 className="mt-2 text-3xl md:text-4xl font-heading font-bold">Complete your payment</h1>
            <p className="mt-3 text-slate-600">Tracking number: <span className="font-heading font-semibold" data-testid="payment-tracking">{tracking}</span></p>

            {config?.hubtel_sandbox && (
                <div className="mt-6 bg-ghana-gold/20 border border-ghana-gold text-ghana-black rounded-md px-4 py-3 text-sm flex items-center gap-2" data-testid="payment-sandbox-banner">
                    <ShieldCheck size={16} /> Payment gateway in <strong>SANDBOX</strong> mode. No real charges will be made.
                </div>
            )}

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
                        <button
                            onClick={startPayment}
                            disabled={!hubtelActive || loading}
                            data-testid="payment-hubtel-btn"
                            className="bg-ghana-green text-white px-6 py-2.5 rounded-md text-sm font-medium hover:bg-ghana-green-dark transition-colors disabled:opacity-50 inline-flex items-center gap-2"
                        >
                            {loading ? <Loader2 className="animate-spin" size={14} /> : null} Pay now
                        </button>
                    </div>
                </div>

                {/* USDT slots */}
                {["usdt_trc20", "usdt_bep20"].map((code) => {
                    const method = (config?.payment_methods || []).find((p) => p.code === code);
                    return (
                        <div key={code} className="bg-white rounded-xl border border-black/5 p-6 opacity-60">
                            <div className="flex items-center gap-4">
                                <div className="w-12 h-12 rounded-lg bg-slate-100 flex items-center justify-center text-slate-500"><Bitcoin size={22} /></div>
                                <div className="flex-1">
                                    <div className="font-heading font-semibold flex items-center gap-2">
                                        {method?.name || (code === "usdt_trc20" ? "USDT (TRC20)" : "USDT (BEP20)")}
                                        <span className="text-[10px] uppercase tracking-widest bg-ghana-gold/40 text-ghana-black px-2 py-0.5 rounded font-bold">Coming Soon</span>
                                    </div>
                                    <div className="text-xs text-slate-500">Crypto wallet payment · not yet available</div>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Sandbox confirm modal */}
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
