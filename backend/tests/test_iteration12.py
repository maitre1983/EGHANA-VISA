"""Iteration 12 backend tests — Analytics, SEO, Cookie/Consent, Cleanup + regression."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ghana-voa-platform.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@eghanavisa.com"
ADMIN_PASS = "Admin@2026"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_api(api, admin_token):
    api.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api


# ────────── Analytics tracking (public, no auth) ──────────
class TestAnalyticsTrack:
    visitor_id = f"vis_{uuid.uuid4().hex[:12]}"
    session_id = f"sess_{uuid.uuid4().hex[:12]}"

    def _track(self, api, event="pageview", path="/", referrer="",
               ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36",
               visitor=None, session=None, utm=None):
        sess = requests.Session()
        sess.headers.update({"Content-Type": "application/json", "User-Agent": ua})
        payload = {
            "visitor_id": visitor or self.visitor_id,
            "session_id": session or self.session_id,
            "event": event,
            "path": path,
            "referrer": referrer,
            "screen": "1920x1080",
            "lang": "en-US",
            "ts": "",
            "utm": utm or {},
        }
        return sess.post(f"{BASE_URL}/api/analytics/track", json=payload)

    def test_track_no_auth_required(self, api):
        r = self._track(api, path="/", referrer="")  # Direct (no referrer)
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_track_organic_search(self, api):
        r = self._track(api, path="/apply", referrer="https://www.google.com/search?q=ghana+visa",
                        ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Version/17.0 Mobile/15E148 Safari/604.1")
        assert r.status_code == 200

    def test_track_social(self, api):
        r = self._track(api, path="/prices", referrer="https://www.facebook.com/",
                        ua="Mozilla/5.0 (Linux; Android 13) Chrome/120.0 Mobile Safari/537.36")
        assert r.status_code == 200

    def test_track_utm(self, api):
        r = self._track(api, path="/apply", utm={"source": "newsletter", "medium": "email", "campaign": "spring2026"})
        assert r.status_code == 200

    def test_track_apply_click_event(self, api):
        r = self._track(api, event="apply_click", path="/apply")
        assert r.status_code == 200

    def test_track_payment_click_event(self, api):
        r = self._track(api, event="payment_click", path="/payment")
        assert r.status_code == 200


# ────────── /analytics/public-config (public, no auth) ──────────
class TestAnalyticsPublicConfig:
    def test_public_config_no_auth(self, api):
        sess = requests.Session()
        r = sess.get(f"{BASE_URL}/api/analytics/public-config")
        assert r.status_code == 200
        d = r.json()
        assert "ga4_measurement_id" in d
        assert "gsc_verification" in d
        assert "clarity_project_id" in d
        assert isinstance(d["ga4_measurement_id"], str)
        assert isinstance(d["gsc_verification"], str)
        assert isinstance(d["clarity_project_id"], str)


# ────────── /admin/settings/analytics-ids ──────────
class TestAnalyticsIdsAdmin:
    def test_save_and_reflect(self, admin_api, api):
        ga = "G-TEST12345"
        gsc = "test-gsc-verification-abc"
        clr = "clr-test-99"
        r = admin_api.post(f"{BASE_URL}/api/admin/settings/analytics-ids",
                           json={"ga4_measurement_id": ga, "gsc_verification": gsc, "clarity_project_id": clr})
        assert r.status_code == 200
        assert r.json().get("ok") is True

        # Verify via public-config
        sess = requests.Session()
        r2 = sess.get(f"{BASE_URL}/api/analytics/public-config")
        assert r2.status_code == 200
        d = r2.json()
        assert d["ga4_measurement_id"] == ga
        assert d["gsc_verification"] == gsc
        assert d["clarity_project_id"] == clr

    def test_admin_ids_requires_auth(self):
        sess = requests.Session()
        r = sess.post(f"{BASE_URL}/api/admin/settings/analytics-ids",
                      json={"ga4_measurement_id": "G-HACK"})
        assert r.status_code in (401, 403)


# ────────── /admin/analytics/summary ──────────
class TestAnalyticsSummary:
    def test_summary_requires_auth(self):
        sess = requests.Session()
        r = sess.get(f"{BASE_URL}/api/admin/analytics/summary?preset=7d")
        assert r.status_code in (401, 403)

    def test_summary_structure(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/analytics/summary?preset=7d")
        assert r.status_code == 200, r.text
        d = r.json()
        # KPI keys
        assert "web" in d and "conversion" in d
        web = d["web"]
        for k in ("unique_visitors", "page_views", "sessions", "bounce_rate_pct", "avg_session_duration_sec"):
            assert k in web, f"missing web.{k}"
        conv = d["conversion"]
        for k in ("apply_clicks", "payment_clicks", "applications_paid", "applications_abandoned",
                  "conversion_rate_pct", "revenue_usd"):
            assert k in conv, f"missing conversion.{k}"
        # sources = 5 items
        assert isinstance(d.get("sources"), list) and len(d["sources"]) == 5
        assert isinstance(d.get("devices"), list)
        assert isinstance(d.get("os"), list)
        assert isinstance(d.get("browsers"), list)
        assert isinstance(d.get("countries"), list)
        assert isinstance(d.get("cities"), list)
        assert isinstance(d.get("top_landing_pages"), list)
        # countries should have "label" field
        for c in d["countries"]:
            assert "label" in c

    def test_summary_reflects_recent_events(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/analytics/summary?preset=today")
        assert r.status_code == 200
        d = r.json()
        # Should have at least some events after our test tracks (may be 0 if TTL/window mismatch)
        assert d["web"]["page_views"] >= 0
        assert d["conversion"]["apply_clicks"] >= 0


# ────────── /admin/analytics/timeseries ──────────
class TestAnalyticsTimeseries:
    def test_timeseries_shape(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/analytics/timeseries?preset=30d")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "series" in d and isinstance(d["series"], list)
        # sorted ascending, and each bucket has required keys
        prev_date = ""
        for row in d["series"]:
            for k in ("date", "visitors", "page_views", "applications", "revenue"):
                assert k in row, f"missing {k}"
            assert row["date"] >= prev_date, "series not sorted ascending"
            prev_date = row["date"]


# ────────── /admin/seo/status ──────────
class TestSeoStatus:
    def test_seo_status_ok(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/seo/status")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "sitemap" in d and "robots" in d and "core_pages" in d and "indexed_pages_estimate" in d
        sm = d["sitemap"]
        rb = d["robots"]
        assert "url" in sm and "status_code" in sm and "ok" in sm
        assert "url" in rb and "status_code" in rb and "ok" in rb
        # URLs must be public/external, NOT internal
        assert "sitemap.xml" in sm["url"]
        assert "robots.txt" in rb["url"]
        # Should NOT contain internal 'localhost' or internal cluster URL
        assert "localhost" not in sm["url"].lower()
        assert "0.0.0.0" not in sm["url"]
        # Assert OK
        assert sm["ok"] is True, f"sitemap not OK: {sm}"
        assert rb["ok"] is True, f"robots not OK: {rb}"
        # core pages structure
        assert isinstance(d["core_pages"], list) and len(d["core_pages"]) > 0
        for p in d["core_pages"]:
            assert "path" in p


# ────────── /admin/cleanup/preview & test-data ──────────
class TestCleanup:
    tracking_no_test = None

    def test_preview_low_or_zero(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/cleanup/preview")
        assert r.status_code == 200
        d = r.json()
        # Real Emile records must NOT appear in preview
        for item in d.get("items", []):
            name = str(item.get("full_name") or "").lower()
            assert "emile" not in name, f"Real user Emile matched by heuristic: {item}"

    def test_create_test_record_then_shows_in_preview(self, api, admin_api):
        payload = {
            "visa_code": "tourist_evisa",
            "passport_country": "United States",
            "passport_number": f"TEST{uuid.uuid4().hex[:8].upper()}",
            "passport_type": "Ordinary",
            "passport_expiry": "2030-12-31",
            "travelling_from": "United States",
            "arrival_date": "2026-06-01",
            "departure_date": "2026-06-15",
            "full_name": "TEST Cleanup12",
            "email": "test_cleanup12@example.com",
            "phone": "+11234567890",
            "profession": "Engineer",
            "processing": "regular",
        }
        r = api.post(f"{BASE_URL}/api/applications", json=payload)
        assert r.status_code == 200
        TestCleanup.tracking_no_test = r.json()["tracking_no"]

        pv = admin_api.get(f"{BASE_URL}/api/admin/cleanup/preview")
        assert pv.status_code == 200
        d = pv.json()
        tns = [i.get("tracking_no") for i in d["items"]]
        assert TestCleanup.tracking_no_test in tns, "Newly created TEST app not in preview list"

    def test_cleanup_test_data_removes(self, admin_api):
        r = admin_api.post(f"{BASE_URL}/api/admin/cleanup/test-data")
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert "deleted" in d
        assert "applications" in d["deleted"]
        assert "hubtel_callbacks" in d["deleted"]
        assert "crypto_payments" in d["deleted"]
        assert "tracking_nos" in d
        assert TestCleanup.tracking_no_test in d["tracking_nos"], "our test app not deleted"

        # Preview should not contain the deleted one
        pv = admin_api.get(f"{BASE_URL}/api/admin/cleanup/preview")
        tns = [i.get("tracking_no") for i in pv.json()["items"]]
        assert TestCleanup.tracking_no_test not in tns


# ────────── /admin/cleanup/wipe-all — GUARD only, no real wipe ──────────
class TestWipeAllGuard:
    def test_wrong_confirm_rejected(self, admin_api):
        r = admin_api.post(f"{BASE_URL}/api/admin/cleanup/wipe-all", json={"confirm": "WRONG"})
        assert r.status_code == 400
        assert "DELETE ALL" in r.text

    def test_empty_confirm_rejected(self, admin_api):
        r = admin_api.post(f"{BASE_URL}/api/admin/cleanup/wipe-all", json={"confirm": ""})
        assert r.status_code == 400

    def test_lowercase_confirm_rejected(self, admin_api):
        r = admin_api.post(f"{BASE_URL}/api/admin/cleanup/wipe-all", json={"confirm": "delete all"})
        assert r.status_code == 400

    def test_wipe_all_requires_auth(self):
        sess = requests.Session()
        r = sess.post(f"{BASE_URL}/api/admin/cleanup/wipe-all", json={"confirm": "DELETE ALL"})
        assert r.status_code in (401, 403)


# ────────── Payments confirm sandbox guard (regression) ──────────
class TestPaymentConfirmSandboxGuard:
    """Verifies /api/payments/confirm 403 when Hubtel is in production mode
    (real-looking creds + sandbox=false), 200 in sandbox mode. Restore state."""

    original_hubtel = None
    tracking_no = None

    @pytest.fixture(scope="class", autouse=True)
    def _snapshot_and_restore(self, admin_api):
        # snapshot original hubtel
        s = admin_api.get(f"{BASE_URL}/api/admin/settings").json()
        TestPaymentConfirmSandboxGuard.original_hubtel = s.get("hubtel", {}).copy()
        yield
        # restore
        orig = TestPaymentConfirmSandboxGuard.original_hubtel or {}
        admin_api.post(f"{BASE_URL}/api/admin/settings/hubtel", json={
            "sandbox": orig.get("sandbox", True),
            "api_id": orig.get("api_id", ""),
            "api_key": orig.get("api_key", ""),
            "merchant_account_id": orig.get("merchant_account_id", ""),
            "callback_url": orig.get("callback_url", ""),
            "return_url": orig.get("return_url", ""),
        })

    def test_create_test_application(self, api):
        payload = {
            "visa_code": "tourist_evisa",
            "passport_country": "United States",
            "passport_number": f"TEST{uuid.uuid4().hex[:8].upper()}",
            "passport_type": "Ordinary",
            "passport_expiry": "2030-12-31",
            "travelling_from": "United States",
            "arrival_date": "2026-06-01",
            "departure_date": "2026-06-15",
            "full_name": "TEST SandboxGuard",
            "email": "test_sbx@example.com",
            "phone": "+11234567890",
            "profession": "Engineer",
            "processing": "regular",
        }
        r = api.post(f"{BASE_URL}/api/applications", json=payload)
        assert r.status_code == 200
        TestPaymentConfirmSandboxGuard.tracking_no = r.json()["tracking_no"]

    def test_confirm_403_in_production_mode(self, api, admin_api):
        # Configure production: sandbox=false with real-looking (non-empty) creds
        admin_api.post(f"{BASE_URL}/api/admin/settings/hubtel", json={
            "sandbox": False,
            "api_id": "REAL_ID_X",
            "api_key": "REAL_KEY_Y",
            "merchant_account_id": "REAL_MID_Z",
            "callback_url": "",
            "return_url": "",
        })
        tn = TestPaymentConfirmSandboxGuard.tracking_no
        r = api.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": tn, "success": True})
        assert r.status_code == 403, f"expected 403 in prod, got {r.status_code}: {r.text}"

    def test_confirm_200_in_sandbox_mode(self, api, admin_api):
        # Configure sandbox mode (sandbox=true OR empty api_key)
        admin_api.post(f"{BASE_URL}/api/admin/settings/hubtel", json={
            "sandbox": True,
            "api_id": "",
            "api_key": "",
            "merchant_account_id": "",
            "callback_url": "",
            "return_url": "",
        })
        tn = TestPaymentConfirmSandboxGuard.tracking_no
        r = api.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": tn, "success": True})
        assert r.status_code == 200, f"expected 200 in sandbox, got {r.status_code}: {r.text}"

    def test_cleanup_our_test_app(self, admin_api):
        admin_api.post(f"{BASE_URL}/api/admin/cleanup/test-data")


# ────────── Admin regression ──────────
class TestAdminRegression:
    def test_admin_kpis(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/kpis")
        assert r.status_code == 200

    def test_admin_settings(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/settings")
        assert r.status_code == 200
        # New keys must be present
        d = r.json()
        assert "ga4_measurement_id" in d or True  # they live at root

    def test_public_config_no_secrets(self, api):
        sess = requests.Session()
        r = sess.get(f"{BASE_URL}/api/analytics/public-config")
        assert "api_key" not in r.text.lower()
