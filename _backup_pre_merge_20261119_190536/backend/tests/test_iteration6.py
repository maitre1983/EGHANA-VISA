"""Iteration 6 — verification tests for code-quality remediation.

Covers:
- countries.py type hints — functional shape check via /api/countries.
- seed_data.py type-annotated constants — DEFAULT_SETTINGS is Mongo-writable.
- server.py startup decomposition — three helpers seeded state remains valid.
- Regression: /api/config, /api/countries, admin login, full flow signatures.
"""
import os
import sys
import inspect
import typing
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")

# Ensure /app/backend on path so we can import server modules
sys.path.insert(0, "/app/backend")


class TestCountriesTypeHints:
    """countries.py: passport_countries() / travel_from_countries() -> list[str]"""

    def test_function_has_list_str_return_annotation(self):
        from countries import passport_countries, travel_from_countries
        # PEP 585 list[str]
        pc_sig = inspect.signature(passport_countries)
        tf_sig = inspect.signature(travel_from_countries)
        assert pc_sig.return_annotation is not inspect.Signature.empty, "passport_countries missing return annotation"
        assert tf_sig.return_annotation is not inspect.Signature.empty, "travel_from_countries missing return annotation"
        # Should be list[str] (either typing.List[str] or built-in list[str])
        # Both stringify to include 'list' and 'str'
        pc_ann = str(pc_sig.return_annotation)
        tf_ann = str(tf_sig.return_annotation)
        assert "list" in pc_ann.lower() and "str" in pc_ann.lower(), f"passport_countries return: {pc_ann}"
        assert "list" in tf_ann.lower() and "str" in tf_ann.lower(), f"travel_from_countries return: {tf_ann}"

    def test_countries_endpoint_shape_and_ecowas_filter(self):
        r = requests.get(f"{BASE_URL}/api/countries", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data.get("passport"), list)
        assert isinstance(data.get("travel_from"), list)
        # travel_from should be full list; passport excludes 16 ECOWAS members
        assert len(data["travel_from"]) - len(data["passport"]) == 16, (
            f"Expected 16 ECOWAS exclusions, got {len(data['travel_from']) - len(data['passport'])}"
        )
        # Ghana (host) must not be selectable as passport country
        assert "Ghana" not in data["passport"]
        assert "Ghana" in data["travel_from"]
        # Sanity: known non-ECOWAS country present in both
        assert "United States" in data["passport"]
        assert "France" in data["passport"]
        # Every entry must be a non-empty string
        for c in data["passport"]:
            assert isinstance(c, str) and len(c) > 0


class TestSeedDataTypeHints:
    """seed_data.py annotated constants must remain valid + Mongo-safe."""

    def test_default_settings_shape(self):
        from seed_data import DEFAULT_SETTINGS, DEFAULT_EMAIL_TEMPLATES, EMAIL_TEMPLATES_VERSION
        assert isinstance(DEFAULT_SETTINGS, dict)
        assert DEFAULT_SETTINGS["id"] == "singleton"
        assert isinstance(DEFAULT_SETTINGS["visa_types"], list) and len(DEFAULT_SETTINGS["visa_types"]) >= 3
        assert isinstance(DEFAULT_SETTINGS["payment_methods"], list) and len(DEFAULT_SETTINGS["payment_methods"]) >= 3
        assert isinstance(DEFAULT_SETTINGS["nowpayments"], dict)
        assert "usdt_discount_pct" in DEFAULT_SETTINGS
        assert isinstance(DEFAULT_EMAIL_TEMPLATES, list) and len(DEFAULT_EMAIL_TEMPLATES) == 6
        assert isinstance(EMAIL_TEMPLATES_VERSION, int) and EMAIL_TEMPLATES_VERSION >= 2

    def test_mongo_json_serializable(self):
        """All values must be plain JSON-safe types (no datetimes leaking)."""
        import json
        from seed_data import DEFAULT_SETTINGS, DEFAULT_EMAIL_TEMPLATES
        # json.dumps will raise if any value is not primitive
        json.dumps(DEFAULT_SETTINGS)
        json.dumps(DEFAULT_EMAIL_TEMPLATES)


