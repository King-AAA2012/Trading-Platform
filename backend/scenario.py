"""What-if scenario engine.

1. A free-text event ("oil hits $130 after a Gulf conflict") is turned into a structured shock: % moves in ten macro
   drivers, sector tilts, industry themes and country tilts. The local AI does this; a keyword rulebook is the fallback.
2. Every stock's sensitivity to those drivers is estimated with a ridge regression of its weekly returns on the
   drivers' weekly returns over two years (weekly bars sidestep different exchange time zones).
3. Projected move = Σ beta × driver move + sector/theme/country tilts. It is blended with the current technical
   score (a scenario pick that is already trending the right way ranks higher), then sized like any other idea.
"""
from __future__ import annotations

import json
import re

import numpy as np
import requests

from . import ai, data

DRIVERS = {  # key: (symbol, label, unit)
    "equities": ("^GSPC", "Global stocks (S&P 500)", "%"), "oil": ("CL=F", "Crude oil", "%"), "gold": ("GC=F", "Gold", "%"),
    "rates": ("^TNX", "US 10Y yield", "pp"), "dollar": ("DX-Y.NYB", "US dollar", "%"), "vol": ("^VIX", "Volatility (VIX)", "%"),
    "copper": ("HG=F", "Copper", "%"), "bitcoin": ("BTC-USD", "Bitcoin", "%"), "china": ("FXI", "China stocks", "%"),
    "natgas": ("NG=F", "Natural gas", "%"),
}
SECTORS = ["Technology", "Financial Services", "Healthcare", "Consumer Cyclical", "Consumer Defensive", "Energy", "Industrials",
           "Basic Materials", "Communication Services", "Utilities", "Real Estate"]
LIMIT = {"rates": 3.0, "vol": 200.0}


# ---------------------------------------------------------------- parsing
def _blank() -> dict:
    return {"title": "", "summary": "", "moves": {k: 0.0 for k in DRIVERS}, "sectors": {}, "themes": [], "countries": {}, "source": "rules"}


