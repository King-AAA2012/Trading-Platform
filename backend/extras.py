"""Deep-dive analytics for one instrument and for the market as a whole.

Per stock: performance table, seasonality, return distribution, drawdown, rolling volatility, candlestick patterns,
pivot points, auto support/resistance, Fibonacci levels, Supertrend, Parabolic SAR, Keltner/Donchian channels,
dividends & splits, a Piotroski-style health checklist, fair-value estimates, a volatility price cone, expected moves,
probability of hitting target before stop, the engine's signal history, multi-timeframe scores and peers.
Market: fear & greed composite, yield curve, currency strength, world indices, sector rotation, movers and breadth.
"""
from __future__ import annotations

import math
import time

import numpy as np

from . import data, engine
from . import indicators as ta

PERIODS = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252, "3Y": 756, "5Y": 1260}


def _r(x, d=4):
    return float(round(float(x), d)) if x is not None and math.isfinite(float(x)) else None


def performance(t, c):
    out = {k: _r(c[-1] / c[-n - 1] - 1) if len(c) > n else None for k, n in PERIODS.items()}
    yr = time.gmtime(int(t[-1])).tm_year
    idx = np.flatnonzero(np.array([time.gmtime(int(x)).tm_year for x in t]) < yr)
    out["YTD"] = _r(c[-1] / c[idx[-1]] - 1) if len(idx) else None
    return out


def seasonality(t, c):
    months = np.array([time.gmtime(int(x)).tm_mon for x in t])
    years = np.array([time.gmtime(int(x)).tm_year for x in t])
    key = years * 100 + months
    last = np.flatnonzero(np.diff(key, append=key[-1] + 1))
    mc, mk = c[last], key[last]
    rets = mc[1:] / mc[:-1] - 1
    mons = mk[1:] % 100
    out = []
    for m in range(1, 13):
        r = rets[mons == m]
        out.append({"month": m, "avg": _r(r.mean()) if len(r) else None, "win": _r((r > 0).mean()) if len(r) else None, "n": int(len(r))})
    return out


def distribution(c):
    r = np.diff(np.log(c[-756:]))
    if len(r) < 30:
        return None
    hist, edges = np.histogram(r, bins=31)
    s = r.std()
    return {"bins": [_r(e, 5) for e in edges], "counts": hist.tolist(), "mean": _r(r.mean(), 5), "std": _r(s, 5),
            "skew": _r(((r - r.mean()) ** 3).mean() / (s ** 3 + 1e-12), 3), "kurt": _r(((r - r.mean()) ** 4).mean() / (s ** 4 + 1e-12) - 3, 3),
            "best": _r(r.max()), "worst": _r(r.min()), "upDays": _r((r > 0).mean(), 3), "annVol": _r(s * math.sqrt(252))}


