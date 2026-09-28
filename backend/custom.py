"""Custom / contest markets. Create a market, add any tickers (real or made up) and paste price history as CSV,
or add today's price every day. Useful for contests (e.g. Wolves of Wall Street) whose prices are not on public feeds.
Symbols are addressed as CUS:<market_id>:<TICKER>."""
from __future__ import annotations

import re
import time
from datetime import datetime

import numpy as np

from . import store


def list_markets() -> list[dict]:
    return list(store.load().get("customMarkets", {}).values())


def get_market(mid: str) -> dict | None:
    return store.load().get("customMarkets", {}).get(mid)


def create_market(name: str, currency: str = "USD") -> dict:
    st = store.load()
    mid = "c-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or f"c-{int(time.time())}"
    m = {"id": mid, "name": name, "currency": currency, "tickers": {}}
    st.setdefault("customMarkets", {})[mid] = m
    store.save(st)
    return m


def delete_market(mid: str) -> None:
    st = store.load()
    st.get("customMarkets", {}).pop(mid, None)
    store.save(st)


def _parse_date(s: str) -> int | None:
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%b %d %Y", "%d %b %Y"):
        try:
            return int(datetime.strptime(s, fmt).timestamp())
        except ValueError:
            pass
    return None


def parse_csv(text: str) -> list[list[float]]:
    """Accepts: 'date,close' | 'date,open,high,low,close[,volume]' | one close per line. Header rows are skipped."""
    rows = []
    lines = [x for x in re.split(r"[\r\n]+", text.strip()) if x.strip()]
    day = int(time.time() // 86400) - len(lines)
    for ln in lines:
        parts = [p.strip() for p in re.split(r"[,\t;]", ln) if p.strip()]
        try:
            nums = [float(p.replace("$", "").replace("_", "")) for p in parts[1:]] if len(parts) > 1 else []
        except ValueError:
            continue
        t = _parse_date(parts[0]) if len(parts) > 1 else None
        if t is None:
            try:
                vals = [float(p.replace("$", "")) for p in parts]
            except ValueError:
                continue
            day += 1
            t, nums = day * 86400, vals
        if len(nums) == 1:
            c = nums[0]
            rows.append([t, c, c, c, c, 0])
        elif len(nums) >= 4:
            rows.append([t, nums[0], nums[1], nums[2], nums[3], nums[4] if len(nums) > 4 else 0])
    rows.sort(key=lambda r: r[0])
    return rows


def upsert_ticker(mid: str, ticker: str, name: str = "", sector: str = "Other", csv_text: str = "") -> dict:
    st = store.load()
    m = st["customMarkets"][mid]
    tk = re.sub(r"[^A-Z0-9.\-]", "", ticker.upper())[:12]
    cur = m["tickers"].get(tk, {"name": name or tk, "sector": sector or "Other", "bars": []})
    if name:
        cur["name"] = name
    if sector:
        cur["sector"] = sector
    if csv_text.strip():
        new = parse_csv(csv_text)
        merged = {int(r[0]) // 86400: r for r in cur["bars"]}
        merged.update({int(r[0]) // 86400: r for r in new})
        cur["bars"] = [merged[k] for k in sorted(merged)]
    m["tickers"][tk] = cur
    store.save(st)
    return {"ticker": tk, "bars": len(cur["bars"])}


def add_price(mid: str, ticker: str, price: float, date: str | None = None) -> dict:
    t = _parse_date(date) if date else int(time.time())
    st = store.load()
    tk = ticker.upper()
    cur = st["customMarkets"][mid]["tickers"].setdefault(tk, {"name": tk, "sector": "Other", "bars": []})
    d = t // 86400
    cur["bars"] = [b for b in cur["bars"] if int(b[0]) // 86400 != d] + [[t, price, price, price, price, 0]]
    cur["bars"].sort(key=lambda r: r[0])
    store.save(st)
    return {"ticker": tk, "bars": len(cur["bars"])}


def delete_ticker(mid: str, ticker: str) -> None:
    st = store.load()
    st["customMarkets"][mid]["tickers"].pop(ticker.upper(), None)
    store.save(st)


def history(symbol: str) -> dict | None:
    _, mid, tk = symbol.split(":", 2)
    m = get_market(mid)
    if not m or tk not in m["tickers"]:
        return None
    bars = np.array(m["tickers"][tk]["bars"], dtype=float)
    if len(bars) < 2:
        return None
    return {"symbol": symbol, "t": bars[:, 0].astype(np.int64), "o": bars[:, 1], "h": bars[:, 2], "l": bars[:, 3], "c": bars[:, 4],
            "v": bars[:, 5], "meta": {"name": m["tickers"][tk]["name"], "currency": m.get("currency", "USD"),
                                      "exchange": m["name"], "type": "EQUITY"}}


def sector(symbol: str) -> str:
    _, mid, tk = symbol.split(":", 2)
    m = get_market(mid) or {"tickers": {}}
    return m["tickers"].get(tk, {}).get("sector", "Other")
