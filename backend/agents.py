"""Investment committee: ten specialist agents debate every candidate.

Round 1  each agent studies the evidence from its own discipline and votes a stance (-1 sell .. +1 buy) with a
         confidence and a written argument. Agents without usable data abstain (confidence 0).
Round 2  rebuttal: low-confidence agents that contradict a strong majority update part-way toward it, and the
         devil's advocate attacks whatever the majority believes with the strongest counter-evidence it can find.
Verdict  a judge weights the votes by horizon/style relevance x the market regime x each agent's confidence and
         reports consensus, conviction (agreement x evidence quality) and the best bull and bear arguments.
"""
from __future__ import annotations

import math

import numpy as np

AGENTS = {
    "trend": "Trend Follower", "momentum": "Momentum Hunter", "reversion": "Mean-Reversion Trader", "value": "Value Investor",
    "quality": "Quality & Growth Analyst", "risk": "Risk Manager", "macro": "Macro Strategist", "quant": "Quant Statistician",
    "street": "Street Sentiment Tracker", "devil": "Devil's Advocate",
}
# relevance of each agent by holding horizon
HORIZON_W = {
    "short": {"trend": 1.2, "momentum": 1.1, "reversion": 1.2, "value": 0.1, "quality": 0.15, "risk": 1.0, "macro": 0.6, "quant": 1.2, "street": 0.4, "devil": 0.8},
    "medium": {"trend": 1.0, "momentum": 1.0, "reversion": 0.6, "value": 0.7, "quality": 0.8, "risk": 1.0, "macro": 0.8, "quant": 1.0, "street": 0.7, "devil": 0.8},
    "long": {"trend": 0.5, "momentum": 0.6, "reversion": 0.2, "value": 1.3, "quality": 1.4, "risk": 1.0, "macro": 0.7, "quant": 0.6, "street": 0.9, "devil": 0.8},
}
STYLE_W = {
    "growth": {"quality": 1.5, "momentum": 1.3, "value": 0.6}, "value": {"value": 1.8, "reversion": 1.2, "momentum": 0.7},
    "dividend": {"value": 1.4, "quality": 1.2, "risk": 1.3}, "momentum": {"momentum": 1.7, "trend": 1.4, "value": 0.5},
    "quality": {"quality": 1.8, "risk": 1.2}, "defensive": {"risk": 1.8, "macro": 1.3, "momentum": 0.8},
}
DEFENSIVE = {"Consumer Defensive", "Utilities", "Healthcare"}
CYCLICAL = {"Consumer Cyclical", "Technology", "Industrials", "Basic Materials", "Financial Services", "Energy", "Communication Services"}


def _clip(x, lo=-1.0, hi=1.0):
    return float(min(hi, max(lo, x))) if x is not None and math.isfinite(x) else 0.0


def _f(row, key):
    for f in row.get("factors", []):
        if f["key"] == key:
            return f["value"]
    return 0.0


def _pct(x):
    return f"{x * 100:+.1f}%" if isinstance(x, (int, float)) and math.isfinite(x) else "n/a"


def price_stats(c: np.ndarray) -> dict:
    """Risk/return statistics from ~1y of daily closes."""
    c = c[-253:]
    r = np.diff(np.log(np.maximum(c, 1e-12)))
    if len(r) < 40:
        return {}
    vol = float(np.std(r) * math.sqrt(252))
    eq = np.exp(np.cumsum(r))
    dd = float(np.min(eq / np.maximum.accumulate(eq) - 1))
    down = r[r < 0]
    y = np.log(c[-126:])
    x = np.arange(len(y))
    fit = np.polyfit(x, y, 1)
    resid = y - np.polyval(fit, x)
    r2 = float(1 - np.var(resid) / (np.var(y) + 1e-12))
    return {"vol": vol, "maxdd": dd, "sharpe": float(np.mean(r) * 252 / (vol + 1e-9)), "downside": float(np.std(down) * math.sqrt(252)) if len(down) > 5 else vol,
            "worst": float(np.min(r)), "trendR2": r2, "trendSlope": float(fit[0] * 252), "skew": float(((r - r.mean()) ** 3).mean() / (np.std(r) ** 3 + 1e-12))}


# ---------------------------------------------------------------- the agents (round 1)
def a_trend(row, fd, st, ctx):
    t, adx = _f(row, "trend"), row.get("adx", 20)
    stance = _clip(t * 1.4)
    conf = _clip(0.3 + (adx - 15) / 30, 0.15, 0.95)
    txt = (f"{'Up' if t > 0 else 'Down'}trend with ADX {adx:.0f} ({'strong' if adx > 25 else 'weak'} trend); "
           f"trend fit R² {st.get('trendR2', 0):.2f}.")
    return stance, conf * (0.6 + 0.4 * st.get("trendR2", 0.5)), txt


