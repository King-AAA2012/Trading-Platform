"""Subscriptions via Razorpay (Orders API + Checkout).

Flow: the browser asks us to create an order for the chosen plan -> Razorpay Checkout collects the payment ->
we verify Razorpay's HMAC signature server-side -> the user's paid period is extended by 30 or 365 days, starting
from whichever is later: now, the end of the free trial, or the end of the current paid period.
A webhook (payment.captured / order.paid) makes this reliable even if the browser closes mid-payment.
Keys come from the environment (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET / RAZORPAY_WEBHOOK_SECRET); never hard-code them.
Renewal is manual (pay again for the next period); Razorpay Subscriptions can be added later for auto-debit.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import requests
from fastapi import APIRouter, Body, HTTPException, Request

from . import auth, config, db

router = APIRouter()
API = "https://api.razorpay.com/v1"


def _configured():
    if not (config.RAZORPAY_KEY_ID and config.RAZORPAY_KEY_SECRET):
        raise HTTPException(503, f"Payments aren't set up yet. Please contact {config.COMPANY_EMAIL}.")


def _grant(order_id: str, payment_id: str | None) -> None:
    """Idempotently mark an order paid and extend the user's access."""
    p = db.q("SELECT * FROM payments WHERE order_id=?", (order_id,), one=True)
    if not p or p["status"] == "paid":
        return
    u = db.q("SELECT * FROM users WHERE id=?", (p["user_id"],), one=True)
    if not u:
        return
    now = int(time.time())
    start = max(now, u["trial_end"], u.get("paid_until") or 0)
    until = start + config.PLANS[p["plan"]]["days"] * 86400
    db.execute("UPDATE payments SET status='paid', payment_id=?, paid_at=? WHERE order_id=?", (payment_id, now, order_id))
    db.execute("UPDATE users SET paid_until=?, plan=? WHERE id=?", (until, p["plan"], u["id"]))


@router.get("/api/billing/status")
def status(request: Request):
    u = auth.user_from_request(request)
    if not u:
        raise HTTPException(401, "Not logged in")
    pays = db.q("SELECT order_id, payment_id, plan, amount, currency, status, created, paid_at FROM payments WHERE user_id=? ORDER BY created DESC LIMIT 50", (u["id"],))
    return {"access": auth.access(u), "plans": config.PLANS, "currency": config.PRICE_CURRENCY, "payments": pays,
            "keyId": config.RAZORPAY_KEY_ID or None, "configured": bool(config.RAZORPAY_KEY_ID and config.RAZORPAY_KEY_SECRET)}


@router.post("/api/billing/order")
def create_order(request: Request, body: dict = Body(...)):
    u = auth.user_from_request(request)
    if not u:
        raise HTTPException(401, "Not logged in")
    plan = body.get("plan")
    if plan not in config.PLANS:
        raise HTTPException(400, "Unknown plan")
    _configured()
    amount = config.PLANS[plan]["amount"]
    r = requests.post(f"{API}/orders", auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET), timeout=20,
                      json={"amount": amount, "currency": config.PRICE_CURRENCY, "receipt": f"u{u['id']}-{int(time.time())}",
                            "notes": {"user_id": str(u["id"]), "plan": plan, "email": u["email"]}})
    if r.status_code >= 300:
        raise HTTPException(502, f"Payment provider error: {r.json().get('error', {}).get('description', r.text[:200])}")
    o = r.json()
    db.execute("INSERT INTO payments(user_id, order_id, plan, amount, currency, status, created) VALUES(?,?,?,?,?,?,?)",
               (u["id"], o["id"], plan, amount, config.PRICE_CURRENCY, "created", int(time.time())))
    return {"orderId": o["id"], "amount": amount, "currency": config.PRICE_CURRENCY, "keyId": config.RAZORPAY_KEY_ID,
            "name": config.APP_NAME, "description": f"{config.PLANS[plan]['label']} subscription", "email": u["email"], "userName": u.get("name") or ""}


@router.post("/api/billing/verify")
def verify(request: Request, body: dict = Body(...)):
    u = auth.user_from_request(request)
    if not u:
        raise HTTPException(401, "Not logged in")
    _configured()
    oid, pid, sig = body.get("razorpay_order_id"), body.get("razorpay_payment_id"), body.get("razorpay_signature")
    p = db.q("SELECT * FROM payments WHERE order_id=? AND user_id=?", (oid, u["id"]), one=True)
    if not p:
        raise HTTPException(404, "Order not found")
    expected = hmac.new(config.RAZORPAY_KEY_SECRET.encode(), f"{oid}|{pid}".encode(), hashlib.sha256).hexdigest()
    if not sig or not hmac.compare_digest(expected, sig):
        raise HTTPException(400, "Payment signature check failed. If you were charged, contact support.")
    _grant(oid, pid)
    return {"ok": True, "access": auth.access(db.q("SELECT * FROM users WHERE id=?", (u["id"],), one=True))}


@router.post("/api/billing/webhook")
async def webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")
    if not config.RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(503, "Webhook secret not configured")
    expected = hmac.new(config.RAZORPAY_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(400, "Bad signature")
    ev = json.loads(raw)
    if ev.get("event") in ("payment.captured", "order.paid"):
        pay = ev.get("payload", {}).get("payment", {}).get("entity", {})
        oid = pay.get("order_id") or ev.get("payload", {}).get("order", {}).get("entity", {}).get("id")
        if oid:
            _grant(oid, pay.get("id"))
    return {"ok": True}
