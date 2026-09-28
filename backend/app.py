"""TradeScope API + static frontend. Run: python -m uvicorn backend.app:app --port 8420"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import ai, custom, data, engine, markets, portfolio, simulator, store

ROOT = Path(__file__).resolve().parent.parent
FRONT = ROOT / "frontend"
app = FastAPI(title="TradeScope", version="1.0")
_scan_cache: dict[str, tuple[float, list]] = {}


def clean(o):
    """Make numpy / NaN values JSON-safe."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    return o


def J(o):
    return JSONResponse(clean(o))


def _market_for(symbol: str, market: str | None) -> dict:
    if market:
        try:
            return markets.market_def(market)
        except KeyError:
            pass
    if symbol.startswith("SIM:"):
        return markets.market_def("sim")
    if symbol.startswith("CUS:"):
        return markets.market_def(symbol.split(":")[1])
    for k, m in markets.PRESETS.items():
        if symbol in m["symbols"]:
            return m
    suffix = {".NS": "india", ".BO": "india", ".L": "uk", ".T": "japan", ".HK": "hongkong", ".TO": "canada", ".AX": "australia"}
    for s, k in suffix.items():
        if symbol.endswith(s):
            return markets.PRESETS[k]
    if symbol.endswith("-USD"):
        return markets.PRESETS["crypto"]
    if symbol.endswith("=X"):
        return markets.PRESETS["forex"]
    if symbol.endswith("=F"):
        return markets.PRESETS["commodities"]
    if "." in symbol:
        return markets.PRESETS["europe"]
    return markets.PRESETS["us"]


def _can_short(md: dict) -> bool:
    """Backtests include short trades only if the market allows it AND the user opted into short ideas."""
    return bool(md.get("shortable", True) and store.load()["profile"].get("allowShorts"))


def analyze(symbol: str, market: str | None = None, full: bool = True) -> dict:
    md = _market_for(symbol, market)
    b = data.get_history(symbol, "5y" if full else "2y")
    if b is None or len(b["c"]) < 30:
        raise HTTPException(404, f"Not enough price history for {symbol} (need 30+ bars).")
    bench = data.get_history(md["benchmark"], "5y" if full else "2y") if md.get("benchmark") and md["benchmark"] != symbol else None
    fund = data.fundamentals(symbol) if full else None
    a = engine.evaluate(b, bench, _can_short(md), fund, full=full)
    a["sector"] = (fund or {}).get("sector") or data.sector_of(symbol)
    a["marketName"] = md["name"]
    a["exchange"] = b["meta"].get("exchange", "")
    return a


# ---------------------------------------------------------------- routes
@app.get("/api/markets")
def api_markets():
    return J({"markets": markets.all_markets(), "risk": portfolio.RISK})


@app.get("/api/macro")
def api_macro():
    qs = {q["symbol"]: q for q in data.quotes([s for s, _ in markets.MACRO])}
    return J([{**qs[s], "label": lbl} for s, lbl in markets.MACRO if s in qs])


@app.get("/api/quotes")
def api_quotes(symbols: str):
    return J(data.quotes([s for s in symbols.split(",") if s]))


@app.get("/api/search")
def api_search(q: str):
    out = data.search(q) if len(q) >= 1 else []
    ql = q.lower()
    for c in simulator.COMPANIES:
        if ql in c[0].lower() or ql in c[1].lower():
            out.insert(0, {"symbol": f"SIM:{c[0]}", "name": c[1], "exchange": "Wolf Exchange", "type": "Imaginary"})
    return J(out[:15])


@app.get("/api/analyze/{symbol:path}")
def api_analyze(symbol: str, market: str | None = None):
    a = analyze(symbol, market)
    prof = store.load()["profile"]
    a["sizing"] = portfolio.size(a, prof)
    return J(a)


@app.get("/api/history/{symbol:path}")
def api_history(symbol: str, range: str = "1d", interval: str = "5m"):
    b = data.get_history(symbol, range, interval)
    if not b:
        raise HTTPException(404, "no data")
    return J({"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"], "meta": b["meta"]})


