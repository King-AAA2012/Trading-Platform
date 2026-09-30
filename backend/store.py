"""Per-user private app state (profile, holdings, watchlists, alerts, notes, journal, saved screens).

The logged-in user for the current request is held in a context variable set by the auth middleware, so every
load()/save() reads and writes only that user's row in data/app.db. Nothing is shared between accounts.
data/state.json is the old single-user file; it is imported into the very first account created."""
import contextvars
import json

from .data import DATA_DIR

PATH = DATA_DIR / "state.json"          # legacy single-user state (imported once, see auth.signup)
current_uid: contextvars.ContextVar = contextvars.ContextVar("current_uid", default=None)
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


def _private() -> bool:
    from . import config
    return config.PRIVATE


def load() -> dict:
    from . import db
    if _private():                # private mode: your own local file, exactly like the original app
        try:
            st = json.loads(PATH.read_text("utf-8"))
        except Exception:
            st = {}
    else:
        uid = current_uid.get()
        st = (db.get_state(uid) if uid else None) or {}
    out = json.loads(json.dumps(DEFAULT))
    out.update(st)
    out["profile"] = {**DEFAULT["profile"], **st.get("profile", {})}
    return out


def save(st: dict) -> None:
    from . import db
    if _private():
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=1), "utf-8")
        tmp.replace(PATH)
        return
    uid = current_uid.get()
    if uid:                       # anonymous requests never persist anything
        db.put_state(uid, st)
