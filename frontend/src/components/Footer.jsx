import React from "react";
import { Link } from "react-router-dom";
import Logo from "./Logo";

export default function Footer() {
    return (
        <footer className="bg-ghana-black text-white/80 mt-24">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-14 grid md:grid-cols-4 gap-10">
                <div>
                    <div className="[&_span]:text-white [&_.font-heading]:text-white">
                        <Logo />
                    </div>
                    <p className="text-sm text-white/60 mt-4">Official-style portal for Ghana Visa On Arrival applications. Secure, fast and transparent.</p>
                </div>
                <div>
                    <h4 className="text-white font-heading font-semibold mb-3 text-sm uppercase tracking-widest">Services</h4>
                    <ul className="space-y-2 text-sm">
                        <li><Link to="/apply" className="hover:text-ghana-gold" data-testid="footer-apply">Apply for Visa</Link></li>
                        <li><Link to="/track" className="hover:text-ghana-gold" data-testid="footer-track">Track Application</Link></li>
                        <li><Link to="/prices" className="hover:text-ghana-gold" data-testid="footer-prices">Prices</Link></li>
                    </ul>
                </div>
                <div>
                    <h4 className="text-white font-heading font-semibold mb-3 text-sm uppercase tracking-widest">Support</h4>
                    <ul className="space-y-2 text-sm">
                        <li><Link to="/faq" className="hover:text-ghana-gold" data-testid="footer-faq">FAQ</Link></li>
                        <li><Link to="/terms" className="hover:text-ghana-gold" data-testid="footer-terms">Terms & Conditions</Link></li>
                        <li><Link to="/privacy" className="hover:text-ghana-gold" data-testid="footer-privacy">Privacy Policy</Link></li>
                    </ul>
                </div>
                <div>
                    <h4 className="text-white font-heading font-semibold mb-3 text-sm uppercase tracking-widest">Ghana</h4>
                    <p className="text-sm text-white/60">Comptroller-General of Immigration<br/>Republic of Ghana</p>
                    <div className="mt-4 h-1 w-24 ghana-stripe-h rounded-sm"></div>
                </div>
            </div>
            <div className="border-t border-white/10 py-6 text-center text-xs text-white/50">
                © {new Date().getFullYear()} eghanavisa.com — All rights reserved
            </div>
        </footer>
    );
}
