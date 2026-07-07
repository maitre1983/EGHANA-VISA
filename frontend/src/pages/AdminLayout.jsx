import React from "react";
import { NavLink, Outlet, useNavigate, Navigate } from "react-router-dom";
import { LayoutDashboard, Settings as SettingsIcon, BarChart3, LogOut, Mail } from "lucide-react";
import Logo from "../components/Logo";

const NAV = [
    { to: "/admin/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/admin/settings", label: "Settings", icon: SettingsIcon },
    { to: "/admin/templates", label: "Emails", icon: Mail },
    { to: "/admin/analytics", label: "Analytics", icon: BarChart3 },
];

export default function AdminLayout() {
    const nav = useNavigate();
    const token = localStorage.getItem("egv_admin_token");
    if (!token) return <Navigate to="/admin" replace />;
    const mustChange = localStorage.getItem("egv_admin_must_change") === "true";
    if (mustChange) return <Navigate to="/admin/change-password" replace />;

    const logout = () => {
        localStorage.removeItem("egv_admin_token");
        localStorage.removeItem("egv_admin_email");
        localStorage.removeItem("egv_admin_must_change");
        nav("/admin");
    };

    return (
        <div className="min-h-screen flex bg-slate-100">
            <aside className="w-64 bg-ghana-black text-white/80 min-h-screen flex-col hidden md:flex">
                <div className="p-6 border-b border-white/10">
                    <div className="[&_.text-ghana-black]:text-white [&_.text-ghana-green]:text-ghana-gold"><Logo /></div>
                    <div className="mt-2 text-[10px] uppercase tracking-widest text-ghana-gold">Command Center</div>
                </div>
                <nav className="flex-1 p-4 space-y-1">
                    {NAV.map((n) => {
                        const Icon = n.icon;
                        return (
                            <NavLink
                                key={n.to}
                                to={n.to}
                                data-testid={`admin-nav-${n.label.toLowerCase()}`}
                                className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors ${isActive ? "bg-white/10 text-white" : "text-white/60 hover:bg-white/5 hover:text-white"}`}
                            >
                                <Icon size={16} /> {n.label}
                            </NavLink>
                        );
                    })}
                </nav>
                <div className="p-4 border-t border-white/10">
                    <div className="text-xs text-white/50 mb-3">{localStorage.getItem("egv_admin_email")}</div>
                    <button onClick={logout} data-testid="admin-logout" className="w-full inline-flex items-center gap-2 text-sm text-white/70 hover:text-white bg-white/5 hover:bg-white/10 px-3 py-2 rounded-md transition-colors">
                        <LogOut size={14} /> Sign out
                    </button>
                </div>
            </aside>
            <main className="flex-1 min-w-0">
                <Outlet />
            </main>
        </div>
    );
}
