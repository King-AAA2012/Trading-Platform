"""Wolf Exchange: a deterministic imaginary stock market for practice and contests.

Prices come from a factor model (market + sector + stock-specific noise) with bull/bear regime switching and random
news-driven jumps. The full path is generated from a seed, and only bars up to the current day pointer are ever
revealed, so the engine never sees the future. Advancing a day reveals the next bar."""
from __future__ import annotations

import json
import time

import numpy as np

from .data import DATA_DIR

MARKET_NAME = "Wolf Exchange (imaginary)"
STATE = DATA_DIR / "sim_state.json"
WARMUP, TOTAL = 400, 1400
COMPANIES = [  # ticker, name, sector, drift (annual), vol (annual)
    ("WOLF", "Wolfpack Capital", "Financials", 0.10, 0.30), ("BULL", "Bullrun Holdings", "Financials", 0.08, 0.25),
    ("STRT", "Stratton Securities", "Financials", 0.02, 0.45), ("GRDN", "Gordon Gekko Partners", "Financials", 0.06, 0.28),
    ("NOVA", "NovaChip Semiconductors", "Technology", 0.22, 0.45), ("QBIT", "Qubit Labs", "Technology", 0.15, 0.60),
    ("CLDX", "CloudNexus", "Technology", 0.14, 0.38), ("PIXL", "Pixel Forge Games", "Technology", 0.05, 0.42),
    ("HELX", "Helix Biotherapeutics", "Healthcare", 0.09, 0.55), ("MEDI", "MediCore Systems", "Healthcare", 0.07, 0.22),
    ("GENX", "GenomeX", "Healthcare", 0.03, 0.65), ("PETR", "Petra Oil & Gas", "Energy", 0.04, 0.35),
    ("SOLR", "Solaris Renewables", "Energy", 0.12, 0.50), ("VOLT", "Voltline Utilities", "Energy", 0.05, 0.18),
    ("STEK", "Steakhouse Brands", "Consumer", 0.06, 0.24), ("LUXE", "Maison Luxe", "Consumer", 0.09, 0.30),
    ("DRIP", "Drip Coffee Co", "Consumer", -0.02, 0.33), ("YOLO", "YOLO Motors", "Consumer", 0.18, 0.75),
    ("RAIL", "Iron Rail Logistics", "Industrials", 0.06, 0.25), ("AERO", "AeroDyne Defense", "Industrials", 0.08, 0.27),
    ("BLDR", "Titan Builders", "Industrials", 0.03, 0.32), ("MINE", "Deepcore Mining", "Materials", 0.02, 0.48),
    ("GOLD", "Aurum Metals", "Materials", 0.04, 0.26), ("MEME", "Diamond Hands Inc", "Speculative", 0.00, 1.00),
]
_TPL_UP = ["{n} smashes earnings expectations", "{n} wins major government contract", "Analysts upgrade {n} to Strong Buy",
           "{n} announces surprise buyback", "{n} unveils breakthrough product", "Takeover rumours swirl around {n}"]
_TPL_DN = ["{n} misses revenue estimates", "Regulators open probe into {n}", "{n} CEO resigns unexpectedly",
           "{n} cuts full-year guidance", "Short seller publishes report on {n}", "{n} recalls flagship product"]
_cache: dict = {}


def _state() -> dict:
    try:
        return json.loads(STATE.read_text("utf-8"))
    except Exception:
        return {"seed": 1987, "day": WARMUP}


def _save(s: dict) -> None:
    STATE.write_text(json.dumps(s), "utf-8")
    _cache.clear()


