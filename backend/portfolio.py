"""Position sizing and the daily portfolio plan.

Sizing is risk-based: each idea risks a fixed slice of the budget between entry and stop (scaled by confidence),
capped by a maximum position weight, a sector cap, available cash and the user's daily deployment limit."""
from __future__ import annotations

import math

from .data import fx_rate

RISK = {
    "conservative": {"risk": 0.005, "maxpos": 0.10, "maxn": 12, "sector": 0.30, "label": "Conservative"},
    "balanced": {"risk": 0.010, "maxpos": 0.15, "maxn": 10, "sector": 0.35, "label": "Balanced"},
    "aggressive": {"risk": 0.020, "maxpos": 0.25, "maxn": 7, "sector": 0.50, "label": "Aggressive"},
}


def size(a: dict, profile: dict, cash: float | None = None, fractional: bool | None = None) -> dict:
    cfg = RISK.get(profile.get("risk"), RISK["balanced"])
    budget = float(profile.get("budget") or 0)
    frac = profile.get("fractional") if fractional is None else fractional
    lv = a["levels"]
    fx = fx_rate(a.get("currency") or profile.get("currency"), profile.get("currency", "USD"))
    px = lv["entry"] * fx
    rps = abs(lv["entry"] - lv["stop"]) * fx
    out = {"qty": 0, "cost": 0.0, "riskAmount": 0.0, "pct": 0.0, "fx": fx, "priceLocal": px, "gainT1": 0.0, "gainT2": 0.0,
           "note": ""}
    if a["bias"] == "short" and not profile.get("allowShorts"):
        out["note"] = "Bearish: avoid buying, and consider exiting if you hold it. (Turn on short ideas to size a short.)"
        return out
    if a["bias"] == "neutral" or budget <= 0 or px <= 0 or rps <= 0:
        out["note"] = "No position: signal is neutral." if a["bias"] == "neutral" else "Set a budget to get sizing."
        return out
    conf_mult = 0.5 + a["confidence"] / 100
    strength = min(1.2, max(0.6, abs(a["score"]) / 60))
    risk_amt = budget * cfg["risk"] * conf_mult * strength
    qty = risk_amt / rps
    cap = budget * cfg["maxpos"] / px
    limits = [("risk budget", qty), ("max position size", cap)]
    if cash is not None:
        limits.append(("available cash", max(cash, 0) / px))
    why, qty = min(limits, key=lambda x: x[1])
    qty = qty if frac else math.floor(qty)
    if qty <= 0 and not frac:
        out["note"] = f"One unit costs {px:,.2f}, more than your {why} allows. Consider fractional shares or a bigger budget."
        return out
    qty = round(qty, 4) if frac else int(qty)
    out.update(qty=qty, cost=qty * px, riskAmount=qty * rps, pct=qty * px / budget,
               gainT1=qty * abs(lv["t1"] - lv["entry"]) * fx, gainT2=qty * abs(lv["t2"] - lv["entry"]) * fx,
               note=f"Sized by {why}. Risking {qty * rps:,.2f} ({qty * rps / budget * 100:.2f}% of budget) if the stop is hit.")
    return out