RULES = [  # (pattern, spec fragment). Fragments are summed, then clipped.
    (r"oil|crude|opec|brent|strait of hormuz|refiner", {"moves": {"oil": 30, "natgas": 12, "equities": -3, "vol": 15},
      "sectors": {"Energy": 0.8}, "themes": [("airline", -0.8), ("oil", 0.8), ("shipping", 0.3), ("chemical", -0.3)]}),
    (r"rate cut|cuts? rates|dovish|easing|fed (?:cut|pivot)|lower rates|qe\b", {"moves": {"rates": -0.75, "equities": 5, "gold": 4, "dollar": -3, "vol": -10, "bitcoin": 10},
      "sectors": {"Real Estate": 0.6, "Utilities": 0.4, "Technology": 0.4, "Consumer Cyclical": 0.3, "Financial Services": -0.2}}),
    (r"rate hike|hikes? rates|hawkish|tightening|higher rates|inflation (?:surge|spike|jump|rise)|stagflation", {"moves": {"rates": 0.75, "equities": -6, "gold": -2, "dollar": 3, "vol": 25, "bitcoin": -12},
      "sectors": {"Technology": -0.5, "Real Estate": -0.6, "Utilities": -0.3, "Financial Services": 0.3}, "themes": [("bank", 0.4), ("insurance", 0.3)]}),
    (r"recession|crash|depression|slowdown|downturn|bear market|financial crisis|credit crunch", {"moves": {"equities": -20, "vol": 90, "oil": -25, "copper": -20, "rates": -1.0, "gold": 6, "bitcoin": -30, "china": -15},
      "sectors": {"Consumer Defensive": 0.5, "Utilities": 0.4, "Healthcare": 0.3, "Consumer Cyclical": -0.6, "Industrials": -0.4, "Financial Services": -0.4, "Basic Materials": -0.5}}),
    (r"war|invad|invasion|conflict|missile|attack|military|escalat|terror", {"moves": {"vol": 50, "equities": -8, "oil": 15, "gold": 8, "dollar": 2},
      "themes": [("aerospace", 0.9), ("defense", 0.9), ("airline", -0.6), ("travel", -0.5), ("cyber", 0.4)]}),
    (r"taiwan|tsmc|chip ban|semiconductor (?:ban|shortage)", {"moves": {"equities": -8, "vol": 40, "china": -15},
      "themes": [("semiconductor", -0.7)], "countries": {"tw": -0.9, "cn": -0.6, "kr": -0.3, "us": -0.1}}),
    (r"china stimulus|beijing stimulus|china (?:recovery|reopen|boom)|pboc (?:cut|eas)", {"moves": {"china": 18, "copper": 12, "oil": 6, "equities": 3},
      "sectors": {"Basic Materials": 0.6, "Consumer Cyclical": 0.3}, "countries": {"cn": 0.8, "hk": 0.7, "au": 0.3, "kr": 0.2, "de": 0.2}}),
    (r"pandemic|virus|outbreak|lockdown|covid", {"moves": {"equities": -15, "vol": 100, "oil": -30, "rates": -0.8, "gold": 5},
      "sectors": {"Healthcare": 0.5}, "themes": [("biotech", 0.6), ("travel", -0.9), ("airline", -0.9), ("hotel", -0.8), ("casino", -0.7), ("software", 0.3), ("internet retail", 0.5)]}),
    (r"\bai\b|artificial intelligence|data ?center|gpu|chatbot", {"moves": {"equities": 6, "copper": 4, "natgas": 4},
      "sectors": {"Technology": 0.8, "Utilities": 0.3, "Communication Services": 0.4}, "themes": [("semiconductor", 0.9), ("software", 0.5), ("electrical", 0.5)]}),
    (r"tariff|trade war|sanction|protectionis", {"moves": {"equities": -6, "china": -12, "dollar": 3, "vol": 25, "copper": -5},
      "sectors": {"Industrials": -0.3, "Consumer Cyclical": -0.3}, "themes": [("auto", -0.5), ("steel", 0.3)], "countries": {"cn": -0.6, "mx": -0.5, "ca": -0.3, "de": -0.3}}),
    (r"bitcoin|crypto|ethereum|etf approval", {"moves": {"bitcoin": 35}, "themes": [("crypto", 0.9), ("capital markets", 0.3)]}),
    (r"dollar (?:surge|rall|strength|soar)|strong dollar", {"moves": {"dollar": 8, "gold": -5, "china": -6, "copper": -5, "equities": -2}, "countries": {"in": -0.3, "br": -0.3, "za": -0.3, "tr": -0.4}}),
    (r"dollar (?:crash|fall|weak|plunge)|weak dollar|de-?dollari", {"moves": {"dollar": -8, "gold": 10, "copper": 6, "bitcoin": 15, "china": 6}, "countries": {"in": 0.3, "br": 0.3, "za": 0.3}}),
    (r"gold (?:surge|rall|soar|spike)|gold to", {"moves": {"gold": 20}, "themes": [("gold", 0.9), ("silver", 0.6)]}),
    (r"natural gas|lng|gas shortage|energy crisis", {"moves": {"natgas": 60, "oil": 10}, "sectors": {"Utilities": -0.3, "Energy": 0.5}, "countries": {"de": -0.4, "it": -0.3}}),
    (r"housing (?:boom|recovery)|mortgage rates? fall", {"moves": {"rates": -0.4}, "sectors": {"Real Estate": 0.6}, "themes": [("residential construction", 0.8), ("building", 0.5)]}),
    (r"bank(?:ing)? crisis|bank run|bank failure", {"moves": {"equities": -8, "vol": 60, "rates": -0.6, "gold": 6, "bitcoin": 10},
      "sectors": {"Financial Services": -0.8}, "themes": [("bank", -0.9)]}),
    (r"climate|renewable|green deal|carbon tax|solar|wind power|\bev\b|electric vehicle", {"moves": {"copper": 8},
      "themes": [("solar", 0.8), ("renewable", 0.7), ("utilities", 0.3), ("auto", 0.2), ("coal", -0.6), ("oil", -0.3)]}),
    (r"soft landing|rally|boom|bull market|goldilocks", {"moves": {"equities": 10, "vol": -25, "copper": 5, "rates": 0.1},
      "sectors": {"Consumer Cyclical": 0.4, "Technology": 0.3, "Consumer Defensive": -0.2, "Utilities": -0.2}}),
]
BEAR = r"(fall|drop|crash|collapse|plunge|slump|sink|tumble|decline|cheap|glut|below)"
COUNTRY_WORDS = {"india": "in", "china": "cn", "japan": "jp", "germany": "de", "uk": "gb", "britain": "gb", "france": "fr", "brazil": "br",
                 "mexico": "mx", "canada": "ca", "korea": "kr", "taiwan": "tw", "australia": "au", "russia": None, "saudi": "sa", "israel": "il",
                 "turkey": "tr", "south africa": "za", "italy": "it", "spain": "es", "switzerland": "ch", "hong kong": "hk", "indonesia": "id"}