def _generate(seed: int) -> dict:
    if seed in _cache:
        return _cache[seed]
    rng = np.random.default_rng(seed)
    n, k = TOTAL, len(COMPANIES)
    sectors = sorted({c[2] for c in COMPANIES})
    # market regime: Markov switching between bull (low vol, positive drift) and bear
    regime = np.zeros(n, dtype=int)
    for i in range(1, n):
        regime[i] = regime[i - 1] if rng.random() > (0.006 if regime[i - 1] == 0 else 0.02) else 1 - regime[i - 1]
    mdrift = np.where(regime == 0, 0.10, -0.20) / 252
    mvol = np.where(regime == 0, 0.13, 0.28) / np.sqrt(252)
    mkt = mdrift + mvol * rng.standard_normal(n)
    sec = {s: 0.12 / np.sqrt(252) * rng.standard_normal(n) for s in sectors}
    events: list[dict] = []
    closes = np.zeros((n, k))
    opens, highs, lows, vols = (np.zeros((n, k)) for _ in range(4))
    for j, (tk, name, s, mu, sig) in enumerate(COMPANIES):
        beta = 0.6 + rng.random() * 0.9
        idio = sig / np.sqrt(252) * rng.standard_normal(n) * 0.8
        jumps = np.zeros(n)
        for d in np.flatnonzero(rng.random(n) < 0.006):
            size = rng.choice([-1, 1]) * (0.05 + rng.random() * 0.15) * (1.5 if tk in ("MEME", "YOLO", "GENX") else 1)
            jumps[d] = size
            tpl = _TPL_UP if size > 0 else _TPL_DN
            events.append({"day": int(d), "symbol": tk, "title": tpl[rng.integers(len(tpl))].format(n=name), "move": float(size)})
        # slowly varying idiosyncratic trend, so real trends exist for the engine to find
        tr = np.cumsum(rng.standard_normal(n)) * 0.00015
        r = mu / 252 + beta * mkt + sec[s] + idio + jumps + (tr - tr.mean()) * 0.02
        c = (20 + rng.random() * 280) * np.exp(np.cumsum(r - 0.5 * (sig / np.sqrt(252)) ** 2))
        o = c * np.exp(rng.standard_normal(n) * sig / np.sqrt(252) * 0.35)
        o[1:] = np.where(rng.random(n - 1) < 0.5, c[:-1] * (1 + jumps[1:] * 0.7), o[1:])
        spread = np.abs(rng.standard_normal(n)) * sig / np.sqrt(252) * c * 0.6
        closes[:, j], opens[:, j] = c, o
        highs[:, j] = np.maximum(o, c) + spread
        lows[:, j] = np.maximum(np.minimum(o, c) - spread, 0.01)
        base = rng.integers(200_000, 5_000_000)
        vols[:, j] = base * (1 + 4 * np.abs(r) / (sig / np.sqrt(252))) * np.exp(rng.standard_normal(n) * 0.3)
    # business-day timestamps with WARMUP ending "today" at generation time
    today = int(time.time() // 86400)
    days = []
    d = today
    while len(days) < WARMUP:
        if (d + 3) % 7 < 5:  # 1970-01-01 was Thursday; weekday check
            days.append(d)
        d -= 1
    days = days[::-1]
    d = today + 1
    while len(days) < TOTAL:
        if (d + 3) % 7 < 5:
            days.append(d)
        d += 1
    idx = {"t": np.array(days, dtype=np.int64) * 86400 + 20 * 3600, "o": opens, "h": highs, "l": lows, "c": closes, "v": vols,
           "events": events, "index": np.exp(np.cumsum(mkt)) * 1000}
    _cache.clear()
    _cache[seed] = idx
    return idx


def _col(symbol: str) -> int:
    tk = symbol.split(":", 1)[1]
    for j, c in enumerate(COMPANIES):
        if c[0] == tk:
            return j
    raise KeyError(symbol)


def history(symbol: str) -> dict | None:
    st = _state()
    g = _generate(st["seed"])
    day = st["day"]
    if symbol == "SIM:INDEX":
        c = g["index"][:day]
        return {"symbol": symbol, "t": g["t"][:day], "o": c, "h": c, "l": c, "c": c, "v": np.zeros(day),
                "meta": {"name": "Wolf Exchange Index", "currency": "USD", "exchange": "Wolf Exchange", "type": "INDEX"}}
    try:
        j = _col(symbol)
    except KeyError:
        return None
    tk, name, sec, *_ = COMPANIES[j]
    return {"symbol": symbol, "t": g["t"][:day], "o": g["o"][:day, j], "h": g["h"][:day, j], "l": g["l"][:day, j],
            "c": g["c"][:day, j], "v": g["v"][:day, j],
            "meta": {"name": name, "currency": "USD", "exchange": "Wolf Exchange", "type": "EQUITY", "sector": sec}}


def sector(symbol: str) -> str:
    try:
        return COMPANIES[_col(symbol)][2]
    except KeyError:
        return "Index"


def news(symbol: str) -> list[dict]:
    st = _state()
    g = _generate(st["seed"])
    tk = symbol.split(":", 1)[1]
    ev = [e for e in g["events"] if e["day"] < st["day"] and (e["symbol"] == tk or tk == "INDEX")]
    return [{"title": e["title"], "publisher": "Wolf Street Journal", "link": None, "time": int(g["t"][e["day"]]),
             "move": e["move"]} for e in sorted(ev, key=lambda e: -e["day"])[:15]]


def market_def() -> dict:
    return {"name": MARKET_NAME, "benchmark": "SIM:INDEX", "currency": "USD", "shortable": True, "fractional": False,
            "symbols": [f"SIM:{c[0]}" for c in COMPANIES]}


def status() -> dict:
    st = _state()
    g = _generate(st["seed"])
    return {"seed": st["seed"], "day": st["day"] - WARMUP, "date": int(g["t"][st["day"] - 1]), "remaining": TOTAL - st["day"],
            "latestNews": [dict(e, date=int(g["t"][e["day"]])) for e in g["events"] if st["day"] - 5 <= e["day"] < st["day"]]}


def advance(days: int = 1) -> dict:
    st = _state()
    st["day"] = int(min(TOTAL, st["day"] + max(1, days)))
    _save(st)
    from . import data
    with data._cache_lock:
        for k in [k for k in data._cache if "SIM:" in k]:
            del data._cache[k]
    return status()


def reset(seed: int | None = None) -> dict:
    _save({"seed": int(seed if seed is not None else np.random.default_rng().integers(1, 1_000_000)), "day": WARMUP})
    return status()
