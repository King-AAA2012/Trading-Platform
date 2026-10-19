"""International sources for the Daily Desk. All free, public and keyless.

Futures chains for the global roll-cost job (previous-session settlement prices):
  US         CME / CBOT / NYMEX / COMEX / ICE US   Yahoo contract-month quotes (index, rates, energy, metals, grains, softs,
                                                    livestock, FX, crypto), with open interest and expiry dates
  Japan      JPX (Osaka)                           official daily settlement CSV (Nikkei 225, TOPIX, JGB, gold, ...)
  Singapore  SGX                                   SGX derivatives API (Nikkei, FTSE China A50, FTSE Taiwan, MSCI Singapore, iron ore)
  Hong Kong  HKEX                                  daily market reports (Hang Seng, HSCEI, Hang Seng TECH)

Company filings for the results / concall / dividend tracker:
  SEC EDGAR  US listings (8-K results press releases) and foreign companies with a US listing (6-K)
  HKEXnews   Hong Kong listings
  ASX        Australian listings
"""
from __future__ import annotations

import csv
import datetime as dt
import html as _html
import io
import json
import re
import time

import requests

from . import config, data

DIR = data.DATA_DIR / "desk"
DIR.mkdir(exist_ok=True)
MONTH_CODES = "FGHJKMNQUVXZ"
MON3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CUR_SIGN = {"USD": "$", "JPY": "¥", "HKD": "HK$", "SGD": "S$", "INR": "₹"}
_web = requests.Session()
_web.headers.update({"User-Agent": data.UA, "Accept-Language": "en-US,en;q=0.9"})


def _get(url, params=None, timeout=30, as_json=False, tries=3):
    for attempt in range(tries):
        try:
            r = _web.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json() if as_json else r
            if r.status_code == 404:
                return None
        except Exception:
            pass
        if attempt < tries - 1:
            time.sleep(1 + attempt)
    return None


def _wd_back(d: dt.date) -> dt.date:
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


# ================================================================ futures chains
# root, Yahoo exchange suffix, name, asset class, actively traded months, multiplier (currency per 1.0 of price), spot symbol
US_FUT = [
    ("ES", "CME", "E-mini S&P 500", "Index", "HMUZ", 50, "^GSPC"),
    ("NQ", "CME", "E-mini Nasdaq-100", "Index", "HMUZ", 20, "^NDX"),
    ("YM", "CBT", "E-mini Dow ($5)", "Index", "HMUZ", 5, "^DJI"),
    ("RTY", "CME", "E-mini Russell 2000", "Index", "HMUZ", 50, "^RUT"),
    ("NKD", "CME", "Nikkei 225 (USD, CME)", "Index", "HMUZ", 5, "^N225"),
    ("ZT", "CBT", "2-Year T-Note", "Rates", "HMUZ", 2000, None),
    ("ZF", "CBT", "5-Year T-Note", "Rates", "HMUZ", 1000, None),
    ("ZN", "CBT", "10-Year T-Note", "Rates", "HMUZ", 1000, None),
    ("ZB", "CBT", "30-Year T-Bond", "Rates", "HMUZ", 1000, None),
    ("CL", "NYM", "WTI crude oil", "Energy", "FGHJKMNQUVXZ", 1000, None),
    ("BZ", "NYM", "Brent crude oil", "Energy", "FGHJKMNQUVXZ", 1000, None),
    ("NG", "NYM", "Henry Hub natural gas", "Energy", "FGHJKMNQUVXZ", 10000, None),
    ("HO", "NYM", "ULSD heating oil", "Energy", "FGHJKMNQUVXZ", 42000, None),
    ("RB", "NYM", "RBOB gasoline", "Energy", "FGHJKMNQUVXZ", 42000, None),
    ("GC", "CMX", "Gold", "Metals", "GJMQVZ", 100, None),
    ("SI", "CMX", "Silver", "Metals", "HKNUZ", 5000, None),
    ("HG", "CMX", "Copper", "Metals", "HKNUZ", 25000, None),
    ("PL", "NYM", "Platinum", "Metals", "FJNV", 50, None),
    ("PA", "NYM", "Palladium", "Metals", "HMUZ", 100, None),
    ("ZC", "CBT", "Corn (¢/bu)", "Agri", "HKNUZ", 50, None),
    ("ZS", "CBT", "Soybeans (¢/bu)", "Agri", "FHKNQUX", 50, None),
    ("ZW", "CBT", "Chicago wheat (¢/bu)", "Agri", "HKNUZ", 50, None),
    ("ZL", "CBT", "Soybean oil (¢/lb)", "Agri", "FHKNQUVZ", 600, None),
    ("ZM", "CBT", "Soybean meal", "Agri", "FHKNQUVZ", 100, None),
    ("KC", "NYB", "Coffee (¢/lb)", "Softs", "HKNUZ", 375, None),
    ("SB", "NYB", "Sugar No.11 (¢/lb)", "Softs", "HKNV", 1120, None),
    ("CC", "NYB", "Cocoa", "Softs", "HKNUZ", 10, None),
    ("CT", "NYB", "Cotton (¢/lb)", "Softs", "HKNVZ", 500, None),
    ("LE", "CME", "Live cattle (¢/lb)", "Livestock", "GJMQVZ", 400, None),
    ("HE", "CME", "Lean hogs (¢/lb)", "Livestock", "GJKMNQVZ", 400, None),
    ("GF", "CME", "Feeder cattle (¢/lb)", "Livestock", "FHJKQUVX", 500, None),
    ("6E", "CME", "Euro FX", "FX", "HMUZ", 125000, "EURUSD=X"),
    ("6J", "CME", "Japanese yen", "FX", "HMUZ", 12500000, "1/JPY=X"),
    ("6B", "CME", "British pound", "FX", "HMUZ", 62500, "GBPUSD=X"),
    ("6A", "CME", "Australian dollar", "FX", "HMUZ", 100000, "AUDUSD=X"),
    ("6C", "CME", "Canadian dollar", "FX", "HMUZ", 100000, "1/CAD=X"),
    ("6S", "CME", "Swiss franc", "FX", "HMUZ", 125000, "1/CHF=X"),
    ("6M", "CME", "Mexican peso", "FX", "HMUZ", 500000, "1/MXN=X"),
    ("BTC", "CME", "Bitcoin (CME)", "Crypto", "FGHJKMNQUVXZ", 5, "BTC-USD"),
    ("ETH", "CME", "Ether (CME)", "Crypto", "FGHJKMNQUVXZ", 50, "ETH-USD"),
]
EXCH = {"CME": "CME", "CBT": "CBOT", "NYM": "NYMEX", "CMX": "COMEX", "NYB": "ICE US"}
US_ID = {r[0]: f"{EXCH[r[1]]}:{r[0]}" for r in US_FUT}

