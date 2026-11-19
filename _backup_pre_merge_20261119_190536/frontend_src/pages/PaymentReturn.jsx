import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, CheckCircle2, AlertTriangle } from "lucide-react";
import api from "../lib/api";
import { log } from "../lib/log";

/**
 * Customer landing page after Hubtel redirects them back from the hosted checkout.
 *
 * Hubtel appends `clientReference` (our tracking_no) and a status query param to
 * the return URL. This page shows a friendly "verifying payment…" state while
 * we poll our own /payments/status endpoint — the actual payment state is
 * flipped server-to-server by the Hubtel webhook, not by this page.
 */
export default function PaymentReturn() {
    const [params] = useSearchParams();
    const nav = useNavigate();
    const tracking =
        params.get("clientReference") ||
        params.get("client_reference") ||
        params.get("tracking") ||
        params.get("tracking_no") ||
        "";
    const [state, setState] = useState("verifying"); // verifying | paid | timeout | notfound
    const pollRef = useRef(null);
    const startRef = useRef(Date.now());

    useEffect(() => {
        if (!tracking) {
            setState("notfound");
            return undefined;
        }
        const tick = async () => {
            try {
                const { data } = await api.get(`/payments/status/${tracking}`);
                if (data.payment_status === "paid") {
                    if (pollRef.current) clearInterval(pollRef.current);
                    setState("paid");
                    setTimeout(() => nav(`/success/${tracking}`), 1200);
                } else if (Date.now() - startRef.current > 90_000) {
                    if (pollRef.current) clearInterval(pollRef.current);
                    setState("timeout");
                }
            } catch (err) {
                log.warn("Return-page status poll failed:", err?.message || err);
                if (Date.now() - startRef.current > 90_000) {
                    if (pollRef.current) clearInterval(pollRef.current);
                    setState("notfound");
                }
            }
        };
        tick();
        pollRef.current = setInterval(tick, 4000);
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, [tracking, nav]);

    return (
        <div className="max-w-xl mx-auto px-6 py-24 text-center" data-testid="payment-return">
            {state === "verifying" && (
                <>
                    <Loader2 className="mx-auto text-ghana-green animate-spin" size={44} />
                    <h1 className="mt-6 font-heading text-3xl font-bold">Verifying your payment…</h1>
                    <p className="mt-3 text-slate-600">Hubtel is confirming your transaction. This usually takes a few seconds.</p>
                    {tracking && (
                        <p className="mt-6 text-xs uppercase tracking-widest text-slate-500">Tracking # <span className="font-heading font-semibold text-ghana-black" data-testid="return-tracking">{tracking}</span></p>
                    )}
                </>
            )}
            {state === "paid" && (
                <>
                    <CheckCircle2 className="mx-auto text-ghana-green" size={48} />
                    <h1 className="mt-6 font-heading text-3xl font-bold">Payment received</h1>
                    <p className="mt-3 text-slate-600">Redirecting you to your confirmation…</p>
                </>
            )}
            {state === "timeout" && (
                <>
                    <AlertTriangle className="mx-auto text-ghana-gold" size={48} />
                    <h1 className="mt-6 font-heading text-3xl font-bold">Still processing…</h1>
                    <p className="mt-3 text-slate-600">Your bank is taking longer than usual to confirm. You will receive an email as soon as it goes through. You can also check status any time on the Track page.</p>
                    <div className="mt-8 flex gap-3 justify-center">
                        <a href={`/track?number=${tracking}`} data-testid="return-track" className="bg-ghana-black text-white px-6 py-3 rounded-md text-sm font-medium hover:bg-ghana-black/90">Go to Track</a>
                    </div>
                </>
            )}
            {state === "notfound" && (
                <>
                    <AlertTriangle className="mx-auto text-ghana-red" size={48} />
                    <h1 className="mt-6 font-heading text-3xl font-bold">Reference missing</h1>
                    <p className="mt-3 text-slate-600">We couldn&apos;t identify your payment. If you were just charged, please contact support with your bank reference.</p>
                    <div className="mt-8 flex gap-3 justify-center">
                        <a href="/track" data-testid="return-track" className="bg-ghana-black text-white px-6 py-3 rounded-md text-sm font-medium hover:bg-ghana-black/90">Go to Track</a>
                    </div>
                </>
            )}
        </div>
    );
}
