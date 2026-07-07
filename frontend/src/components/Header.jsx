import React from "react";
import { Link, NavLink } from "react-router-dom";
import Logo from "./Logo";

export default function Header() {
    return (
        <header className="sticky top-0 z-40 bg-white/90 backdrop-blur-lg border-b border-black/5">
            <div className="h-1 ghana-stripe-h" />
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                <Link to="/" data-testid="header-logo-link"><Logo /></Link>
                <nav className="hidden md:flex items-center gap-8">
                    {[
                        { to: "/", label: "Home" },
                        { to: "/apply", label: "Apply" },
                        { to: "/track", label: "Track" },
                        { to: "/prices", label: "Prices" },
                        { to: "/faq", label: "FAQ" },
                    ].map((item) => (
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
                <Link
                    to="/apply"
                    data-testid="header-cta-apply"
                    className="hidden sm:inline-flex items-center gap-2 bg-ghana-green text-white px-5 py-2.5 rounded-md text-sm font-medium hover:bg-ghana-green-dark transition-colors"
                >
                    Apply Now
                </Link>
            </div>
        </header>
    );
}