def run_scan(market: str, force: bool = False) -> list[dict]:
    hit = _scan_cache.get(market)
    ttl = 5 if market == "sim" or market.startswith("c-") else 600
    if hit and not force and time.time() - hit[0] < ttl:
        return hit[1]
    md = markets.market_def(market)
    syms = md["symbols"]
    hists = data.many_histories(syms + ([md["benchmark"]] if md.get("benchmark") else []), "2y")
    bench = hists.get(md.get("benchmark"))
    rows = []
    for s in syms:
        if s in hists:
            try:
                r = engine.evaluate(hists[s], bench, _can_short(md))
                rows.append(r)
            except Exception as e:  # one bad series shouldn't kill the scan
                print("scan error", s, e)
    for r, sec in zip(rows, data.POOL.map(lambda r: data.sector_of(r["symbol"]), rows)):
        r["sector"] = sec
    # cross-sectional momentum rank (percentile within this market)
    order = sorted(rows, key=lambda r: r["ret3m"] if r["ret3m"] is not None else -9)
    for i, r in enumerate(order):
        r["rsRank"] = round(100 * (i + 1) / len(order))
    rows.sort(key=lambda r: -r["score"])
    _scan_cache[market] = (time.time(), rows)
    return rows


@app.get("/api/scan/{market}")
def api_scan(market: str, force: bool = False):
    try:
        rows = run_scan(market, force)
    except KeyError:
        raise HTTPException(404, "unknown market")
    prof = store.load()["profile"]
    md = markets.market_def(market)
    for r in rows:
        r["sizing"] = portfolio.size(r, prof, fractional=prof.get("fractional") or md.get("fractional"))
    breadth = {"bull": sum(r["bias"] == "long" for r in rows), "bear": sum(r["bias"] == "short" for r in rows),
               "neutral": sum(r["bias"] == "neutral" for r in rows),
               "avgScore": float(np.mean([r["score"] for r in rows])) if rows else 0,
               "advancers": sum(r["changePct"] > 0 for r in rows), "decliners": sum(r["changePct"] < 0 for r in rows)}
    return J({"market": market, "name": md["name"], "rows": rows, "breadth": breadth, "shortable": md.get("shortable", True),
              "sim": simulator.status() if market == "sim" else None})


@app.get("/api/news/{symbol:path}")
def api_news(symbol: str, name: str = ""):
    return J(data.news(symbol, name))


@app.get("/api/state")
def api_state():
    return J(store.load())


@app.post("/api/state")
def api_state_save(patch: dict = Body(...)):
    st = store.load()
    if "profile" in patch and patch["profile"].get("allowShorts") != st["profile"].get("allowShorts"):
        _scan_cache.clear()  # backtest/confidence depend on whether shorts are allowed
    for k in ("profile", "holdings", "watchlist", "lastMarket"):
        if k in patch:
            st[k] = patch[k]
    store.save(st)
    return J(st)


@app.post("/api/plan")
def api_plan(body: dict = Body(...)):
    st = store.load()
    prof = {**st["profile"], **body.get("profile", {})}
    market = body.get("market") or st.get("lastMarket", "us")
    md = markets.market_def(market)
    rows = run_scan(market)
    for r in rows:
        r.setdefault("sector", data.sector_of(r["symbol"]))
    holdings = [dict(h) for h in body.get("holdings", st["holdings"]) if h.get("symbol") and float(h.get("qty") or 0) > 0]
    held = {}
    for h, a in zip(holdings, data.POOL.map(lambda h: _safe_analyze(h["symbol"]), holdings)):
        if a:
            held[h["symbol"]] = a
    if not prof.get("fractional") and md.get("fractional"):
        prof["fractional"] = True
    plan = portfolio.build_plan(rows, holdings, held, prof, md.get("shortable", True))
    plan["market"] = md["name"]
    plan["generated"] = int(time.time())
    return J(plan)


def _safe_analyze(sym):
    try:
        return analyze(sym, full=False)
    except Exception:
        return None


# custom markets
@app.post("/api/custom")
def api_custom_create(body: dict = Body(...)):
    return J(custom.create_market(body["name"], body.get("currency", "USD")))


@app.delete("/api/custom/{mid}")
def api_custom_delete(mid: str):
    custom.delete_market(mid)
    return J({"ok": True})


@app.post("/api/custom/{mid}/ticker")
def api_custom_ticker(mid: str, body: dict = Body(...)):
    if body.get("price") not in (None, ""):
        r = custom.add_price(mid, body["ticker"], float(body["price"]), body.get("date"))
    else:
        r = custom.upsert_ticker(mid, body["ticker"], body.get("name", ""), body.get("sector", ""), body.get("csv", ""))
    _scan_cache.pop(mid, None)
    return J(r)


@app.delete("/api/custom/{mid}/ticker/{ticker}")
def api_custom_ticker_del(mid: str, ticker: str):
    custom.delete_ticker(mid, ticker)
    _scan_cache.pop(mid, None)
    return J({"ok": True})


