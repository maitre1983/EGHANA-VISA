import React from "react";

/** Ghana e.Visa logo — circle with flag colors and centered "e". */
export default function Logo({ size = 40, showText = true }) {
    return (
        <div className="flex items-center gap-3" data-testid="egv-logo">
            <svg width={size} height={size} viewBox="0 0 40 40" className="shrink-0" aria-label="e.GHANA Visa Logo">
                <defs>
                    <clipPath id="circleClip"><circle cx="20" cy="20" r="19" /></clipPath>
                </defs>
                <g clipPath="url(#circleClip)">
                    <rect x="0" y="0" width="40" height="13.33" fill="#CE1126" />
                    <rect x="0" y="13.33" width="40" height="13.33" fill="#FCD116" />
                    <rect x="0" y="26.66" width="40" height="13.34" fill="#006B3F" />
                </g>
                <circle cx="20" cy="20" r="19" fill="none" stroke="#0A0A0A" strokeWidth="1.5" />
                <circle cx="20" cy="20" r="11" fill="#FFFFFF" />
                <text x="20" y="26" textAnchor="middle" fontFamily="Outfit, sans-serif" fontWeight="800" fontSize="16" fill="#0A0A0A">e</text>
            </svg>
            {showText && (
                <div className="leading-tight">
                    <div className="font-heading font-bold tracking-wide text-ghana-black text-base">e.GHANA VISA</div>
                    <div className="text-[10px] uppercase tracking-[0.2em] text-ghana-green font-semibold">eVisa &amp; ETA Assistance</div>
                </div>
            )}
        </div>
    );
}