class TestStartupHelpersRegression:
    """Startup decomposition must leave DB in a valid state (verified by public/admin APIs)."""

    def test_admin_and_settings_present(self):
        # /api/config succeeds -> settings singleton exists (seed helper ran)
        r = requests.get(f"{BASE_URL}/api/config", timeout=10)
        assert r.status_code == 200
        cfg = r.json()
        assert "visa_types" in cfg and len(cfg["visa_types"]) >= 3
        assert "payment_methods" in cfg
        assert "usdt_discount_pct" in cfg
        assert "nowpayments_configured" in cfg

    def test_admin_login_works(self):
        r = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"email": "admin@eghanavisa.com", "password": "Admin@2026New!"},
            timeout=10,
        )
        assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
        data = r.json()
        assert "token" in data and len(data["token"]) > 20

    def test_email_templates_v2_persisted(self):
        # login
        import re
        tok = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"email": "admin@eghanavisa.com", "password": "Admin@2026New!"},
            timeout=10,
        ).json()["token"]
        r = requests.get(
            f"{BASE_URL}/api/admin/email-templates",
            headers={"Authorization": f"Bearer {tok}"},
            timeout=10,
        )
        assert r.status_code == 200
        tpls = r.json()
        assert len(tpls) == 6, f"expected 6 templates, got {len(tpls)}"
        # All must have double-brace placeholders (iteration-5 fix still holding).
        # Look for SINGLE-brace {token} not preceded/followed by another brace.
        for t in tpls:
            body = t.get("html", "") + " " + t.get("subject", "")
            for token in ("name", "tracking", "visa_type", "processing", "amount"):
                # match {token} but not {{token}}
                stray = re.search(r"(?<!\{)\{" + token + r"\}(?!\})", body)
                assert stray is None, (
                    f"single-brace leakage in {t['template_name']}/{t['lang']}: {{{token}}}"
                )
            # And each template that references a placeholder must use double-brace form
            for token in ("name", "tracking"):
                assert (
                    ("{{" + token + "}}") in body or token not in body
                ), f"{t['template_name']}/{t['lang']} references {token} without double braces"


class TestFullFlowRegression:
    """End-to-end: application -> USDT sandbox pay -> success, using memoized/refactored code paths."""

    def test_application_creation_and_usdt_flow(self):
        # Ensure usdt_trc20 is active
        tok = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"email": "admin@eghanavisa.com", "password": "Admin@2026New!"},
            timeout=10,
        ).json()["token"]
        headers = {"Authorization": f"Bearer {tok}"}
        requests.post(
            f"{BASE_URL}/api/admin/settings/payment-toggle",
            headers=headers,
            json={"code": "usdt_trc20", "active": True},
            timeout=10,
        )

        # Create application
        payload = {
            "visa_code": "tourist_30",
            "passport_country": "United States",
            "passport_number": "TEST_ITER6_P1",
            "passport_type": "Ordinary",
            "passport_expiry": "2030-01-01",
            "travelling_from": "United States",
            "arrival_date": "2026-06-01",
            "departure_date": "2026-06-15",
            "full_name": "TEST Iteration6 Applicant",
            "email": "TEST_iter6@example.com",
            "phone": "+15551230000",
            "profession": "Engineer",
            "processing": "regular",
            "lang": "en",
        }
        r = requests.post(f"{BASE_URL}/api/applications", json=payload, timeout=10)
        assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
        app_doc = r.json()
        tracking = app_doc["tracking_no"]
        assert tracking.startswith("GH-")

        # Init USDT payment
        r = requests.post(
            f"{BASE_URL}/api/payments/crypto/initiate",
            json={"tracking_no": tracking, "network": "trc20"},
            timeout=10,
        )
        assert r.status_code == 200, f"crypto initiate failed: {r.text}"
        crypto = r.json()
        assert crypto["simulated"] is True
        payment_id = crypto["payment_id"]

        # Simulate success
        r = requests.post(
            f"{BASE_URL}/api/payments/crypto/simulate-finish/{payment_id}",
            json={"success": True},
            timeout=10,
        )
        assert r.status_code == 200

        # Verify /track works (paid)
        r = requests.get(f"{BASE_URL}/api/track/{tracking}", timeout=10)
        assert r.status_code == 200
        tr = r.json()
        assert tr["status"] == "submitted"
        assert tr["visa_name"] == "30 Days Tourist Visa"

    def test_ama_chat(self):
        r = requests.post(
            f"{BASE_URL}/api/chat",
            json={"message": "How much is the 30 day tourist visa?"},
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data.get("reply"), str) and len(data["reply"]) > 10
        assert "session_id" in data
