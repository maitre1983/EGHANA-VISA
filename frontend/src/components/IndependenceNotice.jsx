import React from "react";
import { ShieldCheck } from "lucide-react";

export const IndependenceNotice = ({ testid = "independence-notice", className = "" }) => (
    <div
        data-testid={testid}
        className={`flex items-start gap-2.5 bg-ghana-gold/15 border border-ghana-gold/60 text-ghana-black rounded-md px-4 py-3 text-left ${className}`}
    >
        <ShieldCheck size={18} className="shrink-0 mt-0.5 text-ghana-green" />
        <div className="text-sm">
            <div className="font-heading font-bold">We are independent — not the Government of Ghana</div>
            <div className="text-xs text-slate-600 mt-0.5">eGhanaVisa is a private visa assistance service. Your application is submitted to the competent Ghanaian authorities, who alone decide on and issue visas.</div>
        </div>
    </div>
);