def build_plan(candidates: list[dict], holdings: list[dict], held_analyses: dict[str, dict], profile: dict) -> dict:
    cfg = RISK.get(profile.get("risk"), RISK["balanced"])
    budget = float(profile.get("budget") or 0)
    ccy = profile.get("currency", "USD")
    allow_short = bool(profile.get("allowShorts"))
    actions, alloc = [], []
    sector_val: dict[str, float] = {}

    # value current holdings
    mv_total = 0.0
    for h in holdings:
        a = held_analyses.get(h["symbol"])
        if not a:
            continue
        fx = fx_rate(a.get("currency") or ccy, ccy)
        h["_px"] = a["price"] * fx
        h["_mv"] = h["_px"] * float(h["qty"])
        mv_total += h["_mv"]
    cash = profile.get("cash")
    cash = float(cash) if cash not in (None, "") else max(budget - mv_total, 0.0)
    cash_start = cash
    equity = mv_total + cash if holdings else budget

    # 1) review holdings
    kept = 0
    for h in holdings:
        a = held_analyses.get(h["symbol"])
        if not a:
            actions.append({"action": "REVIEW", "symbol": h["symbol"], "name": h["symbol"], "qty": h["qty"], "value": 0,
                            "reason": "No data available for this symbol, so check it manually."})
            continue
        side = h.get("side", "long")
        qty, px, mv = float(h["qty"]), h["_px"], h["_mv"]
        w = mv / equity if equity else 0
        pnl = (a["price"] / float(h["avgCost"]) - 1) * (1 if side == "long" else -1) if h.get("avgCost") else None
        base = {"symbol": h["symbol"], "name": a["name"], "price": a["price"], "currency": a["currency"], "score": a["score"],
                "signal": a["signal"], "confidence": a["confidence"], "pnl": pnl, "sector": a.get("sector", "Other")}
        against = (side == "long" and a["score"] <= -20) or (side == "short" and a["score"] >= 20)
        if against:
            actions.append({**base, "action": "SELL" if side == "long" else "COVER", "qty": qty, "value": mv,
                            "reason": f"The signal flipped to {a['signal']} (score {a['score']:+.0f}). Exit to protect capital."})
            cash += mv if side == "long" else 0
            continue
        kept += 1
        if w > cfg["maxpos"] * 1.35:
            tq = qty - equity * cfg["maxpos"] / px
            tq = round(tq, 4) if profile.get("fractional") else math.floor(tq)
            if tq > 0:
                actions.append({**base, "action": "TRIM", "qty": tq, "value": tq * px,
                                "reason": f"Position is {w * 100:.0f}% of the portfolio, above the {cfg['maxpos'] * 100:.0f}% limit for a {cfg['label'].lower()} profile. Trim to rebalance."})
                cash += tq * px
                mv -= tq * px
        elif side == "long" and -20 < a["score"] < 0 and pnl is not None and pnl > 0.25:
            tq = qty / 3
            tq = round(tq, 4) if profile.get("fractional") else math.floor(tq)
            if tq > 0:
                actions.append({**base, "action": "TRIM", "qty": tq, "value": tq * px,
                                "reason": f"Up {pnl * 100:.0f}% but momentum is fading (score {a['score']:+.0f}). Lock in part of the gain."})
                cash += tq * px
                mv -= tq * px
        elif side == "long" and a["score"] >= 35 and w < cfg["maxpos"] * 0.6:
            s = size(a, {**profile, "budget": equity}, cash=min(cash, equity * cfg["maxpos"] - mv))
            if s["qty"] > 0:
                actions.append({**base, "action": "ADD", "qty": s["qty"], "value": s["cost"], "stop": a["levels"]["stop"],
                                "target": a["levels"]["t1"], "reason": f"Still a {a['signal']} with {a['confidence']:.0f}% confidence and underweight at {w * 100:.1f}%."})
                cash -= s["cost"]
                mv += s["cost"]
        else:
            actions.append({**base, "action": "HOLD", "qty": qty, "value": mv, "stop": a["levels"]["stop"] if side == "long" else None,
                            "reason": f"Signal {a['signal']} ({a['score']:+.0f}). Keep holding with a stop near {a['levels']['stop']:,.2f}."})
        sector_val[base["sector"]] = sector_val.get(base["sector"], 0) + mv
        alloc.append({"symbol": h["symbol"], "name": a["name"], "value": mv, "sector": base["sector"], "side": side})

    # 2) new ideas
    held = {h["symbol"] for h in holdings}
    daily_left = float(profile.get("dailyLimit") or 1e18)
    slots = cfg["maxn"] - kept
    ideas = [c for c in candidates if c["symbol"] not in held
             and (c["bias"] == "long" or (allow_short and c["bias"] == "short" and c.get("shortable", True)))]
    ideas.sort(key=lambda c: abs(c["score"]) * c["confidence"], reverse=True)
    watch = []
    for c in ideas:
        if slots <= 0 or cash <= 0 or daily_left <= 0:
            watch.append(c)
            continue
        sec = c.get("sector", "Other")
        room_sector = equity * cfg["sector"] - sector_val.get(sec, 0)
        if room_sector <= equity * 0.02:
            watch.append(c)
            continue
        s = size(c, {**profile, "budget": equity}, cash=min(cash, daily_left, room_sector),
                 fractional=bool(profile.get("fractional") or c.get("fractional")))
        full = size(c, {**profile, "budget": equity}, fractional=bool(profile.get("fractional") or c.get("fractional")))
        if s["qty"] <= 0 or s["cost"] < 0.25 * full["cost"]:   # don't open token-sized positions with leftover cash
            watch.append(c)
            continue
        act ="BUY" if c["bias"] == "long" else "SHORT"
        actions.append({"action": act, "symbol": c["symbol"], "name": c["name"], "qty": s["qty"], "value": s["cost"],
                        "market": c.get("marketName"), "expected": c.get("expected"),
                        "price": c["price"], "currency": c["currency"], "score": c["score"], "signal": c["signal"],
                        "confidence": c["confidence"], "stop": c["levels"]["stop"], "target": c["levels"]["t1"],
                        "target2": c["levels"]["t2"], "setup": c["setup"], "risk": s["riskAmount"], "sector": sec,
                        "reason": f"{c['setup']}: score {c['score']:+.0f}, confidence {c['confidence']:.0f}%. {s['note']}"})
        cash -= s["cost"]
        daily_left -= s["cost"]
        slots -= 1
        sector_val[sec] = sector_val.get(sec, 0) + s["cost"]
        alloc.append({"symbol": c["symbol"], "name": c["name"], "value": s["cost"], "sector": sec, "market": c.get("marketName"),
                      "side": "short" if act == "SHORT" else "long"})

    order = {"SELL": 0, "COVER": 0, "TRIM": 1, "BUY": 2, "SHORT": 2, "ADD": 3, "HOLD": 4, "REVIEW": 5}
    actions.sort(key=lambda x: (order.get(x["action"], 9), -abs(x.get("score") or 0)))
    invested = sum(x["value"] for x in alloc)
    return {
        "currency": ccy, "profile": cfg["label"], "equity": equity, "cashStart": cash_start, "cashEnd": cash,
        "invested": invested, "positions": len(alloc), "actions": actions,
        "allocation": sorted(alloc, key=lambda x: -x["value"]) + ([{"symbol": "CASH", "name": "Cash", "value": max(cash, 0), "sector": "Cash"}] if cash > 0 else []),
        "sectors": sorted(({"sector": k, "value": v} for k, v in sector_val.items()), key=lambda x: -x["value"]),
        "byMarket": sorted(({"market": k, "value": v} for k, v in _group(alloc, "market").items()), key=lambda x: -x["value"]),
        "totalRisk": sum(x.get("risk", 0) for x in actions if x["action"] in ("BUY", "SHORT")),
        "watchlist": [{"symbol": c["symbol"], "name": c["name"], "score": c["score"], "signal": c["signal"], "confidence": c["confidence"]} for c in watch[:8]],
        "rules": {"riskPerTrade": cfg["risk"], "maxPosition": cfg["maxpos"], "maxPositions": cfg["maxn"], "sectorCap": cfg["sector"]},
    }


def _group(alloc: list[dict], key: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for a in alloc:
        k = a.get(key) or "Holdings"
        out[k] = out.get(k, 0) + a["value"]
    return out
