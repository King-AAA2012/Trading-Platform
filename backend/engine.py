"""TradeScope Alpha engine.

Seven technical factors, each scaled to [-1, +1], are computed for EVERY bar of history (vectorised), blended into a
composite score in [-100, +100]. Because the score exists for every past day, each recommendation carries its own
walk-forward track record on that instrument, which is what the confidence number is calibrated from.
Optionally a fundamentals score (valuation, growth, profitability, balance sheet, analyst view) is blended in.
"""
from __future__ import annotations

import math

import numpy as np

from . import indicators as ta

FACTORS = [  # key, label, weight, beginner explanation
    ("trend", "Trend", 0.24, "Is the price generally heading up or down over weeks and months?"),
    ("momentum", "Momentum", 0.18, "How strongly has the price moved over the last 3-12 months, adjusted for how jumpy it is?"),
    ("relative", "Relative strength", 0.12, "Is it beating or lagging the overall market?"),
    ("breakout", "Breakout / range", 0.14, "Is it pushing to new highs (bullish) or breaking to new lows (bearish)?"),
    ("macd", "MACD impulse", 0.10, "Is short-term buying pressure speeding up or slowing down?"),
    ("reversion", "RSI / stretch", 0.11, "Has it been over-sold (possible bounce) or over-bought (possible pullback)?"),
    ("volume", "Volume flow", 0.11, "Are big volumes flowing in on up days (accumulation) or down days (distribution)?"),
]
BUY_T, SELL_T = 20.0, -20.0


def _tanh(x):
    return np.tanh(np.nan_to_num(x, nan=0.0, posinf=3.0, neginf=-3.0))


