// First-party analytics client + optional GA4/Clarity loader.
// Fires POST /api/analytics/track for pageviews/events only when the visitor
// has consented to the "analytics" cookie category.
import axios from "axios";
import { readConsent, isAllowed, onConsentChange } from "./consent";

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : "/api";
const VISITOR_KEY = "egv_visitor_id";
const SESSION_KEY = "egv_session_id";
const SESSION_TTL_MS = 30 * 60 * 1000; // 30 min sliding window

const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);

const getVisitorId = () => {
    let v = localStorage.getItem(VISITOR_KEY);
    if (!v) { v = uid(); localStorage.setItem(VISITOR_KEY, v); }
    return v;
};

const getSessionId = () => {
    try {
        const raw = sessionStorage.getItem(SESSION_KEY);
        if (raw) {
            const p = JSON.parse(raw);
            if (Date.now() - p.last < SESSION_TTL_MS) {
                p.last = Date.now();
                sessionStorage.setItem(SESSION_KEY, JSON.stringify(p));
                return p.id;
            }
        }
    } catch { /* ignore */ }
    const id = uid();
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ id, last: Date.now() }));
    return id;
};

const collectMeta = () => ({
    path: window.location.pathname + window.location.search,
    referrer: document.referrer || "",
    screen: `${window.screen.width}x${window.screen.height}`,
    lang: navigator.language || "",
    ts: new Date().toISOString(),
    utm: {
        source: new URLSearchParams(window.location.search).get("utm_source") || "",
        medium: new URLSearchParams(window.location.search).get("utm_medium") || "",
        campaign: new URLSearchParams(window.location.search).get("utm_campaign") || "",
    },
});

const post = async (payload) => {
    if (!isAllowed("analytics")) return;
    try {
        await axios.post(`${API}/analytics/track`, {
            visitor_id: getVisitorId(),
            session_id: getSessionId(),
            ...payload,
        }, { headers: { "Content-Type": "application/json" } });
    } catch { /* fire-and-forget */ }
};

export const trackPageView = () => post({ event: "pageview", ...collectMeta() });
export const trackEvent = (name, extra = {}) => post({ event: name, extra, ...collectMeta() });

// -------- GA4 / Clarity loaders (consent-gated) --------
let ga4Loaded = false;
let clarityLoaded = false;

const loadGA4 = (measurementId) => {
    if (ga4Loaded || !measurementId) return;
    ga4Loaded = true;
    const s = document.createElement("script");
    s.async = true;
    s.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    function gtag() { window.dataLayer.push(arguments); }
    window.gtag = gtag;
    gtag("js", new Date());
    gtag("config", measurementId, { anonymize_ip: true });
};

const loadClarity = (projectId) => {
    if (clarityLoaded || !projectId) return;
    clarityLoaded = true;
    // Official Microsoft Clarity snippet
    (function (c, l, a, r, i, t, y) {
        c[a] = c[a] || function () { (c[a].q = c[a].q || []).push(arguments); };
        t = l.createElement(r); t.async = 1; t.src = "https://www.clarity.ms/tag/" + i;
        y = l.getElementsByTagName(r)[0]; y.parentNode.insertBefore(t, y);
    })(window, document, "clarity", "script", projectId);
};

const loadGSC = (verificationCode) => {
    if (!verificationCode) return;
    if (document.querySelector('meta[name="google-site-verification"]')) return;
    const m = document.createElement("meta");
    m.name = "google-site-verification";
    m.content = verificationCode;
    document.head.appendChild(m);
};

let cachedConfig = null;
const fetchPublicAnalyticsConfig = async () => {
    if (cachedConfig) return cachedConfig;
    try {
        const { data } = await axios.get(`${API}/analytics/public-config`);
        cachedConfig = data || {};
    } catch { cachedConfig = {}; }
    return cachedConfig;
};

// Applies external analytics scripts based on current consent.
// Called on mount and whenever consent changes.
const applyExternalScripts = async () => {
    const cfg = await fetchPublicAnalyticsConfig();
    // GSC verification is a passive meta tag — always safe to inject; not a cookie.
    loadGSC(cfg.gsc_verification);
    if (!isAllowed("analytics")) return;
    loadGA4(cfg.ga4_measurement_id);
    loadClarity(cfg.clarity_project_id);
};

export const initAnalytics = () => {
    // Emit an initial pageview if consent already granted
    if (isAllowed("analytics")) trackPageView();
    applyExternalScripts();
    // React to consent changes
    onConsentChange(() => { applyExternalScripts(); });
};

export const currentConsent = readConsent;
