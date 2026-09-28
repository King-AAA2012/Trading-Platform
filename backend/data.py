"""Market data layer. Real markets come from Yahoo Finance's public JSON endpoints (global coverage: stocks,
ETFs, indices, FX, crypto, futures). Symbols prefixed SIM: or CUS: are routed to the imaginary-market providers."""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote as urlquote

try:  # use the Windows/macOS trust store so antivirus HTTPS inspection doesn't break TLS
    import truststore
    truststore.inject_into_ssl()
except Exception:  # pragma: no cover
    pass

import numpy as np
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
Q1 = "https://query1.finance.yahoo.com"

_session = requests.Session()
_session.headers["User-Agent"] = UA
_crumb: str | None = None
_crumb_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()
POOL = ThreadPoolExecutor(max_workers=10)


def cached(key: str, ttl: float, fn):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    val = fn()
    if val is not None:
        with _cache_lock:
            _cache[key] = (now, val)
    return val


def _get_crumb(force: bool = False) -> str:
    global _crumb
    with _crumb_lock:
        if _crumb and not force:
            return _crumb
        try:
            _session.get("https://fc.yahoo.com", timeout=10)
        except requests.RequestException:
            pass
        r = _session.get(f"{Q1}/v1/test/getcrumb", timeout=10)
        _crumb = r.text.strip() if r.status_code == 200 else ""
        return _crumb


def _yget(path: str, params: dict | None = None, crumb: bool = False, timeout: float = 20):
    params = dict(params or {})
    for attempt in range(3):
        if crumb:
            params["crumb"] = _get_crumb(force=attempt > 0)
        try:
            r = _session.get(Q1 + path, params=params, timeout=timeout)
        except requests.RequestException:
            time.sleep(0.6 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (401, 403) and crumb:
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(1.2 * (attempt + 1))
            continue
        return None
    return None


# ---------------------------------------------------------------- history
def _num(xs) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in xs], dtype=np.float64)


def yahoo_history(symbol: str, rng: str = "2y", interval: str = "1d") -> dict | None:
    def load():
        j = _yget(f"/v8/finance/chart/{urlquote(symbol, safe='')}",
                  {"range": rng, "interval": interval, "includeAdjustedClose": "true", "events": "div,splits"})
        res = ((j or {}).get("chart", {}).get("result") or [None])[0]
        if not res or "timestamp" not in res:
            return None
        q = res["indicators"]["quote"][0]
        o, h, l, c, v = (_num(q.get(k, [])) for k in ("open", "high", "low", "close", "volume"))
        adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose")
        f = _num(adj) / c if adj is not None and interval in ("1d", "1wk", "1mo") else np.ones_like(c)
        f = np.where(np.isfinite(f) & (f > 0), f, 1.0)
        t = np.array(res["timestamp"], dtype=np.int64)
        keep = np.isfinite(c) & (c > 0)
        o = np.where(np.isfinite(o), o, c); h = np.where(np.isfinite(h), h, c); l = np.where(np.isfinite(l), l, c)
        m = res.get("meta", {})
        div = 100.0 if m.get("currency") == "GBp" else 1.0      # LSE quotes in pence
        return {
            "symbol": symbol, "t": t[keep], "o": (o * f / div)[keep], "h": (h * f / div)[keep], "l": (l * f / div)[keep],
            "c": (c * f / div)[keep], "v": np.nan_to_num(v[keep]),
            "meta": {"name": m.get("longName") or m.get("shortName") or symbol, "currency": "GBP" if div == 100 else m.get("currency", ""),
                     "exchange": m.get("fullExchangeName") or m.get("exchangeName", ""), "type": m.get("instrumentType", ""),
                     "price": (m.get("regularMarketPrice") or float("nan")) / div,
                     "prevClose": (m.get("chartPreviousClose") or m.get("previousClose") or float("nan")) / div,
                     "high52": (m.get("fiftyTwoWeekHigh") or float("nan")) / div, "low52": (m.get("fiftyTwoWeekLow") or float("nan")) / div},
        }
    ttl = 60 if interval not in ("1d", "1wk", "1mo") else 600
    return cached(f"hist:{symbol}:{rng}:{interval}", ttl, load)


def get_history(symbol: str, rng: str = "2y", interval: str = "1d") -> dict | None:
    if symbol.startswith("SIM:"):
        from . import simulator
        return simulator.history(symbol)
    if symbol.startswith("CUS:"):
        from . import custom
        return custom.history(symbol)
    return yahoo_history(symbol, rng, interval)