# JPX product code -> symbol, name, class, yen per 1.0 of price
JPX_FUT = {
    "FUT_225": ("NK225", "Nikkei 225 (large, JPX)", "Index", 1000),
    "FUT_TPX": ("TOPIX", "TOPIX", "Index", 10000),
    "FUT_400": ("JPXN400", "JPX-Nikkei 400", "Index", 100),
    "FUT_JBL": ("JGB10", "10-year JGB", "Rates", 1_000_000),
    "FUT_GLD": ("GOLD", "Gold (1 kg, ¥/g)", "Metals", 1000),
    "FUT_PLT": ("PLAT", "Platinum (500 g, ¥/g)", "Metals", 500),
    "FUT_DBAI": ("DUBAI", "Dubai crude oil (¥/kl)", "Energy", 50),
    "FUT_RSS3": ("RSS3", "Rubber RSS3 (¥/kg)", "Agri", 5000),
}
# SGX contract code -> name, class, currency, multiplier, spot symbol
SGX_FUT = {
    "NK": ("SGX Nikkei 225 (yen)", "Index", "JPY", 500, "^N225"),
    "NU": ("SGX Nikkei 225 (USD)", "Index", "USD", 5, "^N225"),
    "CN": ("FTSE China A50", "Index", "USD", 1, "XIN9.FGI"),
    "TWN": ("FTSE Taiwan", "Index", "USD", 40, None),
    "SGP": ("MSCI Singapore", "Index", "SGD", 100, None),
    "FEF": ("Iron ore 62% Fe ($/t)", "Metals", "USD", 100, None),
}
# HKEX daily-report code -> symbol, name, HK$ per point, spot symbol
HKEX_FUT = {
    "hsif": ("HSI", "Hang Seng Index", 50, "^HSI"),
    "hhif": ("HHI", "Hang Seng China Enterprises", 50, "^HSCE"),
    "htif": ("HTI", "Hang Seng TECH", 50, "HSTECH.HK"),
}
BENCHMARKS = ["CME:ES", "CME:NQ", "JPX:NK225", "HKEX:HSI", "SGX:CN", "COMEX:GC", "NYMEX:CL", "NYMEX:BZ", "CBOT:ZN", "CME:6E", "CME:BTC"]
COMMODITY = {"Energy", "Metals", "Agri", "Softs", "Livestock"}