@app.get("/api/custom/{mid}")
def api_custom_get(mid: str):
    m = custom.get_market(mid)
    if not m:
        raise HTTPException(404)
    return J({**m, "tickers": {k: {"name": v["name"], "sector": v["sector"], "bars": len(v["bars"]),
                                   "last": v["bars"][-1][4] if v["bars"] else None} for k, v in m["tickers"].items()}})


# simulator
@app.get("/api/sim")
def api_sim():
    return J(simulator.status())


@app.post("/api/sim/advance")
def api_sim_advance(body: dict = Body(default={})):
    _scan_cache.pop("sim", None)
    return J(simulator.advance(int(body.get("days", 1))))


@app.post("/api/sim/reset")
def api_sim_reset(body: dict = Body(default={})):
    _scan_cache.pop("sim", None)
    return J(simulator.reset(body.get("seed")))


# AI
@app.get("/api/ai/status")
def api_ai_status():
    return J(ai.status())


def _text_stream(gen, fallback: str):
    def g():
        first = True
        for chunk in gen:
            if chunk is None:
                yield fallback
                return
            first = False
            yield chunk
        if first:
            yield fallback
    return StreamingResponse(g(), media_type="text/plain; charset=utf-8")


@app.post("/api/ai/report")
def api_ai_report(body: dict = Body(...)):
    sym = body["symbol"]
    a = analyze(sym, body.get("market"))
    prof = store.load()["profile"]
    sz = portfolio.size(a, prof)
    nw = data.news(sym, a["name"])
    ctx = ai.stock_context(a, sz, nw, prof)
    return _text_stream(ai.stream([{"role": "user", "content": ai.REPORT_PROMPT.format(ctx=ctx)}], body.get("model")),
                        ai.fallback_report(a, sz, prof))


@app.post("/api/ai/chat")
def api_ai_chat(body: dict = Body(...)):
    msgs = [m for m in body.get("messages", []) if m.get("role") in ("user", "assistant")][-12:]
    ctx = ""
    if body.get("symbol"):
        try:
            a = analyze(body["symbol"], body.get("market"))
            prof = store.load()["profile"]
            ctx = "Context for the instrument the user is viewing:\n" + ai.stock_context(a, portfolio.size(a, prof), data.news(body["symbol"], a["name"]), prof)
        except HTTPException:
            pass
    if body.get("plan"):
        ctx += "\nUser's current portfolio plan (JSON):\n" + json.dumps(body["plan"])[:4000]
    if ctx and msgs:
        msgs = [{"role": "user", "content": ctx}, {"role": "assistant", "content": "Understood. I'll use only this data."}] + msgs
    return _text_stream(ai.stream(msgs, body.get("model")),
                        "The local AI (Ollama) isn't running. Start it with `ollama serve` and pull a model, e.g. `ollama pull llama3.1:8b`.")


@app.post("/api/ai/plan")
def api_ai_plan(body: dict = Body(...)):
    plan = body["plan"]
    acts = "\n".join(f"- {x['action']} {x.get('qty')} {x['symbol']} ({x.get('name')}) ≈ {x.get('value', 0):,.0f}: {x.get('reason')}" for x in plan["actions"])
    prompt = (f"Explain today's portfolio plan to the user in markdown: sections '## Today's game plan', '## Why these moves', "
              f"'## Portfolio shape' (diversification, cash, risk) and '## Watch out for'. Profile: {plan['profile']}, equity "
              f"{plan['equity']:,.0f} {plan['currency']}, cash after plan {plan['cashEnd']:,.0f}, total risk at stops {plan['totalRisk']:,.0f}.\n"
              f"Actions:\n{acts}\nSectors: {json.dumps(plan['sectors'])}")
    fb = "## Today's game plan\n" + acts + f"\n\nCash after plan: {plan['cashEnd']:,.2f} {plan['currency']}. *(Start Ollama for an AI explanation.)*"
    return _text_stream(ai.stream([{"role": "user", "content": prompt}]), fb)


# ---------------------------------------------------------------- static
VENDOR = ROOT / "frontend" / "vendor"


@app.get("/vendor/lwc.js")
def vendor_lwc():
    """TradingView lightweight-charts, cached locally after the first download so the app works offline."""
    p = VENDOR / "lightweight-charts.js"
    if not p.exists():
        VENDOR.mkdir(exist_ok=True)
        r = data._session.get("https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js", timeout=30)
        r.raise_for_status()
        p.write_bytes(r.content)
    return Response(p.read_bytes(), media_type="application/javascript", headers={"Cache-Control": "max-age=86400"})


@app.get("/")
def index():
    return FileResponse(FRONT / "index.html")


app.mount("/", StaticFiles(directory=FRONT, html=True), name="static")
