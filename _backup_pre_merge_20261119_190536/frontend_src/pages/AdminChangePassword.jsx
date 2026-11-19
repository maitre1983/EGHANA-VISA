import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { toast } from "sonner";

export default function AdminChangePassword() {
    const nav = useNavigate();
    const [form, setForm] = useState({ current_password: "", new_password: "", confirm: "", new_email: "" });
    const [loading, setLoading] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        if (form.new_password.length < 8) return toast.error("Password must be at least 8 characters");
        if (form.new_password !== form.confirm) return toast.error("Passwords do not match");
        setLoading(true);
        try {
            await api.post("/admin/credentials", {
                current_password: form.current_password,
                new_password: form.new_password,
                new_email: form.new_email || undefined,
            });
            toast.success("Credentials updated");
            localStorage.setItem("egv_admin_must_change", "false");
            if (form.new_email) localStorage.setItem("egv_admin_email", form.new_email);
            nav("/admin/dashboard");
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Update failed");
        } finally { setLoading(false); }
    };

    return (
        <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
            <form onSubmit={submit} className="w-full max-w-md bg-white rounded-2xl border border-black/10 p-8 shadow-sm">
                <div className="text-xs uppercase tracking-widest text-ghana-red font-semibold">Required</div>
                <h1 className="mt-2 font-heading text-2xl font-bold">Change your default password</h1>
                <p className="mt-2 text-sm text-slate-500">For your security you must set a new password before continuing.</p>

                <div className="mt-6 space-y-4">
                    <FieldPw label="Current password" value={form.current_password} onChange={(v) => setForm((f) => ({ ...f, current_password: v }))} testid="cp-current" />
                    <FieldPw label="New password" value={form.new_password} onChange={(v) => setForm((f) => ({ ...f, new_password: v }))} testid="cp-new" />
                    <FieldPw label="Confirm new password" value={form.confirm} onChange={(v) => setForm((f) => ({ ...f, confirm: v }))} testid="cp-confirm" />
                    <div>
                        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">New email (optional)</label>
                        <input type="email" value={form.new_email} onChange={(e) => setForm((f) => ({ ...f, new_email: e.target.value }))} data-testid="cp-email"
                            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
                    </div>
                </div>

                <button type="submit" disabled={loading} data-testid="cp-submit" className="mt-6 w-full bg-ghana-black text-white py-3 rounded-md font-heading font-semibold hover:bg-ghana-black/90 transition-colors">
                    {loading ? "Saving…" : "Save & continue"}
                </button>
            </form>
        </div>
    );
}

const FieldPw = ({ label, value, onChange, testid }) => (
    <div>
        <label className="text-xs uppercase tracking-wider text-slate-600 font-medium">{label}</label>
        <input type="password" value={value} onChange={(e) => onChange(e.target.value)} required data-testid={testid}
            className="mt-1.5 w-full border border-black/10 rounded-md px-3 py-2.5 text-sm focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none" />
    </div>
);
