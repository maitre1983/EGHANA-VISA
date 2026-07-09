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
