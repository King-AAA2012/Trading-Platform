"""Pro mode: CasuallyHedge's own terminal.

Data for the terminal's functions (world indices, market map, movers, sectors, company profile, financials, peers,
analysts, earnings, owners, dividends, options, currencies, yields, rate path, commodities, crypto, calendar, news,
correlation, seasons, risk…) built only from free, public data. Every endpoint is cached so a
full screen of panels refreshing stays light on the sources. Data notes: Yahoo (prices, fundamentals, options
for US listings), US Treasury (official daily yield curve), CME fed funds futures via Yahoo (rate expectations),
ForexFactory's weekly calendar feed (economic events), Google News RSS (headlines)."""
from __future__ import annotations

import calendar
import csv
import datetime as dt
import io
import math
import re
import time
from collections import defaultdict
from urllib.parse import quote as urlquote

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from . import alerts, data, desk, extras, intl, markets, store

router = APIRouter(prefix="/api/t")


def _r(x, d=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, d) if math.isfinite(x) else None


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def _ok(o):
    return JSONResponse(_clean(o))


def _day(ts) -> str:
    return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).strftime("%Y-%m-%d")


def _scan(market: str):
    from .app import run_scan                      # late import: app imports this module
    return run_scan(market)


# ================================================================ quotes
def _nq(q: dict) -> dict:
    ccy, div = data.SUBUNIT.get(q.get("currency"), (q.get("currency") or "", 1.0))

    def pv(k):
        v = q.get(k)
        return _r(v / div, 6) if isinstance(v, (int, float)) else None
    dy = q.get("trailingAnnualDividendYield")
    return {
        "symbol": q["symbol"], "name": q.get("shortName") or q.get("longName") or q["symbol"], "type": q.get("quoteType"),
        "exchange": q.get("fullExchangeName") or q.get("exchange"), "currency": ccy, "state": q.get("marketState"), "time": q.get("regularMarketTime"),
        "price": pv("regularMarketPrice"), "change": pv("regularMarketChange"), "changePct": _r(q.get("regularMarketChangePercent"), 3),
        "open": pv("regularMarketOpen"), "high": pv("regularMarketDayHigh"), "low": pv("regularMarketDayLow"), "prevClose": pv("regularMarketPreviousClose"),
        "bid": pv("bid"), "ask": pv("ask"), "volume": q.get("regularMarketVolume"), "avgVolume": q.get("averageDailyVolume3Month"),
        "marketCap": q.get("marketCap"), "pe": _r(q.get("trailingPE"), 2), "fpe": _r(q.get("forwardPE"), 2), "pb": _r(q.get("priceToBook"), 2),
        "eps": _r(q.get("epsTrailingTwelveMonths"), 3), "divYield": _r(dy * 100, 2) if isinstance(dy, (int, float)) and dy else _r(q.get("dividendYield"), 2),
        "hi52": pv("fiftyTwoWeekHigh"), "lo52": pv("fiftyTwoWeekLow"), "chg52": _r(q.get("fiftyTwoWeekChangePercent"), 2),
        "rating": q.get("averageAnalystRating"), "sharesOut": q.get("sharesOutstanding"),
    }


def rich_quotes(symbols) -> dict:
    syms = [s for s in dict.fromkeys(symbols) if s]
    out = {}
    for i in range(0, len(syms), 50):
        chunk = syms[i:i + 50]
        j = data.cached("tq:" + ",".join(chunk), 10, lambda c=chunk: data._yget("/v7/finance/quote", {"symbols": ",".join(c)}, crumb=True))
        for q in (j or {}).get("quoteResponse", {}).get("result", []):
            if q.get("symbol"):
                out[q["symbol"]] = _nq(q)
    return out


def _ret_of(h):
    if not h or len(h["c"]) < 2:
        return None
    c, t = h["c"], h["t"]

    def back(n):
        return _r(c[-1] / c[-n - 1] - 1) if len(c) > n else None
    yr = _day(t[-1])[:4]
    first = next((i for i, x in enumerate(t) if _day(x)[:4] == yr), None)
    return {"1W": back(5), "1M": back(21), "3M": back(63), "1Y": back(252),
            "YTD": _r(c[-1] / c[first - 1] - 1) if first else None, "spark": [round(float(x), 6) for x in c[-30:]]}


def _rets(symbols) -> dict:
    """Period returns from daily history, refreshed every 30 minutes (the live day move comes from quotes)."""
    def one(s):
        return data.cached(f"tret:{s}", 1800, lambda: _ret_of(data.get_history(s, "2y")))
    syms = list(dict.fromkeys(symbols))
    return dict(zip(syms, data.POOL.map(one, syms)))


@router.get("/quotes")
def t_quotes(symbols: str):
    syms = [s.strip() for s in symbols.split(",") if s.strip()][:60]
    q, rt = rich_quotes(syms), _rets(syms)
    return _ok({"rows": [{**q[s], **{k: (rt.get(s) or {}).get(k) for k in ("1W", "1M", "YTD", "1Y", "spark")}} for s in syms if s in q], "asOf": time.time()})


# ================================================================ world stock indices (INDICES, MAP)
INDICES = {
    "Americas": [("^GSPC", "S&P 500", "United States"), ("^DJI", "Dow Jones", "United States"), ("^IXIC", "Nasdaq Comp", "United States"),
                 ("^RUT", "Russell 2000", "United States"), ("^GSPTSE", "S&P/TSX", "Canada"), ("^BVSP", "Ibovespa", "Brazil"),
                 ("^MXX", "S&P/BMV IPC", "Mexico"), ("^MERV", "Merval", "Argentina")],
    "EMEA": [("^FTSE", "FTSE 100", "United Kingdom"), ("^GDAXI", "DAX", "Germany"), ("^FCHI", "CAC 40", "France"),
             ("^STOXX50E", "Euro Stoxx 50", "Eurozone"), ("^IBEX", "IBEX 35", "Spain"), ("FTSEMIB.MI", "FTSE MIB", "Italy"),
             ("^AEX", "AEX", "Netherlands"), ("^SSMI", "SMI", "Switzerland"), ("^OMX", "OMX Stockholm 30", "Sweden"),
             ("XU100.IS", "BIST 100", "Turkey"), ("TA35.TA", "TA-35", "Israel"), ("^TASI.SR", "Tadawul All Share", "Saudi Arabia"),
             ("^J203.JO", "JSE All Share", "South Africa")],
    "Asia Pacific": [("^N225", "Nikkei 225", "Japan"), ("^HSI", "Hang Seng", "Hong Kong"), ("000001.SS", "Shanghai Comp", "China"),
                     ("^KS11", "KOSPI", "South Korea"), ("^TWII", "TAIEX", "Taiwan"), ("^NSEI", "Nifty 50", "India"), ("^BSESN", "Sensex", "India"),
                     ("^AXJO", "S&P/ASX 200", "Australia"), ("^NZ50", "NZX 50", "New Zealand"), ("^STI", "Straits Times", "Singapore"),
                     ("^JKSE", "Jakarta Comp", "Indonesia"), ("^KLSE", "FTSE Bursa KLCI", "Malaysia"), ("^SET.BK", "SET", "Thailand")],
}


