import React from "react";
import { useSearchParams, Link } from "react-router-dom";
import { XCircle } from "lucide-react";

export default function PaymentCancelled() {
    const [params] = useSearchParams();
    const tracking =
        params.get("clientReference") ||
        params.get("client_reference") ||
        params.get("tracking") ||
        "";
    return (
        <div className="max-w-xl mx-auto px-6 py-24 text-center" data-testid="payment-cancelled">
            <XCircle className="mx-auto text-ghana-red" size={48} />
            <h1 className="mt-6 font-heading text-3xl font-bold">Payment cancelled</h1>
            <p className="mt-3 text-slate-600">Your payment was cancelled and no charge was made. Your application is still saved and you can resume checkout any time.</p>
            {tracking && (
                <p className="mt-6 text-xs uppercase tracking-widest text-slate-500">Tracking # <span className="font-heading font-semibold text-ghana-black">{tracking}</span></p>
            )}
            <div className="mt-8 flex gap-3 justify-center">
                {tracking && (
                    <Link to={`/payment/${tracking}`} data-testid="cancelled-retry" className="bg-ghana-green text-white px-6 py-3 rounded-md text-sm font-medium hover:bg-ghana-green-dark">Retry payment</Link>
                )}
                <Link to="/" className="border border-black/10 px-6 py-3 rounded-md text-sm font-medium hover:bg-slate-50">Back to home</Link>
            </div>
        </div>
    );
}
