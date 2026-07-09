// Cookie consent state & event bus (GDPR-friendly, first-party only).
// Categories: essential (always true), analytics, marketing, functional.

const KEY = "egv_cookie_consent_v1";
const EVENT = "egv:consent-changed";

const DEFAULT = { essential: true, analytics: false, marketing: false, functional: false };

export const readConsent = () => {
    try {
        const raw = localStorage.getItem(KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return { ...DEFAULT, ...parsed, essential: true };
    } catch {
        return null;
    }
};

export const hasChosen = () => readConsent() !== null;

export const writeConsent = (next) => {
    const merged = {
        ...DEFAULT,
        ...(readConsent() || {}),
        ...next,
        essential: true,
        ts: new Date().toISOString(),
    };
    localStorage.setItem(KEY, JSON.stringify(merged));
    window.dispatchEvent(new CustomEvent(EVENT, { detail: merged }));
    return merged;
};

export const acceptAll = () => writeConsent({ analytics: true, marketing: true, functional: true });
export const rejectNonEssential = () => writeConsent({ analytics: false, marketing: false, functional: false });

export const onConsentChange = (cb) => {
    const handler = (e) => cb(e.detail || readConsent());
    window.addEventListener(EVENT, handler);
    return () => window.removeEventListener(EVENT, handler);
};

export const openPreferences = () => {
    window.dispatchEvent(new CustomEvent("egv:consent-open"));
};

// Helper — has the user consented to a specific category?
export const isAllowed = (category) => {
    const c = readConsent();
    if (!c) return false;
    return Boolean(c[category]);
};
