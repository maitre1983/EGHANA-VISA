import React, { useEffect, useState } from "react";
import { X } from "lucide-react";
import api from "../lib/api";

// Conversational WhatsApp widget. Closed = floating avatar button.
// Open = mini chat preview with agent name, avatar, online status, teaser
// message, and a green "Start chat on WhatsApp" CTA. All fields come from
// /api/config so admins can update them without code changes.
export default function WhatsAppButton() {
    const [cfg, setCfg] = useState(null);
    const [open, setOpen] = useState(false);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const { data } = await api.get("/config");
                if (cancelled) return;
                setCfg({
                    number: data.whatsapp_public_number || "",
                    message: data.whatsapp_public_message || "",
                    agentName: data.whatsapp_agent_name || "Ghana Visa Support",
                    avatarUrl: data.whatsapp_agent_avatar_url || "",
                    statusText: data.whatsapp_agent_status_text || "Online",
                    teaser: data.whatsapp_teaser_message || "Hi! How can we help you today?",
                });
            } catch (_e) {
                // Silent — non-critical enhancement.
            }
        })();
        return () => { cancelled = true; };
    }, []);

    if (!cfg || !cfg.number) return null;

    const cleanNumber = cfg.number.replace(/[^0-9]/g, "");
    const href = `https://wa.me/${cleanNumber}${cfg.message ? `?text=${encodeURIComponent(cfg.message)}` : ""}`;

    // Fallback avatar: white circle with a green person silhouette
    const initials = (cfg.agentName || "GV")
        .split(/\s+/).slice(0, 2).map((s) => s[0] || "").join("").toUpperCase() || "GV";

    return (
        <div
            className="fixed z-[60] bottom-4 right-4 md:bottom-6 md:right-6"
            data-testid="whatsapp-widget-root"
        >
            {open && (
                <div
                    className="mb-3 w-[300px] md:w-[340px] rounded-2xl shadow-2xl overflow-hidden bg-white border border-black/5 animate-in fade-in slide-in-from-bottom-2 duration-200"
                    data-testid="whatsapp-widget-panel"
                    role="dialog"
                    aria-label="WhatsApp support widget"
                >
                    {/* Header — WhatsApp green */}
                    <div className="bg-[#075E54] text-white px-4 py-3 flex items-center gap-3">
                        <div className="relative">
                            {cfg.avatarUrl ? (
                                <img
                                    src={cfg.avatarUrl}
                                    alt={cfg.agentName}
                                    className="w-11 h-11 rounded-full object-cover border-2 border-white/30"
                                />
                            ) : (
                                <div className="w-11 h-11 rounded-full bg-white text-[#075E54] font-bold flex items-center justify-center text-sm border-2 border-white/30">
                                    {initials}
                                </div>
                            )}
                            <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-[#4ade80] border-2 border-[#075E54]" />
                        </div>
                        <div className="flex-1 min-w-0">
                            <div className="text-sm font-semibold truncate">{cfg.agentName}</div>
                            <div className="text-[11px] text-white/85 flex items-center gap-1">
                                <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#4ade80]" />
                                <span className="truncate">{cfg.statusText}</span>
                            </div>
                        </div>
                        <button
                            onClick={() => setOpen(false)}
                            className="text-white/80 hover:text-white transition-colors"
                            aria-label="Close WhatsApp widget"
                            data-testid="whatsapp-widget-close"
                        >
                            <X size={18} />
                        </button>
                    </div>

                    {/* Chat body — WhatsApp cream */}
                    <div className="bg-[#ECE5DD] px-4 py-5 min-h-[110px]">
                        <div className="relative bg-white rounded-lg px-3.5 py-2.5 text-[13.5px] text-slate-800 leading-relaxed shadow-sm max-w-[92%]">
                            <span
                                className="absolute -top-1.5 -left-1 w-3 h-3 bg-white"
                                style={{ clipPath: "polygon(0 0, 100% 0, 100% 100%)" }}
                                aria-hidden="true"
                            />
                            {cfg.teaser}
                            <div className="text-[10px] text-slate-400 mt-1 text-right">now</div>
                        </div>
                    </div>

                    {/* Footer — CTA */}
                    <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={() => setOpen(false)}
                        data-testid="whatsapp-widget-cta"
                        className="flex items-center justify-center gap-2 bg-[#25D366] hover:bg-[#20b858] text-white text-sm font-semibold py-3 transition-colors"
                    >
                        <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5" aria-hidden="true">
                            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.198.296-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
                        </svg>
                        Start chat on WhatsApp
                    </a>
                </div>
            )}

            {/* Floating trigger */}
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-label={open ? "Close WhatsApp widget" : "Open WhatsApp widget"}
                data-testid="whatsapp-floating-button"
                className="relative group"
            >
                {!open && (
                    <span
                        className="absolute inset-0 rounded-full bg-[#25D366] opacity-60 animate-ping"
                        aria-hidden="true"
                    />
                )}
                <span className="relative flex items-center justify-center w-14 h-14 md:w-16 md:h-16 rounded-full bg-[#25D366] text-white shadow-xl hover:scale-105 active:scale-95 transition-transform">
                    {open ? (
                        <X className="w-7 h-7" />
                    ) : (
                        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className="w-7 h-7 md:w-8 md:h-8">
                            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.198.296-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
                        </svg>
                    )}
                </span>
                {/* Unread badge to entice clicks (only when closed) */}
                {!open && (
                    <span
                        className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-ghana-red text-white text-[11px] font-bold flex items-center justify-center border-2 border-white"
                        aria-hidden="true"
                    >1</span>
                )}
            </button>
        </div>
    );
}
