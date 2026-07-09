import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { trackPageView, initAnalytics } from "../lib/analytics";

let bootstrapped = false;

export default function useAnalyticsRouter() {
    const location = useLocation();
    useEffect(() => {
        if (!bootstrapped) {
            bootstrapped = true;
            initAnalytics();
            return; // initAnalytics already fired the first pageview
        }
        trackPageView();
    }, [location.pathname, location.search]);
}
