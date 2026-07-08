/**
 * Tiny dev-only logger. In production builds these are no-ops so no debug
 * information leaks to the browser console.
 */
const isDev = process.env.NODE_ENV !== "production";

export const log = {
    warn: (...args) => { if (isDev && typeof console !== "undefined") console.warn(...args); },
    error: (...args) => { if (isDev && typeof console !== "undefined") console.error(...args); },
    info: (...args) => { if (isDev && typeof console !== "undefined") console.info(...args); },
};
