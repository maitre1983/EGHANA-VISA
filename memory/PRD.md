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
- ✅ New admin setting `admin_notification_email` (default `mirtoken2022@gmail.com`), editable in `/admin/settings → WhatsApp & AI` tab (leave empty to disable).
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
