"""Tiny JSON persistence for the user's profile, holdings, watchlist and portfolio markets (data/state.json)."""
import json
import threading

from .data import DATA_DIR

PATH = DATA_DIR / "state.json"
_lock = threading.Lock()
DEFAULT = {
    "profile": {"budget": 10000, "currency": "USD", "risk": "balanced", "allowShorts": False, "fractional": False,
                "dailyLimit": 2500, "cash": None, "experience": "beginner"},
    "holdings": [],       # {symbol, qty, avgCost, side: long|short}
    "watchlist": ["AAPL", "NVDA", "MSFT", "RELIANCE.NS", "BTC-USD", "GC=F"],
    "lastMarket": "us",
    "planMarkets": ["us"],
    "watchlists": {},      # extra named watchlists {name: [symbols]}
    "alerts": [],          # {id, symbol, kind: above|below|score_above|score_below, value, note, active, triggered}
    "journal": [],         # recorded trades {t, symbol, action, qty, price, value, realized}
    "notes": {},           # {symbol: text}
    "screens": {},         # saved screener filters {name: {...}}
}


def load() -> dict:
    with _lock:
        try:
            st = json.loads(PATH.read_text("utf-8"))
        except Exception:
            st = {}
    out = json.loads(json.dumps(DEFAULT))
    out.update(st)
    out["profile"] = {**DEFAULT["profile"], **st.get("profile", {})}
    return out


def save(st: dict) -> None:
    with _lock:
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=1), "utf-8")
        tmp.replace(PATH)
