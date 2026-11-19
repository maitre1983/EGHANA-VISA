import React from "react";

/** Blurred Ghana Visa sample preview panel — right column of Apply page. */
export default function VisaSample({ name, passport, arrival, departure, visaType }) {
    return (
        <div
            data-testid="visa-sample-card"
            className="relative w-full aspect-[3/2] bg-white border-2 border-ghana-black/10 rounded-xl overflow-hidden shadow-lg grain-overlay"
        >
            {/* Header */}
            <div className="h-12 bg-ghana-green flex items-center justify-between px-4">
                <span className="text-white font-heading font-bold uppercase tracking-widest text-xs">Republic of Ghana</span>
                <span className="text-ghana-gold font-heading font-bold uppercase tracking-widest text-xs">Visa on Arrival</span>
            </div>

            <div className="p-4 grid grid-cols-3 gap-4">
                {/* Photo placeholder */}
                <div className="col-span-1 aspect-[3/4] bg-gray-200 rounded border border-gray-300 flex items-center justify-center overflow-hidden">
                    <div className="w-full h-full bg-gradient-to-br from-gray-300 to-gray-400 visa-blur" />
                </div>

                {/* Data */}
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

            {/* QR mock */}
            <div className="absolute bottom-3 right-3 w-14 h-14 rounded border border-gray-300 visa-blur"
                 style={{ background: "conic-gradient(from 0deg,#CE1126,#FCD116,#006B3F,#CE1126)" }} />

            {/* Footer */}
            <div className="absolute bottom-0 left-0 right-0 h-8 bg-ghana-black text-white text-[9px] uppercase tracking-widest flex items-center justify-between px-4">
                <span>Comptroller-General of Immigration</span>
                <span className="text-ghana-red">Employment Prohibited</span>
            </div>
        </div>
    );
}
