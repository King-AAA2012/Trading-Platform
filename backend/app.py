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

from . import ai, data, engine, markets, portfolio, scenario, store

ROOT = Path(__file__).resolve().parent.parent
FRONT = ROOT / "frontend"
app = FastAPI(title="TradeScope", version="2.0")
_scan_cache: dict[str, tuple[float, list, dict]] = {}


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


def _can_short(md: dict) -> bool:
    """Backtests include short trades only if the market allows it AND the user opted into short ideas."""
    return bool(md.get("shortable", True) and store.load()["profile"].get("allowShorts"))


def _market_for(symbol: str, market: str | None) -> dict:
    if market:
        try:
            return markets.market_def(market)
        except KeyError:
            pass
    for m in markets.PRESETS.values():
        if symbol in m["symbols"]:
            return m
    reg = scenario.region_for("", symbol)
    if reg and reg in markets.REGIONS:
        n, f, bench, sh, g = markets.REGIONS[reg]
        return {"name": n, "benchmark": bench, "shortable": sh, "currency": ""}
    if symbol.endswith("-USD"):
        return markets.PRESETS["crypto"]
    if symbol.endswith("=X"):
        return markets.PRESETS["forex"]
    if symbol.endswith("=F"):
        return markets.PRESETS["commodities"]
    if symbol.startswith("^"):
        return markets.PRESETS["indices"]
    return {"name": "Global", "benchmark": "^GSPC", "shortable": True, "currency": ""}


def analyze(symbol: str, market: str | None = None, full: bool = True) -> dict:
    md = _market_for(symbol, market)
    b = data.get_history(symbol, "5y" if full else "2y")
    if b is None or len(b["c"]) < 30:
        raise HTTPException(404, f"Not enough price history for {symbol} (need 30+ bars).")
    bench = data.get_history(md["benchmark"], "5y" if full else "2y") if md.get("benchmark") and md["benchmark"] != symbol else None
    fund = data.fundamentals(symbol) if full else None
    a = engine.evaluate(b, bench, _can_short(md), fund, full=full)
    info = data.info_of(symbol)
    a["sector"] = (fund or {}).get("sector") or info["sector"]
    a["industry"] = (fund or {}).get("industry") or info["industry"]
    a["marketName"] = md["name"]
    a["exchange"] = b["meta"].get("exchange", "")
    return a


# ---------------------------------------------------------------- routes
@app.get("/api/markets")
def api_markets():
    return J({"markets": markets.all_markets(), "risk": portfolio.RISK, "drivers": scenario.DRIVERS, "sectors": scenario.SECTORS})


@app.get("/api/macro")
def api_macro():
    qs = {q["symbol"]: q for q in data.quotes([s for s, _ in markets.MACRO])}
    return J([{**qs[s], "label": lbl} for s, lbl in markets.MACRO if s in qs])


@app.get("/api/quotes")
def api_quotes(symbols: str):
    return J(data.quotes([s for s in symbols.split(",") if s]))


@app.get("/api/search")
def api_search(q: str):
    return J(data.search(q)[:15] if q else [])


@app.get("/api/analyze/{symbol:path}")
def api_analyze(symbol: str, market: str | None = None):
    a = analyze(symbol, market)
    a["sizing"] = portfolio.size(a, store.load()["profile"])
    return J(a)


@app.get("/api/history/{symbol:path}")
def api_history(symbol: str, range: str = "1d", interval: str = "5m"):
    b = data.get_history(symbol, range, interval)
    if not b:
        raise HTTPException(404, "no data")
    return J({"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"], "meta": b["meta"]})