def many_histories(symbols: list[str], rng: str = "2y") -> dict[str, dict]:
    out = {}
    for s, h in zip(symbols, POOL.map(lambda x: get_history(x, rng), symbols)):
        if h is not None and len(h["c"]) >= 30:
            out[s] = h
    return out


# ---------------------------------------------------------------- quotes / fundamentals / search / news
def quotes(symbols: list[str]) -> list[dict]:
    real = [s for s in symbols if not s.startswith(("SIM:", "CUS:"))]
    out: dict[str, dict] = {}
    if real:
        def load():
            j = _yget("/v7/finance/quote", {"symbols": ",".join(real)}, crumb=True)
            return (j or {}).get("quoteResponse", {}).get("result")
        for q in cached("q:" + ",".join(real), 30, load) or []:
            div = 100.0 if q.get("currency") == "GBp" else 1.0
            out[q["symbol"]] = {"symbol": q["symbol"], "name": q.get("shortName") or q.get("longName") or q["symbol"],
                                "price": (q.get("regularMarketPrice") or 0) / div, "change": (q.get("regularMarketChange") or 0) / div,
                                "changePct": q.get("regularMarketChangePercent") or 0, "currency": "GBP" if div == 100 else q.get("currency", ""),
                                "marketState": q.get("marketState", ""), "volume": q.get("regularMarketVolume")}
    for s in symbols:  # fall back to chart data for anything the quote endpoint missed (and SIM/CUS)
        if s not in out:
            h = get_history(s, "5d") if not s.startswith(("SIM:", "CUS:")) else get_history(s)
            if h and len(h["c"]) >= 2:
                p, pc = float(h["c"][-1]), float(h["c"][-2])
                out[s] = {"symbol": s, "name": h["meta"]["name"], "price": p, "change": p - pc, "changePct": (p / pc - 1) * 100,
                          "currency": h["meta"]["currency"], "marketState": "", "volume": float(h["v"][-1])}
    return [out[s] for s in symbols if s in out]


def _raw(d: dict, k: str):
    v = d.get(k)
    if isinstance(v, dict):
        v = v.get("raw")
    return v if isinstance(v, (int, float)) else None


