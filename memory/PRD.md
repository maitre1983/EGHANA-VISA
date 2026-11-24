# e.GHANA Visa Portal — PRD

## Original problem statement
Build a full-stack Ghana Visa On Arrival web application for **eghanavisa.com** with:
- Application form (visa type / passport / travel / personal / 4 file uploads)
- Two processing types (Regular 5–7d — Express 48–72h with configurable surcharge)
- Hubtel Visa card payment (Visa only at launch, USDT crypto prepared but disabled)
- Application tracking (`Submitted → In Progress → Done`), each transition sends email
- Admin dashboard "command center" with KPIs, filtered table, actions, settings and analytics
- Floating AI chat assistant "Abena"
- Legal (Terms + Privacy), FAQ (8 Qs), departure-date compliance warning
- Blurred Ghana Visa sample preview card
- Full SEO (title, meta, OG, Schema.org, sitemap, robots)

## Architecture
- **Backend**: FastAPI + Motor (Mongo) + JWT + bcrypt
- **Frontend**: React 19 + React-Router 7 + Tailwind + shadcn/ui + sonner
- **Storage**: Emergent Object Storage (behind abstract `StorageService`, future-ready for R2/S3)
- **Email**: Resend (real when `RESEND_API_KEY` set — simulation-log fallback otherwise, previewable in admin)
- **Payments**: Hubtel Online Checkout with **SANDBOX** simulation mode until keys are added in `/admin/settings`. Optional outbound static-IP proxy (Fixie-style) supported via `outbound_proxy_url`.
- **AI chat**: Claude Sonnet 4.5 via `emergentintegrations` + Emergent Universal Key; **model is configurable in `/admin/settings`**. Assistant name: **Abena**.
- **Colors**: Ghana flag (#CE1126 red / #FCD116 gold / #006B3F green / #0A0A0A black)
- **Fonts**: Inter (body) + Outfit (headings / numbers)

## What's implemented (v1 — 2026-02-07)
- ✅ Public site: Home, Apply (with live summary + visa sample), Payment (sandbox modal + prepared USDT slots), Success, Track, Prices, FAQ, Terms, Privacy
- ✅ Ama floating chat (Claude Sonnet 4.5), WhatsApp fallback
- ✅ Ghana Visa sample preview panel (blurred data + blurred QR)
- ✅ Departure date compliance warning + mandatory checkboxes
- ✅ Admin: JWT login → forced password change → dashboard → applications table with filters → detail modal with document download → status transitions (auto emails) → settings (5 sections + upload limit) → email templates editor (bilingual EN/FR) + email log → analytics
- ✅ ECOWAS exclusion (16 countries) on passport country; full world list on travel-from
- ✅ Bilingual email templates seeded (submitted / in_progress / done) — editable
- ✅ Hubtel integration with SANDBOX and optional outbound proxy
- ✅ File uploads validated server-side (JPEG/PNG/PDF, configurable max MB)
- ✅ SEO: title/meta/OG/Twitter/Schema.org GovernmentService + FAQPage, sitemap.xml, robots.txt
- ✅ Backend tested 100% (38/38 pytest cases pass serially)
- ✅ Frontend end-to-end validated (Home → Apply → Sandbox pay → Track → Admin transitions → Abena chat)

## Iteration 12 (2026-02-08) — Admin notifications + Abena rebrand
- ✅ Internal ops email fired to `admin_notification_email` on: (a) new submission — template `admin_new_submission`; (b) payment success (Hubtel + USDT crypto) — template `admin_payment_success`.
- ✅ New admin setting `admin_notification_email` (defaults from `ADMIN_NOTIFICATION_EMAIL` env var, empty otherwise), editable in `/admin/settings → WhatsApp & AI` tab (leave empty to disable).
- ✅ New endpoint `POST /api/admin/settings/admin-notification-email`.
- ✅ AI assistant renamed globally from **Ama** → **Abena** (frontend component `AbenaChat.jsx`, backend system prompt, all UI copy, admin settings labels).
- ✅ Email templates re-seeded (`EMAIL_TEMPLATES_VERSION = 3`) — adds the two new admin templates without touching existing user-facing ones.
- ✅ Verified end-to-end via curl: submission + payment produced both admin emails (Resend `simulated=false`), and Abena introduces herself correctly.

## Iteration 13 (2026-02-08) — Hubtel production URLs
- ✅ New backend endpoint `POST /api/webhooks/hubtel` — real Hubtel Online Checkout server-to-server callback. Verifies `Data.ClientReference` + optional `CheckoutId` match a payment we initiated, then idempotently marks the application paid (via shared `_mark_application_paid` helper). All callbacks archived to `hubtel_callbacks` collection.
- ✅ New public endpoint `GET /api/payments/status/{tracking_no}` — light payment-state check used by the return page while polling.
- ✅ New frontend routes:
    - `/payment/return` — customer-facing "verifying payment…" page that polls status until the webhook marks it paid, then forwards to `/success/:tracking`.
    - `/payment/cancelled` — cancellation landing page with retry CTA.
- ✅ Security fix: `POST /api/payments/confirm` (formerly publicly callable, could mark ANY application as paid) is now hard-gated to sandbox mode (`is_sandbox(hubtel) == true`); production traffic returns 403.
- ✅ Admin settings > Hubtel tab now shows the three production URLs as copy-only fields (Callback / Return / Cancellation) with an "Auto-fill URLs" helper — same UX as the NowPayments IPN URL.
- ✅ Settings migration adds `cancellation_url` field to existing Hubtel config without touching user overrides.

### Official production URLs (production domain `https://eghanavisa.com`)
- Callback URL (server-to-server, updates payment status): `https://eghanavisa.com/api/webhooks/hubtel`
- Return URL (customer redirect after payment, display-only): `https://eghanavisa.com/payment/return`
- Cancellation URL (customer clicks cancel): `https://eghanavisa.com/payment/cancelled`

## Iteration 14 (2026-02-08) — Cookie Consent, Analytics & SEO Dashboard, Test-Data Cleanup

### 1. Cookie Consent (GDPR)
- ✅ Bottom banner + Customize modal on first visit — Accept All / Reject Non-Essential / Save preferences.
- ✅ 4 categories: **Essential** (locked ON), **Analytics**, **Marketing**, **Functional** — all OFF by default until user opts in.
- ✅ Choice persisted to `localStorage["egv_cookie_consent_v1"]`; footer "Cookie preferences" link reopens modal.
- ✅ Emits `egv:consent-changed` event so analytics + external scripts can react in real time.

### 2. Native Analytics + External integrations
- ✅ First-party analytics stored in MongoDB collection `analytics_events`.
- ✅ Public `POST /api/analytics/track` — parses UA (device/OS/browser), classifies source (Organic/Social/Referral/Direct/Paid), captures country from CDN headers, UTM params, referrer.
- ✅ Client tracker (`/app/frontend/src/lib/analytics.js`) only fires when Analytics cookies are accepted.
- ✅ Route-change page-view emitter via `useAnalyticsRouter` in PublicLayout.
- ✅ Explicit funnel events wired: `apply_click` on Home visa cards, `payment_click` on Hubtel + USDT buttons.
- ✅ Admin endpoints:
    - `GET /api/admin/analytics/summary?preset=…` — KPIs, sources, devices, countries, funnel.
    - `GET /api/admin/analytics/timeseries?preset=…` — daily buckets (visitors/PVs/apps/revenue).
    - `GET /api/analytics/public-config` — returns GA4 + Clarity + GSC IDs to load in the frontend.
- ✅ New Admin Settings section **Analytics IDs** — configure GA4 Measurement ID, GSC verification, Microsoft Clarity Project ID. Scripts injected only after Analytics consent (GDPR-compliant).
- ✅ Overhauled `/admin/analytics` page (React + Recharts): KPI cards, line/bar/pie charts, conversion funnel, date presets (Today / Yesterday / 7d / 30d / 90d / This year / All time) + custom range, tabs (Overview / Traffic / Visitors / SEO).

### 3. SEO Status Dashboard
- ✅ `GET /api/admin/seo/status` — pings sitemap.xml + robots.txt, returns HTTP codes, lists core routes meta status. Prefers `X-Forwarded-Host` so preview points to public URL.
- ✅ Dashboard shows technical health (sitemap ✅, robots ✅, GSC connect, GA4 connect), core pages meta table (title / description / canonical / structured data), indexed-pages estimate + placeholder for GSC search performance.

## Iteration 15 (2026-02-08) — Cloudflare R2 file storage

### Architecture
- All **new** file uploads route to a private Cloudflare R2 bucket (S3-compatible protocol via boto3).
- MongoDB stores only the R2 path + metadata (backend, size, mime, uploaded_at). No blobs in Mongo.
- The **Emergent Object Storage** backend is kept as a legacy fallback so files uploaded before this iteration (3 real Emile applications) still download without any migration.
- Backend auto-selects: R2 when configured + enabled, otherwise Emergent.

### Backend
- `storage_service.py` rewritten with `StorageService` abstract + `R2StorageBackend` (boto3) + `EmergentStorageBackend` (legacy).
- Environment auto-detection (`STORAGE_ENV` > `EMERGENT_ENV` > `APP_URL` / `preview_endpoint` inspection > `development`) → drives the top-level folder prefix.
- Folder layout in the bucket:
    ```
    {env}/applicants/{tracking_no}/photos/{doc_type}-{uuid}.{ext}
    {env}/applicants/{tracking_no}/passports/{doc_type}-{uuid}.{ext}
    {env}/applicants/{tracking_no}/supporting-documents/{doc_type}-{uuid}.{ext}
    {env}/payments/{tracking_no}/{uuid}.{ext}
    {env}/invoices/{tracking_no}/{uuid}.{ext}
    {env}/exports/{yyyy-mm-dd}/{uuid}.{ext}
    ```
- Bucket stays **private**. Downloads use short-lived pre-signed URLs (default TTL 15 min, configurable 60s–24h).
- If a **CDN custom domain** (e.g. `https://cdn.eghanavisa.com`) is configured, signed URLs are generated against that host so downloads flow through Cloudflare's CDN edge.
- New endpoints:
    - `POST /api/admin/settings/r2` — save R2 credentials (secret is write-only; empty means "keep existing").
    - `POST /api/admin/storage/test` — HEAD + probe put/delete round-trip.
    - `GET /api/admin/storage/status` — active backend, env, bucket, TTL, CDN.
    - `DELETE /api/admin/applications/{tracking_no}` — deletes application + purges its R2 folder.
    - `GET /api/admin/applications/{tn}/documents/{type}/signed-url` — returns signed URL for R2 files, streaming fallback for legacy Emergent files.
- Deletion policy wired to Danger Zone:
    - Safe cleanup (`/admin/cleanup/test-data`) purges each matched tracking-no's R2 folder.
    - Nuclear wipe (`/admin/cleanup/wipe-all`) purges `{env}/applicants/`, `{env}/payments/`, `{env}/invoices/` under R2.
- `GET /admin/settings` masks the R2 secret (`****xyz`) so it's never leaked to the browser.

### Frontend
- New **Storage (R2)** tab in Admin Settings with:
    - Live status card (Active backend / Environment / Bucket / Signed URL TTL)
    - All 7 config fields (Account ID, Bucket, Access Key ID, Secret, CDN domain, Env prefix, TTL) with hint text
    - **Save R2 configuration** + **Test R2 connection** buttons
    - Inline test result with success/failure detail
    - Folder-layout reference block
- Secret field is `type=password`, placeholder shows current masked value; leaving empty preserves existing secret.

### Verified
- ✅ Save + reload + secret redaction working via curl.
- ✅ Test button surfaces boto3 endpoint validation errors cleanly.
- ✅ Env auto-detected as `preview` on the current environment.
- ✅ Backward compatibility: Emile's existing Emergent-stored PNG (377KB) downloads correctly via the auto-selecting streaming endpoint.
- ✅ Signed-URL endpoint returns clean fallback (`{url:null, streaming_endpoint:...}`) for legacy files.
- ⏳ End-to-end R2 upload + signed-URL download waiting on the user to paste real Cloudflare R2 credentials.

## Iteration 19 (2026-02-08) — Home banner removed + Abena Phase 1 (live context + escalation)
- ✅ Removed the top-of-Home legal disclaimer banner (still present in Footer where users expect it).
- ✅ **Abena live-data grounding**: `ama_chat.py` now injects a fresh JSON `LIVE PLATFORM DATA` block into the system prompt on every message. Contains current visa types + prices (from admin settings), processing tiers + surcharges, payment methods, USDT discount, required documents, tracking format, ECOWAS list, WhatsApp, refund/overstay policy. Whenever an admin updates a price in the dashboard, Abena's next reply uses the new value automatically — **zero hallucination on prices/processing times** verified (Abena quoted the real $350 USD tourist price).
- ✅ **Auto-escalation with ticketing**: Abena's system prompt now emits an `[ESCALATE]` token when the customer asks for a human, expresses frustration, or the question is a status/refund/complaint. `POST /api/chat` detects the token, strips it from the reply, creates a `support_tickets` document (customer name/email/tracking/question/AI-reply/status/timestamps), and fires the admin notification email.
- ✅ **New admin endpoints**: `GET /api/admin/support-tickets?status=open` (queue) + `POST /api/admin/support-tickets/{id}/reply` (compose reply, optionally close; emails the customer if their address was captured).
- ✅ **AbenaChat.jsx** upgraded: shows the "Transferred to human · Ticket XXXXX" badge on escalated messages; when escalation happens without a captured email, prompts the customer for name + email so ops can reach them. New header tagline: "AI Support · Live 24/7".

### Deliberately deferred to future iterations (per user's Enterprise-scope brief)
- **SMS provider integration** (Twilio/Africa's Talking/other) — needs API keys from user; will build once they choose a provider
- **Multilingual pass** — Abena already respects the user's language via prompt, but a formal supported-language config in admin needs a separate iteration
- **Learning system** (admin-approved answers become part of RAG) — requires vector store; deferred
- **AI analytics dashboard** — will piggyback on the existing `/admin/analytics` framework
- **Working-hours / after-hours rules, emergency keywords, temperature/model tuning UI** — needs a dedicated "Abena Settings" tab
- **Performance pass** (Core Web Vitals, code splitting, image opt, DB query opt) — deserves its own audit iteration
- **Retry/graceful-degradation on external provider failures** — partially in place (FX cascade + Hubtel 502/503), extend to email/SMS in next pass

## Iteration 18 (2026-02-08) — USD → GHS auto-conversion for Hubtel
- **Reported**: Hubtel was charging customers `X GHS` when the visa was priced at `$X USD` — because we sent the raw USD amount and Hubtel treated it as GHS. On a $425 visa, customers were charged 425 GHS (~$36).
- **Fix — new `fx_service.py`**:
    - 4 configurable providers: **open.er-api.com** (default, free, no key), **fawazahmed0** (CDN, free), **frankfurter.app** (ECB rates, free), **Manual** (admin-entered rate)
    - Automatic **cascade fallback** — tries the selected provider, then the two backups, and finally the manual rate if all network providers fail
    - **Cache** (default 15 min TTL, admin-configurable 60s–24h) so checkouts don't hammer the FX API
    - **Buffer %** — admin can add 0–10% safety margin for intraday FX drift between fetch and card settlement
- **Fix — `payments/initiate` flow**:
    - Only converts to GHS when Hubtel is in **production** mode (sandbox skips conversion)
    - **Persists FX + charge metadata BEFORE the Hubtel HTTP call** so an upstream failure still leaves a complete audit trail
    - Payment record now stores: `amount_usd` (original), `amount_charged` (GHS sent), `payment_currency`, and a full `fx` sub-doc with rate, applied-rate, buffer, provider, source URL, fetched_at, from_cache
    - Gateway failures now return proper HTTP 502 with `code: hubtel_gateway_error`; FX unavailable returns 503 with `code: fx_unavailable`
- **Admin UI**:
    - New Settings tab **"Exchange Rate"** with live rate card (raw + buffered + $100 preview + source URL + fetched timestamp), 4 form fields, and Save + Refresh buttons
    - New endpoints: `GET /api/admin/fx/providers`, `GET /api/admin/fx/live`, `POST /api/admin/settings/fx`
- **Verified**: $350 USD visa → 350 × 11.5606 = **4046.21 GHS** sent to Hubtel. Full FX metadata persisted on the application record.
- **Zero hardcoding** — provider list, rates, buffer, TTL all driven by admin DB.

## Iteration 17 (2026-02-08) — 150+ Nationality SEO Landing Pages (P0)
- ✅ New dataset `/app/frontend/src/data/nationalityData.js` with **196 countries**, each with: country name, URL slug (`us-citizens`, `french-citizens`, …), demonym ("U.S.", "French", …), ISO2 code, region, capital, common departure airport, ECOWAS exempt flag, computed 🇺🇸 flag emoji.
- ✅ New dynamic page `NationalityLanding.jsx` served at `/visa-for-{slug}` — one unique landing per country with:
    - Country-specific meta title, description, canonical URL and JSON-LD (TravelAction or Article schema for ECOWAS)
    - Distinct render for **ECOWAS-exempt states** (green "no visa required" banner, 90-day free-movement note) vs non-ECOWAS (full requirements + fees + step-by-step guide)
    - Fact cards (Processing time · Passport requirement · Photo · Departure airport)
    - "Related nationalities" chips linking same-region countries → strong internal linking for SEO
    - CTA that fires `apply_click` analytics event with `source=nationality-cta`
    - Independent-third-party compliance disclaimer
- ✅ New index page `NationalityIndex.jsx` served at `/visa-by-nationality` — searchable A-Z directory grouped by region (Africa, Asia, Caribbean, Central America, Europe, Europe/Asia, Middle East, North America, Oceania, South America, West Africa) with region filter buttons and search box.
- ✅ **Fixed React Router v6 pattern bug** discovered during smoke test — `/visa-for-:slug` didn't match `/visa-for-us-citizens` because v6 requires dynamic params to occupy a whole path segment. Solved by generating explicit `<Route>` for each of the 196 slugs from the dataset (`NATIONALITY_LIST.map`). Page now derives slug from `useLocation().pathname`.
- ✅ `sitemap.xml` regenerated — now contains 216 URLs (base + guide pages + 196 nationality pages + directory).
- ✅ Footer link "Visa by nationality" added for permanent access + SEO discoverability.
- ✅ Verified end-to-end: `/visa-for-us-citizens` shows 🇺🇸 flag + "Ghana Visa for U.S. Citizens" H1; `/visa-for-nigerian-citizens` shows green ECOWAS banner; `/visa-by-nationality` shows all 196 links grouped by region.
- ✅ `yarn build` passes (28.7s, 285KB gzip main bundle).

## Iteration 16 (2026-02-08) — Hubtel silent-sandbox-fallback bug fix
- **Reported**: on production eghanavisa.com the payment page showed *"Payment gateway in SANDBOX mode"* and opened *"Hubtel Sandbox Checkout"* even though the admin had switched Hubtel to production mode and pasted keys.
- **Root cause**: `hubtel_service.is_sandbox()` had a silent fallback — if `sandbox=false` **but any of `api_id/api_key/merchant_account_id` was empty**, it still returned `True`. So any single missing/mistyped field silently downgraded real payments to a mock checkout, with no visible admin warning.
- **Fix (strictly admin-controlled)**:
    - `is_sandbox()` now returns exactly `bool(config.sandbox)`. No implicit fallback.
    - New `HubtelNotConfiguredError` raised when production mode is selected without full credentials.
    - `POST /api/payments/initiate` catches it and returns **HTTP 503** with structured detail `{code:"hubtel_not_configured", message, missing_fields}` — never a sandbox mock URL.
    - `GET /api/config` now exposes `hubtel_ready` + `hubtel_missing_fields` so the frontend renders a red "not fully configured" banner instead of the yellow sandbox banner when the admin has left production incomplete.
    - **Admin Settings → Hubtel tab** shows a red warning card the moment `sandbox=OFF` but any required field is empty, listing exactly which fields are missing.
    - "Pay now" button is disabled in the not-configured state so customers cannot hit a 503.
- **Verified via curl (all three scenarios)**:
    - Sandbox ON → `hubtel_sandbox=True, hubtel_ready=False`, checkout returns sandbox URL (expected).
    - Production ON + keys empty → `hubtel_sandbox=False, hubtel_ready=False, missing=[api_id, api_key, merchant_account_id]`. `/payments/initiate` returns 503 `hubtel_not_configured`. NO sandbox fallback.
    - Production ON + all keys → `hubtel_sandbox=False, hubtel_ready=True, missing=[]`. Real Hubtel endpoint used.

## User personas
1. **Traveller** (any nationality except 16 ECOWAS) — fills form, uploads docs, pays by Visa, tracks status, receives visa by email.
2. **Admin / Operator** — logs in at /admin, reviews applications, downloads documents, transitions status, tunes prices/toggles/keys.

## Backlog / next-phase (P1)
- Hubtel live callback signature verification (verify transaction via Hubtel Status API before flipping to paid)
- Multi-admin support (currently single admin) with role-based access
- Auto-generate & email the actual e-Visa PDF once status = done
- USDT TRC20 / BEP20 wallet payment implementation (crypto slots are prepared, currently "Coming Soon")
- Bilingual UI (currently English UI + bilingual emails)
- Rate-limiting & captcha on public endpoints

## P2 (nice-to-have)
- Two-factor auth for admin
- Refund flow inside admin dashboard
- Application archive & export CSV
- Rich analytics (nationality mix, weekly trends)
- Cloudflare R2 storage backend (interface already prepared)


## Iteration 13 (2026-02-20) — WhatsApp button + fan-out admin notifications
- ✅ **Additional admin recipients**: New `additional_admin_emails` list in settings, seeded from the `INITIAL_ADDITIONAL_ADMIN_EMAILS` environment variable (comma-separated). `_notify_admin()` now fans out every admin notification (new_submission + payment_success) to the primary email AND every entry in this list.
- ✅ **Back-office link in admin emails**: New `admin_backoffice_url` setting (default `https://eghanavisa.com/admin/dashboard`). Every admin email now contains an "Open Back Office →" button with `?tracking={tracking_no}` appended so admins jump straight to the application.
- ✅ **Conversational WhatsApp widget** (`WhatsAppButton.jsx`, upgraded 2026-02-20): Fixed bottom-right. Closed state = green pulsing button + "1" unread badge. Open state = mini WhatsApp-styled chat panel with agent avatar (URL or initials fallback), name, "Online · Replies within X min" status with green dot, teaser message bubble, and green CTA "Start chat on WhatsApp" that opens `wa.me/…?text=…`.
- ✅ **Zero hardcoding** — 6 configurable fields (`whatsapp_public_number`, `whatsapp_public_message`, `whatsapp_agent_name`, `whatsapp_agent_avatar_url`, `whatsapp_agent_status_text`, `whatsapp_teaser_message`) all editable in `Admin → Settings → WhatsApp & AI` tab.
- New admin endpoints:
    - `POST /api/admin/settings/additional-admin-emails` `{ additional_admin_emails: [] }`
    - `POST /api/admin/settings/whatsapp-public` `{ whatsapp_public_number, whatsapp_public_message, whatsapp_agent_name, whatsapp_agent_avatar_url, whatsapp_agent_status_text, whatsapp_teaser_message }`
    - `POST /api/admin/settings/admin-backoffice-url` `{ admin_backoffice_url }`
- Public `/api/config` exposes all 6 WhatsApp widget fields.
- Email templates bumped to version 5 to inject the new "Open Back Office" call-to-action.
- Verified end-to-end: real submission `GH-2026-292849` triggered notification to both the primary admin and an additional recipient (configured via env var) with tracking-scoped link. Widget open/close + CTA validated via Playwright screenshot.

## Iteration 14 (2026-02-20) — Cloudflare 520 root-cause fix (HEAD ≠ GET)
- **Root cause**: FastAPI's `@router.get()` decorator only registers GET, so any HEAD probe (Cloudflare edge, uptime monitors, prefetchers) received `HTTP 405` with `Content-Length: 31` **and** a JSON body `{"detail":"Method Not Allowed"}`. RFC 9110 §9.3.2 forbids a HEAD response from having a message body, so Cloudflare labelled the origin response "unparseable" and returned the 520 banner overlaid on `/admin`.
- **Fix (RFC-compliant, additive)**: New `HEADAsGETMiddleware` (pure ASGI, ~25 lines). It intercepts any HEAD request, routes it internally as GET, and strips the response body before it is sent back to the client. Content-Length still reflects what GET would have returned so probes get accurate size info.
- **Verified**: All 7 sampled routes now return `200/401/404/405` with **0 body bytes** on HEAD while GET/POST are untouched. Admin login → dashboard loads cleanly with zero console errors. No new endpoint introduced returns empty/malformed responses.

## Backlog (P0/P1/P2 remaining)
- **P0**: Abena Tickets Admin UI + SMS Integration (Admin Dashboard view for escalated tickets, SMS notif for admins via Hubtel SMS).
- **P1**: Abena Learning System + AI Analytics Dashboard.
- **P2**: Performance — further wins (image optim, prefetch, service worker).
- **P3**: Payment Gateway Health Monitoring (Hubtel / NowPayments ping).

## Iteration 15 (2026-11-19) — Integration of 5 Lots from feature/eghanavisa-five-lots (GitHub)
- **Source**: `maitre1983/EGHANA-VISA` @ `a7f73ee4c2ac3c029c017a6f3b71794f214e378a`
- **Method**: Selective integration — repo was a strict superset, verified file-by-file. Backup saved to `/app/_backup_pre_merge_20261119_190536/`.
- **Lot 1 — Dashboard SUBMITTED AT**: `submitted_at` persisted on submission, `$ifNull(submitted_at, created_at)` fallback for legacy rows. `GET /api/admin/applications` now accepts `page, page_size (max 1000), search, from_date, to_date`.
- **Lot 2 — Unified financial history**: New `backend/transactions_service.py` (419 lines) aggregating `applications` (paid), `hubtel_callbacks`, `crypto_payments`. New endpoints `GET /api/admin/transactions`, `/transactions/{id}`, `/transactions.csv`. New frontend page `AdminPayments.jsx` at `/admin/payments` with search/filter/sort + revenue cards + reconciliation + Unmatched/Deduplicated tagging.
- **Lot 3 — Payment lifecycle emails**: 3 new templates `admin_payment_failed`, `admin_payment_expired`, `admin_payment_refunded` seeded (templates version 5→6). New helper `_notify_payment_event()` with idempotent `payment_notifications_log` collection (status ∈ {pending, sent, failed}, attempts, sent/failed counts). Replay blocked if status=sent, retry allowed if status=failed.
- **Lot 4 — Performance**: New `_ensure_indexes()` at startup (idempotent): `applications(tracking_no, email, payment_status+status+created_at, created_at, submitted_at sparse)`, `hubtel_callbacks(client_reference, checkout_id, created_at)`, `crypto_payments(payment_id, tracking_no, created_at)`, `payment_notifications_log(key UNIQUE)`, `email_log(created_at)`, `analytics_events(event_time, path)`, `admins(email UNIQUE)`. React code-splitting: `Admin*` + `Seo/Nationality` pages via `lazy()` + `<Suspense>`. Server-side pagination on `/admin/applications`.
- **Lot 5 — Excel export**: New endpoint `GET /api/admin/transactions.xlsx` using `openpyxl==3.1.5`. 2 sheets (Transactions 13 cols + Summary with totals by provider×currency). Formula-injection protection.
- **Preserved from local fork**: `HEADAsGETMiddleware` (Cloudflare 520 fix), conversational WhatsApp widget, Abena chat, Hubtel/NOWPayments/Resend/R2/fx_service integrations, scrub of phishing keywords from `seed_data.py` (admin emails stay in DB only, not in code).
- **Verified end-to-end (preview)**:
    - All Mongo indexes created correctly (`Mongo indexes ensured.` at startup).
    - Login + Dashboard + Payments page render without console errors.
    - `GET /api/admin/transactions.csv` returns 455B valid CSV.
    - `GET /api/admin/transactions.xlsx` returns 6566B valid Microsoft Excel 2007+ file (2 sheets).
    - KPI `revenue_usd=$700` unchanged (2 Hubtel sandbox payments reconciled).
    - 3 new email templates seeded (`admin_payment_failed/expired/refunded`).
    - HEAD request on `/api/config` returns 200 (Cloudflare fix preserved).

## Iteration 16 (2026-11-19) — Admin ops pack (SMS, Monitoring, Activity, Tickets)
- Hubtel SMS admin alerts (`sms_service.py`): config in Admin → Settings → SMS Alerts (Client ID/Secret/Sender ID/numbers, per-event toggles: new submission, payment success, Abena escalation). Secret redacted in GET settings. Log in `sms_log`. Fire-and-forget (never blocks).
- Payment Monitoring (`health_service.py`, /admin/monitoring): probes Hubtel checkout + NowPayments /status (+ Hubtel SMS when on); history in `gateway_health`; email (template `admin_gateway_down`) + SMS on state change. Platform cron `.emergent/crons.yml` every 15 min → POST /api/cron/gateway-health (bearer WEBHOOK_CRON_SECRET, idempotent via `cron_runs`).
- Activity Log (`audit_service.py` ASGI middleware, /admin/activity): records every admin POST/PUT/DELETE + exports + document views, secrets masked, in `admin_audit_log`.
- Abena Tickets UI (/admin/tickets): list/filter, chat history, reply by email (new template `support_reply`), resolve/reopen.
- New email templates are added on startup without overwriting admin-edited ones.
- Payments page added to admin sidebar.
- Tested: iteration_14 (13/13 backend, frontend all flows pass). Real SMS untested — needs user's Hubtel SMS credentials.

## Remaining backlog
- P1: User enters Hubtel SMS credentials in Settings → SMS Alerts and sends a test SMS.
- P2: Abena learning system & AI analytics dashboard.
- NEVER hardcode admin emails in seed files (phishing classifier).

## Iteration 17 (2026-11-19) — Pre-production hardening
- CRITICAL fix: LIVE Hubtel callbacks no longer trusted; payment marked paid only after Hubtel Transaction Status API confirms (status Paid + clientReference + amount >= amount_charged). Retries: /payments/status poll (throttled 20s), cron every 15 min (max 12 attempts / 48h), admin "Verify now" in Monitoring. Requires the outbound proxy IP whitelisted at Hubtel for api-txnstatus.hubtel.com. Sandbox behaviour unchanged.
- Paid applications never downgraded by failure callbacks / sandbox confirm(false); _mark_application_paid atomic (no duplicate emails).
- Email template seed is non-destructive (upsert $setOnInsert only).
- Dashboard Lot 1 UI (search, dates, pagination, Submitted At) restored from GitHub branch.
- Mobile: Abena/WhatsApp buttons no longer overlap; admin mobile top nav.
- Backup: /root/backups/predeploy_20261119_194959 (mongodump preview DB + git commit a5a41f7). Rollback = Emergent "Rollback" to that checkpoint + redeploy.
- Tests: iteration_15, iteration_16 + pytest suites pass. Deploy readiness: PASS. Deployment must be triggered from the UI deploy panel (replace existing app).

## Iteration 18 (2026-11-19) — Compliance fix requested by Emergent support (deploy block)
- VisaSample.jsx: header "eGhanaVisa · Fictitious example" + "Not a real visa" badge, SAMPLE / ILLUSTRATION watermark, disclaimer footer; removed "Republic of Ghana", "Comptroller-General of Immigration", "Employment Prohibited", flag-coloured QR mock.
- Footer.jsx contact note: replaced "Comptroller-General of Immigration / Republic of Ghana" with "eGhanaVisa — independent private visa assistance service".
- Tested iteration_17 (100% frontend). Deployment on hold until Emergent lifts the classifier block.
- 2026-11-19: VisaSample wording updated per user (Visa Sample / Illustrative Visa Sample / third-party disclaimer). Tested iteration_18.
- 2026-11-19: Mobile floating buttons side by side (bottom-4), footer mobile bottom padding, WhatsApp root items-end, Abena ring; Apply note text updated. Tested iteration_19/20.
- 2026-11-19: IndependenceNotice ('We are independent — not the Government of Ghana') on Apply (above submit), Payment, Success; scroll to top on Payment/Success. No PDFs generated by the platform. Tested iteration_21/22. NOTE: NOWPayments is LIVE in preview (real key).

## 2026-06 Fork check
- Verified all 5 lots, admin features (SMS, health, audit, tickets), Hubtel server-side verification and independence notices retained in fork. Preview OK. Awaiting user UI deploy (Replace existing deployment), then non-destructive production smoke test.

## 2026-06 ABENA Livrable A (preview, not deployed)
- Markdown rendering (react-markdown, skipHtml, safe links via react-router), FR/EN welcome per browser language, mobile-friendly window, prompt STYLE section (short, lists, internal links, no self-intro). Tested iteration_23 (100%).
- Livrable B audit written: /app/memory/ABENA_AUDIT.md — awaiting user validation before any dev.
- Hubtel prod egress IP observed 130.211.210.175 (not guaranteed static).

## 2026-06 Livrable A validated by user; regression run OK (deployment awaits explicit user authorization). Step 1 design: /app/memory/ABENA_STEP1_DESIGN.md (awaiting validation; steps 2-8 NOT started). Note: tests iteration15 forged-callback test is stale (preview Hubtel sandbox trusts callbacks by design); iteration14 ticket tests need seeded test-ticket-1 fixture.

## 2026-06 Deploy #2 (Livrable A + temporary payment guard) — LIVE & verified
- Guard: _is_preview_host (Host header endswith .preview.emergentagent.com/.preview.emergentcf.cloud). Outside preview: /payments/confirm 403, sandbox Hubtel checkout 503 payments_suspended, forged Hubtel callbacks only trigger Status API verification, crypto simulate 403, sandbox/simulated NOWPayments initiate 503 & IPN ignored.
- PROD settings: hubtel.sandbox=true, nowpayments.sandbox=true (admin must switch to live). 2 paid apps GH-2026-983566 / GH-2026-585565 paid via mock checkout (Visa card (Hubtel Sandbox), TX- mock ids, 0 hubtel_callbacks) -> to verify in Hubtel dashboard.
- Tests: tests/test_payment_production_guards.py; stale tests fixed (iter15 renamed sandbox-preview test, iter14 self-seeding ticket fixture). iteration_24 100%.
- NEXT: payments live switch by user, optional NOWPayments IPN re-verification hardening (needs auth), then ABENA step 1 (design /app/memory/ABENA_STEP1_DESIGN.md, decisions validated).