def _align_bench(t: np.ndarray, bench: dict | None) -> np.ndarray | None:
    if not bench or len(bench["c"]) < 30:
        return None
    bd, bc = bench["t"] // 86400, bench["c"]
    pos = np.searchsorted(bd, t // 86400, side="right") - 1
    ok = pos >= 0
    if ok.mean() < 0.8:
        return None
    out = np.where(ok, bc[np.maximum(pos, 0)], bc[0])
    return out


def factor_series(b: dict, bench: dict | None = None) -> dict:
    o, h, l, c, v = b["o"], b["h"], b["l"], b["c"], b["v"]
    n = len(c)
    e20, e50, e200 = ta.ema(c, 20), ta.ema(c, 50), ta.ema(c, 200)
    a = ta.atr(h, l, c)
    lr = np.diff(np.log(c), prepend=np.log(c[0]))
    vol = np.maximum(ta.rolling_std(lr, 20), 1e-4)
    vol = np.maximum(vol, 0.5 * np.nanmedian(vol))

    # 1 trend
    t20, t50, t200 = _tanh((c - e20) / a / 2), _tanh((c - e50) / a / 3), _tanh((c - e200) / a / 4)
    align = np.where(e20 > e50, 0.5, -0.5) + np.where(e50 > e200, 0.5, -0.5)
    slope = _tanh((e50 / ta.shift(e50, 10) - 1) / (vol * math.sqrt(10)))
    adx, pdi, ndi = ta.adx(h, l, c)
    strength = np.clip((adx - 15) / 20, 0, 1)
    trend = (0.2 * t20 + 0.2 * t50 + 0.2 * t200 + 0.25 * align + 0.15 * slope) * (0.65 + 0.35 * strength)

    # 2 momentum (volatility-adjusted, 12-1 month excludes the last month's reversal effect)
    def mom(k, skip=0):
        r = ta.shift(c, skip) / ta.shift(c, k) - 1 if skip else c / ta.shift(c, k) - 1
        return _tanh(r / (vol * math.sqrt(k - skip)) / 1.5)
    momentum = 0.4 * mom(min(63, n - 1)) + 0.3 * mom(min(126, n - 1)) + 0.3 * mom(min(252, n - 1), min(21, n // 4))

    # 3 relative strength vs benchmark
    bc = _align_bench(b["t"], bench)
    if bc is not None:
        rel = 0.6 * _tanh(((c / ta.shift(c, 63)) / (bc / ta.shift(bc, 63)) - 1) / (vol * math.sqrt(63)) / 1.2) \
            + 0.4 * _tanh(((c / ta.shift(c, 21)) / (bc / ta.shift(bc, 21)) - 1) / (vol * math.sqrt(21)) / 1.2)
    else:
        rel = None

    # 4 breakout / 52-week range position
    hi, lo = ta.rolling_max(h, 252), ta.rolling_min(l, 252)
    pos = (c - lo) / np.maximum(hi - lo, 1e-12)
    newhigh = c > ta.shift(ta.rolling_max(h, 55), 1)
    newlow = c < ta.shift(ta.rolling_min(l, 55), 1)
    has_vol = float(np.nansum(v)) > 0
    surge = v / np.maximum(ta.sma(v, 50), 1) if has_vol else np.ones(n)
    recent_high = ta.rolling_max(newhigh.astype(float), 10) > 0
    recent_low = ta.rolling_max(newlow.astype(float), 10) > 0
    breakout = np.clip(0.5 * (pos * 2 - 1) + 0.35 * recent_high - 0.35 * recent_low
                       + 0.15 * (newhigh & (surge > 1.5)) - 0.15 * (newlow & (surge > 1.5)), -1, 1)

    # 5 MACD impulse
    ml, ms, mh = ta.macd(c)
    macd = 0.7 * _tanh(mh / a * 4) + 0.3 * np.sign(mh - ta.shift(mh, 3))

    # 6 RSI / Bollinger stretch, interpreted in the context of the trend
    r = ta.rsi(c)
    bu, bm, bl = ta.bollinger(c)
    z = (c - bm) / np.maximum((bu - bm) / 2, 1e-12)
    rev = np.where((trend > 0.15) & (r < 45), (45 - r) / 15, 0.0)
    rev -= np.where((trend < -0.15) & (r > 55), (r - 55) / 15, 0.0)
    rev -= np.where(r > 75, (r - 75) / 10, 0.0)
    rev += np.where(r < 25, (25 - r) / 10, 0.0)
    rev += -0.25 * np.clip(z - 2, 0, 2) + 0.25 * np.clip(-z - 2, 0, 2)
    reversion = np.clip(rev, -1, 1)

    # 7 volume flow
    if has_vol:
        ob = ta.obv(c, v)
        d = np.diff(c, prepend=c[0])
        flow = np.clip((ob - ta.shift(ob, 20)) / np.maximum(ta.sma(v, 20) * 20, 1), -1, 1)
        ud = ta.sma(np.where(d > 0, v, 0.0), 20) / np.maximum(ta.sma(np.where(d < 0, v, 0.0), 20), 1)
        volume = 0.5 * flow + 0.5 * _tanh(np.log(np.maximum(ud, 1e-6)))
    else:
        volume = None

    f = {"trend": trend, "momentum": momentum, "relative": rel, "breakout": breakout, "macd": macd,
         "reversion": reversion, "volume": volume}
    num = np.zeros(n)
    den = 0.0
    for k, _, w, _ in FACTORS:
        if f[k] is not None:
            num += w * f[k]
            den += w
    score = np.clip(100 * num / den, -100, 100)
    return {"f": f, "score": score, "ind": {"e20": e20, "e50": e50, "e200": e200, "atr": a, "adx": adx, "pdi": pdi, "ndi": ndi,
            "rsi": r, "bbu": bu, "bbm": bm, "bbl": bl, "macd": ml, "macds": ms, "macdh": mh, "vol": vol, "surge": surge,
            "hi52": hi, "lo52": lo, "newhigh": newhigh, "newlow": newlow, "pos52": pos}}


# ---------------------------------------------------------------- backtest
def positions(score: np.ndarray, shortable: bool) -> np.ndarray:
    """Hysteresis: enter long at >= +20, exit below +5; enter short at <= -20, exit above -5."""
    p = np.zeros(len(score))
    cur = 0
    for i, s in enumerate(score):
        if cur == 0:
            if s >= BUY_T:
                cur = 1
            elif shortable and s <= SELL_T:
                cur = -1
        elif cur == 1 and s < 5:
            cur = -1 if shortable and s <= SELL_T else 0
        elif cur == -1 and s > -5:
            cur = 1 if s >= BUY_T else 0
        p[i] = cur
    return p


def backtest(b: dict, score: np.ndarray, shortable: bool, horizon: int = 10, cost: float = 0.001) -> dict:
    c, t = b["c"], b["t"]
    n = len(c)
    start = int(min(200, max(40, n // 4)))
    if n - start < horizon + 20:
        return {"ok": False}
    years = max((t[-1] - t[start]) / (365.25 * 86400), 1e-6)
    per_year = (n - start) / years
    idx = np.arange(start, n - horizon)
    fwd = c[idx + horizon] / c[idx] - 1
    s = score[idx]
    cur = float(score[-1])

    def stats(mask, sign):
        k = int(mask.sum())
        if k == 0:
            return {"n": 0, "hit": None, "avg": None}
        hits = int(((fwd[mask] * sign) > 0).sum())
        return {"n": k, "hit": hits / k, "avg": float(np.mean(fwd[mask] * sign)), "shrunk": (hits + 5) / (k + 10)}
    longs, shorts = stats(s >= BUY_T, 1), stats(s <= SELL_T, -1)
    sign = 1 if cur >= 0 else -1
    similar = stats((np.sign(s) == sign) & (np.abs(s - cur) <= 15), sign)

    pos = positions(score, shortable)
    r = np.diff(c) / c[:-1]
    sr = pos[:-1] * r - cost * np.abs(np.diff(pos))
    sr, br = sr[start:], r[start:]
    eq, bh = np.cumprod(1 + sr), np.cumprod(1 + br)

    def dd(x):
        return float(np.min(x / np.maximum.accumulate(x) - 1)) if len(x) else 0.0
    trades, entry, side = [], None, 0
    for i in range(start, n):
        if pos[i] != side:
            if side != 0 and entry is not None:
                trades.append(side * (c[i] / c[entry] - 1))
            side, entry = pos[i], i if pos[i] != 0 else None
    step = max(1, len(eq) // 300)
    ts = t[start + 1:]
    return {
        "ok": True, "horizon": horizon, "longs": longs, "shorts": shorts, "similar": similar,
        "strategy": {"total": float(eq[-1] - 1), "cagr": float(eq[-1] ** (1 / years) - 1) if eq[-1] > 0 else -1.0,
                     "maxdd": dd(eq), "sharpe": float(np.mean(sr) / (np.std(sr) + 1e-12) * math.sqrt(per_year)),
                     "trades": len(trades), "winrate": float(np.mean(np.array(trades) > 0)) if trades else None,
                     "exposure": float(np.mean(pos[start:] != 0))},
        "buyhold": {"total": float(bh[-1] - 1), "cagr": float(bh[-1] ** (1 / years) - 1) if bh[-1] > 0 else -1.0, "maxdd": dd(bh)},
        "curve": {"t": ts[::step].tolist(), "eq": np.round(eq[::step], 4).tolist(), "bh": np.round(bh[::step], 4).tolist()},
        "years": round(years, 1),
    }


# ---------------------------------------------------------------- fundamentals
def fundamental_score(fd: dict, price: float) -> tuple[float | None, list[dict]]:
    if not fd:
        return None, []
    parts = []

    def add(label, val, text):
        if val is not None and np.isfinite(val):
            parts.append({"label": label, "value": float(np.clip(val, -1, 1)), "text": text})
    pe = fd.get("forwardPE") or fd.get("trailingPE")
    if pe is not None:
        add("Valuation", (25 - pe) / 20 if pe > 0 else -0.6,
            f"P/E of {pe:.1f} " + ("looks cheap" if 0 < pe < 15 else "is reasonable" if 0 < pe < 30 else "is expensive" if pe > 0 else "(company is loss-making)"))
    g = [x for x in (np.tanh((fd.get("revenueGrowth") or np.nan) / 0.15), np.tanh((fd.get("earningsGrowth") or np.nan) / 0.25)) if np.isfinite(x)]
    if g:
        add("Growth", float(np.mean(g)), f"Revenue growth {_pct(fd.get('revenueGrowth'))}, earnings growth {_pct(fd.get('earningsGrowth'))}")
    p = [x for x in (np.tanh((fd.get("profitMargin") or np.nan) / 0.12), np.tanh((fd.get("roe") or np.nan) / 0.15)) if np.isfinite(x)]
    if p:
        add("Profitability", float(np.mean(p)), f"Profit margin {_pct(fd.get('profitMargin'))}, return on equity {_pct(fd.get('roe'))}")
    de = fd.get("debtToEquity")
    if de is not None:
        add("Balance sheet", (100 - de) / 150, f"Debt/equity {de / 100:.2f}x" + (" - low leverage" if de < 60 else " - high leverage" if de > 150 else ""))
    tm = fd.get("targetMean")
    if tm and price:
        up = tm / price - 1
        rm = fd.get("recommendationMean")
        val = 0.6 * np.tanh(up / 0.15) + (0.4 * (3 - rm) / 2 if rm else 0)
        add("Analyst view", val, f"{fd.get('analysts') or '?'} analysts, average target {tm:,.2f} ({up * 100:+.1f}%), consensus '{fd.get('recommendationKey') or 'n/a'}'")
    if not parts:
        return None, []
    return float(np.mean([x["value"] for x in parts])), parts


def _pct(x):
    return f"{x * 100:.1f}%" if isinstance(x, (int, float)) else "n/a"


# ---------------------------------------------------------------- evaluation
def classify(score: float) -> str:
    return ("STRONG BUY" if score >= 50 else "BUY" if score >= BUY_T else "HOLD" if score > SELL_T
            else "SELL" if score > -50 else "STRONG SELL")


def evaluate(b: dict, bench: dict | None = None, shortable: bool = True, fund: dict | None = None,
             full: bool = False) -> dict:
    fs = factor_series(b, bench)
    ind, f = fs["ind"], fs["f"]
    c = b["c"]
    i = len(c) - 1
    price = float(c[-1])
    tech = float(fs["score"][-1])
    fscore, fparts = fundamental_score(fund or {}, price)
    score = 0.8 * tech + 0.2 * 100 * fscore if fscore is not None else tech
    bt = backtest(b, fs["score"], shortable)

    fac = []
    for k, label, w, expl in FACTORS:
        if f[k] is not None:
            fac.append({"key": k, "label": label, "weight": w, "value": round(float(f[k][i]), 3), "explain": expl})
    bias = "long" if score >= BUY_T else "short" if score <= SELL_T else "neutral"
    sgn = 1 if score >= 0 else -1
    tot = sum(x["weight"] * abs(x["value"]) for x in fac) or 1
    agree = sum(x["weight"] * abs(x["value"]) for x in fac if np.sign(x["value"]) == sgn) / tot
    hist = None
    if bt.get("ok"):
        st = bt["longs"] if sgn > 0 else bt["shorts"]
        hist = st.get("shrunk") if st["n"] else None
    h = hist if hist is not None else 0.5
    # a weak track record on this instrument must drag confidence down hard, not just average out
    conf = 100 * (0.35 * agree + 0.65 * h) - max(0.0, 0.5 - h) * 60
    if bias == "neutral":
        conf *= 0.6
    conf = float(np.clip(conf, 5, 95))

    atr = float(ind["atr"][i])
    rsi = float(ind["rsi"][i])
    trend = float(f["trend"][i])
    newhigh_recent = bool(ind["newhigh"][max(0, i - 5):].any())
    newlow_recent = bool(ind["newlow"][max(0, i - 5):].any())
    if bias == "long":
        setup = ("Breakout" if newhigh_recent else "Pullback in uptrend" if trend > 0.3 and rsi < 45
                 else "Trend continuation" if trend > 0.2 else "Oversold bounce" if rsi < 32 else "Improving momentum")
    elif bias == "short":
        setup = ("Breakdown" if newlow_recent else "Bear-rally fade" if trend < -0.3 and rsi > 55
                 else "Overbought fade" if rsi > 72 else "Downtrend continuation")
    else:
        setup = "No clear edge - wait"

    swing_lo = float(np.min(b["l"][-20:]))
    swing_hi = float(np.max(b["h"][-20:]))
    if bias == "short":
        stop = min(price + 2.2 * atr, swing_hi + 0.3 * atr)
        stop = max(stop, price + 1.2 * atr)
        risk = stop - price
        levels = {"entry": price, "entryLow": price, "entryHigh": price + 0.5 * atr, "stop": stop,
                  "t1": max(price - 2 * risk, price * 0.05), "t2": max(price - 3.5 * risk, price * 0.02)}
    else:
        stop = max(price - 2.2 * atr, swing_lo - 0.3 * atr)
        stop = min(stop, price - 1.2 * atr)
        risk = price - stop
        lowzone = float(ind["e20"][i]) if setup == "Pullback in uptrend" or trend > 0.3 else price - 0.5 * atr
        levels = {"entry": price, "entryLow": min(price, max(lowzone, price - atr)), "entryHigh": price, "stop": stop,
                  "t1": price + 2 * risk, "t2": price + 3.5 * risk}
    levels["support"], levels["resistance"] = swing_lo, swing_hi
    levels["rr"] = 2.0
    levels["riskPct"] = abs(levels["entry"] - levels["stop"]) / price

    meta = b.get("meta", {})
    chg = (price / float(c[-2]) - 1) * 100 if len(c) > 1 else 0.0
    out = {
        "symbol": b["symbol"], "name": meta.get("name", b["symbol"]), "currency": meta.get("currency", ""),
        "price": price, "changePct": chg, "score": round(score, 1), "techScore": round(tech, 1),
        "fundScore": round(fscore * 100, 1) if fscore is not None else None, "signal": classify(score), "bias": bias,
        "setup": setup, "confidence": round(conf, 1), "factors": fac, "levels": levels, "atr": atr, "atrPct": atr / price,
        "rsi": rsi, "adx": float(ind["adx"][i]), "ret1m": _ret(c, 21), "ret3m": _ret(c, 63), "ret1y": _ret(c, 252),
        "pos52": float(ind["pos52"][i]), "hitRate": (bt["longs"] if sgn > 0 else bt["shorts"]).get("hit") if bt.get("ok") else None,
        "backtestN": (bt["longs"] if sgn > 0 else bt["shorts"]).get("n") if bt.get("ok") else 0,
        "spark": np.round(c[-60:], 4).tolist(),
    }
    out["reasons"] = reasons(out, f, ind, i, bench is not None and f["relative"] is not None, fparts)
    out["risks"] = risks(out, ind, i, fund or {})
    if full:
        out["backtest"] = bt
        out["fundamentals"] = fund or {}
        out["fundParts"] = fparts
        out["series"] = _series(b, fs, shortable)
    return out


def _ret(c, k):
    return float(c[-1] / c[-k - 1] - 1) if len(c) > k else None


def _series(b, fs, shortable):
    ind = fs["ind"]
    r = lambda x, d=4: np.round(np.nan_to_num(x), d).tolist()  # noqa: E731
    pos = positions(fs["score"], shortable)
    marks = []
    for i in range(1, len(pos)):
        if pos[i] != pos[i - 1]:
            marks.append({"t": int(b["t"][i]), "type": {1: "buy", -1: "short", 0: "exit"}[int(pos[i])], "price": float(b["c"][i])})
    return {"t": b["t"].tolist(), "o": r(b["o"]), "h": r(b["h"]), "l": r(b["l"]), "c": r(b["c"]), "v": r(b["v"], 0),
            "e20": r(ind["e20"]), "e50": r(ind["e50"]), "e200": r(ind["e200"]), "bbu": r(ind["bbu"]), "bbl": r(ind["bbl"]),
            "rsi": r(ind["rsi"], 2), "macd": r(ind["macd"]), "macds": r(ind["macds"]), "macdh": r(ind["macdh"]),
            "score": r(fs["score"], 1), "marks": marks}


def reasons(o, f, ind, i, has_rel, fparts) -> list[dict]:
    out = []

    def add(tone, text, pro):
        out.append({"tone": tone, "text": text, "pro": pro})
    c = o["price"]
    e50, e200 = float(ind["e50"][i]), float(ind["e200"][i])
    above50, above200 = c > e50, c > e200
    if above50 and above200:
        add("bull", "The price is above both its 50-day and 200-day averages, so the medium and long-term trend is up.",
            f"Close {((c / e200) - 1) * 100:+.1f}% vs EMA200, {((c / e50) - 1) * 100:+.1f}% vs EMA50; ADX {o['adx']:.0f}")
    elif not above50 and not above200:
        add("bear", "The price is below both its 50-day and 200-day averages, so the trend is down. Buying here means fighting it.",
            f"Close {((c / e200) - 1) * 100:+.1f}% vs EMA200, {((c / e50) - 1) * 100:+.1f}% vs EMA50; ADX {o['adx']:.0f}")
    else:
        add("neutral", "The trend is mixed: the short and long-term averages disagree, which often means a turning point or a sideways market.",
            f"EMA50 {'>' if above50 else '<'} price, EMA200 {'<' if above200 else '>'} price")
    m = float(f["momentum"][i])
    if abs(m) > 0.25:
        add("bull" if m > 0 else "bear",
            f"Momentum is {'strong' if m > 0 else 'weak'}: {o['ret3m'] * 100 if o['ret3m'] is not None else 0:+.1f}% over 3 months"
            + (f" and {o['ret1y'] * 100:+.1f}% over a year." if o["ret1y"] is not None else "."),
            f"Vol-adjusted momentum factor {m:+.2f}")
    if has_rel:
        rv = float(f["relative"][i])
        if abs(rv) > 0.2:
            add("bull" if rv > 0 else "bear", f"It is {'outperforming' if rv > 0 else 'underperforming'} its market benchmark recently.",
                f"Relative-strength factor {rv:+.2f} (63d/21d vs benchmark)")
    if ind["newhigh"][max(0, i - 5):i + 1].any():
        add("bull", "It just broke out to a new 55-day high. Breakouts often keep running when volume confirms.",
            f"55d Donchian breakout; volume {float(ind['surge'][i]):.1f}x 50d avg; {o['pos52'] * 100:.0f}% of 52w range")
    elif ind["newlow"][max(0, i - 5):i + 1].any():
        add("bear", "It just fell to a new 55-day low, a sign that sellers are in control.",
            f"55d Donchian breakdown; {o['pos52'] * 100:.0f}% of 52w range")
    r = o["rsi"]
    if r > 72:
        add("bear", f"RSI is {r:.0f}, which is over-bought. The stock has run hot and could pause or pull back; avoid chasing it.", f"RSI14 {r:.1f}")
    elif r < 30:
        add("bull" if f["trend"][i] > -0.3 else "neutral", f"RSI is {r:.0f}, which is over-sold. Sellers may be exhausted and a bounce is possible.", f"RSI14 {r:.1f}")
    elif f["trend"][i] > 0.2 and r < 45:
        add("bull", "It is pulling back inside an uptrend, often a lower-risk spot to buy.", f"RSI14 {r:.1f} with trend factor {float(f['trend'][i]):+.2f}")
    mh = float(ind["macdh"][i])
    add("bull" if mh > 0 else "bear", f"Short-term buying pressure is {'building' if mh > 0 else 'fading'} (MACD {'above' if mh > 0 else 'below'} its signal line).",
        f"MACD hist {mh:+.4f}, factor {float(f['macd'][i]):+.2f}")
    if f["volume"] is not None:
        vv = float(f["volume"][i])
        if abs(vv) > 0.2:
            add("bull" if vv > 0 else "bear", f"Volume shows {'accumulation: more shares trade on up days than down days' if vv > 0 else 'distribution: heavier selling on down days'}.",
                f"OBV/up-down volume factor {vv:+.2f}")
    for p in fparts:
        add("bull" if p["value"] > 0.15 else "bear" if p["value"] < -0.15 else "neutral", p["text"] + ".", f"{p['label']} {p['value']:+.2f}")
    if o["hitRate"] is not None and o["backtestN"]:
        add("neutral", f"Track record: when this model gave a similar {'buy' if o['score'] >= 0 else 'sell'} signal on this instrument, it was right {o['hitRate'] * 100:.0f}% of the time over the next 10 trading days ({o['backtestN']} signal-days).",
            f"10d fwd hit-rate {o['hitRate'] * 100:.1f}% (n={o['backtestN']})")
    return out


def risks(o, ind, i, fd) -> list[str]:
    out = []
    if o["atrPct"] > 0.04:
        out.append(f"High volatility: it typically moves {o['atrPct'] * 100:.1f}% a day, so keep the position small.")
    if o["rsi"] > 75:
        out.append("Over-bought: a short-term pullback is likely even if the trend holds.")
    if fd.get("nextEarnings"):
        out.append(f"Earnings due around {fd['nextEarnings']}; results can gap the price either way.")
    if fd.get("shortPercentFloat") and fd["shortPercentFloat"] > 0.1:
        out.append(f"High short interest ({fd['shortPercentFloat'] * 100:.0f}% of float): expect sharp squeezes.")
    if fd.get("debtToEquity") and fd["debtToEquity"] > 200:
        out.append("Heavy debt load raises risk if rates rise or earnings slip.")
    if o["bias"] == "short":
        out.append("Short selling has unlimited loss potential. Always use the stop.")
    if o["confidence"] < 45:
        out.append("Low conviction: the factors disagree or the historical track record is weak.")
    out.append("Past signals do not guarantee future results. This is research, not financial advice.")
    return out
