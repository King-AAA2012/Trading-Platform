"""Local, free AI analyst via Ollama (https://ollama.com). Nothing leaves your machine.
If Ollama isn't running, a deterministic write-up built from the engine's reasons is returned instead."""
from __future__ import annotations

import json
import os

import requests

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
PREFERRED = ["llama3.1:8b", "llama3.1:latest", "qwen2.5:7b", "llama3:latest", "mistral:latest", "qwen3.5:0.8b"]
SYSTEM = ("You are TradeScope's research analyst. You explain stock, crypto, FX and commodity setups clearly for both beginners "
          "and professionals. Use ONLY the data provided; never invent numbers, news or events. Be specific, balanced and concise. "
          "Always mention the key risk and the stop level. This is a research tool: never tell the user to place a trade with a broker, "
          "and remind them it is not financial advice in one short line at the end.")


def status() -> dict:
    try:
        r = requests.get(f"{OLLAMA}/api/tags", timeout=2)
        models = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return {"online": False, "model": None, "models": []}
    chat = [m for m in models if "embed" not in m]
    pick = os.environ.get("TRADESCOPE_MODEL") or next((m for m in PREFERRED if m in chat), chat[0] if chat else None)
    return {"online": bool(pick), "model": pick, "models": chat}


def stream(messages: list[dict], model: str | None = None):
    st = status()
    model = model if model in st["models"] else st["model"]
    if not st["online"]:
        yield None
        return
    try:
        with requests.post(f"{OLLAMA}/api/chat", json={"model": model, "messages": [{"role": "system", "content": SYSTEM}] + messages,
                                                        "stream": True, "options": {"temperature": 0.3, "num_ctx": 8192}},
                           stream=True, timeout=300) as r:
            for line in r.iter_lines():
                if not line:
                    continue
                j = json.loads(line)
                if j.get("message", {}).get("content"):
                    yield j["message"]["content"]
                if j.get("done"):
                    break
    except Exception as e:
        yield f"\n\n[AI error: {e}]"


def fmt_money(x, ccy=""):
    return f"{x:,.2f} {ccy}".strip() if isinstance(x, (int, float)) else "n/a"


def stock_context(a: dict, sz: dict | None, news: list[dict], profile: dict) -> str:
    lv = a["levels"]
    f = a.get("fundamentals") or {}
    lines = [
        f"Instrument: {a['name']} ({a['symbol']}), price {fmt_money(a['price'], a['currency'])}, today {a['changePct']:+.2f}%",
        f"Model signal: {a['signal']} | composite score {a['score']:+.1f}/100 (technical {a['techScore']:+.1f}, fundamental {a['fundScore'] if a['fundScore'] is not None else 'n/a'}) | confidence {a['confidence']:.0f}% | setup: {a['setup']}",
        "Factors (-1 bearish .. +1 bullish): " + ", ".join(f"{x['label']} {x['value']:+.2f}" for x in a["factors"]),
        f"RSI {a['rsi']:.0f}, ADX {a['adx']:.0f}, daily volatility (ATR) {a['atrPct'] * 100:.1f}%, 1m {pct(a['ret1m'])}, 3m {pct(a['ret3m'])}, 1y {pct(a['ret1y'])}, at {a['pos52'] * 100:.0f}% of 52-week range",
        f"Levels: entry zone {lv['entryLow']:.2f}-{lv['entryHigh']:.2f}, stop {lv['stop']:.2f}, target1 {lv['t1']:.2f}, target2 {lv['t2']:.2f}, support {lv['support']:.2f}, resistance {lv['resistance']:.2f}",
        "Engine reasons: " + " | ".join(r["text"] for r in a["reasons"]),
        "Risks: " + " | ".join(a["risks"][:-1]),
    ]
    bt = a.get("backtest") or {}
    if bt.get("ok"):
        s = bt["strategy"]
        lines.append(f"Backtest over {bt['years']}y on this instrument: model strategy {pct(s['total'])} (max drawdown {pct(s['maxdd'])}, {s['trades']} trades, win rate {pct(s['winrate'])}) vs buy & hold {pct(bt['buyhold']['total'])}")
    if f:
        keys = ["sector", "industry", "marketCap", "trailingPE", "forwardPE", "revenueGrowth", "earningsGrowth", "profitMargin", "roe",
                "debtToEquity", "dividendYield", "targetMean", "recommendationKey", "analysts", "nextEarnings"]
        lines.append("Fundamentals: " + ", ".join(f"{k}={f[k]}" for k in keys if f.get(k) is not None))
        if f.get("summary"):
            lines.append("Business: " + f["summary"][:600])
    if sz:
        lines.append(f"User profile: budget {fmt_money(profile.get('budget'), profile.get('currency'))}, risk {profile.get('risk')}. Suggested size: {sz['qty']} units ≈ {fmt_money(sz['cost'], profile.get('currency'))} ({sz['pct'] * 100:.1f}% of budget), max loss at stop {fmt_money(sz['riskAmount'], profile.get('currency'))}")
    if news:
        lines.append("Recent headlines: " + " | ".join(n["title"] for n in news[:8] if n.get("title")))
    return "\n".join(lines)


def pct(x):
    return f"{x * 100:+.1f}%" if isinstance(x, (int, float)) else "n/a"


REPORT_PROMPT = """Write a research note from the data below using these markdown sections:
## Verdict
(1-2 sentences: the action — buy / accumulate / hold / avoid / short candidate — and conviction)
## Why
(4-6 bullets combining trend, momentum, fundamentals and news)
## The plan
(entry zone, stop, targets, how much to buy for this user's budget and why, how long to hold)
## What could go wrong
(3 bullets)
## For beginners
(2-3 sentences in plain English)

DATA:
{ctx}"""


def fallback_report(a: dict, sz: dict | None, profile: dict) -> str:
    lv = a["levels"]
    verb = {"STRONG BUY": "Buy with high conviction", "BUY": "Buy / accumulate", "HOLD": "Hold / wait for a clearer setup",
            "SELL": "Avoid or reduce", "STRONG SELL": "Avoid; short candidate for experienced traders"}[a["signal"]]
    out = [f"## Verdict\n**{verb}**: score {a['score']:+.0f}/100, confidence {a['confidence']:.0f}%, setup *{a['setup']}*.",
           "## Why"] + [f"- {r['text']}" for r in a["reasons"]]
    out.append("## The plan")
    if a["bias"] != "neutral":
        out.append(f"- Entry zone **{lv['entryLow']:,.2f} to {lv['entryHigh']:,.2f}**, stop **{lv['stop']:,.2f}** ({lv['riskPct'] * 100:.1f}% away)")
        out.append(f"- Target 1 **{lv['t1']:,.2f}** (2R), Target 2 **{lv['t2']:,.2f}** (3.5R). Take partial profits at T1 and move the stop to breakeven.")
        if sz and sz["qty"]:
            out.append(f"- Suggested size: **{sz['qty']} units ≈ {sz['cost']:,.2f} {profile.get('currency')}** ({sz['pct'] * 100:.1f}% of budget). {sz['note']}")
        out.append("- Typical holding period: 2 to 8 weeks (swing), reviewed daily by the plan.")
    else:
        out.append(f"- No trade. Watch for a close above **{lv['resistance']:,.2f}** (bullish) or below **{lv['support']:,.2f}** (bearish).")
    out.append("## What could go wrong")
    out += [f"- {r}" for r in a["risks"]]
    out.append("\n*Start Ollama for a full AI-written narrative. This report was generated by the rules engine.*")
    return "\n".join(out)