ALIASES = {"ja": "jp", "uk": "gb", "sk": "kr", "so": "kr", "ko": "kr", "usa": "us", "prc": "cn", "ch": "cn"}  # LLMs often write CH for China


def _country_code(k: str) -> str | None:
    k = k.strip().lower()
    if k in COUNTRY_WORDS:
        return COUNTRY_WORDS[k]
    if k in ("switzerland", "swiss", "sw"):
        return "ch"
    k = ALIASES.get(k, k)
    return k if len(k) == 2 and k.isalpha() else None


def parse_rules(text: str) -> dict:
    t = text.lower()
    spec = _blank()
    hits = []
    for pat, frag in RULES:
        m = re.search(pat, t)
        if not m:
            continue
        hits.append(m.group(0))
        # invert commodity/crypto rules when the text says they fall ("oil crashes", "bitcoin collapses")
        window = t[max(0, m.start() - 25): m.end() + 40]
        sign = -1 if pat.startswith(("oil", "bitcoin", r"gold (", "natural")) and re.search(BEAR, window) else 1
        for k, v in frag.get("moves", {}).items():
            spec["moves"][k] += sign * v
        for k, v in frag.get("sectors", {}).items():
            spec["sectors"][k] = spec["sectors"].get(k, 0) + sign * v
        for kw, v in frag.get("themes", []):
            spec["themes"].append({"keyword": kw, "impact": sign * v})
        for k, v in frag.get("countries", {}).items():
            spec["countries"][k] = spec["countries"].get(k, 0) + sign * v
    for w, code in COUNTRY_WORDS.items():
        if code and re.search(rf"\b{w}\b", t) and code not in spec["countries"]:
            spec["countries"][code] = -0.4 if re.search(r"crisis|war|sanction|default|collapse|crash|invad|recession|tariff", t) else 0.4
    if not hits:
        spec["moves"].update({"vol": 20, "equities": -3})
        spec["summary"] = "No known pattern recognised; assuming a generic risk-off shock. Edit the driver moves below."
    else:
        spec["summary"] = "Rule-based interpretation (matched: " + ", ".join(dict.fromkeys(hits)) + "). Edit the moves to refine."
    spec["title"] = text.strip()[:80]
    return clamp(spec)


def clamp(spec: dict) -> dict:
    out = _blank()
    out.update({k: spec.get(k, out[k]) for k in ("title", "summary", "source")})
    for k in DRIVERS:
        v = float((spec.get("moves") or {}).get(k) or 0)
        lim = LIMIT.get(k, 80.0)
        out["moves"][k] = float(np.clip(v, -lim, lim))
    out["sectors"] = {k: float(np.clip(v, -1, 1)) for k, v in (spec.get("sectors") or {}).items() if k in SECTORS and v}
    th = {}
    for x in spec.get("themes") or []:
        if isinstance(x, dict) and x.get("keyword"):
            kw = str(x["keyword"]).lower().strip()[:30]
            th[kw] = float(np.clip(th.get(kw, 0) + float(x.get("impact") or 0), -1, 1))
    out["themes"] = [{"keyword": k, "impact": v} for k, v in th.items() if v]
    out["countries"] = {}
    for k, v in (spec.get("countries") or {}).items():
        code = _country_code(str(k))
        if code and v:
            out["countries"][code] = float(np.clip(out["countries"].get(code, 0) + float(v), -1, 1))
    return out


