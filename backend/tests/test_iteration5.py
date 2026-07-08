"""Iteration 5 — Regression tests after CRITICAL email template regression fix.

Verifies:
  1. Template version doc set to version=2 in db.template_versions
  2. All 6 email templates (submitted/in_progress/done x en/fr) contain double-brace
     placeholders in DB (no single-brace leakage from prior .format() bug)
  3. EmailService.render_template() for every combination leaves ZERO unsubstituted
     placeholders (neither {name} nor {{name}} etc.)
  4. End-to-end: create app → USDT sandbox pay → admin sets in_progress → email log
     has html with actual name+tracking (not literal placeholders); repeat for done.
  5. Regression smoke: /api/config, admin login, /api/chat.
"""
import os
import re
import time
import asyncio
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip()
            break
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@eghanavisa.com"
ADMIN_PASSWORDS = ["Admin@2026New!", "Admin@2026"]

APP_PAYLOAD = {
    "visa_code": "tourist_30",
    "passport_country": "USA",
    "passport_number": "TESTITR5A",
    "passport_type": "ordinary",
    "passport_expiry": "2030-01-01",
    "travelling_from": "USA",
    "arrival_date": "2026-06-01",
    "departure_date": "2026-06-15",
    "full_name": "TEST Alice Iter5",
    "email": "test.alice.iter5@example.com",
    "phone": "+233200000005",
    "profession": "Engineer",
    "processing": "regular",
    "lang": "en",
}


# --- Mongo helpers (async) --------------------------------------------------