def _quotes(syms) -> dict:
    out = {}
    syms = list(dict.fromkeys(s for s in syms if s))
    for i in range(0, len(syms), 50):
        j = data._yget("/v7/finance/quote", {"symbols": ",".join(syms[i:i + 50])}, crumb=True)
        for q in (j or {}).get("quoteResponse", {}).get("result", []):
            out[q["symbol"]] = q
    return out


def _settle_px(q: dict):
    """Previous-session price: while a market is trading, Yahoo's previous close is the last settlement;
    once the session has closed, the regular-market price is that session's close."""
    if not q:
        return None
    if q.get("marketState") == "REGULAR":
        return q.get("regularMarketPreviousClose") or q.get("regularMarketPrice")
    return q.get("regularMarketPrice") or q.get("regularMarketPreviousClose")


def _spot(sym: str | None, quotes: dict):
    if not sym:
        return None
    inv = sym.startswith("1/")
    v = _settle_px(quotes.get(sym[2:] if inv else sym))
    return (1 / v if inv else v) if v else None


def _cme_session(q: dict) -> dt.date:
    t = q.get("regularMarketTime") or time.time()
    ct = dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(hours=-5)))       # Chicago (an hour off in winter is irrelevant here)
    d = ct.date() + dt.timedelta(days=1 if ct.hour >= 17 else 0)                  # the CME trade date starts at 17:00 Chicago time
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    if q.get("marketState") == "REGULAR":                                         # still trading: we use the previous trade date's settlement
        d = _wd_back(d - dt.timedelta(days=1))
    return d


def _next_months(cycle: str, n: int = 4) -> list[tuple[str, int, int]]:
    d, out = dt.date.today(), []
    for k in range(36):
        y, m = divmod(d.month - 1 + k, 12)
        if MONTH_CODES[m] in cycle:
            out.append((MONTH_CODES[m], d.year + y, m + 1))
            if len(out) >= n:
                break
    return out


def us_chains() -> tuple[list[dict], str | None]:
    want = {}
    for root, ex, _n, _k, cyc, *_ in US_FUT:
        for code, y, m in _next_months(cyc, 4):
            want[f"{root}{code}{y % 100:02d}.{ex}"] = (root, f"{MON3[m - 1]} {y % 100:02d}")
    spots = [r[6][2:] if r[6] and r[6].startswith("1/") else r[6] for r in US_FUT]
    q = _quotes(list(want) + spots)
    chains, session = [], None
    for root, ex, name, kind, cyc, mult, spot in US_FUT:
        cons = []
        for sym, (r, month) in want.items():
            if r != root or sym not in q:
                continue
            x = q[sym]
            px, exp = _settle_px(x), (x.get("expireIsoDate") or "")[:10]
            if px and exp:
                cons.append({"code": sym.split(".")[0], "month": month, "expiry": exp, "close": float(px), "oi": x.get("openInterest")})
                if root == "ES":
                    session = session or _cme_session(x)
        chains.append({"id": US_ID[root], "symbol": root, "name": name, "kind": kind, "market": "US", "exchange": EXCH[ex], "currency": "USD",
                       "mult": mult, "spot": _spot(spot, q), "contracts": cons})
    session = session or _wd_back(dt.date.today() - dt.timedelta(days=1))
    for c in chains:
        c["session"] = session
    return chains, session.isoformat()


def jpx_chains() -> tuple[list[dict], str | None]:
    idx = _get("https://www.jpx.co.jp/english/markets/derivatives/settlement-price/index.html")
    links = sorted(set(re.findall(r'href="([^"]*rb_e(\d{8})\.csv)"', idx.text if idx else "")), key=lambda x: x[1])
    if not links:
        raise RuntimeError("JPX settlement file not found")
    href, day = links[-1]
    r = _get("https://www.jpx.co.jp" + href if href.startswith("/") else href, timeout=60)
    if not r:
        raise RuntimeError("JPX settlement file download failed")
    session = dt.date(int(day[:4]), int(day[4:6]), int(day[6:]))
    by: dict[str, dict] = {}
    for row in csv.reader(r.content.decode("utf-8", "replace").splitlines()[3:]):
        if len(row) < 12 or not row[1].startswith("FUT_") or row[2].strip():
            continue
        prod, _, ymd = row[1].rpartition("_")
        if prod not in JPX_FUT or len(ymd) != 6:
            continue
        try:
            px = float(row[5])
            exp = dt.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:]))
        except ValueError:
            continue
        sym, name, kind, mult = JPX_FUT[prod]
        ch = by.setdefault(prod, {"id": f"JPX:{sym}", "symbol": sym, "name": name, "kind": kind, "market": "Japan", "exchange": "JPX", "currency": "JPY",
                                  "mult": mult, "spot": None, "session": session, "contracts": []})
        try:
            und = float(row[7])
            if kind == "Index" and und > 0:
                ch["spot"] = und
        except ValueError:
            pass
        cm = row[3]
        ch["contracts"].append({"code": f"{sym} {cm}", "month": f"{MON3[int(cm[4:6]) - 1]} {cm[2:4]}", "expiry": exp.isoformat(), "close": px, "oi": None})
    return list(by.values()), session.isoformat()


