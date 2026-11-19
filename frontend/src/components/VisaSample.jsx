import React from "react";

/** Illustrative visa sample image — right column of Apply page. */
export default function VisaSample({ name, passport, arrival, departure, visaType }) {
    return (
        <div
            data-testid="visa-sample-card"
            aria-label="Illustrative visa sample image"
            className="relative w-full flex flex-col bg-white border-2 border-dashed border-ghana-black/20 rounded-xl overflow-hidden shadow-lg grain-overlay"
        >
            {/* Header */}
            <div className="min-h-12 py-2 bg-ghana-green flex items-center justify-between px-4 gap-2">
                <span className="text-white font-heading font-bold uppercase tracking-wider text-[10px] leading-tight" data-testid="visa-sample-header">eGhanaVisa · Visa Sample</span>
                <span className="shrink-0 text-ghana-black bg-ghana-gold font-heading font-bold uppercase tracking-widest text-[9px] sm:text-[10px] px-2 py-0.5 rounded">Illustrative Visa Sample</span>
            </div>

            <div className="p-4 pb-5 grid grid-cols-3 gap-4 flex-1">
                <div className="col-span-1 aspect-[3/4] bg-gray-200 rounded border border-gray-300 flex items-center justify-center overflow-hidden">
                    <div className="w-full h-full bg-gradient-to-br from-gray-300 to-gray-400 visa-blur" />
                </div>
                <div className="col-span-2 space-y-2">
                    {[
                        { label: "Full name", value: name || "AAAAAAAAAAAA AAAA" },
                        { label: "Passport No.", value: passport || "AA0000000" },
                        { label: "Visa type", value: visaType || "30 DAYS TOURIST" },
                        { label: "Arrival", value: arrival || "0000-00-00" },
                        { label: "Departure", value: departure || "0000-00-00" },
                    ].map((row) => (
                        <div key={row.label} className="flex flex-col">
                            <span className="text-[9px] text-gray-500 uppercase font-semibold tracking-widest">{row.label}</span>
                            <span className="text-sm font-heading font-semibold visa-blur">{row.value}</span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Watermark */}
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center" data-testid="visa-sample-watermark">
                <span className="-rotate-[18deg] whitespace-nowrap font-heading font-extrabold uppercase tracking-[0.15em] text-base sm:text-xl text-ghana-red/25 border-4 border-ghana-red/25 rounded-lg px-4 py-1">
                    Sample / Illustration
                </span>
            </div>

            {/* Footer disclaimer */}
            <div className="bg-ghana-black text-white/90 text-[9px] sm:text-[10px] leading-snug flex items-center justify-center text-center px-3 py-2" data-testid="visa-sample-disclaimer">
                This image is provided for illustration purposes only. eGhanaVisa is an independent third-party visa assistance service. Visa applications are submitted to the competent Ghanaian authorities, which are solely responsible for reviewing applications and issuing official visas or entry authorizations.
            </div>
        </div>
    );
}
