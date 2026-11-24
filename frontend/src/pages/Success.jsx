import React, { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { CheckCircle2, Copy } from "lucide-react";
import { toast } from "sonner";
import { IndependenceNotice } from "../components/IndependenceNotice";

export default function Success() {
    const { tracking } = useParams();
    const copy = () => { navigator.clipboard.writeText(tracking); toast.success("Copied!"); };
    useEffect(() => { window.scrollTo(0, 0); }, []);

    return (
        <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
            <div className="bg-white rounded-2xl border border-black/10 p-10 text-center shadow-sm">
                <div className="mx-auto w-16 h-16 rounded-full bg-ghana-green/10 flex items-center justify-center">
                    <CheckCircle2 className="text-ghana-green" size={36} />
                </div>
                <h1 className="mt-6 text-3xl font-heading font-bold">Payment received</h1>
                <p className="mt-2 text-slate-600">Your application has been successfully submitted.</p>

                <div className="mt-8 border border-black/10 rounded-xl p-5 bg-slate-50">
                    <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Your tracking number</div>
                    <div className="mt-2 flex items-center justify-center gap-3">
                        <span className="font-heading text-3xl font-bold text-ghana-green tracking-wide" data-testid="success-tracking">{tracking}</span>
                        <button onClick={copy} data-testid="success-copy" className="p-2 rounded hover:bg-slate-200 transition-colors"><Copy size={16} /></button>
                    </div>
                    <p className="mt-3 text-xs text-slate-500">A confirmation email has been sent to your address. Save this number for future reference.</p>
                </div>

                <IndependenceNotice testid="success-independence-notice" className="mt-6" />

                <div className="mt-8 flex flex-col sm:flex-row justify-center gap-3">
                    <Link to={`/track?number=${tracking}`} data-testid="success-track" className="bg-ghana-black text-white px-6 py-3 rounded-md text-sm font-medium hover:bg-ghana-black/90 transition-colors">Track my application</Link>
                    <Link to="/" className="border border-black/10 px-6 py-3 rounded-md text-sm font-medium hover:bg-slate-50 transition-colors">Back to home</Link>
                </div>
            </div>
        </div>
    );
}
