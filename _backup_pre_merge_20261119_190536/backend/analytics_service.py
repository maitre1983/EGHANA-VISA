"""First-party analytics service — parses user-agent, classifies traffic source
and provides aggregation helpers for the Admin Analytics dashboard.

No external dependencies: we implement a tiny UA parser inline (good enough
for device/os/browser breakdowns without shipping a heavyweight library)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import urlparse


def parse_ua(ua: str) -> Tuple[str, str, str]:
    """Return (device, os, browser)."""
    if not ua:
        return "Unknown", "Unknown", "Unknown"
    ua_l = ua.lower()

    if "ipad" in ua_l:
        device = "Tablet"
    elif "tablet" in ua_l or "kindle" in ua_l:
        device = "Tablet"
    elif "mobi" in ua_l or "iphone" in ua_l or "android" in ua_l:
        device = "Mobile"
    else:
        device = "Desktop"

    if "windows" in ua_l:
        os_name = "Windows"
    elif "mac os" in ua_l or "macintosh" in ua_l:
        os_name = "macOS"
    elif "iphone" in ua_l or "ipad" in ua_l or "ios" in ua_l:
        os_name = "iOS"
    elif "android" in ua_l:
        os_name = "Android"
    elif "linux" in ua_l:
        os_name = "Linux"
    else:
        os_name = "Other"

    if "edg/" in ua_l:
        browser = "Edge"
    elif "chrome/" in ua_l and "chromium" not in ua_l:
        browser = "Chrome"
    elif "firefox/" in ua_l:
        browser = "Firefox"
    elif "safari/" in ua_l and "chrome" not in ua_l:
        browser = "Safari"
    elif "opr/" in ua_l or "opera" in ua_l:
        browser = "Opera"
    else:
        browser = "Other"

    return device, os_name, browser


SEARCH_ENGINES = ("google.", "bing.", "duckduckgo.", "yahoo.", "yandex.", "baidu.", "ecosia.")
SOCIAL_NETS = ("facebook.", "instagram.", "twitter.", "x.com", "t.co", "linkedin.", "tiktok.", "pinterest.", "youtube.", "reddit.", "whatsapp.")


def classify_source(referrer: str, host_domain: str, utm_source: str, utm_medium: str) -> str:
    """Classify traffic into: Organic Search / Social / Referral / Direct / Paid Ads."""
    if utm_medium and utm_medium.lower() in ("cpc", "ppc", "paid", "cpm", "display"):
        return "Paid Ads"
    if utm_source:
        us = utm_source.lower()
        if any(s in us for s in ("google_ads", "adwords", "facebook_ads", "meta_ads", "bing_ads")):
            return "Paid Ads"
    if not referrer:
        return "Direct"
    try:
        host = (urlparse(referrer).hostname or "").lower()
    except Exception:
        return "Direct"
    if not host or host_domain in host:
        return "Direct"
    if any(se in host for se in SEARCH_ENGINES):
        return "Organic Search"
    if any(sn in host for sn in SOCIAL_NETS):
        return "Social Media"
    return "Referral"


def country_from_headers(headers) -> str:
    """Pull best-effort ISO country from common CDN/proxy headers."""
    for h in (
        "cf-ipcountry",
        "x-vercel-ip-country",
        "x-forwarded-country",
        "x-country-code",
        "x-appengine-country",
    ):
        val = headers.get(h)
        if val and val.upper() not in ("XX", "T1", ""):
            return val.upper()[:2]
    return "ZZ"  # Unknown


def city_from_headers(headers) -> str:
    for h in ("x-vercel-ip-city", "cf-ipcity", "x-forwarded-city"):
        v = headers.get(h)
        if v:
            return v[:64]
    return ""


# ISO 3166-1 alpha-2 → English country name (subset, extend as needed)
COUNTRY_NAMES = {
    "US": "United States", "GB": "United Kingdom", "FR": "France", "DE": "Germany",
    "ES": "Spain", "IT": "Italy", "NL": "Netherlands", "BE": "Belgium", "CH": "Switzerland",
    "SE": "Sweden", "NO": "Norway", "DK": "Denmark", "FI": "Finland", "IE": "Ireland",
    "PT": "Portugal", "PL": "Poland", "GR": "Greece", "AT": "Austria",
    "CA": "Canada", "MX": "Mexico", "BR": "Brazil", "AR": "Argentina", "CL": "Chile",
    "IN": "India", "CN": "China", "JP": "Japan", "KR": "South Korea", "PH": "Philippines",
    "TH": "Thailand", "SG": "Singapore", "MY": "Malaysia", "ID": "Indonesia", "VN": "Vietnam",
    "AU": "Australia", "NZ": "New Zealand",
    "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya", "GH": "Ghana", "EG": "Egypt", "MA": "Morocco", "TN": "Tunisia",
    "CI": "Ivory Coast", "SN": "Senegal", "CM": "Cameroon", "TG": "Togo", "BJ": "Benin", "BF": "Burkina Faso",
    "AE": "United Arab Emirates", "SA": "Saudi Arabia", "TR": "Turkey", "IL": "Israel", "QA": "Qatar",
    "RU": "Russia", "UA": "Ukraine", "RO": "Romania", "HU": "Hungary", "CZ": "Czechia", "SK": "Slovakia",
    "ZZ": "Unknown",
}


def parse_date_range(from_str: Optional[str], to_str: Optional[str], preset: Optional[str]) -> Tuple[datetime, datetime]:
    """Resolve a date range from either explicit from/to ISO strings or a preset key."""
    now = datetime.now(timezone.utc)
    end = now
    start = now - timedelta(days=30)

    if preset:
        p = preset.lower()
        today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if p == "today":
            start = today0
        elif p == "yesterday":
            start = today0 - timedelta(days=1); end = today0
        elif p == "7d":
            start = today0 - timedelta(days=6)
        elif p == "30d":
            start = today0 - timedelta(days=29)
        elif p == "90d":
            start = today0 - timedelta(days=89)
        elif p == "year":
            start = today0.replace(month=1, day=1)
        elif p == "all":
            start = datetime(2020, 1, 1, tzinfo=timezone.utc)

    if from_str:
        try:
            start = datetime.fromisoformat(from_str.replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    if to_str:
        try:
            end = datetime.fromisoformat(to_str.replace("Z", "+00:00"))
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return start, end


TEST_HEURISTICS_REGEX = re.compile(
    r"("
    r"^test[\s-]|"                # names starting with test
    r"\btest[\s-]|"               # 'test' preceded by boundary
    r"\bwebhook\stest\b|"
    r"\bregression\b|"
    r"\bdummy\b|"
    r"prod\sguard\stest|"
    r"notify\stest"
    r")",
    re.IGNORECASE,
)


def is_test_record(doc: dict) -> bool:
    """Heuristic: flag applications that look like test data."""
    email = str(doc.get("email") or "").lower()
    if email.endswith(("@example.com", "@example.org", "@test.com", "@mailinator.com")):
        return True
    if email.startswith(("test-", "test@", "wh@", "pg@", "e2e@", "qa@")):
        return True
    name = str(doc.get("full_name") or "")
    if TEST_HEURISTICS_REGEX.search(name):
        return True
    passport = str(doc.get("passport_number") or "").upper()
    if passport in {"AB123456", "WH123", "PROD1", "PROD2", "TEST123", "TESTPASS"}:
        return True
    if passport.startswith(("TEST", "DUMMY", "FAKE")):
        return True
    return False