def sgx_chains() -> tuple[list[dict], str | None]:
    chains, sessions = [], []
    q = _quotes([v[4] for v in SGX_FUT.values()])
    for code, (name, kind, cur, mult, spot) in SGX_FUT.items():
        j = _get(f"https://api.sgx.com/derivatives/v1.0/contract-code/{code}",
                 {"order": "asc", "orderby": "delivery-month", "category": "futures", "session": "-1", "t": "1", "showTAHLines": "false"}, as_json=True)
        rows = (j or {}).get("data") or []
        lst = {}
        for x in rows:
            if x.get("symbol") and "_" not in x["symbol"] and x.get("last-trading-date"):       # skip trade-at-close (_TAIC) twins
                lst.setdefault(x["symbol"], x)
        today = dt.date.today().isoformat()
        live = sorted((x for x in lst.values() if x["last-trading-date"] >= today), key=lambda x: x["last-trading-date"])[:6]
        cons, sess = [], None
        for x in live:                                          # official daily settlement history for each contract
            h = _get(f"https://api.sgx.com/derivatives/v1.0/history/symbol/{x['symbol']}", {"days": "1w", "category": "futures"}, as_json=True)
            recs = [y for y in (h or {}).get("data") or [] if y.get("daily-settlement-price-abs") and len(y.get("base-date") or "") == 8]
            if not recs:
                continue
            last = max(recs, key=lambda y: y["base-date"])                  # base-date is the trading day the settlement belongs to
            day = f"{last['base-date'][:4]}-{last['base-date'][4:6]}-{last['base-date'][6:]}"
            sess = max(sess or "", day)
            dm = x.get("delivery-month") or ""
            cons.append({"code": x["symbol"], "month": f"{MON3[int(dm[5:7]) - 1]} {dm[2:4]}" if len(dm) >= 7 else x["symbol"], "expiry": x["last-trading-date"],
                         "close": float(last["daily-settlement-price-abs"]), "oi": last.get("open-interest"), "date": day})
        if not cons:
            continue
        # keep only contracts settled on the newest common date so the spread is like-for-like
        cons = [c for c in cons if c["date"] == sess]
        sessions.append(sess)
        chains.append({"id": f"SGX:{code}", "symbol": code, "name": name, "kind": kind, "market": "Singapore", "exchange": "SGX", "currency": cur,
                       "mult": mult, "spot": _spot(spot, q), "session": dt.date.fromisoformat(sess), "contracts": cons})
    return chains, max(sessions) if sessions else None


def _hk_expiry(year: int, month: int) -> dt.date:
    """HKEX index futures expire on the business day before the last business day of the month (holidays ignored)."""
    d = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    d = _wd_back(d)
    return _wd_back(d - dt.timedelta(days=1))


def hkex_chains() -> tuple[list[dict], str | None]:
    chains, session = [], None
    q = _quotes([v[3] for v in HKEX_FUT.values()])
    hk_today = (dt.datetime.utcnow() + dt.timedelta(hours=8)).date()
    for code, (sym, name, mult, spot) in HKEX_FUT.items():
        txt, day = None, None
        for k in range(0, 9):
            d = hk_today - dt.timedelta(days=k)
            if d.weekday() >= 5:
                continue
            r = _get(f"https://www.hkex.com.hk/eng/stat/dmstat/dayrpt/{code}{d:%y%m%d}.htm", timeout=10, tries=1)
            if r and "DAILY MARKET REPORT" in r.text:
                txt, day = r.text, d
                break
        if not txt:
            continue
        cons = []
        for line in txt.splitlines():
            m = re.match(r"^([A-Z]{3})-(\d{2})\s+(.+)$", line.strip())
            if not m or m.group(1).title() not in MON3:
                continue
            parts = m.group(3).split("|")
            if len(parts) < 3:
                continue
            num = lambda s: [float(v.replace(",", "")) for v in re.findall(r"[+-]?[\d,]+(?:\.\d+)?", s)]  # noqa: E731
            dayp, comb = num(parts[1]), num(parts[2])
            if len(dayp) < 5 or not dayp[4]:
                continue
            mon, yr = MON3.index(m.group(1).title()) + 1, 2000 + int(m.group(2))
            cons.append({"code": f"{sym} {m.group(1)}-{m.group(2)}", "month": f"{m.group(1).title()} {m.group(2)}", "expiry": _hk_expiry(yr, mon).isoformat(),
                         "close": dayp[4], "oi": comb[3] if len(comb) > 3 else None})
        session = max(session or day, day)
        chains.append({"id": f"HKEX:{sym}", "symbol": sym, "name": name, "kind": "Index", "market": "Hong Kong", "exchange": "HKEX", "currency": "HKD",
                       "mult": mult, "spot": _spot(spot, q), "session": day, "contracts": cons})
    return chains, session.isoformat() if session else None


