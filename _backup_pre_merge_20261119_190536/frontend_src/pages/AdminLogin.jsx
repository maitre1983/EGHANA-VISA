import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Lock, Loader2 } from "lucide-react";
import api from "../lib/api";
import Logo from "../components/Logo";
import { toast } from "sonner";

export default function AdminLogin() {
    const nav = useNavigate();
    const [email, setEmail] = useState("");
    const [pw, setPw] = useState("");
    const [loading, setLoading] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            const { data } = await api.post("/admin/login", { email, password: pw });
            localStorage.setItem("egv_admin_token", data.token);
            localStorage.setItem("egv_admin_email", data.email);
            localStorage.setItem("egv_admin_must_change", String(data.must_change_password));
            nav(data.must_change_password ? "/admin/change-password" : "/admin/dashboard");
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Login failed");
        } finally { setLoading(false); }
    };

    return (
        <div className="min-h-screen grid md:grid-cols-2">
            <div className="relative hidden md:flex flex-col justify-between p-12 text-white bg-ghana-black">
                <div className="[&_span]:text-white [&_.font-heading]:text-white"><Logo /></div>
                <div>
                    <div className="h-1 w-24 ghana-stripe-h mb-6" />
                    <h2 className="font-heading text-4xl font-bold">Command Center</h2>
                    <p className="mt-4 text-white/70 max-w-md">Secure operations dashboard for the eghanavisa.com visa portal. Access is restricted to authorised staff only.</p>
                </div>
                <div className="text-xs text-white/40 uppercase tracking-widest">Protected by JWT + bcrypt</div>
            </div>
            <div className="flex items-center justify-center p-8 bg-slate-50">
                <form onSubmit={submit} className="w-full max-w-sm bg-white rounded-2xl border border-black/10 p-8 shadow-sm">
                    <div className="w-12 h-12 rounded-xl bg-ghana-green/10 flex items-center justify-center"><Lock className="text-ghana-green" /></div>
                    <h1 className="mt-6 font-heading text-2xl font-bold">Admin sign in</h1>
                    <p className="text-sm text-slate-500">e.GHANA Visa · Command Center</p>
                    <div className="mt-6 space-y-4">
                        <div>
                            <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Email</label>
                            <input data-testid="admin-email" value={email} onChange={(e) => setEmail(e.target.value)} type="email" required className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                        </div>
                        <div>
                            <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">Password</label>
                            <input data-testid="admin-password" value={pw} onChange={(e) => setPw(e.target.value)} type="password" required className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                        </div>
                    </div>
                    <button type="submit" disabled={loading} data-testid="admin-login-btn"
                        className="mt-6 w-full bg-ghana-black text-white py-3 rounded-md font-heading font-semibold hover:bg-ghana-black/90 transition-colors inline-flex items-center justify-center gap-2">
                        {loading && <Loader2 className="animate-spin" size={14} />} Sign in
                    </button>
                </form>
            </div>
        </div>
    );
}