PARSE_PROMPT = """You convert a hypothetical market event into expected market moves over the next 1-3 months.
Respond with ONLY a JSON object with exactly these keys:
{{"title": "<=8 words", "summary": "one sentence on the causal chain",
 "moves": {{"equities": <% change S&P 500>, "oil": <%>, "gold": <%>, "rates": <change in US 10-year yield in PERCENTAGE POINTS, e.g. -0.5>,
            "dollar": <% change dollar index>, "vol": <% change in VIX>, "copper": <%>, "bitcoin": <%>, "china": <% change China stocks>, "natgas": <%>}},
 "sectors": {{<sector>: <impact -1..1>}},   (only from: {sectors})
 "themes": [{{"keyword": "<lowercase industry word e.g. defense, aerospace, airline, semiconductor, bank, insurance, gold, oil, solar, shipping, biotech, software, auto, steel, travel, hotel, reit, crypto, utilities>", "impact": <-1..1>}}],
 "countries": {{"<country code>": <impact -1..1>}} }}   country codes: us, cn (China), jp (Japan), tw, kr (South Korea), in, gb, de, fr, sw (Switzerland), br, mx, ca, au, sa, il, za
Use realistic magnitudes from historical analogues (e.g. 2022 Ukraine war: oil +30%, VIX +60%, S&P -8%; 2020 pandemic: S&P -30%, VIX +300% capped at 200).
Use 0 for drivers that are unaffected. Event: "{event}" """


def parse_ai(text: str) -> dict | None:
    st = ai.status()
    if not st["online"]:
        return None
    try:
        r = requests.post(f"{ai.OLLAMA}/api/chat", json={
            "model": st["model"], "stream": False, "format": "json", "options": {"temperature": 0.2, "num_ctx": 4096},
            "messages": [{"role": "user", "content": PARSE_PROMPT.format(event=text.replace('"', "'")[:600], sectors=", ".join(SECTORS))}]},
            timeout=180)
        spec = json.loads(r.json()["message"]["content"])
        spec = clamp(spec)
        if not any(spec["moves"].values()) and not spec["sectors"] and not spec["themes"]:
            return None
        spec["source"] = f"AI ({st['model']})"
        spec["title"] = spec["title"] or text[:80]
        return spec
    except Exception as e:
        print("scenario AI parse failed:", e)
        return None


def interpret(text: str, use_ai: bool = True) -> dict:
    spec = parse_ai(text) if use_ai else None
    if spec is None:
        spec = parse_rules(text)
    else:  # add any themes/countries the rulebook catches that the model missed
        rb = parse_rules(text)
        have = {t["keyword"] for t in spec["themes"]}
        spec["themes"] += [t for t in rb["themes"] if t["keyword"] not in have]
        for k, v in rb["countries"].items():
            spec["countries"].setdefault(k, v)
    spec["text"] = text
    return spec


