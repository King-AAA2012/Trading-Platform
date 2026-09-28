# TradeScope: dual-monitor market research platform

A free, local research terminal for beginners and pros. It scans **every major stock market in the world** plus crypto,
FX, commodities, bonds and ETFs, rates every instrument with its own multi-factor algorithm, tells you **what to buy,
short or avoid, and exactly how much** for your budget, builds a **multi-market daily portfolio plan**, answers
**"what if…?" scenarios**, and explains everything with a **local AI** that never sends your data anywhere.

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

- **44 country stock markets**, from the United States, Canada, Brazil and Mexico to the UK and all major European
  exchanges, Japan, China, Hong Kong, India, Korea, Taiwan, Australia, Southeast Asia, Israel, Saudi Arabia, Qatar and
  South Africa. Each country's largest *domestic* companies are pulled live from the Yahoo screener, refreshed daily.
  Foreign cross-listings are filtered out by home exchange, trading currency, reporting currency and turnover.
  Germany and Austria use the DAX 40 and ATX members.
- **Curated sets:** US large caps, Nifty 50, FTSE, Euro Stoxx, Nikkei, Hang Seng, TSX, ASX.
- **Asset classes:** World indices, Bonds & rates, Crypto, Forex, Commodities, Global ETFs.
- Plus *any* Yahoo Finance symbol via search (`/` to focus).
- Countries without a reliable index feed get a synthetic equal-weight benchmark for relative strength.

## Portfolio markets (multi-market)

Click **🌍** in the plan panel (or the What-If Lab) to choose which markets the portfolio draws from. Quick sets
include Majors, Europe, Asia, Emerging and Multi-asset (up to 12 markets). The **daily plan, What-If Lab, AI
explanations and reports** all use this selection. Positions are sized in your currency with live FX, and the plan
shows the split by market.

## What-If Lab 🔮

Type any event ("China invades Taiwan", "Fed cuts 1%", "oil hits $150", "AI boom doubles data-center capex"):

1. The **local AI** turns it into assumed moves in ten macro drivers (S&P 500, oil, gold, US 10Y yield, dollar,
   VIX, copper, Bitcoin, China stocks, natural gas), plus sector, industry-theme and country views. A keyword
   rulebook handles it if the AI is offline. **You can edit every assumed move and re-run.**
2. Each stock's **sensitivity** to those drivers is estimated with a ridge regression on two years of weekly returns.
3. Projected move = Σ sensitivity × driver move + sector/theme/country views, blended 75/25 with the current technical
   score. You get ranked **best-positioned** and **most-exposed** stocks with their drivers, suggested sizes, a
   **"Build my plan for this scenario"** button, an **AI scenario briefing** and a printable **scenario report**.

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
           markets.py (44 countries + presets) · scenario.py (what-if engine) · ai.py (Ollama) · store.py
frontend/  index.html (Command + What-If Lab) · research.html (Research) · report.html (stock / plan / scenario reports)
data/      local state & caches (git-ignored)
```