def make_row(ch: dict) -> dict | None:
    sess = ch["session"]
    cs = sorted((c for c in ch["contracts"] if c.get("close") and c["expiry"] >= sess.isoformat()), key=lambda c: c["expiry"])
    # a front month that has already been rolled out of (tiny open interest next to the following month) isn't the roll that matters
    while len(cs) > 2 and cs[0].get("oi") is not None and cs[1].get("oi") and cs[0]["oi"] < 0.1 * cs[1]["oi"]:
        cs.pop(0)
    # an untraded serial month (zero open interest) isn't where positions roll to: use the next contract that has positions
    while len(cs) > 2 and cs[1].get("oi") == 0 and any(c.get("oi") for c in cs[2:]):
        cs.pop(1)
    if len(cs) < 2:
        return None
    near, nxt = cs[0], cs[1]
    ne, xe = dt.date.fromisoformat(near["expiry"]), dt.date.fromisoformat(nxt["expiry"])
    dn, dr = max((ne - sess).days, 0), max((xe - ne).days, 1)
    pts = nxt["close"] - near["close"]
    rp = pts / near["close"]
    spot = ch.get("spot")
    noi, xoi = near.get("oi"), nxt.get("oi")
    nd = 2 if near["close"] >= 100 else 4 if near["close"] >= 1 else 7
    keep = lambda c: {k: c.get(k) for k in ("code", "month", "expiry", "close", "oi")}  # noqa: E731
    return {
        "id": ch["id"], "symbol": ch["symbol"], "name": ch["name"], "kind": ch["kind"], "market": ch["market"], "exchange": ch["exchange"],
        "currency": ch["currency"], "session": sess.isoformat(), "spot": round(spot, nd + 1) if spot else None,
        "near": keep(near), "next": keep(nxt), "far": keep(cs[2]) if len(cs) > 2 else None,
        "daysNear": dn, "daysRoll": dr, "rollPts": round(pts, nd + 1), "rollPct": round(rp * 100, 3), "rollAnn": round(rp * 365 / dr * 100, 2),
        "lot": ch["mult"], "rollPerLot": round(pts * ch["mult"], 0),
        "carryAnn": round((near["close"] - spot) / spot * 365 / max(dn, 1) * 100, 2) if spot and ch["kind"] in ("Index", "FX", "Crypto") else None,
        "rollover": round(xoi / (noi + xoi) * 100, 1) if noi is not None and xoi is not None and noi + xoi else None,
        "decimals": nd}


SOURCES = {"US (CME/CBOT/NYMEX/COMEX/ICE US)": us_chains, "Japan (JPX)": jpx_chains, "Singapore (SGX)": sgx_chains, "Hong Kong (HKEX)": hkex_chains}


# ---------------------------------------------------------------- which futures relate to a tracked symbol
_PROXY_US = {
    "^GSPC": "ES", "^SPX": "ES", "SPY": "ES", "VOO": "ES", "IVV": "ES", "MES=F": "ES", "^NDX": "NQ", "^IXIC": "NQ", "QQQ": "NQ", "MNQ=F": "NQ",
    "^DJI": "YM", "DIA": "YM", "^RUT": "RTY", "IWM": "RTY", "NIY=F": "NKD", "GLD": "GC", "IAU": "GC", "MGC=F": "GC", "SLV": "SI", "CPER": "HG",
    "USO": "CL", "MCL=F": "CL", "BNO": "BZ", "UNG": "NG", "UGA": "RB", "CORN": "ZC", "SOYB": "ZS", "WEAT": "ZW", "IEF": "ZN", "TLT": "ZB", "SHY": "ZT",
    "EURUSD=X": "6E", "FXE": "6E", "JPY=X": "6J", "FXY": "6J", "GBPUSD=X": "6B", "AUDUSD=X": "6A", "CAD=X": "6C", "CHF=X": "6S", "MXN=X": "6M",
    "BTC-USD": "BTC", "IBIT": "BTC", "FBTC": "BTC", "MBT=F": "BTC", "ETH-USD": "ETH", "ETHA": "ETH",
}
_PROXY = {
    "^N225": ["JPX:NK225", "SGX:NK", "CME:NKD"], "1321.T": ["JPX:NK225"], "EWJ": ["JPX:NK225"], "^TOPX": ["JPX:TOPIX"], "1306.T": ["JPX:TOPIX"],
    "^HSI": ["HKEX:HSI"], "2800.HK": ["HKEX:HSI"], "^HSCE": ["HKEX:HHI"], "2828.HK": ["HKEX:HHI"], "HSTECH.HK": ["HKEX:HTI"], "3033.HK": ["HKEX:HTI"],
    "XIN9.FGI": ["SGX:CN"], "2822.HK": ["SGX:CN"], "ASHR": ["SGX:CN"], "^TWII": ["SGX:TWN"], "EWT": ["SGX:TWN"], "^STI": ["SGX:SGP"], "ES3.SI": ["SGX:SGP"],
    "EWS": ["SGX:SGP"], "TIO=F": ["SGX:FEF"],
}


