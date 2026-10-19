"""Daily desk: scheduled jobs + per-user inbox.

Jobs (times in IST, UTC+5:30):
  roll      09:01 daily        NSE futures roll cost from the previous trading session's official F&O bhavcopy (close prices),
                               before the 09:15 open: near->next roll spread (pts, %, annualised, per lot), cost of carry, rollover %.
  groll     09:01 daily        The same for international futures from each exchange's previous-session settlement: US (CME, CBOT,
                               NYMEX, COMEX, ICE US), Japan (JPX), Singapore (SGX) and Hong Kong (HKEX). See intl.py.
  calendar  09:01 and 20:01    For every stock users track (holdings + watchlists), all markets:
                               (A) summarise results declared since the last run   (B) record upcoming concall dates & dial-ins
                               (C) add concall transcripts once posted              (D) refresh every tracked company
                               (E) keep the dividend tracker current
                               Indian stocks use NSE filings (announcements, corporate actions, event calendar). US listings use
                               SEC EDGAR 8-K results releases, foreign companies with a US listing their 6-K filings, Hong Kong
                               HKEXnews and Australia ASX announcements, all on top of Yahoo (EPS vs estimates, earnings dates,
                               dividends). Each run looks at what appeared since the previous run and messages users only about
                               what is new; a newly tracked company loads its history quietly.
A missed slot (PC asleep, server off) runs as soon as the server is back. Company data is shared (data/desk/corp.json);
inbox messages are per user (inside each user's private state).
"""
from __future__ import annotations

import copy
import csv
import datetime as dt
import hashlib
import io
import json
import re
import smtplib
import ssl
import threading
import time
import uuid
import zipfile
from email.mime.text import MIMEText

import logging

import requests

from . import ai, config, data, db, intl, store

