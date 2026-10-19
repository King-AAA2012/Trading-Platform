"""Your own Daily Desk: the Portfolio list, "Update now", your update interval and email digests.

- Portfolio: the companies the desk follows for you = holdings + watchlists (each can be switched off) + companies added on
  the Portfolio tab, minus ones removed there (removing a holding there only stops the desk tracking it).
- Interval: your companies refresh as soon as something is filed (checked hourly), hourly, every 3 / 6 hours, twice a day,
  daily or weekly, on top of the standard 09:01 / 20:01 IST runs. Each refresh puts anything new in your inbox and, if email
  is on, sends a digest of the topics you picked.
- Update now: refreshes your companies straight away, re-runs the morning futures jobs if they're stale, and emails a digest.
- Whoever triggers a refresh, anything new is delivered to everyone who tracks that company.
- On the public site an email address must be confirmed with a code before anything is sent to it, and every email has a
  one-click unsubscribe link. Private mode (your own computer) skips the code.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re
import secrets
import threading
import time

from . import config, data, db, desk, intl

INTERVALS = {"instant": "As soon as something new is filed", "1h": "Every hour", "3h": "Every 3 hours", "6h": "Every 6 hours",
             "12h": "Twice a day", "daily": "Once a day", "weekly": "Once a week"}
HOURS = {"instant": 1, "1h": 1, "3h": 3, "6h": 6}
KINDS = {"result": "📊 New results (with AI summaries)", "concall": "📞 Earnings-call dates, times & dial-ins", "transcript": "📝 Call transcripts & recordings",
         "dividend": "💰 Dividends declared", "calendar": "📅 New board-meeting & earnings dates", "upcoming": "🗓 Coming up in the next 14 days",
         "roll": "⛽ NSE futures roll cost", "groll": "🌍 Global futures roll cost", "prices": "💹 Price snapshot of every company"}
DEFAULT = {"interval": "daily", "hour": 8, "weekday": 0, "tz": 330, "email": "", "emailOn": False, "verified": False,
           "kinds": ["result", "concall", "transcript", "dividend", "calendar", "upcoming", "roll", "groll"], "skipEmpty": True}
INDEX = desk.DIR / "alerts_index.json"               # who is due when: {user key: {"next": ts}}
CODES = desk.DIR / "email_codes.json"                # pending confirmation codes, server-side only (never in a user's own state)
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,253}\.[a-z]{2,24}$", re.I)
SYMBOL_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.^=&\-]{0,24}$")
_jobs: dict[str, dict] = {}                           # per user: {"running", "started", "finished", "result", "error"}
_queue: list[tuple] = []
_qlock = threading.Lock()
_worker: list = [None]


def _key(uid) -> str:
    return "_private" if uid is None else str(uid)


def _uid(key: str):
    return None if key == "_private" else int(key)


def cfg_of(st: dict) -> dict:
    a = {**DEFAULT, **(st.get("deskAlerts") or {})}
    if config.PRIVATE and not a["email"]:
        a["email"] = config.E("NOTIFY_EMAIL", "")
    return a


def next_due(a: dict, now: float | None = None) -> float:
    now = now or time.time()
    iv = a.get("interval", "daily")
    off = int(a.get("tz", 330)) * 60
    if iv in HOURS:                                   # on the hour in the user's time zone
        h = HOURS[iv] * 3600
        return ((now + off) // h + 1) * h - off
    tz = dt.timezone(dt.timedelta(seconds=off))
    loc = dt.datetime.fromtimestamp(now, tz)
    hours = sorted({int(a.get("hour", 8)) % 24, (int(a.get("hour", 8)) + 12) % 24} if iv == "12h" else {int(a.get("hour", 8)) % 24})
    for d in range(9):
        day = (loc + dt.timedelta(days=d)).date()
        if iv == "weekly" and day.weekday() != int(a.get("weekday", 0)) % 7:
            continue
        for hh in hours:
            t = dt.datetime(day.year, day.month, day.day, hh, tzinfo=tz).timestamp()
            if t > now + 30:
                return t
    return now + 86400


def _index_set(uid, nxt: float | None):
    with desk._lock:
        idx = desk._load(INDEX, {})
        if nxt:
            idx[_key(uid)] = {"next": nxt}
        else:
            idx.pop(_key(uid), None)
        desk._save(INDEX, idx)


def rebuild_index():
    """On start-up: make sure everyone who set an interval is on the schedule (catches up missed ones)."""
    with desk._lock:
        idx = desk._load(INDEX, {})
    for uid in desk._users():
        st = desk.read_state(uid)
        if st.get("deskAlerts") and _key(uid) not in idx:
            _index_set(uid, next_due(cfg_of(st)))


# ================================================================ running updates (one at a time, Update now first)
def start(uid, force: bool = False) -> dict:
    k = _key(uid)
    j = _jobs.get(k) or {}
    if j.get("running"):
        return {"started": False, "reason": "An update is already running."}
    if force and time.time() - (j.get("finished") or 0) < (15 if config.PRIVATE else 60):
        return {"started": False, "reason": "You just updated. Try again in a minute."}
    _jobs[k] = {**j, "running": True, "started": time.time(), "force": force}
    with _qlock:
        if force:
            _queue.insert(0, (uid, force))
        else:
            _queue.append((uid, force))
        if not (_worker[0] and _worker[0].is_alive()):
            _worker[0] = threading.Thread(target=_work, daemon=True, name="desk-user-updates")
            _worker[0].start()
    return {"started": True}


def _work():
    while True:
        with _qlock:
            if not _queue:
                _worker[0] = None
                return
            uid, force = _queue.pop(0)
        k = _key(uid)
        try:
            res = update_user(uid, force)
            _jobs[k] = {"running": False, "started": _jobs.get(k, {}).get("started"), "finished": time.time(), "result": res}
        except Exception as e:
            _jobs[k] = {"running": False, "started": _jobs.get(k, {}).get("started"), "finished": time.time(), "error": str(e)[:300]}


def tick():
    """Called by the desk scheduler every 30 s: start the updates that are due."""
    now = time.time()
    with desk._lock:
        idx = desk._load(INDEX, {})
        due = [k for k, v in idx.items() if v.get("next") and v["next"] <= now and not (_jobs.get(k) or {}).get("running")]
        for k in due:
            idx[k]["next"] = now + 900                # provisional; the update sets the real next time when it finishes
        if due:
            desk._save(INDEX, idx)
    for k in due:
        start(_uid(k), force=False)


def update_user(uid, force: bool = False) -> dict:
    t0 = time.time()
    st = desk.read_state(uid)
    a = cfg_of(st)
    syms = desk.tracked_symbols(st)[:400]
    if force:                                         # stale morning futures data? fetch the latest settlements too
        jobs = desk._load(desk.JOBS, {})
        for job in ("roll", "groll"):
            if time.time() - ((jobs.get(job) or {}).get("last") or 0) > 3 * 3600:
                desk.run_job(job, background=False)
    items, errors, n = desk.refresh_companies(syms, budget=desk._Budget(6), max_age=300 if force else 1500)
    fresh = [i for i in items if i.get("fresh")]
    if fresh:
        desk._deliver_calendar(fresh, desk._tracked_by_user(), False, n)
    mine = [i for i in fresh if i["symbol"] in syms]
    emailed = None
    if a["emailOn"] and a["verified"] and a["email"] and (force or a["interval"] != "instant"):
        emailed = send_digest(uid, force=force)
    nxt = next_due(a) if st.get("deskAlerts") else None
    if nxt:
        _index_set(uid, nxt)
    return {"companies": len(syms), "refreshed": n, "new": len(mine), "emailed": emailed, "errors": errors[:5], "took": round(time.time() - t0, 1), "next": nxt}


# ================================================================ email digest
def _nse_line(x: dict) -> str:
    return (f"| **{x['symbol']}** | {x['near']['close']:,.2f} → {x['next']['close']:,.2f} | {x['rollPts']:+,.2f} | {x['rollPct']:+.2f}% | "
            f"{x['rollAnn']:+.1f}% | ₹{x['rollPerLot']:+,.0f} | {x['rollover'] if x['rollover'] is not None else '–'}% |")


def _when(ts: float, a: dict) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone(dt.timedelta(minutes=int(a.get("tz", 330))))).strftime("%d %b %Y, %I:%M %p")


def upcoming(syms: list[str], corp: dict, days: int = 14) -> list[dict]:
    today = desk.now_ist().date()
    end = (today + dt.timedelta(days=days)).isoformat()
    ev = []
    for s in syms:
        c = corp.get(s) or {}
        nm = c.get("name") or s
        for e in c.get("events") or []:
            ev.append({"date": e["date"], "symbol": s, "name": nm, "what": e.get("purpose") or "", "desc": e.get("desc") or ""})
        for x in c.get("concalls") or []:
            if x.get("status") == "upcoming" and (x.get("time") or x.get("dialIn") or x.get("links")):
                ev.append({"date": x["date"], "symbol": s, "name": nm, "what": "Earnings call" + (f" {x['time']}" if x.get("time") else ""),
                           "desc": ", ".join(x.get("dialIn") or []) or ", ".join(x.get("links") or [])})
        for d in c.get("dividends") or []:
            if d.get("exDate") and d["exDate"] >= today.isoformat():
                ev.append({"date": d["exDate"], "symbol": s, "name": nm, "what": "Ex-dividend", "desc": d.get("subject") or ""})
    seen, out = set(), []
    for e in sorted(ev, key=lambda e: e["date"]):
        k = (e["date"], e["symbol"], e["what"][:12])
        if today.isoformat() <= e["date"] <= end and k not in seen:
            seen.add(k)
            out.append(e)
    return out


def build_digest(st: dict, a: dict, force: bool) -> tuple[str | None, str, dict]:
    kinds = set(a["kinds"])
    since = a.get("lastSent") or time.time() - 86400
    syms = desk.tracked_symbols(st)
    corp = desk._load(desk.CORP, {})
    parts, marks, news, roll_news = [], {}, [], False
    for m in st.get("inbox") or []:
        if m.get("t", 0) > since and m.get("job") == "calendar":
            news += [it for it in m.get("items") or [] if it.get("kind") in kinds or (it.get("kind") == "recording" and "transcript" in kinds)]
    if news:
        parts.append(f"## What's new since {_when(since, a)}")
        for k in desk.KIND_ORDER:
            grp = [i for i in news if i["kind"] == k]
            if grp:
                parts.append(f"### {desk.KIND_HEAD[k]}")
                for i in grp:
                    parts.append(f"**{i['title']}**" + (f" · [filing]({i['link']})" if i.get("link") else "") + (" · *AI summary, verify in the filing*" if i.get("ai") else ""))
                    if i.get("body"):
                        parts.append(i["body"])
                    parts.append("")
    if "roll" in kinds:
        R = desk._load(desk.ROLL, {})
        if R.get("rows") and (force or R.get("session") != a.get("rollSession")):
            by = {r["symbol"]: r for r in R["rows"]}
            rows = [by[n] for n in dict.fromkeys(sorted({desk._nse_symbol(s) for s in syms} - {None}) + ["NIFTY", "BANKNIFTY"]) if n in by]
            if rows:
                parts.append(f"## ⛽ NSE futures roll cost · {R['session']} close\n| Contract | Near → Next | Roll pts | Roll % | Annualised | Per lot | Rollover |\n|---|---|---|---|---|---|---|")
                parts += [_nse_line(x) for x in rows]
                parts.append("")
            roll_news |= R.get("session") != a.get("rollSession")
            marks["rollSession"] = R.get("session")
    if "groll" in kinds:
        G = desk._load(desk.GROLL, {})
        sig = " · ".join(f"{k.split(' (')[0]} {v}" for k, v in sorted((G.get("sessions") or {}).items()))
        if G.get("rows") and (force or sig != a.get("grollSessions")):
            by = {r["id"]: r for r in G["rows"]}
            ids = list(dict.fromkeys(i for s in syms for i in intl.futures_for(s) if i in by)) or [i for i in intl.BENCHMARKS[:6] if i in by]
            parts.append(f"## 🌍 Global futures roll cost · {sig}\n| Contract | Exchange | Near → Next | Roll | Roll % | Annualised | Per contract | Rollover | Near expires in |\n"
                         "|---|---|---|---|---|---|---|---|---|")
            parts += [desk._gline(by[i]) for i in ids]
            parts.append("")
            roll_news |= sig != a.get("grollSessions")
            marks["grollSessions"] = sig
    if "upcoming" in kinds:
        ev = upcoming(syms, corp)
        if ev:
            parts.append("## 🗓 Coming up in the next 14 days\n| Date | Company | What |\n|---|---|---|")
            parts += [f"| {e['date']} | **{e['symbol']}** {e['name'][:40]} | {e['what']}{(' — ' + e['desc'][:80]) if e['desc'] else ''} |" for e in ev[:40]]
            parts.append("")
    if "prices" in kinds and syms:
        q = {}
        for i in range(0, len(syms), 50):
            for x in data.quotes(syms[i:i + 50]):
                q[x["symbol"]] = x
        rows = [q[s] for s in syms if s in q]
        if rows:
            parts.append("## 💹 Prices\n| Company | Price | Day |\n|---|---|---|")
            parts += [f"| **{x['symbol']}** {x['name'][:36]} | {x['price']:,.2f} {x['currency']} | {x['changePct']:+.2f}% |" for x in rows]
            parts.append("")
    if not news and not roll_news and a["skipEmpty"] and not force:
        return None, "", marks
    label = INTERVALS[a["interval"]].lower()
    head = f"Your Daily Desk update for **{len(syms)} companies** · {_when(time.time(), a)}"
    if not news:
        head += f"\n\nNothing new has been filed for your companies since {_when(since, a)}."
    subject = (f"{config.APP_NAME}: {len(news)} new update{'s' if len(news) != 1 else ''} for your companies" if news
               else f"{config.APP_NAME}: your Daily Desk update ({label})")
    return head + "\n\n" + "\n".join(parts), subject, marks


def _footer(uid, a: dict) -> str:
    if config.PRIVATE or not a.get("unsub"):
        return ""
    return f" <a href='{config.SITE_URL}/api/alerts/unsubscribe?u={_key(uid)}&t={a['unsub']}' style='color:#6b7385'>Unsubscribe</a>"


def send_digest(uid, force: bool = False) -> str:
    if not desk.email_ready():
        return "not set up"
    st = desk.read_state(uid)
    a = cfg_of(st)
    if not a["email"]:
        return "no email address"
    md, subject, marks = build_digest(st, a, force)
    if not md:
        return "skipped (nothing new)"
    if not desk.send_email(a["email"], subject, md, footer=_footer(uid, a)):
        return "failed"

    def mark(s):
        s.setdefault("deskAlerts", {}).update({**marks, "lastSent": time.time()})
    desk._with_state(uid, mark)
    return "sent"


def on_message(uid, st: dict, msg: dict):
    """A new inbox message: email it right away for users on "as soon as something new is filed"."""
    a = cfg_of(st)
    if a["emailOn"] and a["verified"] and a["email"] and a["interval"] == "instant" and desk.email_ready():
        kinds = set(a["kinds"])
        mk = {msg["job"]} if msg["job"] in ("roll", "groll") else {i.get("kind") for i in msg.get("items") or []}
        if "recording" in mk:
            mk.add("transcript")
        if mk & kinds:
            threading.Thread(target=desk.send_email, args=(a["email"], f"{config.APP_NAME}: {msg['title']}", msg["body"], _footer(uid, a)), daemon=True).start()
    elif st.get("profile", {}).get("notifyEmail") and not st.get("deskAlerts") and desk.email_ready():     # the older "email every message" switch
        to = config.E("NOTIFY_EMAIL", "") if uid is None else (db.q("SELECT email FROM users WHERE id=?", (uid,), one=True) or {}).get("email")
        if to:
            threading.Thread(target=desk.send_email, args=(to, f"{config.APP_NAME}: {msg['title']}", msg["body"]), daemon=True).start()


# ================================================================ settings, confirmation code, unsubscribe
def save_settings(st: dict, uid, body: dict) -> dict:
    a = cfg_of(st)
    if body.get("interval") in INTERVALS:
        a["interval"] = body["interval"]
    for k, mod in (("hour", 24), ("weekday", 7)):
        if k in body:
            a[k] = int(body[k]) % mod
    if "tz" in body:
        a["tz"] = max(-720, min(840, int(body["tz"])))
    if isinstance(body.get("kinds"), list):
        a["kinds"] = [k for k in body["kinds"] if k in KINDS]
    for k in ("skipEmpty", "emailOn"):
        if k in body:
            a[k] = bool(body[k])
    if "email" in body:
        email = (body.get("email") or "").strip()
        if email and not EMAIL_RE.match(email):
            raise ValueError("That email address doesn't look right.")
        if email.lower() != (st.get("deskAlerts") or {}).get("email", "").lower() or not (st.get("deskAlerts") or {}).get("email"):
            a["verified"] = False
            _code_del(uid)
        a["email"] = email
    if a["emailOn"] and not a["email"]:
        raise ValueError("Enter the email address to send your updates to.")
    out = {"ok": True}
    if a["email"] and not a["verified"]:
        if config.PRIVATE:
            a["verified"] = True                      # your own computer: no confirmation needed
        elif body.get("resend") or (a["emailOn"] and not _code_get(uid)):
            out.update(_send_code(a, uid))
        else:
            out["needsCode"] = bool(_code_get(uid))
    a.setdefault("unsub", secrets.token_urlsafe(16))
    st["deskAlerts"] = a
    _index_set(uid, next_due(a))
    return out


def _code_get(uid) -> dict | None:
    rec = desk._load(CODES, {}).get(_key(uid))
    return rec if rec and rec["exp"] > time.time() else None


def _code_put(uid, rec: dict | None):
    with desk._lock:
        codes = {k: v for k, v in desk._load(CODES, {}).items() if v.get("exp", 0) > time.time()}
        if rec:
            codes[_key(uid)] = rec
        else:
            codes.pop(_key(uid), None)
        desk._save(CODES, codes)


def _code_del(uid):
    _code_put(uid, None)


def _send_code(a: dict, uid) -> dict:
    if not desk.email_ready():
        return {"warning": "Email isn't set up on this server yet, so the address can't be confirmed. Your inbox still updates."}
    log = [t for t in a.get("codeLog") or [] if time.time() - t < 86400]
    if len(log) >= 5:
        return {"needsCode": True, "warning": "Too many codes today. Use the last one you got, or try again tomorrow."}
    code, salt = f"{secrets.randbelow(10 ** 6):06d}", secrets.token_hex(8)
    _code_put(uid, {"hash": hashlib.sha256((salt + code).encode()).hexdigest(), "salt": salt, "exp": time.time() + 1800, "tries": 0, "email": a["email"]})
    a["codeLog"] = log + [time.time()]
    ok = desk.send_email(a["email"], f"{config.APP_NAME} confirmation code: {code}",
                         f"Your confirmation code is **{code}**.\n\nEnter it on the Daily Desk page to start getting your updates at this address. "
                         "It expires in 30 minutes. If you didn't ask for this, you can ignore this email.")
    return {"needsCode": True, "sent": ok, **({} if ok else {"warning": "The code email couldn't be sent. Check the server's email settings."})}


def verify(st: dict, uid, code: str) -> bool:
    a = cfg_of(st)
    p = _code_get(uid)
    st["deskAlerts"] = a
    if not p or p.get("email", "").lower() != (a.get("email") or "").lower():
        _code_del(uid)
        raise ValueError("That code has expired. Press “Send a new code”.")
    p["tries"] += 1
    if p["tries"] > 5:
        _code_del(uid)
        raise ValueError("Too many wrong tries. Press “Send a new code”.")
    if not hmac.compare_digest(p["hash"], hashlib.sha256((p["salt"] + re.sub(r"\D", "", str(code))).encode()).hexdigest()):
        _code_put(uid, p)
        return False
    a["verified"] = True
    _code_del(uid)
    return True


def unsubscribe(key: str, token: str) -> bool:
    try:
        uid = _uid(key)
    except ValueError:
        return False
    if uid is None or not token:
        return False
    done = []

    def off(st):
        a = st.get("deskAlerts") or {}
        if a.get("unsub") and hmac.compare_digest(a["unsub"], token):
            a["emailOn"] = False
            done.append(True)
    if not db.q("SELECT id FROM users WHERE id=?", (uid,), one=True):
        return False
    desk._with_state(uid, off)
    return bool(done)


def public(st: dict, uid) -> dict:
    a = cfg_of(st)
    k = _key(uid)
    j = _jobs.get(k) or {}
    acct = None
    if uid is not None:
        acct = (db.q("SELECT email FROM users WHERE id=?", (uid,), one=True) or {}).get("email")
    return {"configured": bool(st.get("deskAlerts")), **{x: a[x] for x in ("interval", "hour", "weekday", "tz", "email", "emailOn", "verified", "kinds", "skipEmpty")},
            "lastSent": a.get("lastSent"), "pendingCode": bool(_code_get(uid)), "next": (desk._load(INDEX, {}).get(k) or {}).get("next"),
            "job": {x: j.get(x) for x in ("running", "started", "finished", "result", "error")}, "emailReady": desk.email_ready(),
            "private": config.PRIVATE, "accountEmail": acct, "intervals": INTERVALS, "kindLabels": KINDS, "tracked": len(desk.tracked_symbols(st))}


# ================================================================ Portfolio tab
def portfolio(st: dict) -> dict:
    d = st.get("desk") or {}
    hold = {h["symbol"] for h in st.get("holdings", []) if h.get("symbol")}
    wl = set(st.get("watchlist") or [])
    lists: dict[str, list] = {}
    for name, lst in (st.get("watchlists") or {}).items():
        for s in lst:
            lists.setdefault(s, []).append(name)
    added, removed = set(d.get("added") or []), set(d.get("removed") or [])
    tracked = desk.tracked_symbols(st)
    corp = desk._load(desk.CORP, {})
    q = {}
    for i in range(0, len(tracked), 50):
        for x in data.quotes(tracked[i:i + 50]):
            q[x["symbol"]] = x
    ev = {}
    for e in upcoming(tracked, corp, days=120):
        ev.setdefault(e["symbol"], e)
    rows = []
    for s in tracked:
        c, x = corp.get(s) or {}, q.get(s) or {}
        res = (c.get("results") or [None])[0]
        nse = desk._nse_symbol(s)
        filings = bool(nse and nse not in desk.INDEX_MAP.values()) or bool(not nse and intl.filing_source(s))
        rows.append({"symbol": s, "name": c.get("name") or x.get("name") or s, "market": c.get("market") or (None if filings else "Prices & futures only (no company filings)"),
                     "filings": filings, "price": x.get("price"), "changePct": x.get("changePct"),
                     "currency": x.get("currency"), "sources": (["Holding"] if s in hold else []) + (["Watchlist"] if s in wl else []) + lists.get(s, [])
                     + (["Added here"] if s in added else []), "next": ev.get(s), "lastResult": {"date": res["date"], "source": res.get("source")} if res else None,
                     "futures": intl.futures_for(s), "updated": c.get("updated")})
    return {"rows": rows, "excluded": sorted(removed), "holdings": d.get("holdings", True), "watchlists": d.get("watchlists", True),
            "counts": {"holdings": len(hold), "watchlists": len(wl | set(lists))}}


def portfolio_edit(st: dict, body: dict) -> str | None:
    """Returns a symbol that was just added (so it can be loaded straight away)."""
    d = st.setdefault("desk", {})
    added, removed = list(d.get("added") or []), set(d.get("removed") or [])
    new = None
    for k in ("holdings", "watchlists"):
        if k in body:
            d[k] = bool(body[k])
    if body.get("add"):
        sym = str(body["add"]).strip().upper()
        if not SYMBOL_RE.match(sym):
            raise ValueError("That doesn't look like a ticker. Pick one from the suggestions.")
        if len(added) >= 300:
            raise ValueError("You can add up to 300 companies here.")
        removed.discard(sym)
        if sym not in added:
            added.append(sym)
        new = sym
    for sym in [body.get("remove")] if body.get("remove") else []:
        sym = str(sym).upper()
        if sym in added:
            added.remove(sym)
        d["added"], d["removed"] = added, sorted(removed)
        if sym in desk.tracked_symbols(st):           # still followed through holdings / watchlists: stop the desk tracking it
            removed.add(sym)
    if body.get("restore"):
        removed.discard(str(body["restore"]).upper())
    d["added"], d["removed"] = added, sorted(removed)
    return new


def quiet_load(sym: str):
    """Load a newly added company's history in the background (no messages) so its tabs fill in within seconds."""
    threading.Thread(target=desk.refresh_companies, args=([sym],), kwargs={"budget": desk._Budget(0)}, daemon=True).start()