def futures_for(sym: str) -> list[str]:
    s = (sym or "").upper()
    if s in _PROXY:
        return _PROXY[s]
    root = _PROXY_US.get(s) or (s[:-2] if s.endswith("=F") and s[:-2] in US_ID else None)
    return [US_ID[root]] if root else []


# ================================================================ company filings
SEC_TICKERS = DIR / "sec_tickers.json"
_sec = requests.Session()
_sec_last = [0.0]


def _sec_ua() -> str:
    return config.E("SEC_USER_AGENT", "") or f"{config.APP_NAME} research {config.COMPANY_EMAIL}"


def sec_get(url: str, as_json: bool = True):
    for attempt in range(3):
        wait = 0.15 - (time.time() - _sec_last[0])           # SEC fair-access limit is 10 requests/second
        if wait > 0:
            time.sleep(wait)
        _sec_last[0] = time.time()
        try:
            r = _sec.get(url, timeout=30, headers={"User-Agent": _sec_ua(), "Accept-Encoding": "gzip, deflate"})
            if r.status_code == 200:
                return r.json() if as_json else r.text
            if r.status_code == 404:
                return None
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


_SUFFIX = r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|se|ag|nv|sa|asa|ab|oyj|spa|kk|kabushiki|kaisha|holdings?|group|the|adr|ads|new|tw)\b"


def _norm_name(n: str) -> str:
    n = re.sub(r"/[a-z]{2,4}/?$", "", (n or "").lower())
    n = re.sub(r"[^a-z0-9 ]", " ", n.replace("&", " and "))
    return " ".join(re.sub(_SUFFIX, " ", n).split())


def _sec_map() -> dict:
    try:
        m = json.loads(SEC_TICKERS.read_text("utf-8"))
        if time.time() - m.get("t", 0) < 7 * 86400:
            return m
    except Exception:
        m = None
    j = sec_get("https://www.sec.gov/files/company_tickers.json")
    if not j:
        return m or {"tickers": {}, "names": {}}
    tick, names = {}, {}
    for v in j.values():
        tick.setdefault(v["ticker"].upper(), v["cik_str"])
        names.setdefault(_norm_name(v["title"]), v["cik_str"])
    m = {"t": time.time(), "tickers": tick, "names": names}
    SEC_TICKERS.write_text(json.dumps(m), "utf-8")
    return m


def sec_cik(sym: str, name: str | None) -> int | None:
    m = _sec_map()
    if "." not in sym:                                        # a US listing: match the ticker
        return m["tickers"].get(sym.upper())
    return m["names"].get(_norm_name(name)) if name and _norm_name(name) else None   # foreign listing: same company's SEC filings (ADR)


def _iso_ts(s: str) -> float:
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return time.time()


def html_text(raw: str, max_chars: int = 16000) -> str:
    t = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", raw or "")
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|table)>", "\n", t)
    t = _html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"[ \t\xa0​]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()[:max_chars]


def sec_filings(cik: int, since_ts: float) -> tuple[list[dict], str | None]:
    """8-K / 6-K filings since a time, newest last. 8-K item 2.02 = results; anything else is classified from its text."""
    j = sec_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    if not j:
        return [], None
    rec = j.get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(rec.get("form", [])):
        if form not in ("8-K", "6-K"):
            continue
        ts = _iso_ts(rec["acceptanceDateTime"][i])
        if ts < since_ts:
            continue
        items = rec["items"][i] or ""
        if form == "8-K" and not re.search(r"2\.02|7\.01|8\.01", items):
            continue                                           # officer changes, votes, debt etc.
        acc = rec["accessionNumber"][i]
        folder = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/"
        out.append({"id": "sec:" + acc, "acc": acc, "ts": ts, "form": form, "items": items, "kind": "result" if "2.02" in items else "?",
                    "title": "Results press release (8-K item 2.02)" if "2.02" in items else f"{form} filing" + (f" (item {items})" if items else ""),
                    "link": folder + rec["primaryDocument"][i], "folder": folder, "primary": rec["primaryDocument"][i]})
    return sorted(out, key=lambda f: f["ts"]), j.get("name")