def drawdown(t, c):
    eq = c / np.maximum.accumulate(c) - 1
    step = max(1, len(c) // 400)
    i = int(np.argmin(eq))
    return {"t": t[::step].tolist(), "dd": np.round(eq[::step], 4).tolist(), "max": _r(eq.min()), "maxDate": int(t[i]), "current": _r(eq[-1])}


def rolling_vol(t, c, n=21):
    r = np.diff(np.log(c), prepend=np.log(c[0]))
    v = ta.rolling_std(r, n) * math.sqrt(252)
    step = max(1, len(c) // 400)
    return {"t": t[n::step].tolist(), "v": np.round(v[n::step], 4).tolist(), "now": _r(v[-1]), "avg": _r(v[n:].mean())}


def patterns(t, o, h, l, c, lookback=160):
    out = []
    n = len(c)
    body = np.abs(c - o)
    rng = np.maximum(h - l, 1e-12)
    trend = ta.ema(c, 20)
    for i in range(max(3, n - lookback), n):
        up_tr, dn_tr = c[i - 1] > trend[i - 1], c[i - 1] < trend[i - 1]
        lo_sh = min(o[i], c[i]) - l[i]
        up_sh = h[i] - max(o[i], c[i])
        name = None
        if body[i] <= 0.1 * rng[i] and rng[i] > 0:
            name, bias = "Doji", "neutral"
        if lo_sh >= 2 * body[i] and up_sh <= 0.3 * body[i] + 1e-12 and dn_tr:
            name, bias = "Hammer", "bull"
        elif up_sh >= 2 * body[i] and lo_sh <= 0.3 * body[i] + 1e-12 and up_tr:
            name, bias = "Shooting star", "bear"
        if c[i] > o[i] and c[i - 1] < o[i - 1] and c[i] >= o[i - 1] and o[i] <= c[i - 1] and body[i] > body[i - 1]:
            name, bias = "Bullish engulfing", "bull"
        elif c[i] < o[i] and c[i - 1] > o[i - 1] and c[i] <= o[i - 1] and o[i] >= c[i - 1] and body[i] > body[i - 1]:
            name, bias = "Bearish engulfing", "bear"
        if c[i - 2] < o[i - 2] and body[i - 1] < 0.35 * body[i - 2] and c[i] > o[i] and c[i] > (o[i - 2] + c[i - 2]) / 2:
            name, bias = "Morning star", "bull"
        elif c[i - 2] > o[i - 2] and body[i - 1] < 0.35 * body[i - 2] and c[i] < o[i] and c[i] < (o[i - 2] + c[i - 2]) / 2:
            name, bias = "Evening star", "bear"
        if all(c[i - k] > o[i - k] and c[i - k] > c[i - k - 1] for k in range(3)):
            name, bias = "Three white soldiers", "bull"
        elif all(c[i - k] < o[i - k] and c[i - k] < c[i - k - 1] for k in range(3)):
            name, bias = "Three black crows", "bear"
        if l[i] > h[i - 1] * 1.002:
            name, bias = "Gap up", "bull"
        elif h[i] < l[i - 1] * 0.998:
            name, bias = "Gap down", "bear"
        if name:
            out.append({"t": int(t[i]), "name": name, "bias": bias, "price": _r(c[i])})
    return out


def pivots(h, l, c):
    H, L, C = h[-2], l[-2], c[-2]
    P = (H + L + C) / 3
    return {"P": _r(P), "R1": _r(2 * P - L), "R2": _r(P + H - L), "R3": _r(H + 2 * (P - L)), "S1": _r(2 * P - H), "S2": _r(P - (H - L)), "S3": _r(L - 2 * (H - P))}


def sr_levels(h, l, c, atr):
    hh, ll, cc = h[-500:], l[-500:], c[-500:]
    pts = []
    for i in range(2, len(cc) - 2):
        if hh[i] == max(hh[i - 2:i + 3]):
            pts.append(hh[i])
        if ll[i] == min(ll[i - 2:i + 3]):
            pts.append(ll[i])
    pts.sort()
    clusters = []
    for p in pts:
        if clusters and abs(p - clusters[-1][-1]) <= 0.6 * atr:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    lv = [{"price": _r(np.mean(g)), "touches": len(g)} for g in clusters if len(g) >= 2]
    px = c[-1]
    above = sorted([x for x in lv if x["price"] > px], key=lambda x: x["price"])[:4]
    below = sorted([x for x in lv if x["price"] <= px], key=lambda x: -x["price"])[:4]
    return {"resistance": above, "support": below}


def fibonacci(h, l, c, n=180):
    hi_i, lo_i = int(np.argmax(h[-n:])), int(np.argmin(l[-n:]))
    hi, lo = float(h[-n:][hi_i]), float(l[-n:][lo_i])
    up = lo_i < hi_i        # swing up: retracements measured down from the high
    lv = {}
    for f in (0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0):
        lv[f"{f * 100:.1f}%"] = _r(hi - (hi - lo) * f if up else lo + (hi - lo) * f)
    return {"direction": "up" if up else "down", "high": _r(hi), "low": _r(lo), "levels": lv}


def supertrend(h, l, c, atr, mult=3.0):
    mid = (h + l) / 2
    ub, lb = mid + mult * atr, mid - mult * atr
    st = np.zeros(len(c))
    d = np.ones(len(c))
    fu, fl = ub.copy(), lb.copy()
    for i in range(1, len(c)):
        fu[i] = ub[i] if ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1] else fu[i - 1]
        fl[i] = lb[i] if lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1] else fl[i - 1]
        d[i] = 1 if c[i] > fu[i - 1] else -1 if c[i] < fl[i - 1] else d[i - 1]
        st[i] = fl[i] if d[i] > 0 else fu[i]
    st[0] = fl[0]
    return st, d