logging.getLogger("pypdf").setLevel(logging.ERROR)          # malformed exchange PDFs are common; don't spam the console

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
DIR = data.DATA_DIR / "desk"
DIR.mkdir(exist_ok=True)
CORP, ROLL, GROLL, JOBS = DIR / "corp.json", DIR / "roll_cost.json", DIR / "roll_global.json", DIR / "jobs.json"
SCHEDULE = {"roll": [(9, 1)], "groll": [(9, 1)], "calendar": [(9, 1), (20, 1)]}
LABEL = {"roll": "NSE futures roll cost", "groll": "Global futures roll cost", "calendar": "Results, concalls & dividends"}
_lock = threading.RLock()
_running: set[str] = set()
_inflight: set[str] = set()                         # companies being refreshed right now (by the scheduled run or a user's update)
_nse = requests.Session()
_nse.headers.update({"User-Agent": data.UA, "Referer": "https://www.nseindia.com/", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"})
_last_call = [0.0]
INDEX_MAP = {"^NSEI": "NIFTY", "^NSEBANK": "BANKNIFTY", "^CNXFIN": "FINNIFTY", "NIFTY_MID_SELECT.NS": "MIDCPNIFTY"}


def _load(p, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return default


def _save(p, obj):
    with _lock:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, indent=1, default=str), "utf-8")
        tmp.replace(p)


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


def _nse_get(path: str, params: dict | None = None):
    for attempt in range(3):
        wait = 0.4 - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        try:
            r = _nse.get("https://www.nseindia.com" + path, params=params, timeout=25)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (401, 403):
                _nse.get("https://www.nseindia.com/", timeout=15)       # refresh cookies
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def _pdf_text(url: str, pages: int = 6, max_chars: int = 14000, force: bool = False) -> str:
    if not url or not (force or url.lower().endswith(".pdf")):
        return ""
    try:
        import pypdf
        r = (_nse if "nseindia.com" in url else intl._web).get(url, timeout=40)
        if r.status_code != 200 or len(r.content) > 25_000_000 or not r.content.startswith(b"%PDF"):
            return ""
        rd = pypdf.PdfReader(io.BytesIO(r.content))
        txt = "\n".join((p.extract_text() or "") for p in rd.pages[:pages])
        return re.sub(r"[ \t]+", " ", txt)[:max_chars]
    except Exception:
        return ""


# ---------------------------------------------------------------- AI helpers (local Ollama; everything has a non-AI fallback)
class _Budget:
    def __init__(self, n):
        self.n = n

    def take(self):
        if self.n <= 0:
            return False
        self.n -= 1
        return True


def _ai(prompt: str, as_json: bool = False):
    st = ai.status()
    if not st["online"]:
        return None
    try:
        r = requests.post(f"{ai.OLLAMA}/api/chat", timeout=240, json={
            "model": st["model"], "stream": False, "options": {"temperature": 0.1, "num_ctx": 8192},
            **({"format": "json"} if as_json else {}), "messages": [{"role": "user", "content": prompt}]})
        out = r.json()["message"]["content"]
        if as_json:
            return json.loads(out)
        out = out.strip()
        return re.sub(r"(?i)^(here (are|is)|below (are|is))[^\n]*\n+", "", out).strip()
    except Exception:
        return None


# ================================================================ JOB 1: NSE futures roll cost
def _bhavcopy(day: dt.date) -> str | None:
    url = f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
    try:
        r = _nse.get(url, timeout=40)
        if r.status_code == 200 and r.content[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(r.content))
            return z.read(z.namelist()[0]).decode("utf-8", "replace")
    except Exception:
        pass
    return None


def run_roll() -> dict:
    now = now_ist()
    txt, session = None, None
    for k in range(0, 12):                       # newest published session (at 09:01 that is the previous trading day)
        d = now.date() - dt.timedelta(days=k)
        if d.weekday() >= 5:
            continue
        txt = _bhavcopy(d)
        if txt:
            session = d
            break
    if not txt:
        raise RuntimeError("Couldn't download the NSE F&O bhavcopy for the last trading sessions.")
    futs: dict[str, list] = {}
    for r in csv.DictReader(io.StringIO(txt)):
        if r.get("FinInstrmTp") not in ("STF", "IDF"):
            continue
        try:
            close = float(r["ClsPric"] or 0) or float(r["SttlmPric"] or 0)
            futs.setdefault(r["TckrSymb"], []).append({
                "expiry": r["XpryDt"], "close": close, "settle": float(r["SttlmPric"] or 0), "oi": float(r["OpnIntrst"] or 0),
                "vol": float(r["TtlTradgVol"] or 0), "lot": int(float(r["NewBrdLotQty"] or 0)), "spot": float(r["UndrlygPric"] or 0),
                "index": r["FinInstrmTp"] == "IDF"})
        except (KeyError, ValueError):
            continue
    rows = []
    for sym, lst in futs.items():
        lst.sort(key=lambda x: x["expiry"])
        if len(lst) < 2 or not lst[0]["close"] or not lst[1]["close"]:
            continue
        near, nxt = lst[0], lst[1]
        dn = (dt.date.fromisoformat(near["expiry"]) - session).days
        dr = max((dt.date.fromisoformat(nxt["expiry"]) - dt.date.fromisoformat(near["expiry"])).days, 1)
        pts = nxt["close"] - near["close"]
        rp = pts / near["close"]
        spot = near["spot"] or near["close"]
        rows.append({
            "symbol": sym, "kind": "Index" if near["index"] else "Stock", "spot": round(spot, 2),
            "near": {"expiry": near["expiry"], "close": near["close"], "oi": near["oi"]}, "next": {"expiry": nxt["expiry"], "close": nxt["close"], "oi": nxt["oi"]},
            "far": {"expiry": lst[2]["expiry"], "close": lst[2]["close"]} if len(lst) > 2 else None,
            "daysNear": dn, "daysRoll": dr, "rollPts": round(pts, 2), "rollPct": round(rp * 100, 3), "rollAnn": round(rp * 365 / dr * 100, 2),
            "lot": near["lot"], "rollPerLot": round(pts * near["lot"], 0), "carryAnn": round((near["close"] - spot) / spot * 365 / max(dn, 1) * 100, 2) if spot else None,
            "rollover": round(nxt["oi"] / (near["oi"] + nxt["oi"]) * 100, 1) if near["oi"] + nxt["oi"] else None})
    rows.sort(key=lambda r: (r["kind"] != "Index", r["symbol"]))
    prev = _load(ROLL, {})
    hist = prev.get("history", {})
    hist[session.isoformat()] = {r["symbol"]: [r["rollAnn"], r["rollover"]] for r in rows}
    hist = dict(sorted(hist.items())[-40:])
    is_new = prev.get("session") != session.isoformat()
    out = {"session": session.isoformat(), "generated": time.time(), "rows": rows, "history": hist}
    _save(ROLL, out)
    if is_new:
        _deliver_roll(out)
    return {"session": session.isoformat(), "new": is_new, "count": len(rows)}


# ================================================================ JOB 1b: international futures roll cost
KIND_SORT = ["Index", "Rates", "FX", "Crypto", "Energy", "Metals", "Agri", "Softs", "Livestock"]
MARKET_SORT = ["US", "Japan", "Singapore", "Hong Kong"]


def run_groll() -> dict:
    rows, sessions, errors = [], {}, []
    for name, fn in intl.SOURCES.items():
        try:
            chains, sess = fn()
            got = [r for r in (intl.make_row(c) for c in chains) if r]
            for r in got:
                r["source"] = name
            if got:
                rows += got
                sessions[name] = sess
        except Exception as e:                       # one exchange being down must not stop the others
            errors.append(f"{name}: {e}")
    prev = _load(GROLL, {})
    for name in intl.SOURCES:                        # keep the last good prices for an exchange that failed this time
        if name not in sessions and (prev.get("sessions") or {}).get(name):
            rows += [r for r in prev.get("rows", []) if r.get("source") == name]
            sessions[name] = prev["sessions"][name]
    if not rows:
        raise RuntimeError("No international futures data: " + "; ".join(errors))
    rank = lambda r: (MARKET_SORT.index(r["market"]) if r["market"] in MARKET_SORT else 9, KIND_SORT.index(r["kind"]) if r["kind"] in KIND_SORT else 9, r["symbol"])  # noqa: E731
    rows.sort(key=rank)
    hist = prev.get("history", {})
    hist[now_ist().date().isoformat()] = {r["id"]: [r["rollAnn"], r["rollover"]] for r in rows}
    hist = dict(sorted(hist.items())[-40:])
    new = [n for n, s in sessions.items() if s and s != (prev.get("sessions") or {}).get(n)]
    out = {"sessions": sessions, "generated": time.time(), "rows": rows, "history": hist, "errors": errors}
    _save(GROLL, out)
    if new:
        _deliver_groll(out, new)
    return {"sessions": sessions, "new": [n.split(" (")[0] for n in new], "count": len(rows), "errors": errors[:5]}


def _gline(x: dict) -> str:
    d = x.get("decimals", 2)
    cur = intl.CUR_SIGN.get(x["currency"], x["currency"] + " ")
    per = f"{'-' if x['rollPerLot'] < 0 else '+'}{cur}{abs(x['rollPerLot']):,.0f}"
    ro = f"{x['rollover']:.0f}%" if x.get("rollover") is not None else "–"
    return (f"| **{x['symbol']}** {x['near']['month']}→{x['next']['month']} | {x['exchange']} | {x['near']['close']:,.{d}f} → {x['next']['close']:,.{d}f} | "
            f"{x['rollPts']:+,.{d}f} | {x['rollPct']:+.2f}% | {x['rollAnn']:+.1f}% | {per} | {ro} | {x['daysNear']}d |")


def _deliver_groll(r: dict, new: list[str]):
    by = {x["id"]: x for x in r["rows"]}
    head = "| Contract | Exchange | Near → Next | Roll | Roll % | Annualised | Per contract | Rollover | Near expires in |\n|---|---|---|---|---|---|---|---|---|"
    table = lambda xs: head + "\n" + "\n".join(_gline(x) for x in xs)  # noqa: E731
    bench = [by[i] for i in intl.BENCHMARKS if i in by]
    comm = [x for x in r["rows"] if x["kind"] in intl.COMMODITY and x.get("rollover") is not None]
    contango = sorted(comm, key=lambda x: -x["rollAnn"])[:3]
    backw = sorted(comm, key=lambda x: x["rollAnn"])[:3]
    sess = " · ".join(f"{n.split(' (')[0]} {s}" for n, s in r["sessions"].items())
    for uid, syms in _tracked_by_user().items():
        mine_ids = list(dict.fromkeys(i for s in sorted(syms) for i in intl.futures_for(s) if i in by))
        mine = [by[i] for i in mine_ids]
        window = [x for x in r["rows"] if x["daysNear"] <= 7 and (x["id"] in mine_ids or x["id"] in intl.BENCHMARKS or x["kind"] in intl.COMMODITY)][:10]
        body = (f"Each exchange's previous-session settlement prices ({sess}). Roll = next − near contract, annualised over the days between "
                "expiries; per contract = roll × contract size, in the contract's currency. For commodities a positive roll is contango "
                "(rolling a long costs money) and a negative roll is backwardation (it pays).\n\n")
        if mine:
            body += "### Futures linked to your holdings & watchlists\n" + table(mine) + "\n\n"
        body += "### Benchmarks\n" + table(bench) + "\n\n"
        if window:
            body += "### In the roll window (near contract expires within 7 days)\n" + table(window) + "\n\n"
        body += "### Steepest contango (commodities)\n" + table(contango) + "\n\n### Deepest backwardation (commodities)\n" + table(backw)
        rel = [s for s in sorted(syms) if any(i in by for i in intl.futures_for(s))]
        _push(uid, "groll", f"Global futures roll cost · {', '.join(n.split(' (')[0] for n in new)}" + (f" · {len(mine)} of yours" if mine else ""), body,
              [{"kind": "roll", "symbol": s, "title": f"{s} futures roll"} for s in rel])


def _nse_symbol(sym: str) -> str | None:
    if sym in INDEX_MAP:
        return INDEX_MAP[sym]
    if sym.endswith(".NS"):
        return sym[:-3]
    if sym.endswith(".BO") and not sym[:-3].isdigit():
        return sym[:-3]
    return None


def _deliver_roll(r: dict):
    by = {x["symbol"]: x for x in r["rows"]}
    stocks = [x for x in r["rows"] if x["kind"] == "Stock" and x["rollAnn"] is not None]
    hi = sorted(stocks, key=lambda x: -x["rollAnn"])[:3]
    lo = sorted(stocks, key=lambda x: x["rollAnn"])[:3]
    idx = [by[s] for s in ("NIFTY", "BANKNIFTY", "FINNIFTY") if s in by]
    line = lambda x: (f"| **{x['symbol']}** | {x['near']['close']:,.2f} → {x['next']['close']:,.2f} | {x['rollPts']:+,.2f} | {x['rollPct']:+.2f}% | "  # noqa: E731
                      f"{x['rollAnn']:+.1f}% | ₹{x['rollPerLot']:+,.0f} | {x['rollover'] if x['rollover'] is not None else '–'}% |")
    head = "| Contract | Near → Next | Roll pts | Roll % | Annualised | Per lot | Rollover |\n|---|---|---|---|---|---|---|"
    for uid, syms in _tracked_by_user().items():
        mine = [by[n] for n in {_nse_symbol(s) for s in syms} if n and n in by]
        body = f"Prices are the **{r['session']}** session close (official NSE bhavcopy), ready before today's 09:15 open.\n\n"
        if mine:
            body += "### Your F&O stocks\n" + head + "\n" + "\n".join(line(x) for x in sorted(mine, key=lambda x: x["symbol"])) + "\n\n"
        body += "### Indices\n" + head + "\n" + "\n".join(line(x) for x in idx) + "\n\n### Richest rolls\n" + head + "\n" + "\n".join(line(x) for x in hi)
        body += "\n\n### Cheapest / negative rolls\n" + head + "\n" + "\n".join(line(x) for x in lo)
        _push(uid, "roll", f"Futures roll cost · {r['session']} close" + (f" · {len(mine)} of yours" if mine else ""), body,
              [{"kind": "roll", "symbol": x["symbol"] + ".NS", "title": f"{x['symbol']} roll {x['rollAnn']:+.1f}% p.a."} for x in mine])


# ================================================================ JOB 2: results, concalls, transcripts, dividends
RESULT_DESCS = {"Financial Result Updates", "Outcome of Board Meeting", "Integrated Filing- Financial", "Integrated Filing (Financial)"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _ann_ts(a: dict) -> float:
    try:
        return dt.datetime.strptime(a.get("sort_date") or "", "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST).timestamp()
    except ValueError:
        try:
            return dt.datetime.strptime(a.get("an_dt") or "", "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST).timestamp()
        except ValueError:
            return time.time()


def _classify(a: dict) -> str | None:
    t, d = a.get("attchmntText") or "", a.get("desc") or ""
    both = f"{d} {t}"
    if re.search(r"(?i)newspaper|advertisement|publication|clipping", both):
        return None
    if re.search(r"(?i)transcript", both):
        return "transcript"
    if re.search(r"(?i)audio|recording", t) and re.search(r"(?i)call|meet|analyst", both):
        return "recording"
    if d in RESULT_DESCS and re.search(r"(?i)financial result|results for the|audited|unaudited", both) or \
            re.search(r"(?i)submitted to the exchange, the financial results|approved the (audited|unaudited)", t):
        return "result"
    if d.startswith(("Analysts", "Schedule of Analysts")) or "Con. Call" in d:
        if re.search(r"(?i)conference call|earnings call|con\.? ?call|concall|earnings discussion|investor call|analysts? call|webinar|dial", t):
            return "concall"
        if len(t) < 140 and re.search(r"(?i)informed the exchange about", t):
            return "concall?"            # vague summary: decide from the PDF
        return None
    if re.search(r"(?i)\bdividend\b", both) and re.search(r"(?i)declared|recommended|approved|record date|payment of", t) \
            and not re.search(r"(?i)will be held|to consider|intimation of (the )?board meeting|proposal to", t):
        return "dividend"
    return None


def _dates(text: str, after: dt.date | None = None) -> list[dt.date]:
    out = []
    mon = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
    for m in re.finditer(rf"(?i)\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{mon},?\s*(\d{{4}})", text):
        out.append((int(m.group(3)), MONTHS[m.group(2).lower()[:3]], int(m.group(1))))
    for m in re.finditer(rf"(?i)\b{mon}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})", text):
        out.append((int(m.group(3)), MONTHS[m.group(1).lower()[:3]], int(m.group(2))))
    for m in re.finditer(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b", text):
        out.append((int(m.group(3)), int(m.group(2)), int(m.group(1))))
    res = []
    for y, mo, d in out:
        try:
            x = dt.date(y, mo, d)
            if not after or x >= after:
                res.append(x)
        except ValueError:
            pass
    return res


TZ_RE = (r"(IST|ET|EST|EDT|PT|PST|PDT|CT|CST|CDT|GMT|BST|UTC|CET|CEST|HKT|SGT|JST|AEST|AEDT|AWST|Hong Kong time|Sydney time|"
         r"(?:Eastern|Pacific|Central)(?:\s+(?:Standard|Daylight))?(?:\s+Time)?)")
TZ_SHORT = {"eastern": "ET", "pacific": "PT", "central": "CT", "hong": "HKT", "sydney": "Sydney time"}


def _call_time(flat: str, tz: str) -> str | None:
    tm = re.search(rf"(?i)\b(\d{{1,2}}[:.]\d{{2}})\s*(a\.?\s?m\.?|p\.?\s?m\.?|hrs|hours)(?![a-z])(?:\s*\(?\s*{TZ_RE}\b\)?)?", flat) or \
        re.search(rf"(?i)\b(\d{{1,2}})\s*(a\.?\s?m\.?|p\.?\s?m\.?)(?![a-z])(?:\s*\(?\s*{TZ_RE}\b\)?)?", flat)
    if not tm:
        return None
    z = tm.group(3) or ""
    z = TZ_SHORT.get(z.split()[0].lower(), z.upper()) if z else tz
    return f"{tm.group(1).replace('.', ':')} {tm.group(2).replace(' ', '').replace('.', '').upper()} {z}".strip()


def _concall_details(text: str, announced: dt.date, budget: _Budget, tz: str = "IST", who: str = "Indian listed company") -> dict:
    flat = re.sub(r"\s+", " ", text)
    dates = []
    for m in re.finditer(r"(?i)(conference call|earnings call|con.?call|investor call|analysts? (meet|call)|webinar|discussion|will be held|scheduled|held on|to be held)", flat):
        near = _dates(flat[m.end():m.end() + 160], announced)
        if near:
            dates.append(near[0])
    if not dates:
        later = [d for d in _dates(flat, announced) if d > announced]
        dates = later or _dates(flat, announced)
    dial = []
    for m in re.finditer(r"(?<![\w/])(\+?\s?\d{1,3}[\s-]?)?(\(?\d{2,5}\)?[\s-]?){2,4}\d{3,5}(?![\w/])", flat):
        s = m.group(0).strip()
        digits = re.sub(r"\D", "", s)
        ctx = flat[max(0, m.start() - 70):m.start()].lower()
        if 8 <= len(digits) <= 15 and re.search(r"dial|universal|access|toll|phone|tel|number|primary|local|international|call", ctx) \
                and not re.search(r"cin|pin\b|pincode|fax|regd|registered|office|registration no|security code|scrip|e-?mail|website", ctx) and s not in dial:
            dial.append(s)
    pc = re.search(r"(?i)(?:pass\s?code|participant pin|access code|pin)[:\s#-]*(\d{3,10})", flat)
    links = [u.rstrip(").,;") for u in re.findall(r"https?://[^\s\"'<>]+", flat) if not re.search(r"nseindia|bseindia|sebi\.gov|sec\.gov|hkexnews|asx\.com|xbrl|w3\.org", u)]
    # webcast / IR pages written without http (e.g. "at apple.com/investor/earnings-call")
    links += ["https://" + u.rstrip(").,;") for u in re.findall(r"(?i)(?<![@/\w.])((?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,6}/[\w/.\-]*(?:investor|earnings|webcast|events?|ir\b)[\w/.\-]*)", flat)]
    det = {"date": dates[0].isoformat() if dates else None,
           "time": _call_time(flat, tz),
           "dialIn": dial[:6], "passcode": pc.group(1) if pc else None, "links": list(dict.fromkeys(links))[:4], "via": "rules"}
    if (not det["date"] or not det["time"]) and budget.take():
        j = _ai(f"From this {who}'s stock-exchange filing, extract the earnings / investor conference call details. "
                'Respond ONLY with JSON {"date":"YYYY-MM-DD or null","time":"e.g. 4:00 PM ' + (tz or "ET") + ' or null","dial_in":["numbers"],"passcode":"or null"}. '
                f"Notice dated {announced.isoformat()}:\n{flat[:6000]}", as_json=True)
        if isinstance(j, dict):
            if not det["date"] and j.get("date"):
                try:
                    if dt.date.fromisoformat(str(j["date"])[:10]) >= announced:
                        det["date"] = str(j["date"])[:10]
                except ValueError:
                    pass
            det["time"] = det["time"] or j.get("time")
            det["dialIn"] = det["dialIn"] or [str(x) for x in (j.get("dial_in") or [])][:6]
            det["passcode"] = det["passcode"] or j.get("passcode")
            det["via"] = "rules+AI"
    return det


def _summarise_result(name: str, text: str, fallback: str, budget: _Budget, who: str = "Indian listed company",
                      unit: str = "state the unit (₹ crore / lakh)") -> tuple[str, bool]:
    if text and budget.take():
        out = _ai(f"Summarise these quarterly financial results of {name} ({who}) for an investor in at most 7 markdown bullets: "
                  "period; revenue (and YoY / QoQ change if shown); EBITDA or operating profit if shown; net profit (and change); EPS; "
                  f"guidance if given; any dividend declared; one or two notable points. Use only numbers present in the text, {unit}, "
                  f"and write 'not stated' rather than guessing.\n\nFiling text:\n{text[:9000]}")
        if out:
            return out, True
    return fallback, False


def _summarise_transcript(name: str, text: str, budget: _Budget) -> str | None:
    if text and budget.take():
        return _ai(f"Summarise this earnings-call transcript of {name} in at most 8 markdown bullets: management's key messages, guidance / outlook, "
                   f"margins, demand commentary, capex, risks, and notable analyst questions. Use only the text.\n\n{text[:12000]}")
    return None


def _india(sym: str, corp: dict, since: float, boot: bool, budget: _Budget) -> list[dict]:
    nse = _nse_symbol(sym)
    if not nse or nse in INDEX_MAP.values():
        return []
    c = corp.setdefault(sym, {"results": [], "concalls": [], "transcripts": [], "dividends": [], "events": [], "seen": []})
    boot = boot or not c.get("updated")              # a newly tracked company: load its history quietly, no messages
    since = c.get("updated") or since                # pick up from this company's own last refresh
    seen = set(c["seen"])
    now = now_ist()
    frm = (now - dt.timedelta(days=120)) if boot else dt.datetime.fromtimestamp(since, IST) - dt.timedelta(days=1)
    anns = _nse_get("/api/corporate-announcements", {"index": "equities", "symbol": nse, "from_date": f"{frm:%d-%m-%Y}", "to_date": f"{now:%d-%m-%Y}"}) or []
    out: list[dict] = []
    for a in sorted(anns, key=_ann_ts):
        sid = str(a.get("seq_id") or a.get("attchmntFile") or a.get("an_dt"))
        if sid in seen:
            continue
        seen.add(sid)
        kind = _classify(a)
        if not kind:
            continue
        ts = _ann_ts(a)
        fresh = not boot and ts >= since - 3600
        name = a.get("sm_name") or nse
        link = a.get("attchmntFile")
        text = ""
        if kind == "concall?":
            text = _pdf_text(link, pages=3)
            kind = "transcript" if re.search(r"(?i)transcript", text[:3000]) else "concall" if re.search(r"(?i)conference call|earnings call|con.?call|dial|webinar|investor call", text) else None
            if not kind:
                continue
        day = dt.datetime.fromtimestamp(ts, IST).date()
        if kind == "result":
            same = next((r for r in c["results"] if r.get("date") == day.isoformat()), None)
            if same:                                         # several filings for one results day: keep one entry, add the link
                if link and link not in same.setdefault("links", []):
                    same["links"].append(link)
                continue
            text = text or (_pdf_text(link, pages=6) if fresh else "")
            per = re.search(r"(?i)period ended\s+([A-Za-z]+\.? \d{1,2},? \d{4}|\d{1,2}(?:st|nd|rd|th)? [A-Za-z]+,? \d{4})", (a.get("attchmntText") or "") + " " + text[:3000])
            summ, by_ai = _summarise_result(name, text if fresh else "", a.get("attchmntText") or "Results filed.", budget)
            item = {"id": sid, "date": day.isoformat(), "t": ts, "period": per.group(1) if per else None, "summary": summ, "ai": by_ai, "link": link, "links": [link] if link else []}
            c["results"].insert(0, item)
            c["results"] = c["results"][:16]
            out.append({"kind": "result", "symbol": sym, "name": name, "fresh": fresh, "title": f"{name}: results declared" + (f" (period ended {item['period']})" if item["period"] else ""),
                        "body": summ, "link": link, "ai": by_ai})
        elif kind == "concall":
            recent = (now.date() - day).days <= 30          # older notices can't be for an upcoming call
            text = text or (_pdf_text(link, pages=3) if fresh or recent else "")
            det = _concall_details((a.get("attchmntText") or "") + "\n" + text, day, budget if fresh else _Budget(0))
            entry = {"id": sid, "announced": day.isoformat(), "notice": link, **det, "transcript": None, "recording": None}
            dup = next((x for x in c["concalls"] if x.get("date") and x.get("date") == det["date"]), None)
            if dup:                                          # a follow-up notice for the same call (often adds dial-ins)
                before = set(dup.get("dialIn") or [])
                for k in ("time", "passcode"):
                    dup[k] = dup.get(k) or det[k]
                dup["dialIn"] = list(dict.fromkeys((dup.get("dialIn") or []) + det["dialIn"]))[:6]
                dup["links"] = list(dict.fromkeys((dup.get("links") or []) + det["links"]))[:4]
                entry = dup
                if set(dup["dialIn"]) <= before:             # nothing new for the user: no second message
                    continue
            else:
                c["concalls"].insert(0, entry)
                c["concalls"] = c["concalls"][:20]
            when = f"{det['date'] or 'date in notice'}{' · ' + det['time'] if det['time'] else ''}"
            out.append({"kind": "concall", "symbol": sym, "name": name, "fresh": fresh, "title": f"{name}: concall on {when}",
                        "body": ("Dial-in: " + ", ".join(entry["dialIn"]) if entry.get("dialIn") else "Dial-in: see notice / company website")
                        + (f" · passcode {entry['passcode']}" if entry.get("passcode") else ""), "link": link})
        elif kind in ("transcript", "recording"):
            target = next((x for x in c["concalls"] if (x.get("date") or x.get("announced") or "") <= day.isoformat() and not x.get(kind)), None)
            if kind == "transcript":
                text = text or (_pdf_text(link, pages=25, max_chars=16000) if fresh else "")
                summ = _summarise_transcript(name, text, budget) if fresh else None
                tr = {"id": sid, "date": day.isoformat(), "link": link, "summary": summ}
                c["transcripts"].insert(0, tr)
                c["transcripts"] = c["transcripts"][:12]
                if target:
                    target["transcript"] = link
                out.append({"kind": "transcript", "symbol": sym, "name": name, "fresh": fresh, "title": f"{name}: concall transcript posted",
                            "body": summ or "Transcript PDF posted.", "link": link, "ai": bool(summ)})
            else:
                if target:
                    target["recording"] = link
                out.append({"kind": "recording", "symbol": sym, "name": name, "fresh": fresh, "title": f"{name}: concall audio recording posted", "body": a.get("attchmntText") or "", "link": link})
        elif kind == "dividend":
            amt = re.search(r"(?i)(?:rs\.?|₹|inr)\s*([\d,]+(?:\.\d+)?)", a.get("attchmntText") or "")
            d = {"id": sid, "declared": day.isoformat(), "subject": (a.get("attchmntText") or a.get("desc") or "")[:220], "amount": amt.group(1) if amt else None,
                 "exDate": None, "recordDate": None, "link": link, "source": "announcement"}
            c["dividends"].insert(0, d)
            out.append({"kind": "dividend", "symbol": sym, "name": name, "fresh": fresh, "title": f"{name}: dividend announced" + (f" (₹{d['amount']}/share)" if d["amount"] else ""),
                        "body": d["subject"], "link": link})
    # (E) structured dividend record (ex-date / record date) from corporate actions
    for x in _nse_get("/api/corporates-corporateActions", {"index": "equities", "symbol": nse}) or []:
        subj = x.get("subject") or ""
        if "dividend" not in subj.lower():
            continue
        did = "ca:" + hashlib.md5(f"{subj}|{x.get('exDate')}".encode()).hexdigest()[:12]
        if did in seen:
            continue
        seen.add(did)
        try:
            exd = dt.datetime.strptime(x.get("exDate") or "", "%d-%b-%Y").date()
        except ValueError:
            exd = None
        amt = re.search(r"(?i)rs\.?\s*([\d.]+)", subj)
        c["dividends"].insert(0, {"id": did, "declared": None, "subject": subj, "amount": amt.group(1) if amt else None, "exDate": exd.isoformat() if exd else None,
                                  "recordDate": x.get("recDate"), "link": None, "source": "corporate action"})
        if not boot and exd and exd >= now.date() - dt.timedelta(days=3):
            out.append({"kind": "dividend", "symbol": sym, "name": x.get("comp") or nse, "fresh": True, "title": f"{x.get('comp') or nse}: {subj}",
                        "body": f"Ex-date {x.get('exDate')} · record date {x.get('recDate') or '–'}", "link": None})
    c["dividends"] = sorted(c["dividends"], key=lambda d: d.get("exDate") or d.get("declared") or "", reverse=True)[:30]
    # upcoming board meetings (results dates)
    evs = []
    for e in _nse_get("/api/event-calendar", {"index": "equities", "symbol": nse}) or []:
        try:
            d = dt.datetime.strptime(e.get("date") or "", "%d-%b-%Y").date()
        except ValueError:
            continue
        if d >= now.date():
            evs.append({"date": d.isoformat(), "purpose": e.get("purpose"), "desc": (e.get("bm_desc") or "")[:200]})
            eid = f"ev:{d.isoformat()}:{e.get('purpose')}"
            if eid not in seen:
                seen.add(eid)
                if not boot:
                    out.append({"kind": "calendar", "symbol": sym, "name": e.get("company") or nse, "fresh": True,
                                "title": f"{e.get('company') or nse}: {e.get('purpose')} on {d:%d %b %Y}", "body": (e.get("bm_desc") or "")[:200], "link": None})
    c["events"] = sorted(evs, key=lambda e: e["date"])
    for cc in c["concalls"]:
        cc["status"] = "upcoming" if cc.get("date") and cc["date"] >= now.date().isoformat() else "held"
    c["name"] = c.get("name") or (anns[0].get("sm_name") if anns else nse)
    c["market"] = "India (NSE)"
    c["seen"] = list(seen)[-4000:]
    c["updated"] = time.time()
    return out


SUFFIX_COUNTRY = {"L": "UK", "DE": "Germany", "F": "Germany", "PA": "France", "AS": "Netherlands", "SW": "Switzerland", "MI": "Italy", "MC": "Spain",
                  "BR": "Belgium", "IR": "Ireland", "ST": "Sweden", "CO": "Denmark", "OL": "Norway", "HE": "Finland", "LS": "Portugal", "VI": "Austria",
                  "T": "Japan", "KS": "South Korea", "KQ": "South Korea", "TW": "Taiwan", "TWO": "Taiwan", "SS": "China", "SZ": "China", "SI": "Singapore",
                  "TO": "Canada", "V": "Canada", "NE": "Canada", "SA": "Brazil", "MX": "Mexico", "JO": "South Africa", "TA": "Israel", "NZ": "New Zealand",
                  "BK": "Thailand", "JK": "Indonesia", "KL": "Malaysia", "SR": "Saudi Arabia", "HK": "Hong Kong", "AX": "Australia"}
FILING_TZ = {"sec": -5, "sec-adr": -5, "hkex": 8, "asx": 10}            # local date of a filing
CALL_TZ = {"sec": "ET", "sec-adr": "", "hkex": "HKT", "asx": "AEST"}      # time zone assumed when a call time has none
WHO = {"sec": "US-listed company", "sec-adr": "listed company", "hkex": "Hong Kong-listed company", "asx": "ASX-listed company"}
UNIT = "state the currency and unit exactly as written (e.g. $ millions, HK$ million, A$m)"
TRANSCRIPT_NOTE = ("Outside India, call transcripts aren't filed with the exchange; the webcast replay is on the company's IR site. "
                   "Automatic transcripts need a paid data key (e.g. Finnhub or FMP).")


def _new_co() -> dict:
    return {"results": [], "concalls": [], "transcripts": [], "dividends": [], "events": [], "seen": []}


def _global(sym: str, corp: dict, since: float, boot: bool, budget: _Budget) -> list[dict]:
    """Non-Indian stocks: Yahoo (EPS vs estimates, earnings dates, dividends) plus the company's own exchange filings."""
    src = intl.filing_source(sym)
    if not src:
        return []
    c = corp.setdefault(sym, _new_co())
    boot = boot or not c.get("updated")              # a newly tracked company: load its history quietly, no messages
    since = c.get("updated") or since                # pick up from this company's own last refresh
    seen = set(c["seen"])
    j = data._yget(f"/v10/finance/quoteSummary/{requests.utils.quote(sym, safe='')}", {"modules": "price,calendarEvents,earningsHistory,earnings"}, crumb=True)
    res = ((j or {}).get("quoteSummary", {}).get("result") or [None])[0] or {}
    name = (res.get("price") or {}).get("longName") or (res.get("price") or {}).get("shortName") or c.get("name") or sym
    cur = (res.get("price") or {}).get("currency") or ""
    out = []
    raw = lambda d, k: (d.get(k) or {}).get("raw") if isinstance(d.get(k), dict) else d.get(k)  # noqa: E731
    quarters = ((res.get("earnings") or {}).get("financialsChart") or {}).get("quarterly") or []
    hist_rows = (res.get("earningsHistory") or {}).get("history") or []
    latest_q = max((raw(h, "quarter") or 0 for h in hist_rows), default=0)
    for h in hist_rows:
        q = raw(h, "quarter")
        act, est = raw(h, "epsActual"), raw(h, "epsEstimate")
        if not q or act is None:
            continue
        rid = f"eh:{q}"
        if rid in seen:
            continue
        seen.add(rid)
        qd = dt.datetime.fromtimestamp(q, dt.timezone.utc).date()
        surprise = raw(h, "surprisePercent")
        rev = next((x for x in quarters[::-1] if x.get("revenue")), None) if q == latest_q else None   # Yahoo only gives revenue for recent quarters
        summ = (f"- Quarter ended **{qd:%d %b %Y}**\n- EPS **{act:.2f}** vs estimate {est:.2f}" if est is not None else f"- Quarter ended **{qd:%d %b %Y}**\n- EPS **{act:.2f}**")
        if surprise is not None:
            summ += f" (**{surprise * 100:+.1f}%** {'beat' if surprise >= 0 else 'miss'})"
        if rev:
            summ += f"\n- Revenue ({rev.get('date')}): {raw(rev, 'revenue') / 1e9:,.2f}B {cur}" if raw(rev, "revenue") else ""
        c["results"].insert(0, {"id": rid, "date": qd.isoformat(), "period": f"{qd:%b %Y}", "summary": summ, "ai": False, "link": None, "source": "Yahoo"})
        if not boot:
            out.append({"kind": "result", "symbol": sym, "name": name, "fresh": True, "rid": rid, "title": f"{name}: results for quarter ended {qd:%d %b %Y}", "body": summ, "link": None})
    cal = res.get("calendarEvents") or {}
    evs = []
    for ts in ((cal.get("earnings") or {}).get("earningsDate") or []):
        t = ts.get("raw") if isinstance(ts, dict) else ts
        if not t:
            continue
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc).date()
        if d < now_ist().date():
            continue
        evs.append({"date": d.isoformat(), "purpose": "Earnings release & call", "desc": "Estimated date" if (cal.get("earnings") or {}).get("isEarningsDateEstimate") else "Confirmed date"})
        cid = f"ed:{d.isoformat()}"
        if not any(x.get("id") == cid or x.get("date") == d.isoformat() for x in c["concalls"]):
            c["concalls"].insert(0, {"id": cid, "announced": None, "date": d.isoformat(), "time": None, "dialIn": [], "passcode": None, "links": [],
                                     "note": "Call / webcast details are published on the company's investor-relations site", "transcript": None, "via": "Yahoo"})
        if cid not in seen:
            seen.add(cid)
            if not boot:
                out.append({"kind": "calendar", "symbol": sym, "name": name, "fresh": True, "title": f"{name}: earnings on {d:%d %b %Y}", "body": evs[-1]["desc"], "link": None})
        break
    exd = raw(cal, "exDividendDate")
    if exd:
        d = dt.datetime.fromtimestamp(exd, dt.timezone.utc).date()
        did = f"xd:{d.isoformat()}"
        hist = (data.get_history(sym, "2y") or {}).get("events", {}).get("dividends", {})
        amt = None
        if hist:
            k = max(hist, key=lambda x: int(x))
            amt = round(float(hist[k]), 4)
        if did not in seen:
            seen.add(did)
            c["dividends"].insert(0, {"id": did, "declared": None, "subject": f"Dividend{f' {amt} {cur}' if amt else ''}", "amount": amt, "exDate": d.isoformat(),
                                      "recordDate": None, "payDate": (dt.datetime.fromtimestamp(raw(cal, 'dividendDate'), dt.timezone.utc).date().isoformat() if raw(cal, "dividendDate") else None),
                                      "link": None, "source": "Yahoo"})
            if not boot and d >= now_ist().date() - dt.timedelta(days=3):
                out.append({"kind": "dividend", "symbol": sym, "name": name, "fresh": True, "title": f"{name}: ex-dividend {d:%d %b %Y}" + (f" ({amt} {cur} last paid)" if amt else ""), "body": "", "link": None})
        if d >= now_ist().date():
            evs.append({"date": d.isoformat(), "purpose": "Ex-dividend", "desc": ""})
    c["seen"] = list(seen)
    # (A)-(E) from the company's own exchange filings: results releases, call details, transcripts, dividends, board-meeting dates
    label = None
    if ((res.get("price") or {}).get("quoteType") or "EQUITY") == "EQUITY":
        try:                                         # first time for this company's filings (also after an upgrade): load quietly
            got, label = _intl_filings(sym, src, c, name, since, boot or not c.get("filingsBoot"), budget)
            out += got
            c["filingsBoot"] = True
            c.pop("filingsError", None)
        except Exception as e:                       # filings are a bonus on top of Yahoo: never lose the Yahoo part
            c["filingsError"] = str(e)[:200]
    _merge_eps(c, out)
    today = now_ist().date().isoformat()
    c["fevents"] = [e for e in c.get("fevents", []) if e["date"] >= today][-10:]
    for y in [d for d in c["dividends"] if d.get("source") == "Yahoo" and d.get("exDate")]:     # one dividend, two sources: keep the filing
        f = next((d for d in c["dividends"] if d.get("source") not in ("Yahoo", None) and y["exDate"] in (d.get("exDate"), d.get("recordDate"))), None)
        if f:
            f["exDate"] = f.get("exDate") or y["exDate"]
            f["payDate"] = f.get("payDate") or y.get("payDate")
            c["dividends"].remove(y)
    for cc in c["concalls"]:
        cc["status"] = "upcoming" if cc.get("date") and cc["date"] >= today else "held"
    c["concalls"] = sorted(c["concalls"], key=lambda x: x.get("date") or x.get("announced") or "", reverse=True)[:12]
    c["results"] = sorted(c["results"], key=lambda r: r["date"], reverse=True)[:12]
    c["transcripts"] = c["transcripts"][:12]
    c["dividends"] = sorted(c["dividends"], key=lambda d: d.get("exDate") or d.get("declared") or "", reverse=True)[:20]
    c["events"] = sorted(evs + c["fevents"], key=lambda e: e["date"])
    country = SUFFIX_COUNTRY.get(sym.rsplit(".", 1)[-1], "Global") if "." in sym else "US"
    c.update(name=name, market=label or f"{country} (Yahoo)", seen=c["seen"][-3000:], updated=time.time(), transcriptNote=TRANSCRIPT_NOTE)
    return out


def _intl_filings(sym: str, src: str, c: dict, name: str, since: float, boot: bool, budget: _Budget) -> tuple[list[dict], str | None]:
    start = time.time() - 120 * 86400 if boot else since - 86400
    country = SUFFIX_COUNTRY.get(sym.rsplit(".", 1)[-1], "Global") if "." in sym else "US"
    if src in ("sec", "sec-adr"):
        if "cik" not in c or (not c["cik"] and time.time() - c.get("cikT", 0) > 7 * 86400):
            c["cik"], c["cikT"] = intl.sec_cik(sym, name), time.time()
        if not c["cik"]:
            return [], None
        anns, _ = intl.sec_filings(c["cik"], start)
        for a in anns:
            a["source"], a["text"] = "SEC", (lambda a=a: intl.sec_text(a))
        label = "US (SEC EDGAR + Yahoo)" if src == "sec" else f"{country} (SEC filings of its US listing + Yahoo)"
    elif src == "hkex":
        if not c.get("hkexId"):
            c["hkexId"] = intl.hkex_stock_id(sym[:-3].zfill(5))
        if not c["hkexId"]:
            return [], None
        anns = intl.hkex_filings(c["hkexId"], start)
        for a in anns:
            a["source"], a["text"] = "HKEX", (lambda a=a: (_pdf_text(a["link"], pages=6), a["link"]))
        label = "Hong Kong (HKEXnews + Yahoo)"
    else:
        anns = intl.asx_filings(sym[:-3], start)
        for a in anns:                               # PDF text only for the latest announcements (ASX's file API); otherwise the headline
            a["source"], a["text"] = "ASX", (lambda a=a: (_pdf_text(a["file"], pages=6, force=True) if a.get("file") else "", a["link"]))
        label = "Australia (ASX + Yahoo)"
    return _process_filings(sym, c, name, anns, since, boot, budget, src), label


def _process_filings(sym: str, c: dict, name: str, anns: list[dict], since: float, boot: bool, budget: _Budget, src: str) -> list[dict]:
    seen, out = set(c["seen"]), []
    tzo = dt.timezone(dt.timedelta(hours=FILING_TZ[src]))
    ctz, who = CALL_TZ[src], WHO[src]
    probes = 6                                       # first load: open at most this many unlabelled filings (6-K, 8-K 7.01/8.01) to classify them
    latest_text = boot                               # first load: read the newest results release too (summary, call link, dividend dates)
    for a in sorted(anns, key=lambda a: a["ts"], reverse=boot):
        if a["id"] in seen:
            continue
        ts = a["ts"]
        day = dt.datetime.fromtimestamp(ts, tzo).date()
        fresh = not boot and ts >= since - 2 * 86400
        recent = time.time() - ts <= 30 * 86400
        doc = {"text": None, "link": a.get("link")}

        def text(doc=doc, a=a) -> str:              # fetched at most once, only when needed
            if doc["text"] is None:
                t, u = a["text"]()
                doc["text"], doc["link"] = t or "", u or doc["link"]
            return doc["text"]
        kind = a["kind"]
        if kind == "?":
            if not fresh and not (boot and probes > 0):
                seen.add(a["id"])
                continue
            probes -= int(boot)
            kind = intl.classify_text(text())
            if not kind:
                seen.add(a["id"])
                continue
        seen.add(a["id"])
        if kind == "result":
            same = next((r for r in c["results"] if r.get("date") == day.isoformat() and r.get("source") == a["source"]), None)
            if same:                                 # several filings on one results day: one entry, extra links
                if a.get("link") and a["link"] not in same.setdefault("links", []):
                    same["links"].append(a["link"])
                if not same.get("ai") and a["source"] != "SEC" and a["title"] not in same["summary"]:
                    same["summary"] = f"{same['summary']} · {a['title']}"
                continue
            body = text() if fresh or (latest_text and a["source"] == "SEC") else (doc["text"] or "")
            latest_text = False
            per = re.search(r"(?i)(?:quarter|three months|six months|nine months|twelve months|half[- ]year|year|period)\s+ended\s+"
                            r"([A-Z][a-z]+\.? \d{1,2},? \d{4}|\d{1,2} [A-Z][a-z]+,? \d{4})", a["title"] + " " + body[:4000])
            fallback = (_excerpt(body) or f"Results release filed with the SEC ({a['form']})") if a["source"] == "SEC" else a["title"]
            summ, by_ai = _summarise_result(name, body if fresh else "", fallback, budget, who, UNIT)
            item = {"id": a["id"], "date": day.isoformat(), "t": ts, "period": per.group(1) if per else None, "summary": summ, "ai": by_ai,
                    "link": doc["link"], "links": [doc["link"]] if doc["link"] else [], "source": a["source"]}
            c["results"].insert(0, item)
            out.append({"kind": "result", "symbol": sym, "name": name, "fresh": fresh, "rid": item["id"], "ai": by_ai, "link": doc["link"], "body": summ,
                        "title": f"{name}: results declared" + (f" (period ended {item['period']})" if item["period"] else "")})
            if body:                                 # results releases usually carry the call details and any dividend declared
                flat = re.sub(r"\s+", " ", body)
                ctx = " … ".join(flat[max(0, m.start() - 250):m.end() + 350] for m in re.finditer(r"(?i)conference call|earnings call|webcast|live stream", flat))
                if ctx:                              # only the text around the call wording, and only a call within 3 days of the release
                    det = _concall_details(ctx, day, _Budget(0), tz=ctz, who=who)
                    if det["date"] and day.isoformat() <= det["date"] <= (day + dt.timedelta(days=3)).isoformat():
                        out += _add_concall(sym, c, name, det, a, day, fresh, doc["link"])
                dv = _dividend_from_text(body)
                if dv:
                    out += _add_dividend(sym, c, name, dv, a, day, fresh, doc["link"])
        elif kind == "concall":
            body = text() if (fresh or recent) else ""
            det = _concall_details(a["title"] + "\n" + body, day, budget if fresh else _Budget(0), tz=ctz, who=who)
            if det["date"]:
                out += _add_concall(sym, c, name, det, a, day, fresh, doc["link"])
        elif kind == "transcript":
            body = text() if fresh else ""
            summ = _summarise_transcript(name, body, budget) if body else None
            c["transcripts"].insert(0, {"id": a["id"], "date": day.isoformat(), "link": doc["link"], "summary": summ})
            target = next((x for x in sorted(c["concalls"], key=lambda x: x.get("date") or "", reverse=True)
                           if (x.get("date") or "9") <= day.isoformat() and not x.get("transcript")), None)
            if target:
                target["transcript"] = doc["link"]
            out.append({"kind": "transcript", "symbol": sym, "name": name, "fresh": fresh, "title": f"{name}: earnings-call transcript filed",
                        "body": summ or "Transcript filed.", "link": doc["link"], "ai": bool(summ)})
        elif kind == "dividend":
            if re.match(r"(?i)update\b", a["title"]) and (boot or any(x.get("source") == a["source"] for x in c["dividends"])):
                continue                             # ASX "Update - Dividend/Distribution" notices restate one already recorded
            body = text() if fresh else ""
            out += _add_dividend(sym, c, name, _dividend_from_text(a["title"] + "\n" + body) or {}, a, day, fresh, doc["link"], subject=a["title"])
        elif kind == "calendar":                     # e.g. HKEX "date of board meeting" (results approval)
            body = text() if (fresh or recent) else ""
            ds = [d for d in _dates(body, day) if d > day]
            if ds:
                c.setdefault("fevents", []).append({"date": ds[0].isoformat(), "purpose": "Board meeting (results)", "desc": a["title"][:200]})
                if fresh:
                    out.append({"kind": "calendar", "symbol": sym, "name": name, "fresh": True, "title": f"{name}: board meeting on {ds[0]:%d %b %Y} (results)",
                                "body": a["title"][:200], "link": doc["link"]})
    c["seen"] = list(seen)
    return out


def _excerpt(text: str, n: int = 4) -> str:
    """First headline lines of a press release, as bullets (used when no AI summary is written)."""
    lines = []
    for ln in text.splitlines():
        ln = ln.strip(" |\t")
        if len(ln) < 25 or re.match(r"(?i)^(ex(hibit)?[- .]?99|\S+\.htm|page \d|[\d\s.]+$)", ln) or re.search(r"(?i)no responsibility|disclaim", ln):
            continue
        lines.append("- " + ln[:200])
        if len(lines) >= n:
            break
    return "\n".join(lines)


def _add_concall(sym, c, name, det, a, day, fresh, link) -> list[dict]:
    dup = next((x for x in c["concalls"] if x.get("date") and x.get("date") == det["date"]), None)
    if dup:                                          # the Yahoo earnings-date placeholder or an earlier filing for the same call
        before = (tuple(dup.get("dialIn") or []), dup.get("time"), tuple(dup.get("links") or []))
        for k in ("time", "passcode"):
            dup[k] = dup.get(k) or det.get(k)
        dup["dialIn"] = list(dict.fromkeys((dup.get("dialIn") or []) + det["dialIn"]))[:6]
        dup["links"] = list(dict.fromkeys((dup.get("links") or []) + det["links"]))[:4]
        dup["notice"] = dup.get("notice") or link
        if dup["dialIn"] or dup["links"] or dup.get("time"):
            dup.pop("note", None)
        entry = dup
        if (tuple(dup["dialIn"]), dup.get("time"), tuple(dup["links"])) == before:
            return []
    else:
        entry = {"id": a["id"] + ":call", "announced": day.isoformat(), "notice": link, **det, "transcript": None, "recording": None, "via": a["source"]}
        c["concalls"].insert(0, entry)
    if not fresh or entry["date"] < now_ist().date().isoformat():
        return []
    when = entry["date"] + (f" · {entry['time']}" if entry.get("time") else "")
    bits = (["Dial-in: " + ", ".join(entry["dialIn"])] if entry.get("dialIn") else []) + ([f"passcode {entry['passcode']}"] if entry.get("passcode") else []) \
        + ([f"webcast: {entry['links'][0]}"] if entry.get("links") else [])
    return [{"kind": "concall", "symbol": sym, "name": name, "fresh": True, "title": f"{name}: earnings call on {when}", "body": " · ".join(bits) or "Details in the filing.", "link": link}]


_CUR = r"(US\$|HK\$|A\$|S\$|C\$|NZ\$|\$|USD|HKD|AUD|SGD|EUR|€|£|GBP|RMB|CNY|JPY|¥)"
_NUM = r"\s?(\d+(?:\.\d+)?)(?!\s*(?:billion|million|bn|mn|m)\b)\s*(cents?)?"


def _dividend_from_text(text: str) -> dict | None:
    flat = re.sub(r"\s+", " ", text[:30000])
    m = re.search(rf"(?i)\bdividends? (?:of|amounting to|totall?ing)\s+{_CUR}{_NUM}", flat) or \
        re.search(rf"(?i)\b(?:declared?|approved|recommended|announced?|resolved to pay)\b[^.]{{0,120}}?{_CUR}{_NUM}[^.]{{0,60}}?\bdividend", flat) or \
        re.search(rf"(?i)\bdividend[^.]{{0,60}}?{_CUR}{_NUM}\s*per (?:ordinary )?(?:share|ADS|unit|security)", flat)
    if not m:
        return None
    cur, amt = m.group(1), float(m.group(2)) / (100 if m.group(3) else 1)
    seg = flat[m.start(): m.start() + 700]

    def near(pat):
        mm = re.search(rf"(?:{pat})[^.]{{0,60}}", seg, re.I)
        ds = _dates(mm.group(0)) if mm else []
        return ds[0].isoformat() if ds else None
    return {"amount": round(amt, 6), "currency": cur, "ex": near(r"ex[- ]?(?:dividend )?date"),
            "record": near(r"record (?:date|as of|on)|holders of record|shareholders of record"), "pay": near(r"payable|payment date|paid on|per (?:ordinary )?(?:share|ADS) on")}


def _add_dividend(sym, c, name, dv, a, day, fresh, link, subject=None) -> list[dict]:
    did = a["id"] + ":div"
    if any(x.get("id") == did for x in c["dividends"]):
        return []
    amt, cur = dv.get("amount"), dv.get("currency") or ""
    d = {"id": did, "declared": day.isoformat(), "subject": subject or (f"Dividend {cur}{amt:g} per share" if amt else "Dividend declared"), "amount": amt,
         "exDate": dv.get("ex"), "recordDate": dv.get("record"), "payDate": dv.get("pay"), "link": link, "source": a["source"]}
    c["dividends"].insert(0, d)
    if not fresh:
        return []
    bits = [f"{k} {v}" for k, v in (("Ex-date", d["exDate"]), ("record date", d["recordDate"]), ("payable", d["payDate"])) if v]
    return [{"kind": "dividend", "symbol": sym, "name": name, "fresh": True, "title": f"{name}: dividend declared" + (f" ({cur}{amt:g}/share)" if amt else ""),
             "body": " · ".join(bits), "link": link}]


def _merge_eps(c: dict, out: list[dict]):
    """Yahoo's EPS-vs-estimate line joins the official results filing of the same quarter (one entry, one message)."""
    filed = [r for r in c["results"] if r.get("source") in ("SEC", "HKEX", "ASX")]
    for r in [r for r in c["results"] if str(r.get("id", "")).startswith("eh:")]:
        qd = dt.date.fromisoformat(r["date"])
        f = next((f for f in filed if 0 < (dt.date.fromisoformat(f["date"]) - qd).days <= 100), None)
        if not f:
            continue
        if not f.get("eps"):
            f["eps"] = True
            f["summary"] = r["summary"] + "\n" + (f.get("summary") or "")
        c["results"].remove(r)
        ym = next((m for m in out if m.get("rid") == r["id"]), None)
        fm = next((m for m in out if m.get("rid") == f["id"]), None)
        if ym and fm:
            fm["body"] = r["summary"] + "\n" + (fm.get("body") or "")
            out.remove(ym)


def run_calendar() -> dict:
    jobs = _load(JOBS, {})
    last = (jobs.get("calendar") or {}).get("windowEnd")
    boot = last is None
    since = last or time.time() - 3 * 86400
    started = time.time()
    users = _tracked_by_user()
    syms = sorted({s for v in users.values() for s in v})[:400]
    items, errors, _n = refresh_companies(syms, since, boot, _Budget(40))
    fresh = [i for i in items if i.get("fresh")]
    _deliver_calendar(fresh, users, boot, len(syms))
    return {"companies": len(syms), "new": len(fresh), "bootstrap": boot, "errors": errors[:10], "windowEnd": started}


def refresh_companies(syms: list[str], since: float | None = None, boot: bool = False, budget: _Budget | None = None,
                      max_age: float = 0) -> tuple[list[dict], list[str], int]:
    """Refresh companies' filings and merge them into the shared company store. Skips companies refreshed within
    `max_age` seconds and ones another run is refreshing right now (that run delivers to everyone who tracks them)."""
    since = since or time.time() - 3 * 86400
    budget = budget or _Budget(10)
    with _lock:
        corp = _load(CORP, {})
        todo = [s for s in dict.fromkeys(syms) if s not in _inflight and time.time() - (corp.get(s) or {}).get("updated", 0) >= max_age]
        _inflight.update(todo)
        local = {s: copy.deepcopy(corp[s]) for s in todo if s in corp}
    items, errors = [], []
    try:
        for s in todo:
            try:
                items += _india(s, local, since, boot, budget) if _nse_symbol(s) else _global(s, local, since, boot, budget)
            except Exception as e:                   # one bad company must not stop the run
                errors.append(f"{s}: {e}")
    finally:
        with _lock:
            corp = _load(CORP, {})
            corp.update({s: local[s] for s in todo if s in local})
            _save(CORP, corp)
            _inflight.difference_update(todo)
    return items, errors, len(todo)


KIND_ORDER = ["result", "concall", "transcript", "recording", "dividend", "calendar"]
KIND_HEAD = {"result": "📊 Results declared", "concall": "📞 Upcoming concalls", "transcript": "📝 Concall transcripts", "recording": "🎧 Concall recordings",
             "dividend": "💰 Dividends", "calendar": "📅 Upcoming dates"}


def _deliver_calendar(items: list[dict], users: dict, boot: bool, n: int):
    for uid, syms in users.items():
        if boot:
            _push(uid, "calendar", f"Tracker set up for {len(syms)} tracked symbols",
                  "Your results, concall, transcript and dividend trackers are ready. From now on you'll get a message twice a day (09:01 and 20:01 IST) "
                  "only when something new is filed for a company you hold or watch.", [])
            continue
        mine = [i for i in items if i["symbol"] in syms]
        if not mine:
            continue                                     # nothing new: no message
        body = []
        for k in KIND_ORDER:
            grp = [i for i in mine if i["kind"] == k]
            if not grp:
                continue
            body.append(f"### {KIND_HEAD[k]}")
            for i in grp:
                body.append(f"**{i['title']}**" + (f" · [filing]({i['link']})" if i.get("link") else "") + (" · *AI summary, verify in the filing*" if i.get("ai") else ""))
                if i.get("body"):
                    body.append(i["body"])
                body.append("")
        counts = ", ".join(f"{sum(1 for i in mine if i['kind'] == k)} {k}{'s' if sum(1 for i in mine if i['kind'] == k) > 1 else ''}" for k in KIND_ORDER if any(i["kind"] == k for i in mine))
        _push(uid, "calendar", f"What's new · {counts}", "\n".join(body),
              [{"kind": i["kind"], "symbol": i["symbol"], "title": i["title"], "body": (i.get("body") or "")[:1500], "link": i.get("link"), "ai": bool(i.get("ai"))} for i in mine])


# ---------------------------------------------------------------- users, inbox, email
def _users():
    if config.PRIVATE:
        return [None]
    return [r["user_id"] for r in db.q("SELECT user_id FROM user_state")]


def _with_state(uid, fn):
    tok = store.current_uid.set(uid)
    try:
        st = store.load()
        res = fn(st)
        store.save(st)
        return res
    finally:
        store.current_uid.reset(tok)


def read_state(uid) -> dict:
    tok = store.current_uid.set(uid)
    try:
        return store.load()
    finally:
        store.current_uid.reset(tok)


def tracked_symbols(st: dict) -> list[str]:
    """What the Daily Desk follows for a user: holdings and watchlists (each can be switched off on the Portfolio tab),
    plus symbols added there, minus the ones removed there."""
    d = st.get("desk") or {}
    s = set()
    if d.get("holdings", True):
        s |= {h["symbol"] for h in st.get("holdings", []) if h.get("symbol")}
    if d.get("watchlists", True):
        s |= set(st.get("watchlist") or [])
        for lst in (st.get("watchlists") or {}).values():
            s |= set(lst)
    s |= set(d.get("added") or [])
    return sorted(s - set(d.get("removed") or []))


def _tracked_by_user() -> dict:
    return {uid: set(tracked_symbols(read_state(uid))) for uid in _users()}


def _push(uid, job: str, title: str, body: str, items: list):
    msg = {"id": uuid.uuid4().hex[:12], "t": time.time(), "job": job, "title": title, "body": body, "items": items[:60], "read": False}

    def add(st):
        prof = st.get("profile", {})
        if job in (prof.get("deskMute") or []):      # the user switched this job's messages off
            return None
        st["inbox"] = ([msg] + (st.get("inbox") or []))[:300]
        return st
    st = _with_state(uid, add)
    if st:
        from . import alerts                         # "email me as soon as something new comes in"
        alerts.on_message(uid, st, msg)


def email_ready() -> bool:
    return bool(config.E("RESEND_API_KEY", "") or config.E("SMTP_HOST", ""))


def md_html(md: str) -> str:
    """Small markdown -> email-safe HTML: ### headings, **bold**, *italic*, [links](url), - bullets and | tables |."""
    import html as _h

    def inline(t):
        t = _h.escape(t)
        t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" style="color:#2f6fed">\1</a>', t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        return re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    out, lines, i = [], (md or "").split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[\s|:-]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            td = "padding:4px 9px;border-bottom:1px solid #e3e6ec;font-size:13px;text-align:{a}"
            out.append("<table style='border-collapse:collapse;margin:6px 0 12px'>" + "".join(
                "<tr>" + "".join(f"<{'th' if r == 0 else 'td'} style='{td.format(a='left' if k == 0 else 'right')}'>{inline(c)}</{'th' if r == 0 else 'td'}>"
                                 for k, c in enumerate(row)) + "</tr>" for r, row in enumerate(rows)) + "</table>")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", ln)
        if m:
            out.append(f"<h{min(len(m.group(1)) + 1, 4)} style='margin:16px 0 6px;font-size:{17 - len(m.group(1))}px'>{inline(m.group(2))}</h{min(len(m.group(1)) + 1, 4)}>")
        elif re.match(r"^\s*[-*•]\s+", ln):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*•]\s+", lines[i]):
                item = re.sub(r"^\s*[-*•]\s+", "", lines[i])
                items.append(f"<li>{inline(item)}</li>")
                i += 1
            out.append("<ul style='margin:4px 0 8px;padding-left:20px'>" + "".join(items) + "</ul>")
            continue
        elif ln.strip():
            out.append(f"<p style='margin:4px 0'>{inline(ln)}</p>")
        i += 1
    return "".join(out)


def send_email(to: str, subject: str, md: str, footer: str = "") -> bool:
    html = ("<div style='font-family:Segoe UI,Arial,sans-serif;font-size:14px;line-height:1.5;color:#1d2330;max-width:860px'>" + md_html(md) +
            f"<hr style='border:0;border-top:1px solid #e3e6ec;margin:18px 0 8px'><small style='color:#6b7385'>{config.APP_NAME} · research only, "
            f"not financial advice. Change what you get on the Daily Desk page.{footer}</small></div>")
    key = config.E("RESEND_API_KEY", "")
    sender = config.E("SMTP_FROM", "") or config.E("EMAIL_FROM", "") or config.COMPANY_EMAIL
    try:
        if key:
            r = requests.post("https://api.resend.com/emails", timeout=20, headers={"Authorization": f"Bearer {key}"},
                              json={"from": sender, "to": [to], "subject": subject, "html": html})
            return r.status_code < 300
        host = config.E("SMTP_HOST", "")
        if host:
            msg = MIMEText(html, "html", "utf-8")
            msg["Subject"], msg["From"], msg["To"] = subject, sender, to
            with smtplib.SMTP_SSL(host, int(config.E("SMTP_PORT", "465")), context=ssl.create_default_context(), timeout=30) as s:
                s.login(config.E("SMTP_USER", ""), config.E("SMTP_PASSWORD", ""))
                s.send_message(msg)
            return True
    except Exception as e:
        print("email failed:", e)
    return False


# ---------------------------------------------------------------- scheduler
def _last_slot(job: str, now: dt.datetime) -> dt.datetime:
    slots = []
    for back in (0, 1):
        day = (now - dt.timedelta(days=back)).date()
        for h, m in SCHEDULE[job]:
            s = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=IST)
            if s <= now:
                slots.append(s)
    return max(slots)


def next_slot(job: str, now: dt.datetime | None = None) -> dt.datetime:
    now = now or now_ist()
    cands = []
    for fwd in (0, 1):
        day = (now + dt.timedelta(days=fwd)).date()
        for h, m in SCHEDULE[job]:
            s = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=IST)
            if s > now:
                cands.append(s)
    return min(cands)


def status() -> dict:
    jobs = _load(JOBS, {})
    return {k: {**(jobs.get(k) or {}), "label": LABEL[k], "running": k in _running, "next": next_slot(k).timestamp(),
                "schedule": [f"{h:02d}:{m:02d} IST" for h, m in SCHEDULE[k]]} for k in SCHEDULE}


def run_job(job: str, background: bool = True):
    with _lock:
        if job in _running:
            return False
        _running.add(job)

    def work():
        t0 = time.time()
        try:
            res = {"roll": run_roll, "groll": run_groll, "calendar": run_calendar}[job]()
            rec = {"last": t0, "ok": True, "duration": round(time.time() - t0, 1), "result": res}
            if job == "calendar":
                rec["windowEnd"] = res["windowEnd"]
        except Exception as e:
            prev = (_load(JOBS, {}).get(job) or {})
            rec = {**prev, "last": t0, "ok": False, "error": str(e)[:300], "duration": round(time.time() - t0, 1)}
        finally:
            _running.discard(job)
        with _lock:
            jobs = _load(JOBS, {})
            jobs[job] = rec
            _save(JOBS, jobs)
    if background:
        threading.Thread(target=work, daemon=True, name=f"desk-{job}").start()
    else:
        work()
    return True


def _loop():
    time.sleep(20)                                   # let the server finish starting
    try:
        from . import alerts
        alerts.rebuild_index()
    except Exception as e:
        print("desk alerts index:", e)
    while True:
        try:
            now = now_ist()
            jobs = _load(JOBS, {})
            for job in SCHEDULE:
                last = (jobs.get(job) or {}).get("last") or 0
                if last < _last_slot(job, now).timestamp() and job not in _running:
                    run_job(job)
            from . import alerts
            alerts.tick()                            # users' own intervals (hourly, daily...) and their email digests
        except Exception as e:
            print("desk scheduler:", e)
        time.sleep(30)


_started = [False]


def start_scheduler():
    if _started[0] or config.E("CH_JOBS", "1") == "0":
        return
    _started[0] = True
    threading.Thread(target=_loop, daemon=True, name="desk-scheduler").start()