def sec_text(f: dict) -> tuple[str, str]:
    """Text of the press-release exhibit (EX-99.x) when there is one, else the main document. Returns (text, url)."""
    url = None
    idx = sec_get(f"{f['folder']}{f['acc']}-index.htm", as_json=False) or ""     # the filing index names each document's type
    for row in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", idx):
        cells = re.findall(r"(?is)<td[^>]*>(.*?)</td>", row)
        href = re.search(r'href="([^"]+\.(?:htm|html|txt))"', row, re.I)
        if href and len(cells) >= 4 and re.sub(r"<[^>]+>|\s", "", cells[3]).upper().startswith("EX-99"):
            url = "https://www.sec.gov" + href.group(1) if href.group(1).startswith("/") else f["folder"] + href.group(1).rsplit("/", 1)[-1]
            break
    if not url:
        ix = sec_get(f["folder"] + "index.json") or {}
        names = sorted(x["name"] for x in ix.get("directory", {}).get("item", [])
                       if re.search(r"(?i)ex[-_]?99|dex99", x["name"]) and x["name"].lower().endswith((".htm", ".html", ".txt")))
        url = f["folder"] + (names[0] if names else f["primary"])
    url = re.sub(r"/ix\?doc=", "", url)
    return html_text(sec_get(url, as_json=False) or ""), url


def classify_text(t: str) -> str | None:
    head = re.sub(r"\s+", " ", t[:2500])
    if re.search(r"(?i)\btranscript\b", head[:800]):
        return "transcript"
    if re.search(r"(?i)\b(reports?|announces?|posts?|delivers?|releases?)\b[^.]{0,90}\b(results|earnings)\b", head) or \
            re.search(r"(?i)\b(first|second|third|fourth|q[1-4]|full[- ]year|half[- ]year|interim|annual|quarterly|fiscal)\b[^.]{0,50}\b(financial )?(results|earnings)\b", head) or \
            re.search(r"(?i)\b(quarterly statement|half[- ]year(ly)? (financial )?(report|statement)|interim (financial )?(report|statement)|earnings release|"
                      r"q[1-4] (fy)?\s?\d{2,4} (results|statement|earnings|report))\b", head[:600]):
        return "result"
    if re.search(r"(?i)\bdeclare[sd]?\b[^.]{0,90}\bdividend|\bdividend of (us)?\$", head):
        return "dividend"
    if re.search(r"(?i)conference call|earnings call|webcast", head):
        return "concall"
    return None


def hkex_stock_id(code5: str) -> int | None:
    r = _get("https://www1.hkexnews.hk/search/prefix.do", {"callback": "callback", "lang": "EN", "type": "A", "name": code5, "market": "SEHK"}, timeout=20)
    m = re.search(r"callback\((.*)\)", r.text if r else "", re.S)
    try:
        for s in json.loads(m.group(1)).get("stockInfo", []):
            if s.get("code") == code5:
                return s["stockId"]
    except Exception:
        pass
    return None


def hkex_filings(stock_id: int, since_ts: float) -> list[dict]:
    hk = dt.timezone(dt.timedelta(hours=8))
    frm = dt.datetime.fromtimestamp(since_ts, hk)
    j = _get("https://www1.hkexnews.hk/search/titleSearchServlet.do", {
        "sortDir": "0", "sortByOptions": "DateTime", "category": "0", "market": "SEHK", "stockId": str(stock_id), "documentType": "-1",
        "fromDate": f"{frm:%Y%m%d}", "toDate": f"{dt.datetime.now(hk):%Y%m%d}", "title": "", "searchType": "0", "t1code": "-2", "t2Gcode": "-2",
        "t2code": "-2", "rowRange": "200", "lang": "E"}, as_json=True)
    try:
        rows = json.loads(j["result"]) if isinstance((j or {}).get("result"), str) else (j or {}).get("result") or []
    except Exception:
        rows = []
    out = []
    for x in rows:
        try:
            ts = dt.datetime.strptime(x["DATE_TIME"], "%d/%m/%Y %H:%M").replace(tzinfo=hk).timestamp()
        except (KeyError, ValueError):
            continue
        title, cat = _html.unescape(x.get("TITLE") or ""), _html.unescape(x.get("LONG_TEXT") or "")
        kind = classify_hkex(title, cat)
        if kind and ts >= since_ts:
            out.append({"id": "hk:" + (x.get("FILE_LINK") or title), "ts": ts, "kind": kind, "title": title.title() if title.isupper() else title,
                        "link": "https://www1.hkexnews.hk" + x["FILE_LINK"] if x.get("FILE_LINK") else None})
    return sorted(out, key=lambda f: f["ts"])


