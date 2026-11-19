import React, { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Menu, X } from "lucide-react";
import Logo from "./Logo";

const NAV_ITEMS = [
    { to: "/", label: "Home" },
    { to: "/apply", label: "Apply" },
    { to: "/track", label: "Track" },
    { to: "/prices", label: "Prices" },
    { to: "/faq", label: "FAQ" },
];

export default function Header() {
    const [open, setOpen] = useState(false);
    return (
        <header className="sticky top-0 z-40 bg-white/90 backdrop-blur-lg border-b border-black/5">
            <div className="h-1 ghana-stripe-h" />
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-3">
                <Link to="/" data-testid="header-logo-link" onClick={() => setOpen(false)}><Logo /></Link>
                <nav className="hidden md:flex items-center gap-8">
                    {NAV_ITEMS.map((item) => (
                        <NavLink
                            key={item.to}
                            to={item.to}
                            end={item.to === "/"}
                            data-testid={`nav-${item.label.toLowerCase()}`}
                            className={({ isActive }) =>
                                `text-sm font-medium transition-colors ${isActive ? "text-ghana-green" : "text-ghana-black/70 hover:text-ghana-black"}`
                            }
                        >
                            {item.label}
                        </NavLink>
                    ))}
                </nav>
                <div className="flex items-center gap-2">
                    <Link
                        to="/apply"
                        data-testid="header-cta-apply"
                        className="hidden sm:inline-flex items-center gap-2 bg-ghana-green text-white px-4 sm:px-5 py-2 sm:py-2.5 rounded-md text-sm font-medium hover:bg-ghana-green-dark transition-colors"
                    >
                        Apply Now
                    </Link>
                    <button
                        onClick={() => setOpen((o) => !o)}
                        data-testid="header-mobile-toggle"
                        aria-label={open ? "Close menu" : "Open menu"}
                        className="md:hidden p-2 rounded-md border border-black/10 hover:bg-slate-50"
                    >
                        {open ? <X size={18} /> : <Menu size={18} />}
                    </button>
                </div>
            </div>
            {/* Mobile dropdown menu */}
            {open && (
                <div className="md:hidden border-t border-black/5 bg-white" data-testid="header-mobile-menu">
                    <div className="px-4 py-3 flex flex-col gap-1">
                        {NAV_ITEMS.map((item) => (
                            <NavLink
                                key={item.to}
                                to={item.to}
                                end={item.to === "/"}
                                onClick={() => setOpen(false)}
                                data-testid={`nav-mobile-${item.label.toLowerCase()}`}
                                className={({ isActive }) =>
                                    `text-base font-medium px-3 py-2.5 rounded-md transition-colors ${isActive ? "bg-ghana-green/10 text-ghana-green" : "text-ghana-black/80 hover:bg-slate-50"}`
                                }
                            >
                                {item.label}
                            </NavLink>
                        ))}
                        <Link
                            to="/apply"
                            onClick={() => setOpen(false)}
                            className="mt-2 bg-ghana-green text-white text-center px-4 py-2.5 rounded-md text-sm font-medium"
                        >
                            Apply Now
                        </Link>
                    </div>
                </div>
            )}
        </header>
    );
}