@router.get("/indices")
def t_indices():
    syms = [s for rows in INDICES.values() for s, _, _ in rows]
    q, rt = rich_quotes(syms), _rets(syms)
    regions = []
    for reg, rows in INDICES.items():
        out = []
        for s, nm, country in rows:
            x, r = q.get(s) or {}, rt.get(s) or {}
            if not x.get("price"):
                continue
            out.append({"symbol": s, "name": nm, "country": country, "price": x["price"], "change": x.get("change"), "changePct": x.get("changePct"),
                        "1W": r.get("1W"), "1M": r.get("1M"), "YTD": r.get("YTD"), "1Y": r.get("1Y"), "time": x.get("time"), "state": x.get("state"),
                        "spark": r.get("spark"), "currency": x.get("currency")})
        chg = [o["changePct"] for o in out if o.get("changePct") is not None]
        regions.append({"region": reg, "avg": _r(np.mean(chg), 3) if chg else None, "rows": out})
    return _ok({"regions": regions, "asOf": time.time()})


# ================================================================ sectors: performance, day-by-day, rotation
def _grid_closes(hists: dict, n: int):
    ref = max(hists.values(), key=lambda h: len(h["t"]))
    grid = ref["t"][-(n + 1):]
    gd = grid // 86400
    out = {}
    for s, h in hists.items():
        pos = np.searchsorted(h["t"] // 86400, gd, side="right") - 1
        c = h["c"][np.maximum(pos, 0)].astype(float)
        c[pos < 0] = np.nan
        out[s] = c
    return grid, out


def _sectors(market: str, days: int) -> dict | None:
    rows, hists = _scan(market)
    by = defaultdict(list)
    for r in rows:
        if r["symbol"] in hists:
            by[r.get("sector") or "Other"].append(r)
    named = {k: v for k, v in by.items() if k not in ("", "Other", "Unknown")}
    if len(named) < 3:
        return None
    N = 260
    grid, C = _grid_closes({r["symbol"]: hists[r["symbol"]] for rs in named.values() for r in rs}, N)
    dates = [_day(t) for t in grid]
    R = {s: c[1:] / c[:-1] - 1 for s, c in C.items()}
    with np.errstate(all="ignore"):
        bench = np.concatenate([[1.0], np.cumprod(1 + np.nan_to_num(np.nanmean(np.vstack(list(R.values())), axis=0)))])
    yr = dates[-1][:4]
    ytd_i = next((i for i, d in enumerate(dates) if d[:4] == yr), 0)
    wk = list(range(len(grid) - 1, -1, -5))[::-1]
    secs, daily, cum, rot, members = [], {}, {}, [], {}
    for sec, rs in named.items():
        with np.errstate(all="ignore"):
            d = np.nan_to_num(np.nanmean(np.vstack([R[r["symbol"]] for r in rs]), axis=0))
        idx = np.concatenate([[1.0], np.cumprod(1 + d)])

        def per(n):
            return _r(idx[-1] / idx[-n - 1] - 1) if len(idx) > n else None
        day = [r["changePct"] for r in rs if r.get("changePct") is not None]
        best, worst = max(rs, key=lambda r: r["changePct"]), min(rs, key=lambda r: r["changePct"])
        secs.append({"sector": sec, "n": len(rs), "day": _r(np.mean(day) / 100) if day else None, "1W": per(5), "1M": per(21), "3M": per(63),
                     "6M": per(126), "YTD": _r(idx[-1] / idx[ytd_i - 1] - 1) if ytd_i >= 1 else None, "score": _r(np.mean([r["score"] for r in rs]), 1),
                     "adv": sum(r["changePct"] > 0 for r in rs), "dec": sum(r["changePct"] < 0 for r in rs),
                     "best": {"symbol": best["symbol"], "chg": _r(best["changePct"], 2)}, "worst": {"symbol": worst["symbol"], "chg": _r(worst["changePct"], 2)}})
        daily[sec] = [_r(x * 100, 3) for x in d[-days:]]
        cum[sec] = [_r((v / idx[-days - 1] - 1) * 100, 3) for v in idx[-days - 1:]]
        ratio = idx[wk] / bench[wk]
        rsr = [100 * ratio[k] / np.mean(ratio[max(0, k - 9):k + 1]) for k in range(len(ratio))]
        rsm = [100 * rsr[k] / np.mean(rsr[max(0, k - 3):k + 1]) for k in range(len(rsr))]
        rot.append({"sector": sec, "tail": [[_r(rsr[k], 3), _r(rsm[k], 3)] for k in range(max(0, len(rsr) - 6), len(rsr))]})
        members[sec] = [{"symbol": r["symbol"], "name": r.get("name"), "changePct": _r(r["changePct"], 2), "score": r["score"]}
                        for r in sorted(rs, key=lambda r: -r["changePct"])][:12]
    md = markets.market_def(market)
    return {"market": market, "name": md["name"], "dates": dates[-days - 1:], "sectors": sorted(secs, key=lambda s: -(s["day"] or 0)),
            "daily": daily, "cum": cum, "rotation": rot, "members": members, "asOf": time.time()}


@router.get("/sectors")
def t_sectors(market: str = "us", days: int = 30):
    days = max(5, min(int(days), 250))
    out = data.cached(f"tsec:{market}:{days}", 300, lambda: _sectors(market, days))
    if out is None and market != "us":                # crypto, FX, commodities… have no sectors: fall back to US large caps
        out = data.cached(f"tsec:us:{days}", 300, lambda: _sectors("us", days))
        if out:
            out = {**out, "fallback": True}
    if out is None:
        raise HTTPException(503, "Sector data isn't ready yet. Try again in a moment.")
    return _ok(out)


# ================================================================ market movers and what drove the index
@router.get("/movers")
def t_movers(market: str = "us"):
    def load():
        rows, hists = _scan(market)
        caps = {s: x.get("marketCap") for s, x in rich_quotes([r["symbol"] for r in rows]).items()}
        items = []
        for r in rows:
            h = hists.get(r["symbol"])
            v = float(h["v"][-1]) if h is not None and len(h["v"]) else 0.0
            av = float(np.mean(h["v"][-21:-1])) if h is not None and len(h["v"]) > 21 else 0.0
            items.append({"symbol": r["symbol"], "name": r.get("name"), "price": r["price"], "changePct": _r(r["changePct"], 3), "volume": v,
                          "relVol": _r(v / av, 2) if av else None, "value": v * r["price"], "cap": caps.get(r["symbol"]), "score": r["score"],
                          "signal": r["signal"], "sector": r.get("sector"), "newHigh52": r.get("newHigh52"), "newLow52": r.get("newLow52")})
        tot = sum(i["cap"] or 0 for i in items)
        for i in items:
            i["contrib"] = _r((i["cap"] or 0) / tot * (i["changePct"] or 0), 4) if tot else None

        def pick(key, rev=True, n=10, keep=lambda i: True):
            return sorted([i for i in items if keep(i) and i.get(key) is not None], key=lambda i: i[key], reverse=rev)[:n]
        return {"market": market, "name": markets.market_def(market)["name"], "gainers": pick("changePct"), "losers": pick("changePct", False),
                "active": pick("value"), "unusual": pick("relVol", keep=lambda i: (i["relVol"] or 0) >= 1.3),
                "highs": [i for i in items if i["newHigh52"]][:15], "lows": [i for i in items if i["newLow52"]][:15],
                "contribUp": pick("contrib"), "contribDown": pick("contrib", False), "adv": sum((i["changePct"] or 0) > 0 for i in items),
                "dec": sum((i["changePct"] or 0) < 0 for i in items), "n": len(items), "asOf": time.time()}
    return _ok(data.cached(f"tmost:{market}", 60, load))


# ================================================================ portfolio monitor
@router.get("/portfolio")
def t_portfolio():
    st = store.load()
    base = (st.get("profile") or {}).get("currency") or "USD"
    hold = [h for h in st.get("holdings", []) if h.get("symbol")]
    src = "holdings"
    if not hold:
        hold, src = [{"symbol": s} for s in (st.get("watchlist") or [])], "watchlist"
    syms = [h["symbol"] for h in hold]
    q, rt = rich_quotes(syms), _rets(syms)
    fx = {}
    rows = []
    for h in hold:
        x, r = q.get(h["symbol"]) or {}, rt.get(h["symbol"]) or {}
        px, ccy = x.get("price"), x.get("currency") or base
        if ccy not in fx:
            fx[ccy] = data.fx_rate(ccy, base) if ccy != base else 1.0
        qty, cost, sgn = h.get("qty"), h.get("avgCost"), (-1 if h.get("side") == "short" else 1)
        val = qty * px * fx[ccy] if qty and px else None
        rows.append({"symbol": h["symbol"], "name": x.get("name"), "currency": ccy, "qty": qty, "avgCost": cost, "price": px, "change": x.get("change"),
                     "changePct": x.get("changePct"), "valueBase": val, "dayBase": sgn * x["change"] * qty * fx[ccy] if qty and x.get("change") is not None else None,
                     "pnlBase": sgn * (px - cost) * qty * fx[ccy] if qty and cost and px else None, "pnlPct": sgn * (px / cost - 1) if cost and px else None,
                     "YTD": r.get("YTD"), "1M": r.get("1M"), "spark": r.get("spark"), "side": h.get("side", "long")})
    tot = sum(abs(r["valueBase"] or 0) for r in rows)
    for r in rows:
        r["weight"] = _r(abs(r["valueBase"]) / tot, 4) if tot and r["valueBase"] else (_r(1 / len(rows), 4) if src == "watchlist" and rows else None)
    return _ok({"source": src, "base": base, "rows": rows, "total": tot or None, "day": sum(r["dayBase"] or 0 for r in rows) if tot else None,
                "pnl": sum(r["pnlBase"] or 0 for r in rows) if tot else None, "asOf": time.time()})


# ================================================================ company: profile, analysts, earnings, owners
def _raw(o):
    if isinstance(o, dict):
        if "raw" in o and len(o) <= 3:
            return o["raw"]
        if not o:
            return None
        return {k: _raw(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_raw(v) for v in o]
    return o


@router.get("/company/{symbol:path}")
def t_company(symbol: str):
    mods = ("price,assetProfile,summaryDetail,defaultKeyStatistics,financialData,recommendationTrend,upgradeDowngradeHistory,earningsHistory,"
            "earningsTrend,calendarEvents,institutionOwnership,fundOwnership,majorHoldersBreakdown,insiderTransactions,netSharePurchaseActivity")

    def load():
        j = data._yget(f"/v10/finance/quoteSummary/{urlquote(symbol, safe='')}", {"modules": mods}, crumb=True)
        res = ((j or {}).get("quoteSummary", {}).get("result") or [None])[0]
        if not res:
            return None
        out = _raw(res)
        if isinstance(out.get("upgradeDowngradeHistory"), dict):
            out["upgradeDowngradeHistory"]["history"] = (out["upgradeDowngradeHistory"].get("history") or [])[:30]
        if isinstance(out.get("insiderTransactions"), dict):
            out["insiderTransactions"]["transactions"] = (out["insiderTransactions"].get("transactions") or [])[:20]
        prof = out.get("assetProfile") or {}
        prof.pop("companyOfficers", None) if not prof.get("companyOfficers") else prof.update(companyOfficers=prof["companyOfficers"][:8])
        return out
    out = data.cached(f"tsec:{symbol}", 900, load)
    if not out:
        raise HTTPException(404, f"No company data for {symbol}.")
    return _ok(out)


# ================================================================ financial statements
STATEMENT_ROWS = [("Revenue", "TotalRevenue"), ("Cost of revenue", "CostOfRevenue"), ("Gross profit", "GrossProfit"), ("R&D", "ResearchAndDevelopment"),
           ("SG&A", "SellingGeneralAndAdministration"), ("Operating income", "OperatingIncome"), ("EBITDA", "EBITDA"), ("Net income", "NetIncome"),
           ("Diluted EPS", "DilutedEPS"), ("Diluted shares", "DilutedAverageShares"), ("Operating cash flow", "OperatingCashFlow"),
           ("Capital expenditure", "CapitalExpenditure"), ("Free cash flow", "FreeCashFlow"), ("Cash & equivalents", "CashAndCashEquivalents"),
           ("Total assets", "TotalAssets"), ("Total liabilities", "TotalLiabilitiesNetMinorityInterest"), ("Total debt", "TotalDebt"),
           ("Shareholders’ equity", "StockholdersEquity")]


@router.get("/financials/{symbol:path}")
def t_financials(symbol: str, period: str = "annual"):
    pre = "quarterly" if period.startswith("q") else "annual"

    def load():
        now = int(time.time())
        j = data._yget(f"/ws/fundamentals-timeseries/v1/finance/timeseries/{urlquote(symbol, safe='')}",
                       {"type": ",".join(pre + k for _, k in STATEMENT_ROWS), "period1": now - 8 * 365 * 86400, "period2": now}, crumb=True)
        series, dates, ccy = {}, set(), None
        for r in (j or {}).get("timeseries", {}).get("result") or []:
            typ = ((r.get("meta") or {}).get("type") or [""])[0]
            for p in r.get(typ) or []:
                if p and p.get("asOfDate") and (p.get("reportedValue") or {}).get("raw") is not None:
                    series.setdefault(typ[len(pre):], {})[p["asOfDate"]] = p["reportedValue"]["raw"]
                    dates.add(p["asOfDate"])
                    ccy = ccy or p.get("currencyCode")
        if not series:
            return None
        cols = sorted(dates)[-(8 if pre == "quarterly" else 5):]
        val = lambda k, d: series.get(k, {}).get(d)  # noqa: E731
        rows = [{"label": lbl, "key": k, "values": [val(k, d) for d in cols]} for lbl, k in STATEMENT_ROWS if k in series]

        def ratio(lbl, num, den, pct=True):
            vs = [(_r(val(num, d) / val(den, d), 4) if val(num, d) is not None and val(den, d) not in (None, 0) else None) for d in cols]
            return {"label": lbl, "values": vs, "pct": pct}
        lag = 4 if pre == "quarterly" else 1
        growth = [(_r(val("TotalRevenue", cols[i]) / val("TotalRevenue", cols[i - lag]) - 1, 4)
                   if i >= lag and val("TotalRevenue", cols[i]) and val("TotalRevenue", cols[i - lag]) else None) for i in range(len(cols))]
        ratios = [{"label": "Revenue growth" + (" (YoY)" if pre == "quarterly" else ""), "values": growth, "pct": True},
                  ratio("Gross margin", "GrossProfit", "TotalRevenue"), ratio("Operating margin", "OperatingIncome", "TotalRevenue"),
                  ratio("Net margin", "NetIncome", "TotalRevenue"), ratio("FCF margin", "FreeCashFlow", "TotalRevenue"),
                  ratio("Return on equity", "NetIncome", "StockholdersEquity"), ratio("Debt / equity", "TotalDebt", "StockholdersEquity", False)]
        return {"symbol": symbol, "period": pre, "dates": cols, "rows": rows, "ratios": [x for x in ratios if any(v is not None for v in x["values"])], "currency": ccy}
    out = data.cached(f"tfa:{symbol}:{pre}", 21600, load)
    if not out:
        raise HTTPException(404, f"No financial statements for {symbol} (funds, indices, FX and crypto don't file them).")
    return _ok(out)


# ================================================================ peer comparison
def _keystats(s: str):
    def load():
        j = data._yget(f"/v10/finance/quoteSummary/{urlquote(s, safe='')}", {"modules": "defaultKeyStatistics,financialData,summaryDetail"}, crumb=True)
        res = ((j or {}).get("quoteSummary", {}).get("result") or [None])[0] or {}
        flat = {}
        for mod in res.values():
            if isinstance(mod, dict):
                for k, v in mod.items():
                    vv = v.get("raw") if isinstance(v, dict) else v
                    if isinstance(vv, (int, float)) and k not in flat:
                        flat[k] = vv
        return flat or None
    return data.cached(f"tks:{s}", 3600, load)


PEER_METRICS = ["pe", "fpe", "pb", "evEbitda", "evRev", "gm", "om", "nm", "roe", "revG", "divY", "chg52", "beta"]


@router.get("/peers/{symbol:path}")
def t_peers(symbol: str, peers: str = ""):
    def load():
        cand = [p.strip().upper() for p in peers.split(",") if p.strip()]
        if not cand:
            j = data.cached(f"tpeers:{symbol}", 86400, lambda: data._yget(f"/v6/finance/recommendationsbysymbol/{urlquote(symbol, safe='')}"))
            cand += [x["symbol"] for x in ((((j or {}).get("finance") or {}).get("result") or [{}])[0].get("recommendedSymbols") or [])]
            from .app import _scan_cache
            sector = data.info_of(symbol).get("sector")
            for _, rows, _ in list(_scan_cache.values()):
                if any(r["symbol"] == symbol for r in rows):
                    cand += [r["symbol"] for r in rows if r.get("sector") == sector and r["symbol"] != symbol]
        syms = [symbol] + [p for p in dict.fromkeys(cand) if p != symbol][:9]
        q = rich_quotes(syms)
        ks = dict(zip(syms, data.POOL.map(_keystats, syms)))
        rows = []
        for s in syms:
            x, k = q.get(s) or {}, ks.get(s) or {}
            if not x.get("price"):
                continue
            rows.append({"symbol": s, "name": x.get("name"), "price": x["price"], "currency": x.get("currency"), "changePct": x.get("changePct"),
                         "cap": x.get("marketCap"), "pe": x.get("pe") or _r(k.get("trailingPE"), 2), "fpe": x.get("fpe") or _r(k.get("forwardPE"), 2),
                         "pb": x.get("pb") or _r(k.get("priceToBook"), 2), "evEbitda": _r(k.get("enterpriseToEbitda"), 2), "evRev": _r(k.get("enterpriseToRevenue"), 2),
                         "gm": _r(k.get("grossMargins")), "om": _r(k.get("operatingMargins")), "nm": _r(k.get("profitMargins")), "roe": _r(k.get("returnOnEquity")),
                         "revG": _r(k.get("revenueGrowth")), "divY": x.get("divYield"), "chg52": x.get("chg52"), "beta": _r(k.get("beta"), 2), "rating": x.get("rating")})
        if not rows:
            return None
        peer_rows = [r for r in rows if r["symbol"] != symbol]
        med = {m: _r(np.median([r[m] for r in peer_rows if r.get(m) is not None]), 4) if any(r.get(m) is not None for r in peer_rows) else None for m in PEER_METRICS}
        avg = {m: _r(np.mean([r[m] for r in peer_rows if r.get(m) is not None]), 4) if any(r.get(m) is not None for r in peer_rows) else None for m in PEER_METRICS}
        subj = next((r for r in rows if r["symbol"] == symbol), {})
        prem = {m: _r(subj[m] / med[m] - 1, 4) if subj.get(m) is not None and med.get(m) not in (None, 0) else None for m in PEER_METRICS}
        return {"symbol": symbol, "rows": rows, "median": med, "mean": avg, "premium": prem, "asOf": time.time()}
    out = data.cached(f"tcomps:{symbol}:{peers}", 1800, load)
    if not out:
        raise HTTPException(404, f"No comparable data for {symbol}.")
    return _ok(out)


# ================================================================ option chain and busiest options
def _leg(xs):
    return [{"strike": x.get("strike"), "last": x.get("lastPrice"), "bid": x.get("bid"), "ask": x.get("ask"), "chg": _r(x.get("percentChange"), 2),
             "vol": x.get("volume") or 0, "oi": x.get("openInterest") or 0, "iv": _r(x.get("impliedVolatility"), 4), "itm": bool(x.get("inTheMoney")),
             "sym": x.get("contractSymbol")} for x in xs or []]


def _atm(calls: list, spot):
    """At-the-money call, skipping strikes whose implied volatility isn't quoted (common outside market hours)."""
    if not calls or not spot:
        return None
    near = sorted(calls, key=lambda c: abs(c["strike"] - spot))
    return next((c for c in near[:6] if (c["iv"] or 0) > 0.01), near[0])


def _chain(symbol: str, date: int | None):
    j = data._yget(f"/v7/finance/options/{urlquote(symbol, safe='')}", {"date": date} if date else None, crumb=True)
    return ((j or {}).get("optionChain", {}).get("result") or [None])[0]


@router.get("/options/{symbol:path}")
def t_options(symbol: str, date: int | None = None):
    def load():
        res = _chain(symbol, date)
        if not res or not res.get("options"):
            return None
        o = res["options"][0]
        q = res.get("quote") or {}
        spot = q.get("regularMarketPrice")
        calls, puts = _leg(o.get("calls")), _leg(o.get("puts"))
        if not calls and not puts:
            return None
        cv, pv = sum(c["vol"] for c in calls), sum(p["vol"] for p in puts)
        coi, poi = sum(c["oi"] for c in calls), sum(p["oi"] for p in puts)
        strikes = sorted({x["strike"] for x in calls + puts if x["strike"] is not None})

        def pain(k):
            return sum(max(0, k - c["strike"]) * c["oi"] for c in calls) + sum(max(0, p["strike"] - k) * p["oi"] for p in puts)
        atm = _atm(calls, spot)
        return {"symbol": symbol, "spot": spot, "currency": q.get("currency"), "changePct": _r(q.get("regularMarketChangePercent"), 2),
                "expiries": res.get("expirationDates") or [], "expiry": o.get("expirationDate"), "calls": calls, "puts": puts,
                "summary": {"callVol": cv, "putVol": pv, "callOI": coi, "putOI": poi, "pcrVol": _r(pv / cv, 3) if cv else None,
                            "pcrOI": _r(poi / coi, 3) if coi else None, "maxPain": min(strikes, key=pain) if strikes else None,
                            "atmIV": atm["iv"] if atm else None, "atmStrike": atm["strike"] if atm else None}, "asOf": time.time()}
    out = data.cached(f"topt:{symbol}:{date}", 60, load)
    if not out:
        raise HTTPException(404, f"No listed options found for {symbol}. Options data covers US-listed stocks and ETFs.")
    return _ok(out)


OPT_DEFAULT = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD", "AVGO", "NFLX", "JPM", "PLTR", "COIN", "BA", "XOM"]


def _opt_summary(s: str):
    res = _chain(s, None)
    if not res or not res.get("options"):
        return None
    o, q = res["options"][0], res.get("quote") or {}
    calls, puts = _leg(o.get("calls")), _leg(o.get("puts"))
    cv, pv = sum(c["vol"] for c in calls), sum(p["vol"] for p in puts)
    oi = sum(c["oi"] for c in calls) + sum(p["oi"] for p in puts)
    spot = q.get("regularMarketPrice")
    atm = _atm(calls, spot)
    return {"symbol": s, "price": spot, "changePct": _r(q.get("regularMarketChangePercent"), 2), "callVol": cv, "putVol": pv, "totVol": cv + pv,
            "totOI": oi, "volOI": _r((cv + pv) / oi, 3) if oi else None, "pcr": _r(pv / cv, 2) if cv else None, "atmIV": atm["iv"] if atm else None,
            "expiry": o.get("expirationDate")}


@router.get("/optionheat")
def t_optionheat(symbols: str = ""):
    syms = [s for s in symbols.split(",") if s and "." not in s and "=" not in s and not s.startswith("^") and "-" not in s] or OPT_DEFAULT
    rows = [r for r in data.POOL.map(lambda s: data.cached(f"toh:{s}", 180, lambda: _opt_summary(s)), syms[:20]) if r]
    return _ok({"rows": sorted(rows, key=lambda r: -(r["totVol"] or 0)), "asOf": time.time()})


# ================================================================ currencies: grid and strength
FX_CCYS = ["USD", "EUR", "JPY", "GBP", "CHF", "CAD", "AUD", "NZD", "CNY", "INR", "HKD", "SGD"]


@router.get("/fx")
def t_fx():
    q = rich_quotes([f"{c}=X" for c in FX_CCYS if c != "USD"])
    now, prev = {"USD": 1.0}, {"USD": 1.0}
    for c in FX_CCYS[1:]:
        x = q.get(f"{c}=X") or {}
        if x.get("price"):
            now[c], prev[c] = x["price"], x.get("prevClose") or x["price"]
    ccys = [c for c in FX_CCYS if c in now]
    matrix = [[{"rate": _r(now[col] / now[row], 6), "chg": _r(((now[col] / now[row]) / (prev[col] / prev[row]) - 1) * 100, 3)} for col in ccys] for row in ccys]
    vs = [{"ccy": c, "usdPer": _r(1 / now[c], 6), "chg": _r((prev[c] / now[c] - 1) * 100, 3)} for c in ccys if c != "USD"]
    strength = data.cached("tfx:strength", 1800, extras.currency_strength) or []
    return _ok({"ccys": ccys, "matrix": matrix, "vsUsd": sorted(vs, key=lambda x: -(x["chg"] or 0)), "strength": strength, "asOf": time.time()})


# ================================================================ rates: Treasury yields and the expected path
TENORS = [("1 Mo", 1 / 12), ("2 Mo", 2 / 12), ("3 Mo", 0.25), ("4 Mo", 1 / 3), ("6 Mo", 0.5), ("1 Yr", 1), ("2 Yr", 2), ("3 Yr", 3), ("5 Yr", 5),
          ("7 Yr", 7), ("10 Yr", 10), ("20 Yr", 20), ("30 Yr", 30)]


def _treasury(year: int) -> list[dict]:
    def load():
        r = data._session.get("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
                              f"{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv", timeout=25)
        if r.status_code != 200 or "Date" not in r.text[:60]:
            return None
        out = []
        for x in csv.DictReader(io.StringIO(r.text)):
            try:
                d = dt.datetime.strptime(x["Date"], "%m/%d/%Y").date().isoformat()
            except (KeyError, ValueError):
                continue
            out.append({"date": d, **{t: float(x[t]) for t, _ in TENORS if x.get(t) not in (None, "", "N/A")}})
        return sorted(out, key=lambda r: r["date"]) or None
    return data.cached(f"ust:{year}", 3 * 3600, load) or []


@router.get("/yields")
def t_yields():
    y = dt.date.today().year
    rows = _treasury(y - 1) + _treasury(y)
    if not rows:
        raise HTTPException(503, "The US Treasury yield curve isn't available right now.")
    last = rows[-1]
    ld = dt.date.fromisoformat(last["date"])

    def at(days):
        tgt = (ld - dt.timedelta(days=days)).isoformat()
        return next((r for r in reversed(rows) if r["date"] <= tgt), rows[0])
    curves = {lbl: {"date": r["date"], "values": [r.get(t) for t, _ in TENORS]} for lbl, r in
              (("Today", last), ("1 week ago", at(7)), ("1 month ago", at(30)), ("1 year ago", at(365)))}
    hist = [{"date": r["date"], "s2s10": _r(r["10 Yr"] - r["2 Yr"], 3), "s3m10": _r(r["10 Yr"] - r["3 Mo"], 3), "y10": r.get("10 Yr"), "y2": r.get("2 Yr")}
            for r in rows if r["date"] >= (ld - dt.timedelta(days=365)).isoformat() and r.get("10 Yr") is not None and r.get("2 Yr") is not None and r.get("3 Mo") is not None]
    live = rich_quotes(["^IRX", "^FVX", "^TNX", "^TYX"])
    return _ok({"tenors": [{"label": t, "years": yrs} for t, yrs in TENORS], "curves": curves, "hist": hist,
                "s2s10": _r(last.get("10 Yr", 0) - last.get("2 Yr", 0), 3), "s3m10": _r(last.get("10 Yr", 0) - last.get("3 Mo", 0), 3),
                "live": [{"symbol": s, "label": lbl, "yield": (live.get(s) or {}).get("price"), "chg": (live.get(s) or {}).get("change")}
                         for s, lbl in (("^IRX", "13-week"), ("^FVX", "5-year"), ("^TNX", "10-year"), ("^TYX", "30-year"))],
                "source": "US Treasury daily par yield curve (official); live yields from Yahoo", "asOf": time.time()})


@router.get("/ratepath")
def t_ratepath():
    d = dt.date.today()
    syms = []
    for k in range(13):
        y, m = divmod(d.month - 1 + k, 12)
        syms.append((f"ZQ{intl.MONTH_CODES[m]}{(d.year + y) % 100:02d}.CBT", f"{intl.MON3[m]} {(d.year + y) % 100:02d}"))
    q = rich_quotes([s for s, _ in syms])
    pts = [{"symbol": s, "month": lbl, "rate": _r(100 - q[s]["price"], 3)} for s, lbl in syms if (q.get(s) or {}).get("price")]
    if not pts:
        raise HTTPException(503, "Fed funds futures aren't available right now.")
    base = pts[0]["rate"]
    for p in pts:
        p["chgBp"] = _r((p["rate"] - base) * 100, 1)
        p["moves"] = _r((p["rate"] - base) / 0.25, 2)
    return _ok({"base": base, "points": pts, "source": "CME 30-day fed funds futures (100 − price = average rate the market expects that month)", "asOf": time.time()})


# ================================================================ commodities / crypto / roll
COMMODITIES = [("Energy", [("CL=F", "WTI crude", "CL"), ("BZ=F", "Brent crude", "BZ"), ("NG=F", "Natural gas", "NG"), ("HO=F", "Heating oil", "HO"), ("RB=F", "RBOB gasoline", "RB")]),
         ("Metals", [("GC=F", "Gold", "GC"), ("SI=F", "Silver", "SI"), ("HG=F", "Copper", "HG"), ("PL=F", "Platinum", "PL"), ("PA=F", "Palladium", "PA")]),
         ("Grains", [("ZC=F", "Corn", "ZC"), ("ZW=F", "Wheat", "ZW"), ("ZS=F", "Soybeans", "ZS"), ("ZL=F", "Soybean oil", "ZL"), ("ZM=F", "Soybean meal", "ZM")]),
         ("Softs", [("KC=F", "Coffee", "KC"), ("SB=F", "Sugar", "SB"), ("CC=F", "Cocoa", "CC"), ("CT=F", "Cotton", "CT")]),
         ("Livestock", [("LE=F", "Live cattle", "LE"), ("HE=F", "Lean hogs", "HE"), ("GF=F", "Feeder cattle", "GF")])]


@router.get("/commodities")
def t_commodities():
    syms = [s for _, xs in COMMODITIES for s, _, _ in xs]
    q, rt = rich_quotes(syms), _rets(syms)
    groll = {r["id"]: r for r in desk._load(desk.GROLL, {}).get("rows", [])}
    groups = []
    for g, xs in COMMODITIES:
        rows = []
        for s, nm, root in xs:
            x, r, rl = q.get(s) or {}, rt.get(s) or {}, groll.get(intl.US_ID.get(root, ""))
            if not x.get("price"):
                continue
            rows.append({"symbol": s, "name": nm, "root": root, "price": x["price"], "change": x.get("change"), "changePct": x.get("changePct"),
                         "1W": r.get("1W"), "1M": r.get("1M"), "YTD": r.get("YTD"), "1Y": r.get("1Y"), "spark": r.get("spark"),
                         "roll": {"ann": rl["rollAnn"], "pct": rl["rollPct"], "near": rl["near"]["month"], "next": rl["next"]["month"], "days": rl["daysNear"]} if rl else None})
        groups.append({"group": g, "rows": rows})
    return _ok({"groups": groups, "asOf": time.time()})


@router.get("/crypto")
def t_crypto():
    syms = markets.PRESETS["crypto"]["symbols"]
    q, rt = rich_quotes(syms), _rets(syms)
    rows = [{"symbol": s, "name": (q[s].get("name") or s).replace(" USD", ""), "price": q[s]["price"], "changePct": q[s].get("changePct"), "cap": q[s].get("marketCap"),
             "volume": q[s].get("volume"), "1W": (rt.get(s) or {}).get("1W"), "1M": (rt.get(s) or {}).get("1M"), "YTD": (rt.get(s) or {}).get("YTD"),
             "spark": (rt.get(s) or {}).get("spark")} for s in syms if (q.get(s) or {}).get("price")]
    rows.sort(key=lambda r: -(r["cap"] or 0))
    tot = sum(r["cap"] or 0 for r in rows)
    return _ok({"rows": rows, "totalCap": tot, "btcDominance": _r((rows[0]["cap"] or 0) / tot, 4) if rows and tot else None, "asOf": time.time()})


@router.get("/roll")
def t_roll():
    g, n = desk._load(desk.GROLL, {}), desk._load(desk.ROLL, {})
    return _ok({"global": g.get("rows", []), "sessions": g.get("sessions", {}), "benchmarks": intl.BENCHMARKS,
                "nse": [r for r in n.get("rows", []) if r["kind"] == "Index"], "nseSession": n.get("session")})


# ================================================================ economic calendar
@router.get("/calendar")
def t_calendar():
    def load():
        ev = []
        for wk in ("thisweek", "nextweek"):
            try:
                r = data._session.get(f"https://nfs.faireconomy.media/ff_calendar_{wk}.json", timeout=15)
                if r.status_code == 200:
                    ev += r.json()
            except Exception:
                pass
        out = []
        for e in ev:
            try:
                ts = dt.datetime.fromisoformat(e["date"]).timestamp()
            except (KeyError, ValueError, TypeError):
                continue
            out.append({"ts": ts, "country": e.get("country"), "title": e.get("title"), "impact": e.get("impact"),
                        "forecast": e.get("forecast") or None, "previous": e.get("previous") or None, "actual": e.get("actual") or None})
        return sorted(out, key=lambda x: x["ts"]) or None
    return _ok({"events": data.cached("teco", 1800, load) or [], "source": "ForexFactory weekly economic calendar", "asOf": time.time()})


# ================================================================ news ranked by importance
NEWS_TOPICS = {"top": "stock market", "world": "global markets economy", "us": "Wall Street stocks", "india": "Sensex Nifty stock market",
               "europe": "European stocks", "asia": "Asian markets stocks", "earnings": "quarterly earnings results", "fed": "Federal Reserve interest rates inflation",
               "bonds": "Treasury yields bond market", "fx": "dollar currencies forex", "commodities": "oil gold commodity prices",
               "crypto": "bitcoin crypto market", "mna": "merger acquisition deal", "ipo": "IPO stock market debut"}
TIER = {"Reuters": 3, "The Wall Street Journal": 3, "WSJ": 3, "Financial Times": 3, "CNBC": 2, "Barron's": 2,
        "MarketWatch": 2, "The Economic Times": 2, "Economic Times": 2, "Mint": 2, "Livemint": 2, "Business Standard": 2, "Moneycontrol": 2,
        "Nikkei Asia": 2, "Associated Press": 2, "AP News": 2, "BBC": 2, "The New York Times": 2, "Yahoo Finance": 1, "Forbes": 1,
        "Investing.com": 1, "Fortune": 1, "Business Insider": 1, "Seeking Alpha": 1, "The Hindu BusinessLine": 1, "Fox Business": 1}
HOT = re.compile(r"(?i)\b(fed|rates?|inflation|cpi|jobs|payrolls?|gdp|earnings|guidance|recession|tariffs?|crash|surges?|plunges?|record|rbi|ecb|boj|"
                 r"opec|default|bankrupt\w*|mergers?|acquisitions?|ipo|sell-?off|rally)\b")


def _gnews(q: str) -> list[dict]:
    def load():
        import feedparser
        r = data._session.get(f"https://news.google.com/rss/search?q={urlquote(q + ' when:2d')}&hl=en-US&gl=US&ceid=US:en", timeout=12)
        items = []
        for e in feedparser.parse(r.content).entries[:40]:
            src = (e.get("source") or {}).get("title") or "Google News"
            title = re.sub(r"\s+-\s+" + re.escape(src) + r"\s*$", "", e.get("title") or "")
            items.append({"title": title, "source": src, "link": e.get("link"),
                          "time": calendar.timegm(e.published_parsed) if e.get("published_parsed") else None})
        return items or None
    return data.cached(f"tgn:{q}", 600, load) or []


@router.get("/news")
def t_news(topic: str = "top", symbol: str = "", sort: str = "importance"):
    if topic == "company" and symbol:
        items = [{"title": n["title"], "source": n.get("publisher"), "link": n.get("link"), "time": n.get("time"), "symbol": symbol} for n in data.news(symbol)]
    elif topic == "my":
        st = store.load()
        syms = list(dict.fromkeys([h["symbol"] for h in st.get("holdings", []) if h.get("symbol")] + (st.get("watchlist") or [])))[:8]
        items = []
        for s, ns in zip(syms, data.POOL.map(data.news, syms)):
            items += [{"title": n["title"], "source": n.get("publisher"), "link": n.get("link"), "time": n.get("time"), "symbol": s} for n in ns[:6]]
    else:
        items = [dict(x) for x in _gnews(NEWS_TOPICS.get(topic, topic))]
    now, seen, out = time.time(), set(), []
    for it in items:
        k = (it.get("title") or "").lower()[:80]
        if not k or k in seen:
            continue
        seen.add(k)
        age = (now - (it.get("time") or now)) / 3600
        it["importance"] = _r(TIER.get(it.get("source") or "", 0) * 2 + (2 if HOT.search(it["title"]) else 0) + max(0.0, 6 - age / 4), 2)
        out.append(it)
    out.sort(key=(lambda x: -(x["time"] or 0)) if sort == "time" else (lambda x: -(x["importance"] or 0)))
    return _ok({"topic": topic, "items": out[:40], "asOf": now})


# ================================================================ analysis: correlation, seasons, risk, dividends, events
def _default_symbols() -> list[str]:
    st = store.load()
    return list(dict.fromkeys([h["symbol"] for h in st.get("holdings", []) if h.get("symbol")] + (st.get("watchlist") or [])))


@router.get("/correlation")
def t_correlation(symbols: str = "", days: int = 126):
    syms = [s for s in symbols.split(",") if s] or _default_symbols()
    syms = syms[:16]
    hs = data.many_histories(syms, "2y")
    syms = [s for s in syms if s in hs]
    if len(syms) < 2:
        raise HTTPException(400, "Add at least two symbols with price history.")
    _, C = _grid_closes({s: hs[s] for s in syms}, max(20, min(int(days), 500)))
    with np.errstate(all="ignore"):
        R = np.vstack([np.diff(np.log(C[s])) for s in syms])
    ok = np.all(np.isfinite(R), axis=0)
    R = R[:, ok]
    if R.shape[1] < 10:
        raise HTTPException(400, "Not enough overlapping history.")
    m = np.corrcoef(R)
    return _ok({"symbols": syms, "matrix": np.round(m, 3), "vol": [_r(np.std(r) * math.sqrt(252), 4) for r in R], "days": int(R.shape[1])})


@router.get("/seasons/{symbol:path}")
def t_seasons(symbol: str):
    h = data.get_history(symbol, "10y", "1mo")
    if not h or len(h["c"]) < 14:
        raise HTTPException(404, "Not enough monthly history.")
    grid = defaultdict(dict)
    for i in range(1, len(h["c"])):
        d = dt.datetime.fromtimestamp(int(h["t"][i]), dt.timezone.utc)
        grid[d.year][d.month] = _r(h["c"][i] / h["c"][i - 1] - 1)
    years = sorted(grid)
    avg, hit = [], []
    for mth in range(1, 13):
        vs = [grid[y][mth] for y in years if grid[y].get(mth) is not None]
        avg.append(_r(np.mean(vs)) if vs else None)
        hit.append(_r(np.mean([v > 0 for v in vs])) if vs else None)
    return _ok({"symbol": symbol, "years": years, "grid": {y: [grid[y].get(m) for m in range(1, 13)] for y in years}, "avg": avg, "hit": hit})


@router.get("/risk/{symbol:path}")
def t_risk(symbol: str, bench: str = ""):
    if not bench:
        from .app import _market_for
        bench = (_market_for(symbol, None) or {}).get("benchmark") or "^GSPC"
        if bench == symbol:
            bench = "^GSPC"
    a, b = data.get_history(symbol, "2y", "1wk"), data.get_history(bench, "2y", "1wk")
    if not a or not b:
        raise HTTPException(404, "Not enough history.")
    _, C = _grid_closes({"a": a, "b": b}, min(len(a["c"]), len(b["c"])) - 1)
    with np.errstate(all="ignore"):
        ra, rb = np.diff(np.log(C["a"])), np.diff(np.log(C["b"]))
    ok = np.isfinite(ra) & np.isfinite(rb)
    ra, rb = ra[ok], rb[ok]
    if len(ra) < 20:
        raise HTTPException(404, "Not enough overlapping history.")
    beta = float(np.cov(ra, rb)[0, 1] / np.var(rb, ddof=1))
    corr = float(np.corrcoef(ra, rb)[0, 1])
    return _ok({"symbol": symbol, "bench": bench, "beta": _r(beta, 3), "alpha": _r((np.mean(ra) - beta * np.mean(rb)) * 52, 4), "r2": _r(corr ** 2, 3),
                "corr": _r(corr, 3), "vol": _r(np.std(ra) * math.sqrt(52), 4), "benchVol": _r(np.std(rb) * math.sqrt(52), 4), "n": len(ra),
                "points": [[_r(x, 5), _r(y, 5)] for x, y in zip(rb[-104:], ra[-104:])]})


@router.get("/dividends/{symbol:path}")
def t_dividends(symbol: str):
    h = data.get_history(symbol, "10y", "1mo")
    if not h:
        raise HTTPException(404, "No history.")
    divs = sorted(((int(k), v) for k, v in (h.get("events") or {}).get("dividends", {}).items()), reverse=True)
    splits = sorted(((int(k), v) for k, v in (h.get("events") or {}).get("splits", {}).items()), reverse=True)
    yearly = defaultdict(float)
    for t, v in divs:
        yearly[dt.datetime.fromtimestamp(t, dt.timezone.utc).year] += v
    ttm = sum(v for t, v in divs if t >= time.time() - 365 * 86400)
    price = float(h["c"][-1])
    yrs = sorted(yearly)
    full = [y for y in yrs if y < dt.date.today().year]
    cagr = _r((yearly[full[-1]] / yearly[full[-6]]) ** (1 / 5) - 1) if len(full) >= 6 and yearly[full[-6]] > 0 else None
    return _ok({"symbol": symbol, "currency": h["meta"].get("currency"), "price": price, "ttm": _r(ttm, 4), "yield": _r(ttm / price, 4) if price else None,
                "cagr5": cagr, "dividends": [{"date": _day(t), "amount": _r(v, 4)} for t, v in divs[:40]],
                "yearly": [{"year": y, "total": _r(yearly[y], 4)} for y in yrs], "splits": [{"date": _day(t), "ratio": v} for t, v in splits]})


@router.get("/events")
def t_events(days: int = 45):
    st = store.load()
    syms = desk.tracked_symbols(st)
    return _ok({"events": alerts.upcoming(syms, desk._load(desk.CORP, {}), days=max(1, min(int(days), 120))), "tracked": len(syms)})
