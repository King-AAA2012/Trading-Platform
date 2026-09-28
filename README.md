# TradeScope: dual-monitor market research platform

A free, local research terminal for beginners and pros. It scans any market, rates every instrument with its own
multi-factor algorithm, tells you **what to buy, short or avoid, and exactly how much** for your budget, builds a
**daily portfolio plan**, and explains everything with a **local AI** that never sends your data anywhere.

> **Research only.** TradeScope has no broker connection and cannot place trades. Nothing here is financial advice.

## Quick start (Windows)

1. Install [Python 3.10+](https://python.org) and, optionally, [Ollama](https://ollama.com) for the AI analyst:
   `ollama pull llama3.1:8b`
2. Double-click **`start.bat`**. It installs dependencies, starts Ollama if present, and opens http://127.0.0.1:8420
3. Click **⧉ Open Research Screen**. In Chrome or Edge the window opens straight onto your second monitor
   (allow the "window management" prompt). Otherwise, drag it over.

Manual start: `pip install -r requirements.txt` then `python -m uvicorn backend.app:app --port 8420`.

## The two screens

| Monitor 1: **Command Center** | Monitor 2: **Research** |
|---|---|
| Global macro ticker (indices, VIX, yields, dollar, gold, oil, BTC) | Candlestick chart with EMA 20/50/200, Bollinger, volume, buy/sell markers, entry/stop/target lines |
| Market pulse: model breadth and risk-on/off regime | RSI, MACD and the **TradeScope Score** history panes (Pro mode) |
| Sector heatmap and watchlist | Recommendation card: action, **how many units**, cost, stop, targets, P&L at each level |
| Opportunity scanner: Top Buys / Shorts, score, signal, setup, confidence, suggested size | Tabs: Why (factor bars + reasons + risks), Fundamentals, Backtest, News, ✨ AI Analyst chat |
| Budget & risk profile, holdings, **Today's Portfolio Plan** | 📄 printable report (Save as PDF) |

Clicking anything on the Command screen instantly loads it on the Research screen (the windows sync via
`BroadcastChannel`). **Beginner / Pro** mode toggles plain-English guidance vs. raw indicators, on both screens.

## Markets

- **Real:** US, India NSE, UK, Europe, Japan, Hong Kong, Canada, Australia, Crypto, Forex, Commodities, Global ETFs.
  Plus *any* Yahoo Finance symbol via search (`/` to focus).
- **🐺 Wolf Exchange (imaginary):** 24 fictional companies driven by a market/sector factor model with bull/bear regimes
  and news shocks. Step day by day or auto-play; the engine never sees future bars. Great for practice.
- **🧪 Custom / contest markets** (e.g. *Wolves of Wall Street*): create a market, add tickers, paste CSV history
  (`date,close` or `date,open,high,low,close,volume` or one price per line) or log each day's price.

## The algorithm (`backend/engine.py`)

Seven factors, each scaled to −1…+1 and computed for every historical bar:

| Factor | Weight | Idea |
|---|---|---|
| Trend | 24% | Price vs EMA20/50/200, EMA alignment and slope, scaled by ADX strength |
| Momentum | 18% | Volatility-adjusted 3m, 6m and 12-1m returns |
| Relative strength | 12% | Performance vs the market benchmark |
| Breakout / range | 14% | 52-week range position, 55-day highs/lows, volume confirmation |
| MACD impulse | 10% | Histogram size and direction |
| RSI / stretch | 11% | Trend-aware: pullbacks in uptrends are bullish, over-bought is bearish |
| Volume flow | 11% | OBV and up/down volume (accumulation vs distribution) |

Composite score −100…+100 → **STRONG BUY ≥ 50, BUY ≥ 20, HOLD, SELL ≤ −20, STRONG SELL ≤ −50**. For stocks, a
fundamentals score (valuation, growth, profitability, leverage, analyst targets) is blended in at 20%.

**Confidence** combines factor agreement with the signal's *own walk-forward track record on that instrument*
(10-day hit rate, shrunk toward 50% for small samples). A weak record pulls confidence down hard.

**Levels:** stop = 2.2×ATR beyond entry (respecting the 20-day swing), Target 1 = 2R, Target 2 = 3.5R.

**Sizing** (`backend/portfolio.py`): risk a fixed % of budget between entry and stop (0.5% / 1% / 2% for
conservative / balanced / aggressive), scaled by confidence, capped by max position %, sector cap, cash and your
**daily deployment limit**, converted to your currency via live FX.

**Daily plan:** re-scores your holdings (SELL if the signal flips, TRIM if oversized or fading after a big gain, ADD
if still strong and underweight), then fills free slots with the best new ideas.

## Local AI

Uses Ollama (`llama3.1:8b` preferred, falls back to any installed chat model; override with `TRADESCOPE_MODEL`).
The AI only sees numbers the engine computed plus headlines, and it's instructed never to invent data. Without Ollama,
a rules-based report is shown instead.

## Data

Yahoo Finance public endpoints (prices, fundamentals, news) plus Google News RSS. Data may be delayed. Uses the OS
certificate store (`truststore`) so antivirus HTTPS scanning doesn't break requests. Charts:
[TradingView Lightweight Charts™](https://www.tradingview.com/lightweight-charts/) (downloaded once and cached).

## Layout

```
backend/   app.py (API) · engine.py (algorithm) · portfolio.py (sizing/plan) · data.py (market data)
           markets.py (presets) · simulator.py (Wolf Exchange) · custom.py (contest markets) · ai.py (Ollama) · store.py
frontend/  index.html (Command) · research.html (Research) · report.html (printable) · js/ · css/
data/      local state & caches (git-ignored)
```
