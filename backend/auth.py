"""Accounts & sessions.

- Passwords are hashed with scrypt (random 16-byte salt per user); plain passwords are never stored.
- Sessions are random 256-bit tokens in an HttpOnly, SameSite=Lax cookie; only their SHA-256 hash is stored.
- Login attempts are rate-limited per IP and per email.
- Every signup starts a free trial; access afterwards needs an active paid period (see billing.py).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Body, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from . import config, db, store

router = APIRouter()
COOKIE = "ch_session"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_attempts: dict[str, deque] = defaultdict(deque)


def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_pw(pw: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(got.hex(), h)
    except Exception:
        return False


def _limited(key: str, limit: int = 8, window: int = 600) -> bool:
    dq, now = _attempts[key], time.time()
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= limit:
        return True
    dq.append(now)
    return False


def _tok_hash(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


def new_session(resp: Response, user_id: int, ua: str = "") -> None:
    tok = secrets.token_urlsafe(32)
    now = int(time.time())
    db.execute("INSERT INTO sessions(token_hash, user_id, created, expires, ua) VALUES(?,?,?,?,?)",
               (_tok_hash(tok), user_id, now, now + config.SESSION_DAYS * 86400, ua[:200]))
    resp.set_cookie(COOKIE, tok, max_age=config.SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=config.COOKIE_SECURE, path="/")


def user_from_request(request: Request) -> dict | None:
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None
    s = db.q("SELECT user_id, expires FROM sessions WHERE token_hash=?", (_tok_hash(tok),), one=True)
    if not s or s["expires"] < time.time():
        return None
    u = db.q("SELECT * FROM users WHERE id=? AND disabled=0", (s["user_id"],), one=True)
    return u


def access(u: dict) -> dict:
    now = time.time()
    if u["email"].lower() in config.COMP_EMAILS:
        return {"active": True, "state": "comp", "trialDaysLeft": None, "paidUntil": None}
    if (u.get("paid_until") or 0) > now:
        return {"active": True, "state": "paid", "plan": u.get("plan"), "paidUntil": u["paid_until"], "daysLeft": int((u["paid_until"] - now) // 86400)}
    if u["trial_end"] > now:
        return {"active": True, "state": "trial", "trialDaysLeft": int((u["trial_end"] - now) // 86400) + 1, "trialEnd": u["trial_end"]}
    return {"active": False, "state": "expired", "trialEnd": u["trial_end"], "paidUntil": u.get("paid_until")}


def me_payload(u: dict) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u.get("name"), "created": u["created"], "access": access(u),
            "termsAccepted": u.get("terms_version") == config.TERMS_VERSION}


@router.post("/api/auth/signup")
def signup(request: Request, body: dict = Body(...)):
    email = (body.get("email") or "").strip().lower()
    pw = body.get("password") or ""
    name = (body.get("name") or "").strip()[:80]
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Please enter a valid email address.")
    if len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise HTTPException(400, "Password must be at least 8 characters and include a letter and a number.")
    if not body.get("acceptTerms"):
        raise HTTPException(400, "You must accept the Terms of Service, Privacy Policy and Risk Disclaimer.")
    if not body.get("adult"):
        raise HTTPException(400, "You must confirm you are at least 18 years old.")
    if _limited("signup:" + (request.client.host if request.client else "?"), limit=10, window=3600):
        raise HTTPException(429, "Too many sign-ups from this network. Try again later.")
    if db.q("SELECT id FROM users WHERE email=?", (email,), one=True):
        raise HTTPException(409, "An account with this email already exists. Log in instead.")
    now = int(time.time())
    first = not db.q("SELECT id FROM users LIMIT 1", one=True)
    uid = db.execute("INSERT INTO users(email, name, pw_hash, created, trial_end, terms_version, terms_accepted) VALUES(?,?,?,?,?,?,?)",
                     (email, name, hash_pw(pw), now, now + config.TRIAL_DAYS * 86400, config.TERMS_VERSION, now))
    # the very first account inherits the pre-website local data (settings, holdings…) if any exists
    legacy = store.PATH
    if first and legacy.exists():
        try:
            db.put_state(uid, json.loads(legacy.read_text("utf-8")))
        except Exception:
            pass
    resp = JSONResponse({"ok": True, "user": me_payload(db.q("SELECT * FROM users WHERE id=?", (uid,), one=True))})
    new_session(resp, uid, request.headers.get("user-agent", ""))
    return resp


@router.post("/api/auth/login")
def login(request: Request, body: dict = Body(...)):
    email = (body.get("email") or "").strip().lower()
    ip = request.client.host if request.client else "?"
    if _limited("login-ip:" + ip, limit=20) or _limited("login:" + email, limit=8):
        raise HTTPException(429, "Too many attempts. Please wait 10 minutes and try again.")
    u = db.q("SELECT * FROM users WHERE email=? AND disabled=0", (email,), one=True)
    if not u or not check_pw(body.get("password") or "", u["pw_hash"]):
        raise HTTPException(401, "Wrong email or password.")
    resp = JSONResponse({"ok": True, "user": me_payload(u)})
    new_session(resp, u["id"], request.headers.get("user-agent", ""))
    return resp


@router.post("/api/auth/logout")
def logout(request: Request):
    tok = request.cookies.get(COOKIE)
    if tok:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (_tok_hash(tok),))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@router.get("/api/me")
def me(request: Request):
    u = user_from_request(request)
    if not u:
        raise HTTPException(401, "Not logged in")
    return me_payload(u)


@router.post("/api/me/accept-terms")
def accept_terms(request: Request):
    u = user_from_request(request)
    if not u:
        raise HTTPException(401, "Not logged in")
    db.execute("UPDATE users SET terms_version=?, terms_accepted=? WHERE id=?", (config.TERMS_VERSION, int(time.time()), u["id"]))
    return {"ok": True}


@router.post("/api/me/password")
def change_password(request: Request, body: dict = Body(...)):
    u = user_from_request(request)
    if not u:
        raise HTTPException(401, "Not logged in")
    if not check_pw(body.get("current") or "", u["pw_hash"]):
        raise HTTPException(401, "Current password is wrong.")
    new = body.get("new") or ""
    if len(new) < 8 or not re.search(r"[A-Za-z]", new) or not re.search(r"\d", new):
        raise HTTPException(400, "New password must be at least 8 characters with a letter and a number.")
    db.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(new), u["id"]))
    db.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))       # log out everywhere else
    resp = JSONResponse({"ok": True})
    new_session(resp, u["id"], request.headers.get("user-agent", ""))
    return resp


@router.get("/api/me/export")
def export(request: Request):
    u = user_from_request(request)
    if not u:
        raise HTTPException(401, "Not logged in")
    pays = db.q("SELECT order_id, payment_id, plan, amount, currency, status, created, paid_at FROM payments WHERE user_id=?", (u["id"],))
    data = {"account": {k: u[k] for k in ("email", "name", "created", "trial_end", "paid_until", "plan")}, "state": db.get_state(u["id"]), "payments": pays}
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="casuallyhedge-my-data.json"'})


@router.post("/api/me/delete")
def delete_account(request: Request, body: dict = Body(...)):
    u = user_from_request(request)
    if not u:
        raise HTTPException(401, "Not logged in")
    if not check_pw(body.get("password") or "", u["pw_hash"]):
        raise HTTPException(401, "Password is wrong.")
    db.execute("DELETE FROM users WHERE id=?", (u["id"],))               # cascades to sessions and saved state
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp
