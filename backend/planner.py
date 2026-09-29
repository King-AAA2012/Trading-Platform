"""Daily portfolio planner: screen -> gather data -> committee debate -> optimise -> trade list -> stress-test.

1. Screen: every stock in the chosen markets is scored by the engine; the best long (and, if allowed, short) ideas
   plus everything you already hold go forward. Sector exclusions and a minimum market cap are applied.
2. Gather: fundamentals, analyst data, one year of daily prices, risk statistics and market beta for each candidate.
3. Debate: ten agents argue each candidate (see agents.py). Only ideas with enough conviction survive.
4. Optimise: expected returns come from committee consensus x conviction; covariance from Ledoit-Wolf shrinkage;
   weights from your objective, capped by position size, the per-trade risk budget (ATR stop), sector and market
   caps, the cash reserve and your target volatility (see optimizer.py).
5. Trade list: target weights become share counts in your currency and are compared with your holdings using a
   rebalance band (small differences are ignored to avoid churn). New buys respect the daily deployment limit;
   the rest is queued for the following days.
6. Stress-test: the final book is run through historical-style shocks with the What-If engine, and a Monte Carlo
   of the next year shows the range of outcomes and the chance of breaching your drawdown limit.
"""
from __future__ import annotations

import math

import numpy as np

from . import agents, data, optimizer, scenario

PRESETS = {
    "conservative": {"riskPerTrade": 0.5, "targetVol": 10, "maxDrawdown": 12, "maxPosition": 10, "maxSector": 25, "maxPositions": 15,
                     "minPositions": 8, "cashReserve": 15, "objective": "minvol", "horizon": "long", "style": "defensive", "minConviction": 30,
                     "stopAtr": 2.5, "rebalanceBand": 3},
    "balanced": {"riskPerTrade": 1.0, "targetVol": 16, "maxDrawdown": 20, "maxPosition": 15, "maxSector": 35, "maxPositions": 12,
                 "minPositions": 6, "cashReserve": 5, "objective": "sharpe", "horizon": "medium", "style": "any", "minConviction": 25,
                 "stopAtr": 2.2, "rebalanceBand": 3},
    "aggressive": {"riskPerTrade": 2.0, "targetVol": 28, "maxDrawdown": 35, "maxPosition": 25, "maxSector": 50, "maxPositions": 8,
                   "minPositions": 4, "cashReserve": 0, "objective": "return", "horizon": "short", "style": "momentum", "minConviction": 20,
                   "stopAtr": 2.0, "rebalanceBand": 4},
}
DEFAULTS = {**PRESETS["balanced"], "minMarketCap": 0, "excludeSectors": [], "dailyLimit": None, "allowShorts": False, "fractional": False}
STRESS = {
    "2008-style crash": {"moves": {"equities": -35, "vol": 150, "oil": -40, "copper": -35, "rates": -1.5, "gold": 5, "china": -40, "bitcoin": -50},
                         "sectors": {"Financial Services": -0.8, "Consumer Cyclical": -0.5, "Consumer Defensive": 0.3, "Utilities": 0.2}},
    "Rate shock (+2pp)": {"moves": {"rates": 2.0, "equities": -12, "gold": -6, "dollar": 5, "vol": 40, "bitcoin": -25},
                          "sectors": {"Real Estate": -0.8, "Utilities": -0.5, "Technology": -0.5, "Financial Services": 0.3}},
    "Oil spike (+60%)": {"moves": {"oil": 60, "natgas": 30, "equities": -8, "vol": 40}, "sectors": {"Energy": 0.8},
                         "themes": [{"keyword": "airline", "impact": -0.9}]},
    "Tech bust": {"moves": {"equities": -18, "vol": 70, "rates": -0.5}, "sectors": {"Technology": -0.9, "Communication Services": -0.6},
                  "themes": [{"keyword": "semiconductor", "impact": -0.8}, {"keyword": "software", "impact": -0.6}]},
    "Dollar surge (+10%)": {"moves": {"dollar": 10, "gold": -7, "china": -10, "copper": -8, "equities": -4},
                            "countries": {"in": -0.4, "br": -0.5, "za": -0.5, "tr": -0.6, "mx": -0.4}},
}


def params(profile: dict) -> dict:
    p = {**DEFAULTS, **PRESETS.get(profile.get("risk"), {})}
    for k in DEFAULTS:
        if profile.get(k) not in (None, ""):
            p[k] = profile[k]
    return p


def _fx(ccy: str, to: str) -> float:
    return data.fx_rate(ccy or to, to)


def build(rows: list[dict], hists: dict[str, dict], holdings: list[dict], held: dict[str, dict], profile: dict,
          scenario_spec: dict | None = None) -> dict:
    P = params(profile)
    ccy = profile.get("currency", "USD")
    budget = float(profile.get("budget") or 0)
    frac = bool(P["fractional"])
    log = []

    # ---- value current holdings
    mv = {}
    for h in holdings:
        a = held.get(h["symbol"])
        if a:
            fx = _fx(a.get("currency"), ccy)
            mv[h["symbol"]] = a["price"] * fx * float(h["qty"]) * (1 if h.get("side", "long") == "long" else -1)
    cash = profile.get("cash")
    cash = float(cash) if cash not in (None, "") else max(budget - sum(abs(v) for v in mv.values()), 0.0)
    equity = cash + sum(mv.values()) if holdings else budget
    if equity <= 0:
        return {"error": "Set a budget (or holdings) first."}

    # ---- 1. screen
    excl = set(P["excludeSectors"] or [])
    allow_short = bool(P["allowShorts"])
    pool = [r for r in rows if r.get("sector") not in excl and (r["bias"] == "long" or (allow_short and r["bias"] == "short" and r.get("shortable", True)))]
    pool.sort(key=lambda r: -abs(r["score"]) * r["confidence"])
    pool = pool[:45]
    names = {r["symbol"] for r in pool}
    for s, a in held.items():
        if s not in names:
            a.setdefault("marketName", a.get("marketName") or "Holdings")
            pool.append(a)
            names.add(s)
    log.append(f"Screened {len(rows)} instruments across the selected markets; {len(pool)} advanced to research.")

    # ---- 2. gather
    need = [r["symbol"] for r in pool if r["symbol"] not in hists]
    for s, h in zip(need, data.POOL.map(lambda s: data.get_history(s, "2y"), need)):
        if h is not None:
            hists[s] = h
    funds = dict(zip([r["symbol"] for r in pool], data.POOL.map(lambda r: data.fundamentals(r["symbol"]), pool)))
    if P["minMarketCap"]:
        keep = []
        for r in pool:
            mc = (funds.get(r["symbol"]) or {}).get("marketCap")
            usd = mc * _fx(r.get("currency"), "USD") if mc else None
            if r["symbol"] in held or usd is None or usd >= P["minMarketCap"] * 1e9:
                keep.append(r)
        log.append(f"Market-cap filter (≥ ${P['minMarketCap']}B) kept {len(keep)} of {len(pool)}.")
        pool = keep
    R, syms, _ = optimizer.align(hists, [r["symbol"] for r in pool])
    if not syms:
        return {"error": "Not enough price history to build a portfolio."}
    spx = data.get_history("^GSPC", "2y")
    bench_r = None
    if spx:
        Rb, sb, _ = optimizer.align({**hists, "^GSPC": spx}, syms + ["^GSPC"])
        if sb and sb[-1] == "^GSPC" and len(Rb) == len(R):
            bench_r = Rb[:, -1]
    mkt = bench_r if bench_r is not None else R.mean(1)
    by = {r["symbol"]: r for r in pool}
    for j, s in enumerate(syms):
        by[s]["_beta"] = float(np.cov(R[:, j], mkt)[0, 1] / (np.var(mkt) + 1e-12))

    # ---- 3. debate
    vix = data.get_history("^VIX", "2y")
    spx_trend = float(np.tanh((spx["c"][-1] / np.mean(spx["c"][-200:]) - 1) * 10)) if spx else 0.0
    reg = agents.regime(rows, float(vix["c"][-1]) if vix else None, spx_trend)
    ctx = {"horizon": P["horizon"], "style": P["style"], "maxDrawdown": P["maxDrawdown"] / 100, "regime": reg}
    debates = {}
    for s in syms:
        r = by[s]
        st = agents.price_stats(hists[s]["c"])
        d = agents.debate(r, funds.get(s) or {}, st, ctx)
        if scenario_spec and r.get("expected") is not None:   # scenario plans: the scenario projection joins the debate
            d["consensus"] = float(np.clip(0.5 * d["consensus"] + 0.5 * np.tanh(r["expected"] / 0.1), -1, 1))
            d["verdict"] += f" Scenario projection {r['expected'] * 100:+.1f}% blended in."
        d["stats"] = st
        debates[s] = d
    log.append(f"The committee debated {len(syms)} candidates in a {reg['label']} regime (breadth {reg['breadth']:+.0f}, VIX {reg['vix']:.0f}).")

    # ---- 4. optimise
    minc = P["minConviction"] / 100
    cand = [s for s in syms if s in held or (debates[s]["conviction"] >= minc and
            ((debates[s]["consensus"] > 0.12) or (allow_short and debates[s]["consensus"] < -0.12 and by[s]["bias"] == "short")))]
    cand.sort(key=lambda s: -abs(debates[s]["consensus"]) * debates[s]["conviction"] - (0.05 if s in held else 0))
    cand = cand[: max(P["maxPositions"] * 3, P["minPositions"])]
    log.append(f"{len(cand)} candidates cleared the {P['minConviction']}% conviction bar.")
    if not cand:
        return _empty(P, equity, cash, ccy, log, reg, "No idea cleared the conviction bar today. Holding cash is a position too.")

    def solve(cset):
        idx = [syms.index(s) for s in cset]
        Rs = R[:, idx]
        S_d = optimizer.ledoit_wolf(Rs)
        S_a = S_d * 252
        mu = np.array([0.30 * debates[s]["consensus"] * (0.4 + 0.6 * debates[s]["conviction"]) + (0.01 if s in held else 0) for s in cset])
        hi, lo = np.zeros(len(cset)), np.zeros(len(cset))
        for i, s in enumerate(cset):
            r = by[s]
            stop_pct = max(P["stopAtr"] * r.get("atrPct", 0.02), 0.01)
            cap = min(P["maxPosition"] / 100, (P["riskPerTrade"] / 100) / stop_pct)    # loss at the stop <= risk per trade
            if debates[s]["consensus"] >= 0:
                hi[i] = cap
            elif allow_short and r.get("bias") == "short" and r.get("shortable", True):
                lo[i] = -cap                    # a genuine short idea; a held long that turned bearish is simply sold (weight 0)
        # sector and (multi-market) market caps are enforced inside the optimiser's projection
        groups = []
        multi = len({by[s].get("marketName") for s in cset}) > 1
        for key, cap in (("sector", P["maxSector"] / 100), ("marketName", 0.7 if multi else 1.0)):
            vals = {}
            for i, s in enumerate(cset):
                vals.setdefault(by[s].get(key) or "?", []).append(i)
            groups += [(np.array(ix), cap) for ix in vals.values() if cap < 1.0]
        budget_w = 1 - P["cashReserve"] / 100
        w = optimizer.optimise(mu, S_a, lo, hi, budget_w, P["objective"], P["targetVol"] / 100, groups)
        return w, mu, S_d, Rs

    w, mu, S_d, Rs = solve(cand)
    # keep the strongest positions, drop dust, and re-solve on the final set
    order = np.argsort(-np.abs(w))
    final = [cand[i] for i in order[: P["maxPositions"]] if abs(w[i]) >= 0.015]
    if len(final) < len(cand):
        if not final:
            return _empty(P, equity, cash, ccy, log, reg, "The optimiser found no position worth its risk today.")
        w, mu, S_d, Rs = solve(final)
        cand = final
    # drawdown guard: if last year's path of this book broke the limit, scale exposure down
    pr = Rs @ w
    eq = np.cumprod(1 + pr)
    bt_dd = float(np.min(eq / np.maximum.accumulate(eq) - 1))
    if -bt_dd > P["maxDrawdown"] / 100:
        f = max(0.35, (P["maxDrawdown"] / 100) / -bt_dd)
        w = w * f
        log.append(f"Exposure scaled to {f * 100:.0f}% because this mix fell {bt_dd * 100:.0f}% at worst last year (limit {P['maxDrawdown']}%).")
    ana = optimizer.analytics(w, Rs, mu, S_d, bench_r, 20, P["maxDrawdown"] / 100)
    log.append(f"Optimised with objective '{P['objective']}': expected {ana['expReturn'] * 100:.1f}%/yr at {ana['vol'] * 100:.1f}% volatility (target {P['targetVol']}%).")

    # ---- 5. trade list
    tw = {s: float(w[i]) for i, s in enumerate(cand)}
    actions, alloc, queued = [], [], []
    band = P["rebalanceBand"] / 100
    daily_left = float(P["dailyLimit"]) if P["dailyLimit"] else float("inf")
    cash_now = cash
    total_risk = 0.0

    def mk(s, act, qty, value, reason, extra=None):
        r = by.get(s) or held.get(s) or {}
        d = debates.get(s)
        atr = r.get("atr") or 0
        px = r.get("price", 0)
        stop = px - P["stopAtr"] * atr if act in ("BUY", "ADD", "HOLD") else px + P["stopAtr"] * atr if act == "SHORT" else None
        return {"action": act, "symbol": s, "name": r.get("name", s), "qty": qty, "value": value, "price": px, "currency": r.get("currency"),
                "market": r.get("marketName"), "sector": r.get("sector"), "score": r.get("score"), "signal": r.get("signal"),
                "confidence": round(d["conviction"] * 100, 1) if d else r.get("confidence"), "stop": stop,
                "target": (px + 2 * (px - stop)) if stop and act != "SHORT" else (px - 2 * (stop - px)) if stop else None,
                "consensus": d["consensus"] if d else None, "conviction": d["conviction"] if d else None,
                "targetWeight": tw.get(s, 0.0), "currentWeight": mv.get(s, 0) / equity, "reason": reason, **(extra or {})}

    def qty_for(value, s):
        r = by.get(s) or held.get(s)
        pxl = r["price"] * _fx(r.get("currency"), ccy)
        q = value / pxl if pxl > 0 else 0
        return (round(q, 4) if frac else math.floor(q)), pxl

    # existing holdings first (sells free up cash for buys)
    for h in holdings:
        s = h["symbol"]
        if s not in held:
            actions.append({"action": "REVIEW", "symbol": s, "name": s, "qty": h["qty"], "value": 0, "reason": "No data for this symbol; check it manually."})
            continue
        cur_w = mv.get(s, 0) / equity
        t = tw.get(s, 0.0)
        d = debates.get(s)
        diff = t - cur_w
        why = d["verdict"] if d else ""
        if t == 0:
            q = float(h["qty"])
            reason = (f"Committee turned against it. {why}" if not d or d["consensus"] < 0 else
                      f"Dropped from the optimal portfolio: other ideas offer better return for the risk, or it breaks your limits. {why}")
            actions.append(mk(s, "SELL" if h.get("side", "long") == "long" else "COVER", q, abs(mv[s]), reason))
            cash_now += abs(mv[s])
        elif abs(diff) < band:
            actions.append(mk(s, "HOLD", float(h["qty"]), abs(mv[s]), f"Within {P['rebalanceBand']}% of its target weight ({t * 100:.1f}%). {why}"))
            alloc.append((s, abs(mv[s])))
        elif diff < 0:
            q, pxl = qty_for(-diff * equity, s)
            if q > 0:
                actions.append(mk(s, "TRIM", q, q * pxl, f"Overweight at {cur_w * 100:.1f}% vs target {t * 100:.1f}%. {why}"))
                cash_now += q * pxl
            alloc.append((s, abs(mv[s]) - q * pxl))
        else:
            want = diff * equity
            spend = min(want, max(cash_now, 0), daily_left)
            q, pxl = qty_for(spend, s)
            if q > 0:
                actions.append(mk(s, "ADD", q, q * pxl, f"Underweight at {cur_w * 100:.1f}% vs target {t * 100:.1f}%. {why}"))
                cash_now -= q * pxl
                daily_left -= q * pxl
            alloc.append((s, abs(mv[s]) + q * pxl))
    # new positions, highest conviction first
    for s in sorted([s for s in cand if s not in mv], key=lambda s: -debates[s]["conviction"] * abs(tw[s])):
        want = abs(tw[s]) * equity
        spend = min(want, max(cash_now, 0), daily_left)
        q, pxl = qty_for(spend, s)
        qfull, _ = qty_for(want, s)
        act = "BUY" if tw[s] > 0 else "SHORT"
        if q <= 0 or spend < 0.3 * want:
            if qfull > 0:
                queued.append(mk(s, act, qfull, qfull * pxl, "Queued: daily deployment limit or cash reached. " + debates[s]["verdict"]))
            continue
        a = mk(s, act, q, q * pxl, debates[s]["verdict"], {"partial": q < qfull, "fullQty": qfull})
        total_risk += q * pxl * P["stopAtr"] * by[s].get("atrPct", 0.02)
        actions.append(a)
        cash_now -= q * pxl
        daily_left -= q * pxl
        alloc.append((s, q * pxl))
        if q < qfull:
            queued.append(mk(s, act, qfull - q, (qfull - q) * pxl, "Remainder queued for the next session (daily limit)."))

    # ---- 6. stress tests on the target book
    region = {s: scenario.region_for(by[s].get("market", ""), s) for s in cand}
    stress = []
    for name, spec in STRESS.items():
        proj = scenario.project([by[s] for s in cand], hists, scenario.clamp(spec), region)
        er = {p["symbol"]: p["expected"] for p in proj}
        impact = sum(tw[s] * er.get(s, 0) for s in cand)
        worst = min(cand, key=lambda s: tw[s] * er.get(s, 0))
        stress.append({"name": name, "impact": impact, "value": impact * equity, "worst": worst, "worstMove": er.get(worst, 0)})

    order = {"SELL": 0, "COVER": 0, "TRIM": 1, "BUY": 2, "SHORT": 2, "ADD": 3, "HOLD": 4, "REVIEW": 5}
    actions.sort(key=lambda x: (order.get(x["action"], 9), -(x.get("conviction") or 0)))
    rc = dict(zip(cand, ana.get("riskContrib", [])))
    alloc_out = [{"symbol": s, "name": (by.get(s) or {}).get("name", s), "value": v, "sector": (by.get(s) or {}).get("sector"),
                  "market": (by.get(s) or {}).get("marketName"), "targetWeight": tw.get(s, 0), "riskShare": rc.get(s)} for s, v in alloc if v > 0]
    alloc_out.sort(key=lambda x: -x["value"])
    if cash_now > 0:
        alloc_out.append({"symbol": "CASH", "name": "Cash", "value": cash_now, "sector": "Cash"})
    sectors, markets_ = {}, {}
    for s in cand:
        sectors[by[s].get("sector") or "Other"] = sectors.get(by[s].get("sector") or "Other", 0) + abs(tw[s]) * equity
        markets_[by[s].get("marketName") or "Other"] = markets_.get(by[s].get("marketName") or "Other", 0) + abs(tw[s]) * equity
    votes_summary = {}
    for s in cand:
        for v in debates[s]["votes"]:
            e = votes_summary.setdefault(v["agent"], {"agent": v["agent"], "bull": 0, "bear": 0, "abstain": 0})
            e["bull" if v["stance"] > 0.15 else "bear" if v["stance"] < -0.15 else "abstain"] += 1
    return {
        "currency": ccy, "profile": (f"Risk {profile['riskScore']:.0f}/100" if profile.get("riskScore") is not None else profile.get("risk", "custom").capitalize()), "params": P, "equity": equity, "cashStart": cash, "cashEnd": cash_now,
        "invested": sum(v for _, v in alloc), "positions": len([a for a in alloc_out if a["symbol"] != "CASH"]), "actions": actions,
        "allocation": alloc_out, "sectors": sorted(({"sector": k, "value": v} for k, v in sectors.items()), key=lambda x: -x["value"]),
        "byMarket": sorted(({"market": k, "value": v} for k, v in markets_.items()), key=lambda x: -x["value"]),
        "totalRisk": total_risk, "queued": queued, "watchlist": [{"symbol": q["symbol"], "name": q["name"], "score": q.get("score") or 0,
                                                                  "signal": q.get("signal"), "confidence": q.get("confidence")} for q in queued[:8]],
        "analytics": ana, "stress": stress, "regime": reg, "log": log, "committee": list(votes_summary.values()),
        "debates": {s: {k: debates[s][k] for k in ("consensus", "conviction", "disagreement", "votes", "bull", "bear", "verdict", "stats")} for s in cand},
        "rules": {"riskPerTrade": P["riskPerTrade"] / 100, "maxPosition": P["maxPosition"] / 100, "maxPositions": P["maxPositions"], "sectorCap": P["maxSector"] / 100},
    }


def _empty(P, equity, cash, ccy, log, reg, msg):
    log.append(msg)
    return {"currency": ccy, "profile": "Custom", "params": P, "equity": equity, "cashStart": cash, "cashEnd": cash, "invested": 0, "positions": 0,
            "actions": [], "allocation": [{"symbol": "CASH", "name": "Cash", "value": cash, "sector": "Cash"}], "sectors": [], "byMarket": [],
            "totalRisk": 0, "queued": [], "watchlist": [], "analytics": {"empty": True}, "stress": [], "regime": reg, "log": log, "committee": [],
            "debates": {}, "rules": {"riskPerTrade": P["riskPerTrade"] / 100, "maxPosition": P["maxPosition"] / 100, "maxPositions": P["maxPositions"], "sectorCap": P["maxSector"] / 100}}
