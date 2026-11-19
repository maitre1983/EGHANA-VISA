# e.GHANA Visa Portal — Test Credentials

## Admin (Command Center) — RESET iteration 9 (verified iteration 9 testing)
- URL: /admin
- Email: admin@eghanavisa.com
- Password: Admin@2026
- must_change_password: false (login goes straight to dashboard)
- Verified: POST /api/admin/login returns 200 + valid JWT; JWT unlocks /api/admin/kpis, /api/admin/settings, /api/admin/applications (all 200).

## Payment
- Hubtel: SANDBOX by default
- NowPayments: SANDBOX/simulation until real keys configured
- Real Resend delivery working (domain eghanavisa.com verified)