def a_momentum(row, fd, st, ctx):
    m, rel = _f(row, "momentum"), _f(row, "relative")
    rank = row.get("rsRank", 50) / 100
    stance = _clip(0.5 * m + 0.3 * rel + 0.4 * (rank - 0.5))
    conf = _clip(0.35 + 0.5 * abs(stance), 0.2, 0.9)
    return stance, conf, f"3m {_pct(row.get('ret3m'))}, 1y {_pct(row.get('ret1y'))}, momentum rank {rank * 100:.0f}th percentile in its market."


def a_reversion(row, fd, st, ctx):
    rsi, pos = row.get("rsi", 50), row.get("pos52", 0.5)
    stance = _clip((50 - rsi) / 25 * 0.7 + (0.5 - pos) * 0.5)
    if _f(row, "trend") > 0.3 and rsi < 45:
        stance = _clip(stance + 0.3)        # buyable pullback in an uptrend
    conf = _clip(abs(rsi - 50) / 30, 0.1, 0.8)
    return stance, conf, f"RSI {rsi:.0f}, trading at {pos * 100:.0f}% of its 52-week range: {'stretched' if abs(rsi - 50) > 20 else 'not stretched'}."


def a_value(row, fd, st, ctx):
    if not fd:
        return 0.0, 0.0, "No fundamentals available; abstains."
    parts, notes = [], []
    pe = fd.get("forwardPE") or fd.get("trailingPE")
    if pe:
        parts.append((22 - pe) / 18 if pe > 0 else -0.7)
        notes.append(f"P/E {pe:.1f}")
    if fd.get("peg"):
        parts.append((1.5 - fd["peg"]) / 1.5)
        notes.append(f"PEG {fd['peg']:.2f}")
    if fd.get("priceToBook"):
        parts.append((3 - fd["priceToBook"]) / 4)
    if fd.get("evToEbitda"):
        parts.append((14 - fd["evToEbitda"]) / 12)
        notes.append(f"EV/EBITDA {fd['evToEbitda']:.1f}")
    if fd.get("freeCashflow") and fd.get("marketCap"):
        fcfy = fd["freeCashflow"] / fd["marketCap"]
        parts.append((fcfy - 0.03) / 0.04)
        notes.append(f"FCF yield {fcfy * 100:.1f}%")
    if ctx["style"] == "dividend" and fd.get("dividendYield") is not None:
        parts.append((fd["dividendYield"] - 0.02) / 0.02)
        notes.append(f"dividend {fd['dividendYield'] * 100:.1f}%")
    if not parts:
        return 0.0, 0.0, "Valuation data incomplete; abstains."
    stance = _clip(float(np.mean([_clip(p) for p in parts])))
    return stance, _clip(0.3 + 0.12 * len(parts), 0, 0.85), ("Cheap" if stance > 0.2 else "Expensive" if stance < -0.2 else "Fairly valued") + ": " + ", ".join(notes) + "."


def a_quality(row, fd, st, ctx):
    if not fd:
        return 0.0, 0.0, "No fundamentals available; abstains."
    parts, notes = [], []
    for key, scale, label in (("revenueGrowth", 0.12, "revenue growth"), ("earningsGrowth", 0.2, "EPS growth"),
                              ("roe", 0.15, "ROE"), ("profitMargin", 0.12, "net margin"), ("operatingMargin", 0.15, "op margin")):
        v = fd.get(key)
        if v is not None:
            parts.append(math.tanh(v / scale))
            notes.append(f"{label} {v * 100:.0f}%")
    if fd.get("debtToEquity") is not None:
        parts.append(_clip((100 - fd["debtToEquity"]) / 150))
        notes.append(f"D/E {fd['debtToEquity'] / 100:.2f}x")
    if fd.get("currentRatio"):
        parts.append(_clip((fd["currentRatio"] - 1) / 1.5))
    if not parts:
        return 0.0, 0.0, "Quality data incomplete; abstains."
    stance = _clip(float(np.mean(parts)) * 1.2)
    return stance, _clip(0.3 + 0.08 * len(parts), 0, 0.85), ("High-quality business" if stance > 0.25 else "Weak fundamentals" if stance < -0.2 else "Average quality") + ": " + ", ".join(notes[:5]) + "."