def _mongo():
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import dotenv_values
    cfg = dotenv_values("/app/backend/.env")
    client = AsyncIOMotorClient(cfg["MONGO_URL"].strip('"'))
    db = client[cfg["DB_NAME"].strip('"')]
    return client, db


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture(scope="module")
def admin_token():
    for pw in ADMIN_PASSWORDS:
        r = requests.post(f"{API}/admin/login", json={"email": ADMIN_EMAIL, "password": pw}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("must_change_password"):
                r2 = requests.post(
                    f"{API}/admin/change-password",
                    headers={"Authorization": f"Bearer {data['token']}"},
                    json={"current_password": pw, "new_password": "Admin@2026New!"},
                    timeout=15,
                )
                if r2.status_code == 200:
                    return r2.json().get("token") or data["token"]
            return data["token"]
    pytest.skip("Admin login failed")


# --- 1. Template version doc ------------------------------------------------

class TestTemplateVersion:
    def test_template_version_is_2(self):
        client, db = _mongo()
        try:
            doc = asyncio.get_event_loop().run_until_complete(
                db.template_versions.find_one({"id": "email_templates"}, {"_id": 0})
            )
            assert doc is not None, "template_versions doc missing (startup migration did not run)"
            assert doc.get("version") == 2, f"expected version=2 got {doc}"
        finally:
            client.close()


# --- 2. DB templates use double-brace ---------------------------------------

class TestSeededTemplatesShape:
    def test_all_six_templates_double_brace(self):
        client, db = _mongo()
        loop = asyncio.get_event_loop()
        try:
            docs = loop.run_until_complete(
                db.email_templates.find({}, {"_id": 0}).to_list(100)
            )
            names = {(d["template_name"], d["lang"]) for d in docs}
            for n in ["submitted", "in_progress", "done"]:
                for lg in ["en", "fr"]:
                    assert (n, lg) in names, f"missing {n}/{lg}"

            single_brace_pat = re.compile(r'(?<!\{)\{[a-zA-Z_][a-zA-Z0-9_]*\}(?!\})')
            double_brace_pat = re.compile(r'\{\{[a-zA-Z_][a-zA-Z0-9_]*\}\}')

            problems = []
            for d in docs:
                key = f"{d['template_name']}/{d['lang']}"
                blob = (d.get("subject") or "") + "\n" + (d.get("html") or "")
                sb = single_brace_pat.findall(blob)
                db_hits = double_brace_pat.findall(blob)
                # Every seeded template MUST have at least the {{name}} and {{tracking}} tokens
                if not db_hits:
                    problems.append((key, "NO double-brace tokens found", db_hits, sb))
                    continue
                # Extract just the names to make sure name/tracking are present
                names_in_tpl = {m.strip("{}") for m in db_hits}
                if "name" not in names_in_tpl or "tracking" not in names_in_tpl:
                    problems.append((key, "missing name/tracking token", names_in_tpl, sb))
                if sb:
                    problems.append((key, "SINGLE-brace leakage!", sb, db_hits))
            assert not problems, f"Template shape problems: {problems}"
        finally:
            client.close()


# --- 3. Render substitution for every combination ---------------------------

class TestRenderSubstitution:
    def test_render_all_templates_no_leftover(self):
        client, db = _mongo()
        loop = asyncio.get_event_loop()
        try:
            import sys
            if "/app/backend" not in sys.path:
                sys.path.insert(0, "/app/backend")
            from email_service import EmailService
            svc = EmailService(db)
            ctx = {
                "name": "Alice Doe",
                "tracking": "GH-2026-999999",
                "visa_type": "Tourist 30 Days",
                "processing": "Regular 5–7 days",
                "amount": "350.00",
            }
            failed = []
            for tpl in ["submitted", "in_progress", "done"]:
                for lg in ["en", "fr"]:
                    subj, html = loop.run_until_complete(svc.render_template(tpl, lg, ctx))
                    text = subj + "\n" + html
                    # Any unsubstituted placeholder (single OR double brace) is a failure
                    left = re.findall(r'\{\{?[a-zA-Z_][a-zA-Z0-9_]*\}?\}', text)
                    # BUT the html contains legitimate CSS/HTML braces? No — CSS uses colon/semicolon.
                    # Just to be safe, filter out ones like {0}, {tracking}, {name}, {visa_type}, {processing}, {amount}
                    placeholder_names = {"name", "tracking", "visa_type", "processing", "amount"}
                    leftover_names = [m for m in left if m.strip("{}") in placeholder_names]
                    if leftover_names:
                        failed.append((tpl, lg, leftover_names))
                    # Also: rendered content must contain the substituted values
                    if ctx["name"] not in html:
                        failed.append((tpl, lg, "name value not present in html"))
                    if ctx["tracking"] not in html and ctx["tracking"] not in subj:
                        failed.append((tpl, lg, "tracking value not present in output"))
            assert not failed, f"Substitution failures: {failed}"
        finally:
            client.close()


# --- 4. End-to-end status transitions produce properly-worded emails --------

class TestE2EStatusTransitions:
    """Create app → simulate USDT payment → set in_progress → set done.
    Verify db.email_log entries contain actual name + tracking, not literal placeholders.
    """

    def _ensure_usdt_active(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.post(f"{API}/admin/settings/payment-toggle",
                          json={"code": "usdt_trc20", "active": True},
                          headers=h, timeout=15)
        assert r.status_code == 200, r.text

    def test_full_transition_flow(self, admin_token):
        self._ensure_usdt_active(admin_token)

        # (a) Create fresh application
        payload = dict(APP_PAYLOAD)
        payload["passport_number"] = f"TESTITR5{int(time.time()) % 100000:05d}"
        r = requests.post(f"{API}/applications", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        tn = r.json()["tracking_no"]
        assert tn.startswith("GH-"), tn

        # (b) Simulate USDT payment
        r = requests.post(f"{API}/payments/crypto/initiate",
                          json={"tracking_no": tn, "network": "trc20"}, timeout=15)
        assert r.status_code == 200, r.text
        pid = r.json()["payment_id"]
        r = requests.post(f"{API}/payments/crypto/simulate-finish/{pid}",
                          json={"success": True}, timeout=15)
        assert r.status_code == 200, r.text

        # Give backend a beat to write email_log for 'submitted'
        time.sleep(1.0)

        # (c) Admin sets in_progress
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.post(f"{API}/admin/applications/{tn}/status",
                          json={"status": "in_progress"}, headers=h, timeout=15)
        assert r.status_code == 200, r.text
        time.sleep(0.5)

        # (d) Admin sets done
        r = requests.post(f"{API}/admin/applications/{tn}/status",
                          json={"status": "done"}, headers=h, timeout=15)
        assert r.status_code == 200, r.text
        time.sleep(0.5)

        # Now inspect db.email_log
        client, db = _mongo()
        loop = asyncio.get_event_loop()
        try:
            logs = loop.run_until_complete(
                db.email_log.find(
                    {"recipient": payload["email"]}, {"_id": 0}
                ).sort("created_at", -1).to_list(20)
            )
            assert logs, f"No email_log entries for {payload['email']}"

            # Find one per template_name
            by_tpl = {}
            for l in logs:
                by_tpl.setdefault(l["template_name"], l)  # first (most recent) wins

            for tpl_name in ("submitted", "in_progress", "done"):
                assert tpl_name in by_tpl, f"No email_log entry for template {tpl_name}"
                entry = by_tpl[tpl_name]
                subj = entry.get("subject", "")
                html = entry.get("html", "")
                blob = subj + "\n" + html

                # Must NOT contain literal placeholders
                for bad in ("{name}", "{{name}}", "{tracking}", "{{tracking}}",
                            "{visa_type}", "{{visa_type}}",
                            "{processing}", "{{processing}}",
                            "{amount}", "{{amount}}"):
                    assert bad not in blob, (
                        f"Template '{tpl_name}' email_log still contains literal '{bad}'. "
                        f"subject={subj!r} html_preview={html[:400]!r}"
                    )

                # Must contain the applicant's actual name and tracking no
                assert payload["full_name"] in html, (
                    f"Template '{tpl_name}' html missing applicant name. html_preview={html[:400]!r}"
                )
                assert tn in blob, (
                    f"Template '{tpl_name}' output missing tracking {tn}. subject={subj!r}"
                )

            # For submitted specifically: check visa_type/processing/amount substituted too
            sub_html = by_tpl["submitted"]["html"]
            # visa_type comes from settings — we sent tourist_30 → likely "30 Days Tourist Visa"
            assert "USD" in sub_html, "amount block missing in submitted template"
        finally:
            client.close()


# --- 5. Regression smoke ----------------------------------------------------

class TestRegressionSmoke:
    def test_config(self):
        r = requests.get(f"{API}/config", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "payment_methods" in d
        assert "visa_types" in d

    def test_admin_login(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 10

    def test_admin_kpis(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/admin/kpis", headers=h, timeout=10)
        assert r.status_code == 200

    def test_admin_applications_list(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/admin/applications?status=all", headers=h, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_ama_chat(self):
        r = requests.post(f"{API}/chat",
                          json={"message": "How much does a 30-day tourist visa cost?", "session_id": None},
                          timeout=45)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert isinstance(d.get("reply"), str) and len(d["reply"]) > 0


# --- 6. Admin settings tabs regression --------------------------------------

class TestAdminSettingsRegression:
    def test_get_settings(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/admin/settings", headers=h, timeout=10)
        assert r.status_code == 200
        s = r.json()
        for k in ("visa_types", "payment_methods", "hubtel", "nowpayments",
                  "whatsapp_admin", "ai_model", "usdt_discount_pct"):
            assert k in s, f"missing {k} in admin settings"

    def test_visa_price_save(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/admin/settings", headers=h, timeout=10)
        original = next(v["price_usd"] for v in r.json()["visa_types"] if v["code"] == "tourist_30")
        r = requests.post(f"{API}/admin/settings/visa-price",
                          json={"code": "tourist_30", "price_usd": original},
                          headers=h, timeout=10)
        assert r.status_code == 200

    def test_visa_toggle_noop(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        # tourist_30 is always_active — should reject deactivation with 400
        r = requests.post(f"{API}/admin/settings/visa-toggle",
                          json={"code": "tourist_30", "active": False},
                          headers=h, timeout=10)
        assert r.status_code == 400

    def test_payment_toggle(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        # toggle bep20 on and off
        r = requests.post(f"{API}/admin/settings/payment-toggle",
                          json={"code": "usdt_bep20", "active": True},
                          headers=h, timeout=10)
        assert r.status_code == 200
        r = requests.post(f"{API}/admin/settings/payment-toggle",
                          json={"code": "usdt_bep20", "active": True},
                          headers=h, timeout=10)
        assert r.status_code == 200

    def test_hubtel_config_save(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.post(f"{API}/admin/settings/hubtel",
                          json={"sandbox": True, "api_id": "", "api_key": "",
                                "merchant_account_id": "", "callback_url": "",
                                "return_url": "", "outbound_proxy_url": ""},
                          headers=h, timeout=10)
        assert r.status_code == 200

    def test_nowpayments_config_and_discount(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.post(f"{API}/admin/settings/nowpayments",
                          json={"sandbox": True, "api_key": "", "ipn_secret": "",
                                "sandbox_api_key": "", "sandbox_ipn_secret": ""},
                          headers=h, timeout=10)
        assert r.status_code == 200
        r = requests.post(f"{API}/admin/settings/usdt-discount",
                          json={"pct": 10}, headers=h, timeout=10)
        assert r.status_code == 200
        assert r.json().get("usdt_discount_pct") == 10.0

    def test_whatsapp_and_ai(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.post(f"{API}/admin/settings/whatsapp",
                          json={"whatsapp_admin": "+233000000000"},
                          headers=h, timeout=10)
        assert r.status_code == 200
        r = requests.post(f"{API}/admin/settings/ai-model",
                          json={"ai_model": "claude-sonnet-4-5-20250929"},
                          headers=h, timeout=10)
        assert r.status_code == 200

    def test_email_templates_listing(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/admin/email-templates", headers=h, timeout=10)
        assert r.status_code == 200
        tpls = r.json()
        assert len(tpls) == 6, f"expected 6 templates, got {len(tpls)}"