def psar(h, l, step=0.02, mx=0.2):
    n = len(h)
    sar = np.zeros(n)
    up, af, ep = True, step, h[0]
    sar[0] = l[0]
    for i in range(1, n):
        sar[i] = sar[i - 1] + af * (ep - sar[i - 1])
        if up:
            sar[i] = min(sar[i], l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < sar[i]:
                up, sar[i], ep, af = False, ep, l[i], step
            elif h[i] > ep:
                ep, af = h[i], min(af + step, mx)
        else:
            sar[i] = max(sar[i], h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > sar[i]:
                up, sar[i], ep, af = True, ep, h[i], step
            elif l[i] < ep:
                ep, af = l[i], min(af + step, mx)
    return sar


def dividends(b, price, fx_ccy=None):
    ev = b.get("events") or {}
    divs = sorted(({"t": int(k), "amount": _r(v, 6)} for k, v in (ev.get("dividends") or {}).items()), key=lambda x: x["t"])
    splits = sorted(({"t": int(k), "ratio": v} for k, v in (ev.get("splits") or {}).items()), key=lambda x: x["t"])
    cutoff = time.time() - 365 * 86400
    ttm = sum(d["amount"] for d in divs if d["t"] >= cutoff)
    return {"dividends": divs[-24:], "splits": splits[-10:], "ttm": _r(ttm, 6), "yield": _r(ttm / price) if price and ttm else None}


def health(f):
    """Piotroski-style checklist on the fields Yahoo provides (nine binary tests)."""
    if not f:
        return None
    tests = [
        ("Profitable (ROA > 0)", f.get("roa"), lambda v: v > 0), ("Positive free cash flow", f.get("freeCashflow"), lambda v: v > 0),
        ("Positive net margin", f.get("profitMargin"), lambda v: v > 0), ("Healthy ROE (> 10%)", f.get("roe"), lambda v: v > 0.10),
        ("Revenue growing", f.get("revenueGrowth"), lambda v: v > 0), ("Earnings growing", f.get("earningsGrowth"), lambda v: v > 0),
        ("Moderate debt (D/E < 1)", f.get("debtToEquity"), lambda v: v < 100), ("Liquid (current ratio > 1)", f.get("currentRatio"), lambda v: v > 1),
        ("Cash covers 25% of debt", (f.get("totalCash") / f["totalDebt"]) if f.get("totalCash") and f.get("totalDebt") else None, lambda v: v > 0.25),
    ]
    rows = [{"test": n, "pass": bool(fn(v)) if v is not None else None} for n, v, fn in tests]
    known = [r for r in rows if r["pass"] is not None]
    score = sum(r["pass"] for r in known)
    return {"score": score, "of": len(known), "rows": rows,
            "grade": "Strong" if known and score / len(known) >= 0.78 else "Average" if known and score / len(known) >= 0.5 else "Weak"}


def fair_value(f, price):
    if not f or not price:
        return None
    est = []
    pe, pb = f.get("trailingPE"), f.get("priceToBook")
    eps = price / pe if pe and pe > 0 else None
    bvps = price / pb if pb and pb > 0 else None
    if eps and bvps:
        est.append({"method": "Graham number", "value": _r(math.sqrt(22.5 * eps * bvps), 2), "note": "√(22.5 × EPS × book value)"})
    if eps:
        g = min(max((f.get("earningsGrowth") or 0.05) * 100, 0), 20)
        est.append({"method": "Graham growth", "value": _r(eps * (8.5 + 2 * g) * 4.4 / 4.5, 2), "note": f"EPS × (8.5 + 2×{g:.0f}% growth), bond-adjusted"})
    fpe = f.get("forwardPE")
    if fpe and fpe > 0:
        feps = price / fpe
        est.append({"method": "Market multiple (18× fwd EPS)", "value": _r(feps * 18, 2), "note": "Forward EPS at a long-run average P/E"})
    if f.get("targetMean"):
        est.append({"method": "Analyst consensus", "value": _r(f["targetMean"], 2), "note": f"{f.get('analysts') or '?'} analysts"})
    if not est:
        return None
    fv = float(np.median([e["value"] for e in est]))
    return {"estimates": est, "fair": _r(fv, 2), "upside": _r(fv / price - 1), "verdict": "Undervalued" if fv > price * 1.15 else "Overvalued" if fv < price * 0.85 else "Fairly valued"}


def cone(t, c, horizons=(5, 21, 63)):
    r = np.diff(np.log(c[-253:]))
    sd, mu = r.std(), 0.0
    last, t0 = float(c[-1]), int(t[-1])
    z = {"5": -1.645, "25": -0.674, "50": 0.0, "75": 0.674, "95": 1.645}
    table = [{"days": d, **{k: _r(last * math.exp(mu * d + v * sd * math.sqrt(d)), 4) for k, v in z.items()}} for d in horizons]
    path = [{"t": t0 + int(i * 1.45 * 86400), **{k: _r(last * math.exp(v * sd * math.sqrt(i)), 4) for k, v in z.items()}} for i in range(1, 64, 2)]
    return {"table": table, "path": path, "dailyVol": _r(sd, 5), "week": _r(last * sd * math.sqrt(5), 4), "month": _r(last * sd * math.sqrt(21), 4)}


def hit_probability(c, entry, stop, target, days=60, sims=4000, seed=3):
    r = np.diff(np.log(c[-253:]))
    sd = r.std()
    rng = np.random.default_rng(seed)
    paths = entry * np.exp(np.cumsum(rng.normal(0, sd, size=(sims, days)), axis=1))
    long = target > entry
    hit_t = np.argmax(paths >= target, axis=1) if long else np.argmax(paths <= target, axis=1)
    hit_s = np.argmax(paths <= stop, axis=1) if long else np.argmax(paths >= stop, axis=1)
    reached_t = (paths >= target).any(1) if long else (paths <= target).any(1)
    reached_s = (paths <= stop).any(1) if long else (paths >= stop).any(1)
    win = reached_t & (~reached_s | (hit_t < hit_s))
    loss = reached_s & (~reached_t | (hit_s < hit_t))
    return {"target": _r(win.mean(), 3), "stop": _r(loss.mean(), 3), "neither": _r(1 - win.mean() - loss.mean(), 3), "days": days}


def signal_history(marks, t, c):
    out = []
    for i, m in enumerate(marks):
        if m["type"] not in ("buy", "short"):
            continue
        nxt = marks[i + 1] if i + 1 < len(marks) else None
        exit_px = nxt["price"] if nxt else float(c[-1])
        sgn = 1 if m["type"] == "buy" else -1
        out.append({"t": m["t"], "type": m["type"], "entry": _r(m["price"]), "exit": _r(exit_px), "exitT": nxt["t"] if nxt else None,
                    "ret": _r(sgn * (exit_px / m["price"] - 1)), "open": nxt is None})
    return out[-15:][::-1]


def resample(b, key):
    """Daily bars -> weekly ('W') or monthly ('M') bars."""
    t = b["t"]
    if key == "W":
        k = (t // 86400 + 3) // 7
    else:
        k = np.array([time.gmtime(int(x)).tm_year * 12 + time.gmtime(int(x)).tm_mon for x in t])
    last = np.flatnonzero(np.diff(k, append=k[-1] + 1))
    first = np.concatenate([[0], last[:-1] + 1])
    return {"symbol": b["symbol"], "t": t[last], "o": b["o"][first], "h": np.maximum.reduceat(b["h"], first), "l": np.minimum.reduceat(b["l"], first),
            "c": b["c"][last], "v": np.add.reduceat(b["v"], first), "meta": b.get("meta", {})}


def multi_timeframe(b, daily_score):
    out = {"Daily": daily_score}
    for name, key in (("Weekly", "W"), ("Monthly", "M")):
        rb = resample(b, key)
        out[name] = _r(engine.evaluate(rb, None, False)["score"], 1) if len(rb["c"]) >= 30 else None
    agree = [v for v in out.values() if v is not None]
    out["alignment"] = "All bullish" if agree and all(v >= 20 for v in agree) else "All bearish" if agree and all(v <= -20 for v in agree) else "Mixed"
    return out


def stock_extras(symbol: str, a: dict, b: dict, peers_rows: list[dict]) -> dict:
    t, o, h, l, c = b["t"], b["o"], b["h"], b["l"], b["c"]
    atr = ta.atr(h, l, c)
    st, sd = supertrend(h, l, c, atr)
    e20 = ta.ema(c, 20)
    step = lambda x: np.round(x, 4).tolist()  # noqa: E731
    f = a.get("fundamentals") or {}
    lv = a["levels"]
    peers = []
    for p in peers_rows[:10]:
        peers.append({k: p.get(k) for k in ("symbol", "name", "price", "currency", "changePct", "score", "signal", "ret1m", "ret3m", "ret1y", "atrPct", "rsi")})
    corr = None
    if peers_rows:
        mine = np.diff(np.log(c[-253:]))
        corr = []
        for p in peers_rows[:8]:
            ph = data.get_history(p["symbol"], "2y")
            if ph and len(ph["c"]) > 60:
                pr = np.diff(np.log(ph["c"][-253:]))
                n = min(len(pr), len(mine))
                corr.append({"symbol": p["symbol"], "corr": _r(np.corrcoef(mine[-n:], pr[-n:])[0, 1], 3)})
    return {
        "performance": performance(t, c), "seasonality": seasonality(t, c), "distribution": distribution(c), "drawdown": drawdown(t, c),
        "rollingVol": rolling_vol(t, c), "patterns": patterns(t, o, h, l, c), "pivots": pivots(h, l, c), "sr": sr_levels(h, l, c, float(atr[-1])),
        "fib": fibonacci(h, l, c), "overlays": {"supertrend": step(st), "stDir": sd.astype(int).tolist(), "psar": step(psar(h, l)),
                                                  "kcU": step(e20 + 2 * atr), "kcL": step(e20 - 2 * atr), "dcU": step(ta.rolling_max(h, 20)), "dcL": step(ta.rolling_min(l, 20)),
                                                  "sma50": step(ta.sma(c, 50)), "sma200": step(ta.sma(c, 200))},
        "hi52": _r(np.max(h[-252:])), "lo52": _r(np.min(l[-252:])), "dividends": dividends(b, float(c[-1])), "health": health(f),
        "fairValue": fair_value(f, float(c[-1])), "cone": cone(t, c),
        "hitProb": hit_probability(c, lv["entry"], lv["stop"], lv["t1"]) if a["bias"] != "neutral" else None,
        "signals": signal_history(a["series"]["marks"], t, c), "mtf": multi_timeframe(b, a["score"]), "peers": peers, "peerCorr": corr,
        "ownership": {"institutions": f.get("heldInstitutions"), "shortFloat": f.get("shortPercentFloat")},
    }


# ---------------------------------------------------------------- market overview
def _hist_ret(sym, n):
    h = data.get_history(sym, "2y")
    return float(h["c"][-1] / h["c"][-n - 1] - 1) if h and len(h["c"]) > n else None


def fear_greed(us_rows: list[dict]) -> dict:
    comps = []
    vix = data.get_history("^VIX", "2y")
    if vix:
        v = vix["c"][-252:]
        comps.append({"name": "Volatility (VIX)", "score": _r(100 - (v < v[-1]).mean() * 100, 0), "detail": f"VIX {v[-1]:.1f}, higher than {(v < v[-1]).mean() * 100:.0f}% of the past year"})
    spx = data.get_history("^GSPC", "2y")
    if spx:
        ma = spx["c"][-125:].mean()
        d = spx["c"][-1] / ma - 1
        comps.append({"name": "Market momentum", "score": _r(np.clip(50 + d * 500, 0, 100), 0), "detail": f"S&P 500 {d * 100:+.1f}% vs its 125-day average"})
    s, b = _hist_ret("SPY", 20), _hist_ret("TLT", 20)
    if s is not None and b is not None:
        comps.append({"name": "Safe-haven demand", "score": _r(np.clip(50 + (s - b) * 600, 0, 100), 0), "detail": f"Stocks {s * 100:+.1f}% vs bonds {b * 100:+.1f}% (20 days)"})
    j, i = _hist_ret("HYG", 20), _hist_ret("IEF", 20)
    if j is not None and i is not None:
        comps.append({"name": "Junk-bond demand", "score": _r(np.clip(50 + (j - i) * 1500, 0, 100), 0), "detail": f"High yield {j * 100:+.1f}% vs Treasuries {i * 100:+.1f}%"})
    g = _hist_ret("GC=F", 20)
    if g is not None and s is not None:
        comps.append({"name": "Gold vs stocks", "score": _r(np.clip(50 + (s - g) * 500, 0, 100), 0), "detail": f"Gold {g * 100:+.1f}% vs stocks {s * 100:+.1f}%"})
    if us_rows:
        bull = np.mean([r["score"] >= 20 for r in us_rows])
        above = np.mean([r.get("above200", False) for r in us_rows])
        comps.append({"name": "Breadth", "score": _r(np.clip((bull * 0.5 + above * 0.5) * 100, 0, 100), 0), "detail": f"{above * 100:.0f}% of large caps above their 200-day average"})
    score = float(np.mean([c["score"] for c in comps])) if comps else 50.0
    label = "Extreme fear" if score < 25 else "Fear" if score < 45 else "Neutral" if score <= 55 else "Greed" if score <= 75 else "Extreme greed"
    return {"score": _r(score, 0), "label": label, "components": comps}


def yield_curve():
    pts = []
    for sym, name, yrs in (("^IRX", "3M", 0.25), ("^FVX", "5Y", 5), ("^TNX", "10Y", 10), ("^TYX", "30Y", 30)):
        h = data.get_history(sym, "2y")
        if h and len(h["c"]) > 252:
            pts.append({"tenor": name, "years": yrs, "now": _r(h["c"][-1], 3), "yearAgo": _r(h["c"][-253], 3), "monthAgo": _r(h["c"][-22], 3)})
    inv = len(pts) >= 3 and pts[0]["now"] is not None and pts[2]["now"] is not None and pts[0]["now"] > pts[2]["now"]
    return {"points": pts, "inverted": inv, "spread10y3m": _r(pts[2]["now"] - pts[0]["now"], 3) if len(pts) >= 3 else None}


def currency_strength():
    pairs = {"EUR": ("EURUSD=X", 1), "GBP": ("GBPUSD=X", 1), "JPY": ("USDJPY=X", -1), "AUD": ("AUDUSD=X", 1), "CAD": ("USDCAD=X", -1),
             "CHF": ("USDCHF=X", -1), "CNY": ("USDCNY=X", -1), "INR": ("USDINR=X", -1)}
    vs_usd = {"USD": {"1W": 0.0, "1M": 0.0}}
    for ccy, (sym, sgn) in pairs.items():
        h = data.get_history(sym, "2y")
        if h and len(h["c"]) > 25:
            vs_usd[ccy] = {k: sgn * math.log(h["c"][-1] / h["c"][-n - 1]) for k, n in (("1W", 5), ("1M", 21))}
    out = []
    for c, v in vs_usd.items():   # strength = average move against every other currency
        row = {"ccy": c}
        for k in ("1W", "1M"):
            row[k] = _r(np.mean([v[k] - o[k] for cc, o in vs_usd.items() if cc != c]))
        out.append(row)
    return sorted(out, key=lambda x: -(x["1M"] or 0))


def world_indices():
    from .markets import PRESETS
    syms = PRESETS["indices"]["symbols"]
    q = {x["symbol"]: x for x in data.quotes(syms)}
    out = []
    for s, h in zip(syms, data.POOL.map(lambda s: data.get_history(s, "2y"), syms)):
        if not h:
            continue
        c = h["c"]
        out.append({"symbol": s, "name": q.get(s, {}).get("name") or h["meta"]["name"], "price": _r(c[-1], 2), "day": _r((q.get(s, {}).get("changePct") or 0) / 100),
                    "1M": _r(c[-1] / c[-22] - 1) if len(c) > 22 else None, "YTD": performance(h["t"], c)["YTD"], "1Y": _r(c[-1] / c[-253] - 1) if len(c) > 253 else None})
    return out


def sector_rotation(rows: list[dict]):
    by = {}
    for r in rows:
        by.setdefault(r.get("sector") or "Other", []).append(r)
    out = []
    for s, rs in by.items():
        f = lambda k: _r(np.mean([x[k] for x in rs if x.get(k) is not None])) if any(x.get(k) is not None for x in rs) else None  # noqa: E731
        out.append({"sector": s, "n": len(rs), "1M": f("ret1m"), "3M": f("ret3m"), "1Y": f("ret1y"), "score": _r(np.mean([x["score"] for x in rs]), 1)})
    return sorted(out, key=lambda x: -(x["3M"] or -9))


def breadth(rows):
    if not rows:
        return {}
    return {"n": len(rows), "above200": _r(np.mean([r.get("above200", False) for r in rows]), 3), "newHighs": int(sum(r.get("newHigh52", False) for r in rows)),
            "newLows": int(sum(r.get("newLow52", False) for r in rows)), "bull": _r(np.mean([r["score"] >= 20 for r in rows]), 3),
            "bear": _r(np.mean([r["score"] <= -20 for r in rows]), 3), "avgRsi": _r(np.mean([r["rsi"] for r in rows]), 1)}


def movers(rows):
    s = sorted(rows, key=lambda r: r["changePct"])
    pick = lambda xs: [{k: r.get(k) for k in ("symbol", "name", "price", "changePct", "score", "signal")} for r in xs]  # noqa: E731
    return {"gainers": pick(s[::-1][:6]), "losers": pick(s[:6])}
