"""End-to-end smoke test for a running CasuallyHedge server (used by the GitHub check on every push).

    python scripts/smoke_test.py http://127.0.0.1:8420

Signs up a throwaway account, logs in and out, saves and reloads private data, checks beta mode and the CSRF guard.
Needs no market-data access, so it never fails because Yahoo or an exchange is slow."""
import secrets
import sys

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8420").rstrip("/")
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        fails.append(name)


cfg = requests.get(BASE + "/api/config", timeout=20).json()
check("config answers and says beta", cfg.get("beta") is True, cfg)
check("login page loads", requests.get(BASE + "/login.html", timeout=20).status_code == 200)
check("app pages need a login", requests.get(BASE + "/app", timeout=20, allow_redirects=False).status_code == 303)
check("APIs need a login", requests.get(BASE + "/api/state", timeout=20).status_code == 401)

s = requests.Session()
email, pw = f"smoke-{secrets.token_hex(4)}@example.com", "Beta-test-" + secrets.token_hex(4) + "9"
r = s.post(BASE + "/api/auth/signup", json={"email": email, "password": pw, "name": "Smoke", "acceptTerms": True, "adult": True}, timeout=20)
check("sign-up works", r.status_code == 200, r.text[:200])
me = s.get(BASE + "/api/me", timeout=20).json()
check("new accounts are free during the beta", me.get("access", {}).get("state") == "beta", me.get("access"))

r = s.post(BASE + "/api/state", json={"watchlist": ["AAPL", "RELIANCE.NS"]}, timeout=20)
check("private data saves", r.status_code == 200, r.text[:200])
check("CSRF guard blocks form posts", s.post(BASE + "/api/state", data="watchlist=x", headers={"Content-Type": "application/x-www-form-urlencoded"},
                                             timeout=20).status_code == 415)
r = s.post(BASE + "/api/alerts", json={"interval": "daily", "hour": 8, "tz": 330, "emailOn": False}, timeout=20)
check("Daily Desk alert settings save", r.status_code == 200 and r.json()["alerts"]["interval"] == "daily", r.text[:200])

s.post(BASE + "/api/auth/logout", timeout=20)
check("logout ends the session", s.get(BASE + "/api/state", timeout=20).status_code == 401)
r = s.post(BASE + "/api/auth/login", json={"email": email, "password": pw}, timeout=20)
check("login works", r.status_code == 200, r.text[:200])
st = s.get(BASE + "/api/state", timeout=20).json()
check("private data is still there after logging back in", st.get("watchlist") == ["AAPL", "RELIANCE.NS"], st.get("watchlist"))
other = requests.Session()
other.post(BASE + "/api/auth/signup", json={"email": "x" + email, "password": pw, "name": "Other", "acceptTerms": True, "adult": True}, timeout=20)
check("accounts can't see each other's data", other.get(BASE + "/api/state", timeout=20).json().get("watchlist") != ["AAPL", "RELIANCE.NS"])

print(f"\n{len(fails)} failed" if fails else "\nAll smoke checks passed")
sys.exit(1 if fails else 0)