def fundamentals(symbol: str) -> dict:
    if symbol.startswith(("SIM:", "CUS:")):
        return {}

    def load():
        mods = "price,summaryDetail,defaultKeyStatistics,financialData,assetProfile,recommendationTrend,calendarEvents"
        j = _yget(f"/v10/finance/quoteSummary/{urlquote(symbol, safe='')}", {"modules": mods}, crumb=True)
        res = ((j or {}).get("quoteSummary", {}).get("result") or [None])[0]
        if not res:
            return {}
        sd, ks, fd, ap, pr = (res.get(k, {}) for k in ("summaryDetail", "defaultKeyStatistics", "financialData", "assetProfile", "price"))
        rt = (res.get("recommendationTrend", {}).get("trend") or [{}])[0]
        earn = (res.get("calendarEvents", {}).get("earnings", {}).get("earningsDate") or [{}])
        return {
            "name": pr.get("longName") or pr.get("shortName"), "sector": ap.get("sector"), "industry": ap.get("industry"),
            "country": ap.get("country"), "website": ap.get("website"), "employees": ap.get("fullTimeEmployees"),
            "summary": (ap.get("longBusinessSummary") or "")[:1200],
            "marketCap": _raw(pr, "marketCap") or _raw(sd, "marketCap"), "currency": pr.get("currency"),
            "trailingPE": _raw(sd, "trailingPE"), "forwardPE": _raw(sd, "forwardPE") or _raw(ks, "forwardPE"),
            "peg": _raw(ks, "pegRatio"), "priceToBook": _raw(ks, "priceToBook"), "priceToSales": _raw(sd, "priceToSalesTrailing12Months"),
            "evToEbitda": _raw(ks, "enterpriseToEbitda"), "dividendYield": _raw(sd, "dividendYield"), "beta": _raw(sd, "beta") or _raw(ks, "beta"),
            "revenueGrowth": _raw(fd, "revenueGrowth"), "earningsGrowth": _raw(fd, "earningsGrowth"),
            "profitMargin": _raw(fd, "profitMargins"), "operatingMargin": _raw(fd, "operatingMargins"), "grossMargin": _raw(fd, "grossMargins"),
            "roe": _raw(fd, "returnOnEquity"), "roa": _raw(fd, "returnOnAssets"), "debtToEquity": _raw(fd, "debtToEquity"),
            "currentRatio": _raw(fd, "currentRatio"), "freeCashflow": _raw(fd, "freeCashflow"), "totalCash": _raw(fd, "totalCash"),
            "totalDebt": _raw(fd, "totalDebt"), "revenue": _raw(fd, "totalRevenue"),
            "targetMean": _raw(fd, "targetMeanPrice"), "targetHigh": _raw(fd, "targetHighPrice"), "targetLow": _raw(fd, "targetLowPrice"),
            "recommendationMean": _raw(fd, "recommendationMean"), "recommendationKey": fd.get("recommendationKey"),
            "analysts": _raw(fd, "numberOfAnalystOpinions"),
            "ratings": {k: rt.get(k, 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")} if rt else None,
            "shortPercentFloat": _raw(ks, "shortPercentOfFloat"), "heldInstitutions": _raw(ks, "heldPercentInstitutions"),
            "nextEarnings": (earn[0] or {}).get("fmt") if earn else None,
        }
    return cached(f"fund:{symbol}", 6 * 3600, load) or {}


_meta_path = DATA_DIR / "meta_cache.json"
_meta_lock = threading.Lock()
try:
    _meta: dict = json.loads(_meta_path.read_text("utf-8"))
except Exception:
    _meta = {}


def sector_of(symbol: str) -> str:
    """Sector lookup cached on disk forever (sectors rarely change)."""
    if symbol.startswith("SIM:"):
        from . import simulator
        return simulator.sector(symbol)
    if symbol.startswith("CUS:"):
        from . import custom
        return custom.sector(symbol)
    if symbol in _meta:
        return _meta[symbol]
    f = fundamentals(symbol)
    sec = f.get("sector") or {"CRYPTOCURRENCY": "Crypto", "CURRENCY": "FX", "FUTURE": "Commodities", "ETF": "ETF",
                              "INDEX": "Index"}.get((get_history(symbol) or {}).get("meta", {}).get("type", ""), "Other")
    with _meta_lock:
        _meta[symbol] = sec
        _meta_path.write_text(json.dumps(_meta), "utf-8")
    return sec


def search(q: str) -> list[dict]:
    j = cached(f"search:{q.lower()}", 3600, lambda: _yget("/v1/finance/search", {"q": q, "quotesCount": 12, "newsCount": 0}))
    return [{"symbol": x["symbol"], "name": x.get("longname") or x.get("shortname") or x["symbol"],
             "exchange": x.get("exchDisp", ""), "type": x.get("typeDisp", "")}
            for x in (j or {}).get("quotes", []) if x.get("symbol")]


def news(symbol: str, name: str = "") -> list[dict]:
    if symbol.startswith("SIM:"):
        from . import simulator
        return simulator.news(symbol)
    if symbol.startswith("CUS:"):
        return []

    def load():
        items = []
        j = _yget("/v1/finance/search", {"q": symbol, "quotesCount": 0, "newsCount": 12})
        for n in (j or {}).get("news", []):
            items.append({"title": n.get("title"), "publisher": n.get("publisher"), "link": n.get("link"),
                          "time": n.get("providerPublishTime")})
        if len(items) < 5:
            try:
                import feedparser
                qn = urlquote(f"{name or symbol} stock")
                r = _session.get(f"https://news.google.com/rss/search?q={qn}&hl=en-US&gl=US&ceid=US:en", timeout=10)
                for e in feedparser.parse(r.content).entries[:12]:
                    items.append({"title": e.get("title"), "publisher": (e.get("source") or {}).get("title", "Google News"),
                                  "link": e.get("link"), "time": int(time.mktime(e.published_parsed)) if e.get("published_parsed") else None})
            except Exception:
                pass
        items.sort(key=lambda x: x.get("time") or 0, reverse=True)
        return items[:15]
    return cached(f"news:{symbol}", 900, load) or []


def fx_rate(frm: str, to: str) -> float:
    """Units of `to` per 1 unit of `frm`."""
    frm, to = (frm or to or "USD").upper(), (to or "USD").upper()
    if frm == to or not frm:
        return 1.0
    h = yahoo_history(f"{frm}{to}=X", "5d")
    if h and len(h["c"]):
        return float(h["c"][-1])
    h = yahoo_history(f"{to}{frm}=X", "5d")
    return 1.0 / float(h["c"][-1]) if h and len(h["c"]) else 1.0