def a_risk(row, fd, st, ctx):
    if not st:
        return 0.0, 0.2, "Too little history to judge risk."
    vol, dd, down = st["vol"], st["maxdd"], st["downside"]
    tol = ctx["maxDrawdown"]
    stance = _clip(0.6 - vol / 0.35 - max(0, -dd - tol) * 2 + (0.2 if st["skew"] > 0 else -0.1))
    if row.get("atrPct", 0) > 0.05:
        stance = _clip(stance - 0.3)
    conf = _clip(0.45 + min(vol, 0.8) * 0.5, 0.3, 0.9)
    return stance, conf, f"Volatility {vol * 100:.0f}%/yr, max drawdown {dd * 100:.0f}% last year (your limit {tol * 100:.0f}%), downside vol {down * 100:.0f}%, worst day {st['worst'] * 100:.1f}%."


def a_macro(row, fd, st, ctx):
    reg = ctx["regime"]
    sec = row.get("sector") or ""
    beta = row.get("_beta", 1.0)
    risk_on = reg["score"]
    tilt = 0.4 if sec in DEFENSIVE else -0.1 if sec in CYCLICAL else 0.0
    stance = _clip(risk_on * (beta - 0.7) * 0.8 + (-risk_on) * tilt)
    conf = _clip(0.25 + abs(risk_on) * 0.5, 0.2, 0.75)
    return stance, conf, f"Regime {reg['label']} (breadth {reg['breadth']:+.0f}, VIX {reg['vix']:.0f}); beta {beta:.2f}, sector {sec or 'n/a'}."


def a_quant(row, fd, st, ctx):
    hit, n = row.get("hitRate"), row.get("backtestN") or 0
    score = row.get("techScore", row.get("score", 0)) / 100
    rel = ((hit if hit is not None else 0.5) - 0.5) * 2
    stance = _clip(np.sign(score) * max(0.0, abs(score)) * (0.5 + rel) + (st.get("sharpe", 0) * 0.15 if st else 0))
    conf = _clip(0.2 + min(n, 150) / 300 + abs(rel) * 0.4, 0.1, 0.9)
    return stance, conf, f"Engine score {score * 100:+.0f}; its signals on this stock were right {hit * 100:.0f}% of the time (n={n}), 1y Sharpe {st.get('sharpe', 0):.2f}." if hit is not None else f"Engine score {score * 100:+.0f}; no reliable track record yet."


def a_street(row, fd, st, ctx):
    if not fd or not (fd.get("targetMean") or fd.get("recommendationMean")):
        return 0.0, 0.0, "No analyst coverage; abstains."
    up = fd["targetMean"] / row["price"] - 1 if fd.get("targetMean") and row.get("price") else 0
    rm = fd.get("recommendationMean")
    sp = fd.get("shortPercentFloat") or 0
    stance = _clip(math.tanh(up / 0.2) * 0.6 + ((3 - rm) / 2 * 0.4 if rm else 0) - max(0, sp - 0.08) * 2)
    n = fd.get("analysts") or 0
    return stance, _clip(0.2 + min(n, 30) / 50, 0.1, 0.75), f"{n} analysts, target {_pct(up)} away, consensus '{fd.get('recommendationKey') or 'n/a'}'" + (f", short interest {sp * 100:.0f}%" if sp else "") + "."


def a_devil(row, fd, st, ctx, majority: float):
    """Attack the majority view with the strongest available counter-evidence."""
    ev = []
    if majority > 0:
        if row.get("rsi", 50) > 70:
            ev.append((0.6, f"RSI {row['rsi']:.0f} is over-bought; buyers here are late"))
        pe = (fd or {}).get("forwardPE") or (fd or {}).get("trailingPE")
        if pe and pe > 45:
            ev.append((0.5, f"valuation is rich at {pe:.0f}x earnings"))
        if (fd or {}).get("nextEarnings"):
            ev.append((0.3, f"earnings on {fd['nextEarnings']} can gap it either way"))
        if st and st.get("vol", 0) > 0.5:
            ev.append((0.5, f"{st['vol'] * 100:.0f}% volatility means a normal pullback could hit the stop"))
        if row.get("pos52", 0) > 0.95:
            ev.append((0.3, "it sits at its 52-week high, where resistance and profit-taking live"))
        if ctx["regime"]["score"] < -0.3:
            ev.append((0.4, "the broad market is risk-off; most stocks fall in that tide"))
        if (row.get("hitRate") or 0.5) < 0.48:
            ev.append((0.5, "the model's own record on this stock is below a coin flip"))
    else:
        if row.get("rsi", 50) < 30:
            ev.append((0.6, f"RSI {row['rsi']:.0f} is over-sold; sellers may be exhausted"))
        pe = (fd or {}).get("forwardPE")
        if pe and 0 < pe < 12:
            ev.append((0.4, f"it is already cheap at {pe:.0f}x forward earnings"))
        if (fd or {}).get("shortPercentFloat", 0) and fd["shortPercentFloat"] > 0.15:
            ev.append((0.5, "heavy short interest invites a squeeze"))
        if ctx["regime"]["score"] > 0.3:
            ev.append((0.3, "a risk-on market lifts laggards too"))
    if not ev:
        return -np.sign(majority) * 0.1, 0.15, "Searched for counter-evidence and found little; the majority case looks sound."
    strength = min(1.0, sum(e[0] for e in ev) / 1.5)
    ev.sort(key=lambda e: -e[0])
    return float(-np.sign(majority) * strength), _clip(0.3 + 0.5 * strength, 0, 0.85), "Counter-case: " + "; ".join(e[1] for e in ev[:3]) + "."


