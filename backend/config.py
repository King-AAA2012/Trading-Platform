"""Site configuration. Everything here can be overridden with environment variables or a `.env` file in the project
root (see `.env.example`). Replace the placeholders before going live."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text("utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
E = os.environ.get

APP_NAME = E("APP_NAME", "CasuallyHedge")
MOTTO = E("APP_MOTTO", "Trading, for the little guy.")
# >>> Replace with your real support address (or set COMPANY_EMAIL in .env). Shown in the beta pop-up and legal pages.
COMPANY_EMAIL = E("COMPANY_EMAIL", "support@YOUR-COMPANY-DOMAIN.com")
LEGAL_ENTITY = E("LEGAL_ENTITY", "[Your registered company name]")
LEGAL_ADDRESS = E("LEGAL_ADDRESS", "[Your registered business address]")
JURISDICTION = E("JURISDICTION", "India")
SITE_URL = E("SITE_URL", "http://127.0.0.1:8420")
TERMS_VERSION = "2026-09-30"

TRIAL_DAYS = int(E("TRIAL_DAYS", "30"))
PRICE_CURRENCY = E("PRICE_CURRENCY", "USD")
PRICE_MONTHLY = int(E("PRICE_MONTHLY", "2000"))      # smallest currency unit: 2000 = $20.00
PRICE_YEARLY = int(E("PRICE_YEARLY", "20000"))       # 20000 = $200.00
PLANS = {"monthly": {"amount": PRICE_MONTHLY, "days": 30, "label": "Monthly"},
         "yearly": {"amount": PRICE_YEARLY, "days": 365, "label": "Yearly"}}

RAZORPAY_KEY_ID = E("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = E("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = E("RAZORPAY_WEBHOOK_SECRET", "")

COOKIE_SECURE = E("COOKIE_SECURE", "0") == "1"       # set to 1 when served over HTTPS
SESSION_DAYS = int(E("SESSION_DAYS", "30"))
# comma-separated emails that get free access forever (e.g. the owner / testers)
COMP_EMAILS = {x.strip().lower() for x in E("COMP_EMAILS", "").split(",") if x.strip()}


def public() -> dict:
    return {"appName": APP_NAME, "motto": MOTTO, "email": COMPANY_EMAIL, "entity": LEGAL_ENTITY, "trialDays": TRIAL_DAYS,
            "currency": PRICE_CURRENCY, "monthly": PRICE_MONTHLY, "yearly": PRICE_YEARLY, "termsVersion": TERMS_VERSION,
            "payments": bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)}