# ---------------------------------------------------------------- sensitivities
def _weekly(t: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    wk = (t // 86400 + 3) // 7
    last = np.flatnonzero(np.diff(wk, append=wk[-1] + 1))
    return wk[last], c[last]


def driver_panel() -> dict:
    def load():
        out = {}
        for k, (sym, _, _) in DRIVERS.items():
            h = data.get_history(sym, "2y")
            if h is not None and len(h["c"]) > 60:
                out[k] = _weekly(h["t"], h["c"])
        return out
    return data.cached("scenario:drivers", 3600, load)


def betas(h: dict, panel: dict) -> tuple[dict, float]:
    w, c = _weekly(h["t"][-520:], h["c"][-520:])
    keys = [k for k in DRIVERS if k in panel]
    common = w
    for k in keys:
        common = np.intersect1d(common, panel[k][0])
    if len(common) < 30:
        return {}, 0.0

    def rets(ww, cc):
        idx = np.searchsorted(ww, common)
        return np.diff(np.log(np.maximum(cc[idx], 1e-9)))
    y = rets(w, c)
    X = np.column_stack([rets(*panel[k]) for k in keys])
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    y, X = y[ok], X[ok]
    if len(y) < 40:            # < ~9 months of weekly data: sensitivities would be noise
        return {}, 0.0
    mu, sd = X.mean(0), X.std(0) + 1e-12
    Z = (X - mu) / sd
    lam = 0.15 * len(y)
    b = np.linalg.solve(Z.T @ Z + lam * np.eye(len(keys)), Z.T @ (y - y.mean()))
    pred = Z @ b
    r2 = float(max(0.0, 1 - np.var(y - y.mean() - pred) / (np.var(y) + 1e-12)))
    shrink = len(y) / (len(y) + 30)   # short histories get pulled toward zero exposure
    return {k: float(shrink * b[i] / sd[i]) for i, k in enumerate(keys)}, r2


def driver_levels() -> dict:
    out = {}
    for k, (sym, label, unit) in DRIVERS.items():
        h = data.get_history(sym, "2y")
        out[k] = {"symbol": sym, "label": label, "unit": unit, "level": float(h["c"][-1]) if h else None}
    return out


def _pct_move(k: str, v: float, levels: dict) -> float:
    """Driver move as a fractional change (rates are given in percentage points)."""
    if k == "rates":
        lvl = levels.get("rates", {}).get("level") or 4.0
        return v / lvl
    return v / 100.0


def project(rows: list[dict], hists: dict[str, dict], spec: dict, region_of: dict[str, str]) -> list[dict]:
    panel = driver_panel()
    levels = driver_levels()
    mv = {k: _pct_move(k, v, levels) for k, v in spec["moves"].items() if v}
    labels = {k: v[1] for k, v in DRIVERS.items()}
    out = []
    for r in rows:
        h = hists.get(r["symbol"])
        if h is None:
            continue
        b, r2 = betas(h, panel)
        drivers = []
        er = 0.0
        for k, m in mv.items():
            if k in b:
                # log-space shock so that e.g. VIX +200% doesn't explode linearly
                c = b[k] * np.log1p(max(m, -0.95))
                er += c
                if abs(c) > 0.002:
                    drivers.append({"label": f"{labels[k]} {spec['moves'][k]:+g}{'pp' if k == 'rates' else '%'} × β {b[k]:+.2f}", "contrib": float(c)})
        sec = r.get("sector") or ""
        if spec["sectors"].get(sec):
            c = 0.10 * spec["sectors"][sec]
            er += c
            drivers.append({"label": f"Sector view: {sec}", "contrib": c})
        hay = f"{r.get('industry', '')} {sec} {r.get('name', '')}".lower()
        for th in spec["themes"]:
            if th["keyword"] and th["keyword"] in hay:
                c = 0.08 * th["impact"]
                er += c
                drivers.append({"label": f"Theme: {th['keyword']}", "contrib": c})
        reg = region_of.get(r["symbol"], "")
        if reg and spec["countries"].get(reg):
            c = 0.06 * spec["countries"][reg]
            er += c
            drivers.append({"label": f"Country view: {reg.upper()}", "contrib": c})
        er = float(np.clip(np.expm1(er), -0.7, 1.5))
        s_scen = 100 * np.tanh(er / 0.10)
        score = float(np.clip(0.75 * s_scen + 0.25 * r["techScore"], -100, 100))
        agree = np.sign(s_scen) == np.sign(r["techScore"])
        conf = float(np.clip(30 + 35 * min(r2 * 2, 1) + (12 if agree else -8) + min(abs(er) * 60, 15), 8, 90))
        out.append({**r, "expected": er, "scenScore": float(s_scen), "score": round(score, 1), "confidence": round(conf, 1), "r2": r2,
                    "bias": "long" if score >= 20 else "short" if score <= -20 else "neutral",
                    "drivers": sorted(drivers, key=lambda d: -abs(d["contrib"]))[:6], "betas": b})
    out.sort(key=lambda x: -x["score"])
    return out


def region_for(market_id: str, symbol: str) -> str:
    if market_id.startswith("r-"):
        return market_id[2:]
    suf = {".NS": "in", ".BO": "in", ".L": "gb", ".T": "jp", ".HK": "hk", ".TO": "ca", ".AX": "au", ".DE": "de", ".PA": "fr", ".AS": "nl",
           ".MI": "it", ".MC": "es", ".SW": "ch", ".CO": "dk", ".KS": "kr", ".TW": "tw", ".SS": "cn", ".SZ": "cn", ".SA": "br", ".MX": "mx"}
    for k, v in suf.items():
        if symbol.endswith(k):
            return v
    return "us" if "." not in symbol and "=" not in symbol and "-" not in symbol and not symbol.startswith("^") else ""
