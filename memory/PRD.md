# e.GHANA Visa Portal — PRD

## Original problem statement
Build a full-stack Ghana Visa On Arrival web application for **eghanavisa.com** with:
- Application form (visa type / passport / travel / personal / 4 file uploads)
- Two processing types (Regular 5–7d — Express 48–72h with configurable surcharge)
- Hubtel Visa card payment (Visa only at launch, USDT crypto prepared but disabled)
- Application tracking (`Submitted → In Progress → Done`), each transition sends email
- Admin dashboard "command center" with KPIs, filtered table, actions, settings and analytics
- Floating AI chat assistant "Ama"
- Legal (Terms + Privacy), FAQ (8 Qs), departure-date compliance warning
- Blurred Ghana Visa sample preview card
- Full SEO (title, meta, OG, Schema.org, sitemap, robots)

## Architecture
- **Backend**: FastAPI + Motor (Mongo) + JWT + bcrypt
- **Frontend**: React 19 + React-Router 7 + Tailwind + shadcn/ui + sonner
- **Storage**: Emergent Object Storage (behind abstract `StorageService`, future-ready for R2/S3)
- **Email**: Resend (real when `RESEND_API_KEY` set — simulation-log fallback otherwise, previewable in admin)
- **Payments**: Hubtel Online Checkout with **SANDBOX** simulation mode until keys are added in `/admin/settings`. Optional outbound static-IP proxy (Fixie-style) supported via `outbound_proxy_url`.
- **AI chat**: Claude Sonnet 4.5 via `emergentintegrations` + Emergent Universal Key; **model is configurable in `/admin/settings`**.
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
- ✅ Frontend end-to-end validated (Home → Apply → Sandbox pay → Track → Admin transitions → Ama chat)

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