def classify_hkex(title: str, cat: str) -> str | None:
    if re.search(r"(?i)supplemental|clarification|correction|annual report|interim report|esg|next day disclosure|monthly return", title + " " + cat):
        return None
    if re.search(r"(?i)\[(final|interim|quarterly) results\]", cat) or \
            re.search(r"(?i)\b(annual|interim|quarterly|final|half[- ]year|(first|second|third|fourth) quarter( and \w+ months)?) results\b|results announcement|announcement of (the )?(\w+ )?results", title):
        return "result"
    if re.search(r"(?i)transcript", title):
        return "transcript"
    if re.search(r"(?i)conference call|webcast|results presentation|earnings call|analyst briefing", title):
        return "concall"
    if re.search(r"(?i)date of board meeting", title + " " + cat):
        return "calendar"
    if re.search(r"(?i)\[dividend or distribution\]", cat) or re.search(r"(?i)\bdividend\b", title):
        return "dividend"
    return None


def asx_filings(code: str, since_ts: float) -> list[dict]:
    """Six months of headlines from ASX's announcements list; the PDF text is available for the latest few (ASX's public file API).
    ASX's conditions allow free use for private / personal purposes; a commercial site needs ASX's agreement (FILING_SOURCES in .env)."""
    syd = dt.timezone(dt.timedelta(hours=10))
    files = {}
    j = _get(f"https://asx.api.markitdigital.com/asx-research/1.0/companies/{code.lower()}/announcements", as_json=True, tries=2)
    for x in ((j or {}).get("data") or {}).get("items") or []:
        if x.get("documentKey"):
            files[(x.get("headline") or "").strip().lower()] = f"https://asx.api.markitdigital.com/asx-research/1.0/file/{x['documentKey']}"
    r = _get("https://www.asx.com.au/asx/v2/statistics/announcements.do", {"by": "asxCode", "asxCode": code.upper(), "timeframe": "D", "period": "M6"}, tries=2)
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text if r else "", re.S):
        cells = [re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        link = re.search(r'href="([^"]*idsId=(\d+)[^"]*)"', row)
        if len(cells) < 3 or not link:
            continue
        try:
            ts = dt.datetime.strptime(cells[0], "%d/%m/%Y %I:%M %p").replace(tzinfo=syd).timestamp()
        except ValueError:
            continue
        title = re.sub(r"\s+\d+ pages?\s+[\d.,]+\s*[KM]B\s*$", "", cells[2]).strip()
        kind = classify_asx(title, "")
        if kind and ts >= since_ts:
            out.append({"id": "asx:" + link.group(2), "ts": ts, "kind": kind, "title": title, "sensitive": "pricesens" in row.lower(),
                        "link": "https://www.asx.com.au" + _html.unescape(link.group(1)), "file": files.get(title.lower())})
    return sorted(out, key=lambda f: f["ts"])


def classify_asx(title: str, cat: str) -> str | None:
    if re.search(r"(?i)transcript", title):
        return "transcript"
    if re.search(r"(?i)appendix 4[cde]\b|(half|full)[- ]?year (results|report|financial)|annual results|financial results|results (announcement|release|presentation)|"
                 r"\b(1h|2h|h1|h2|fy|hy)\s?'?\d{2,4}\s+results?\b|quarterly (activities |production |cash ?flow )?report|operational review", title):
        return "result"
    if cat.upper() == "DISTRIBUTION ANNOUNCEMENT" or re.search(r"(?i)dividend/distribution|\bdividend\b", title):
        return "dividend"
    if re.search(r"(?i)(results|earnings|investor|analyst) (briefing|call|webcast|teleconference)|teleconference|webcast|conference call", title):
        return "concall"
    return None


def filing_source(sym: str) -> str | None:
    """Which official filing source covers a symbol. FILING_SOURCES (.env) lists the enabled ones (default: sec,hkex,asx)."""
    on = {x.strip().lower() for x in config.E("FILING_SOURCES", "sec,hkex,asx").split(",")}
    if sym.startswith("^") or sym.endswith(("=X", "=F", "-USD")):
        return None
    if sym.endswith(".HK"):
        return "hkex" if "hkex" in on else None
    if sym.endswith(".AX"):
        return "asx" if "asx" in on else None
    if "sec" not in on:
        return None
    return "sec" if "." not in sym else "sec-adr"