R1 = {"trend": a_trend, "momentum": a_momentum, "reversion": a_reversion, "value": a_value, "quality": a_quality,
      "risk": a_risk, "macro": a_macro, "quant": a_quant, "street": a_street}


def regime(rows: list[dict], vix: float | None, spx_trend: float) -> dict:
    breadth = float(np.mean([r["score"] for r in rows])) if rows else 0.0
    v = vix or 18.0
    score = _clip(breadth / 40 * 0.5 + (18 - v) / 12 * 0.3 + spx_trend * 0.2)
    return {"score": score, "breadth": breadth, "vix": v, "label": "risk-on" if score > 0.25 else "risk-off" if score < -0.25 else "neutral"}


def debate(row: dict, fd: dict | None, st: dict, ctx: dict) -> dict:
    votes = {}
    for k, fn in R1.items():
        s, c, txt = fn(row, fd, st, ctx)
        votes[k] = {"agent": AGENTS[k], "key": k, "stance": float(s), "conf": float(c), "arg": txt, "r1": float(s)}
    w = dict(HORIZON_W[ctx["horizon"]])
    for k, m in STYLE_W.get(ctx["style"], {}).items():
        w[k] = w.get(k, 1) * m
    if ctx["regime"]["score"] < -0.25:        # in risk-off markets the risk manager and macro desk speak louder
        w["risk"] *= 1.4
        w["macro"] *= 1.3

    def consensus(vs):
        num = sum(w[k] * v["conf"] * v["stance"] for k, v in vs.items())
        den = sum(w[k] * v["conf"] for k, v in vs.items()) or 1e-9
        return num / den
    maj = consensus(votes)
    # round 2: rebuttal
    for k, v in votes.items():
        if v["conf"] < 0.45 and np.sign(v["stance"]) != np.sign(maj) and abs(maj) > 0.3:
            v["stance"] = float(v["stance"] + 0.35 * (maj - v["stance"]) * (1 - v["conf"]))
            v["arg"] += " (Round 2: partly persuaded by the majority.)"
    s, c, txt = a_devil(row, fd, st, ctx, maj)
    votes["devil"] = {"agent": AGENTS["devil"], "key": "devil", "stance": float(s), "conf": float(c), "arg": txt, "r1": float(s)}
    cons = consensus(votes)
    active = [v for v in votes.values() if v["conf"] > 0.05]
    tw = sum(w[v["key"]] * v["conf"] for v in active) or 1e-9
    disagree = math.sqrt(sum(w[v["key"]] * v["conf"] * (v["stance"] - cons) ** 2 for v in active) / tw)
    coverage = len(active) / len(votes)
    conviction = _clip(abs(cons) * (1 - min(disagree, 1) * 0.6) * (0.55 + 0.45 * coverage) * 1.6, 0, 1)
    ranked = sorted(active, key=lambda v: -(w[v["key"]] * v["conf"] * abs(v["stance"])))
    bulls = [f"{v['agent']}: {v['arg']}" for v in ranked if v["stance"] > 0.15][:3]
    bears = [f"{v['agent']}: {v['arg']}" for v in ranked if v["stance"] < -0.15][:3]
    nb, ns = sum(v["stance"] > 0.15 for v in active), sum(v["stance"] < -0.15 for v in active)
    verdict = (f"{'Buy' if cons > 0.15 else 'Avoid' if cons < -0.15 else 'No edge'}: committee votes {nb} bullish / {ns} bearish / "
               f"{len(active) - nb - ns} neutral, conviction {conviction * 100:.0f}%, disagreement {'high' if disagree > 0.55 else 'moderate' if disagree > 0.35 else 'low'}.")
    return {"consensus": float(cons), "conviction": float(conviction), "disagreement": float(disagree), "coverage": coverage,
            "votes": sorted(votes.values(), key=lambda v: -abs(v["stance"] * v["conf"])), "bull": bulls, "bear": bears, "verdict": verdict}
