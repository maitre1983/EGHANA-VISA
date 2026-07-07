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
                    <p className="text-sm text-white/60 mt-4">Third-party portal for Ghana Visa On Arrival applications. Secure, fast and transparent.</p>
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

            {/* Payment methods */}
            <div className="border-t border-white/10">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                    <div className="flex items-center justify-between gap-6 flex-wrap">
                        <div className="text-xs uppercase tracking-[0.25em] text-white/50 font-semibold">Accepted payment methods</div>
                        <div className="flex items-center gap-4 flex-wrap" data-testid="footer-payment-logos">
                            <PaymentLogo name="Visa" bg="#1A1F71" fg="#FFFFFF">VISA</PaymentLogo>
                            <PaymentLogo name="Mastercard">
                                <span className="relative flex items-center h-5">
                                    <span className="w-5 h-5 rounded-full bg-[#EB001B] block" />
                                    <span className="w-5 h-5 rounded-full bg-[#F79E1B] block -ml-2 mix-blend-multiply" />
                                </span>
                            </PaymentLogo>
                            <PaymentLogo name="Hubtel" bg="#1FCBB2" fg="#0A0A0A">HUBTEL</PaymentLogo>
                            <PaymentLogo name="USDT · TRC20" bg="#26A17B" fg="#FFFFFF">
                                <span className="flex items-center gap-1.5">
                                    <span className="w-4 h-4 rounded-full bg-white text-[#26A17B] flex items-center justify-center text-[10px] font-black">₮</span>
                                    <span className="text-[10px] font-bold tracking-widest">TRC20</span>
                                </span>
                            </PaymentLogo>
                            <PaymentLogo name="USDT · BEP20" bg="#F0B90B" fg="#0A0A0A">
                                <span className="flex items-center gap-1.5">
                                    <span className="w-4 h-4 rotate-45 bg-[#0A0A0A] flex items-center justify-center">
                                        <span className="rotate-[-45deg] text-[9px] font-black text-[#F0B90B]">B</span>
                                    </span>
                                    <span className="text-[10px] font-bold tracking-widest">BEP20</span>
                                </span>
                            </PaymentLogo>
                        </div>
                    </div>
                </div>
            </div>
            <div className="border-t border-white/10 py-6 text-center text-xs text-white/50">
                © {new Date().getFullYear()} eghanavisa.com — All rights reserved
            </div>
        </footer>
    );
}

const PaymentLogo = ({ name, bg = "#FFFFFF", fg = "#0A0A0A", children }) => (
    <div
        title={name}
        data-testid={`footer-logo-${name.toLowerCase().replace(/[^a-z0-9]/g, "-")}`}
        className="h-9 min-w-[64px] px-3 rounded-md flex items-center justify-center text-xs font-heading font-bold tracking-widest shadow-sm ring-1 ring-white/10"
        style={{ backgroundColor: bg, color: fg }}
    >
        {children}
    </div>
);
