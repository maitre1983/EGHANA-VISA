import React from "react";
import { Outlet } from "react-router-dom";
import Header from "./Header";
import Footer from "./Footer";
import AbenaChat from "./AbenaChat";
import CookieConsent from "./CookieConsent";
import useAnalyticsRouter from "../hooks/useAnalyticsRouter";

export default function PublicLayout() {
    useAnalyticsRouter();
    return (
        <>
            <Header />
            <main className="min-h-[70vh]">
                <Outlet />
            </main>
            <Footer />
            <AbenaChat />
            <CookieConsent />
        </>
    );
}
