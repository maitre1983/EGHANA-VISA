import React from "react";
import "./App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";

import PublicLayout from "./components/PublicLayout";
import Home from "./pages/Home";
import Apply from "./pages/Apply";
import Payment from "./pages/Payment";
import Success from "./pages/Success";
import Track from "./pages/Track";
import Prices from "./pages/Prices";
import FAQ from "./pages/FAQ";
import Terms from "./pages/Terms";
import Privacy from "./pages/Privacy";

import AdminLogin from "./pages/AdminLogin";
import AdminChangePassword from "./pages/AdminChangePassword";
import AdminLayout from "./pages/AdminLayout";
import AdminDashboard from "./pages/AdminDashboard";
import AdminSettings from "./pages/AdminSettings";
import AdminTemplates from "./pages/AdminTemplates";
import AdminAnalytics from "./pages/AdminAnalytics";

function App() {
    return (
        <div className="App">
            <BrowserRouter>
                <Toaster position="top-right" richColors />
                <Routes>
                    <Route element={<PublicLayout />}>
                        <Route path="/" element={<Home />} />
                        <Route path="/apply" element={<Apply />} />
                        <Route path="/payment/:tracking" element={<Payment />} />
                        <Route path="/success/:tracking" element={<Success />} />
                        <Route path="/track" element={<Track />} />
                        <Route path="/prices" element={<Prices />} />
                        <Route path="/faq" element={<FAQ />} />
                        <Route path="/terms" element={<Terms />} />
                        <Route path="/privacy" element={<Privacy />} />
                    </Route>

                    <Route path="/admin" element={<AdminLogin />} />
                    <Route path="/admin/change-password" element={<AdminChangePassword />} />
                    <Route element={<AdminLayout />}>
                        <Route path="/admin/dashboard" element={<AdminDashboard />} />
                        <Route path="/admin/settings" element={<AdminSettings />} />
                        <Route path="/admin/templates" element={<AdminTemplates />} />
                        <Route path="/admin/analytics" element={<AdminAnalytics />} />
                    </Route>
                </Routes>
            </BrowserRouter>
        </div>
    );
}

export default App;