def _equal_weight(hists: dict[str, dict]) -> dict | None:
    """Synthetic equal-weight benchmark for countries without a reliable index feed."""
    if len(hists) < 5:
        return None
    grid = max(hists.values(), key=lambda h: len(h["t"]))["t"]
    gd = grid // 86400
    acc, cnt = np.zeros(len(grid)), np.zeros(len(grid))
    for h in hists.values():
        pos = np.searchsorted(h["t"] // 86400, gd, side="right") - 1
        ok = pos >= 0
        c = h["c"][np.maximum(pos, 0)] / h["c"][0]
        acc[ok] += c[ok]
        cnt[ok] += 1
    return {"t": grid, "c": acc / np.maximum(cnt, 1)}


def run_scan(market: str, force: bool = False) -> tuple[list[dict], dict]:
    hit = _scan_cache.get(market)
    if hit and not force and time.time() - hit[0] < 600:
        return hit[1], hit[2]
    md = markets.market_def(market)
    syms = md["symbols"]
    if not syms:
        raise HTTPException(503, f"Couldn't load the stock list for {md['name']} right now. Try again shortly.")
    bsym = md.get("benchmark")
    hists = data.many_histories(syms + ([bsym] if bsym else []), "2y")
    bench = hists.pop(bsym, None) if bsym else None
    if bench is None and market not in ("forex", "commodities", "indices"):
        bench = _equal_weight(hists)
    rows = []
    for s in syms:
        if s in hists:
            try:
                r = engine.evaluate(hists[s], bench, _can_short(md))
                r.update(market=market, marketName=md["name"], shortable=md.get("shortable", True), fractional=md.get("fractional", False))
                rows.append(r)
            except Exception as e:  # one bad series shouldn't kill the scan
                print("scan error", s, e)
    for r, info in zip(rows, data.POOL.map(lambda r: data.info_of(r["symbol"]), rows)):
        r["sector"], r["industry"] = info["sector"], info["industry"]
    order = sorted(rows, key=lambda r: r["ret3m"] if r["ret3m"] is not None else -9)
    for i, r in enumerate(order):
        r["rsRank"] = round(100 * (i + 1) / len(order))
    rows.sort(key=lambda r: -r["score"])
    _scan_cache[market] = (time.time(), rows, {s: hists[s] for s in syms if s in hists})
    return rows, _scan_cache[market][2]


@app.get("/api/scan/{market}")
def api_scan(market: str, force: bool = False):
    try:
        rows, _ = run_scan(market, force)
        md = markets.market_def(market)
    except KeyError:
        raise HTTPException(404, "unknown market")
    prof = store.load()["profile"]
    out = []
    for r in rows:
        out.append({**r, "sizing": portfolio.size(r, prof, fractional=prof.get("fractional") or md.get("fractional"))})
    breadth = {"bull": sum(r["bias"] == "long" for r in rows), "bear": sum(r["bias"] == "short" for r in rows),
               "neutral": sum(r["bias"] == "neutral" for r in rows),
               "avgScore": float(np.mean([r["score"] for r in rows])) if rows else 0,
               "advancers": sum(r["changePct"] > 0 for r in rows), "decliners": sum(r["changePct"] < 0 for r in rows)}
    return J({"market": market, "name": md["name"], "rows": out, "breadth": breadth, "shortable": md.get("shortable", True)})


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
    for k in ("profile", "holdings", "watchlist", "lastMarket", "planMarkets"):
        if k in patch:
            st[k] = patch[k]
    store.save(st)
    return J(st)


def _scan_many(mkts: list[str]) -> tuple[list[dict], dict]:
    rows, hists = [], {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:      # separate pool: each scan uses data.POOL internally
        results = list(ex.map(_safe_scan, mkts))
    for m, res in zip(mkts, results):
        if res:
            rows += res[0]
            hists.update(res[1])
    seen, uniq = set(), []
    for r in rows:                  # a symbol in two selected markets counts once
        if r["symbol"] not in seen:
            seen.add(r["symbol"])
            uniq.append(r)
    return uniq, hists


def _safe_scan(m):
    try:
        return run_scan(m)
    except Exception as e:
        print("scan failed", m, e)
        return None


def _plan_markets(body: dict, st: dict) -> list[str]:
    mk = body.get("markets") or st.get("planMarkets") or [st.get("lastMarket", "us")]
    valid = {m["id"] for m in markets.all_markets()}
    return [m for m in mk if m in valid][:12] or ["us"]


@app.post("/api/plan")
def api_plan(body: dict = Body(...)):
    st = store.load()
    prof = {**st["profile"], **body.get("profile", {})}
    mkts = _plan_markets(body, st)
    rows, hists = _scan_many(mkts)
    if body.get("scenario"):
        rows = _scenario_rows(body["scenario"], mkts, rows, hists)
    holdings = [dict(h) for h in body.get("holdings", st["holdings"]) if h.get("symbol") and float(h.get("qty") or 0) > 0]
    held = {}
    by_sym = {r["symbol"]: r for r in rows}
    for h, a in zip(holdings, data.POOL.map(lambda h: by_sym.get(h["symbol"]) or _safe_analyze(h["symbol"]), holdings)):
        if a:
            held[h["symbol"]] = a
    plan = portfolio.build_plan(rows, holdings, held, prof)
    plan["markets"] = [markets.market_def(m)["name"] for m in mkts]
    plan["market"] = ", ".join(plan["markets"])
    plan["scenario"] = body["scenario"].get("title") if body.get("scenario") else None
    plan["generated"] = int(time.time())
    return J(plan)


def _safe_analyze(sym):
    try:
        return analyze(sym, full=False)
    except Exception:
        return None


# ---------------------------------------------------------------- what-if scenarios
def _scenario_rows(spec: dict, mkts: list[str], rows: list[dict], hists: dict) -> list[dict]:
    spec = scenario.clamp(spec)
    region = {r["symbol"]: scenario.region_for(r["market"], r["symbol"]) for r in rows}
    out = scenario.project(rows, hists, spec, region)
    for r in out:
        r["signal"] = engine.classify(r["score"])
        L, px = dict(r["levels"]), r["price"]      # re-point stop/targets to the scenario direction
        risk = abs(L["entry"] - L["stop"])
        if r["bias"] == "short":
            L.update(stop=px + risk, t1=max(px - 2 * risk, px * 0.05), t2=max(px - 3.5 * risk, px * 0.02), entryLow=px, entryHigh=px + 0.3 * risk)
        elif r["bias"] == "long":
            L.update(stop=px - risk, t1=px + 2 * risk, t2=px + 3.5 * risk, entryLow=px - 0.3 * risk, entryHigh=px)
        r["levels"] = L
        r["setup"] = "Scenario winner" if r["bias"] == "long" else "Scenario loser" if r["bias"] == "short" else "Little exposure"
    return out


@app.post("/api/scenario/interpret")
def api_scenario_interpret(body: dict = Body(...)):
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Describe an event first.")
    spec = scenario.interpret(text, body.get("ai", True))
    return J({"spec": spec, "levels": scenario.driver_levels()})


@app.post("/api/scenario/run")
def api_scenario_run(body: dict = Body(...)):
    st = store.load()
    mkts = _plan_markets(body, st)
    spec = body.get("spec") or scenario.interpret(body.get("text", ""), body.get("ai", True))
    rows, hists = _scan_many(mkts)
    out = _scenario_rows(spec, mkts, rows, hists)
    prof = st["profile"]
    for r in out:
        r["sizing"] = portfolio.size(r, prof, fractional=prof.get("fractional") or r.get("fractional"))
        r.pop("betas", None)
    return J({"spec": scenario.clamp(spec) | {"text": spec.get("text", ""), "source": spec.get("source", "")},
              "markets": [markets.market_def(m)["name"] for m in mkts], "rows": out, "levels": scenario.driver_levels()})


# ---------------------------------------------------------------- AI
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
              f"'## Portfolio shape' (diversification across markets/sectors, cash, currency risk) and '## Watch out for'. "
              f"Markets used: {plan.get('market')}. " + (f"The plan is built for the what-if scenario: {plan['scenario']}. " if plan.get("scenario") else "")
              + f"Profile: {plan['profile']}, equity {plan['equity']:,.0f} {plan['currency']}, cash after plan {plan['cashEnd']:,.0f}, "
              f"total risk at stops {plan['totalRisk']:,.0f}.\nActions:\n{acts}\nSectors: {json.dumps(plan['sectors'])}")
    fb = "## Today's game plan\n" + acts + f"\n\nCash after plan: {plan['cashEnd']:,.2f} {plan['currency']}. *(Start Ollama for an AI explanation.)*"
    return _text_stream(ai.stream([{"role": "user", "content": prompt}]), fb)


@app.post("/api/ai/scenario")
def api_ai_scenario(body: dict = Body(...)):
    spec, rows = body["spec"], body.get("rows", [])
    mv = ", ".join(f"{scenario.DRIVERS[k][1]} {v:+g}{'pp' if k == 'rates' else '%'}" for k, v in spec["moves"].items() if v)
    top = lambda rs: "\n".join(f"- {r['symbol']} ({r['name']}, {r.get('sector')}, {r.get('marketName')}): projected {r['expected'] * 100:+.1f}%, score {r['score']:+.0f}; drivers: "  # noqa: E731
                               + "; ".join(d["label"] for d in r.get("drivers", [])[:3]) for r in rs)
    winners = [r for r in rows if r["score"] > 0][:8]
    losers = sorted([r for r in rows if r["score"] < 0], key=lambda r: r["score"])[:6]
    prompt = (f"A user asked: what if \"{spec.get('text') or spec.get('title')}\"?\nOur model translated it into: {mv}. "
              f"Sector views: {json.dumps(spec.get('sectors'))}. Themes: {json.dumps(spec.get('themes'))}.\n"
              f"Markets screened: {', '.join(body.get('markets', []))}.\nBest positioned:\n{top(winners)}\nMost exposed:\n{top(losers)}\n\n"
              "Write markdown with sections '## How this scenario could play out' (causal chain, 3-5 bullets), '## Best-positioned stocks' "
              "(why each top pick benefits, referencing its drivers), '## Most exposed', '## How to position' (practical, sized, with hedges) and "
              "'## What would make this wrong'. Use only the data given.")
    fb = "## Best-positioned\n" + top(winners) + "\n\n## Most exposed\n" + top(losers) + "\n\n*(Start Ollama for an AI narrative.)*"
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
