import React from "react";
import { Outlet } from "react-router-dom";
import Header from "./Header";
import Footer from "./Footer";
import AbenaChat from "./AbenaChat";

export default function PublicLayout() {
    return (
        <>
            <Header />
            <main className="min-h-[70vh]">
                <Outlet />
            </main>
            <Footer />
            <AbenaChat />
        </>
    );
}
