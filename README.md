# TradeScope: dual-monitor market research platform

A free, local research terminal for beginners and pros. It scans **every major stock market in the world** plus crypto,
FX, commodities, bonds and ETFs, rates every instrument with its own multi-factor algorithm, tells you **what to buy,
short or avoid, and exactly how much** for your budget, builds a **multi-market daily portfolio plan**, answers
**"what if…?" scenarios**, and explains everything with a **local AI** that never sends your data anywhere.

> **Research only.** TradeScope has no broker connection and cannot place trades. Nothing here is financial advice.

## What it costs: $0

Everything runs on your own PC or on free public data. There are no accounts, API keys, subscriptions or cloud bills.

| Part | What it uses | Cost |
|---|---|---|
| App server | Python + FastAPI, runs locally on `127.0.0.1` | Free, open source |
| Market data | Yahoo Finance public endpoints (2 hosts with failover) + Google News RSS | Free, no key |
| Offline mode | Last good price history saved in `data/hist/`, used automatically when offline | Free, local |
| AI analyst and What-If parsing | [Ollama](https://ollama.com) + Llama 3.1 8B, on your machine | Free, local |
| Charts | TradingView Lightweight Charts, bundled in `frontend/vendor/` (Apache-2.0) | Free, local |
| Fonts | Your system fonts | Free, local |

Without Ollama, every feature still works: reports use the rules engine, and What-If uses the keyword rulebook.
Yahoo's endpoints are unofficial, so data can be delayed or occasionally unavailable. The offline cache covers gaps.

## Quick start (Windows)

1. Install [Python 3.10+](https://python.org) (free).
2. Double-click **`start.bat`**. It installs the Python packages, offers to install Ollama for free, downloads the
   free AI model once, and opens http://127.0.0.1:8420
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

## Portfolio engine: the investment committee

**Build plan** runs a six-stage pipeline (`backend/planner.py`, `agents.py`, `optimizer.py`):

1. **Screen:** every stock in your portfolio markets is scored. The best ideas plus everything you hold go forward, after
   sector exclusions and a minimum market cap.
2. **Gather:** fundamentals, analyst data, a year of daily prices, volatility, drawdown, Sharpe, trend quality and beta.
3. **Debate:** ten agents argue every candidate: Trend Follower, Momentum Hunter, Mean-Reversion Trader, Value Investor,
   Quality & Growth Analyst, Risk Manager, Macro Strategist, Quant Statistician, Street Sentiment Tracker and a
   **Devil's Advocate** that attacks the majority view. Round 2 lets unsure agents update. A judge weighs the votes by your
   horizon, your style and the market regime, and reports consensus, **conviction** and the best bull and bear cases.
4. **Optimise:** expected returns come from consensus × conviction. Covariance uses Ledoit-Wolf shrinkage. Weights
   maximise your chosen goal (Sharpe, lowest volatility, highest return, risk parity or a balanced blend) under:
   - your max-per-position limit
   - a per-trade risk cap (loss at the ATR stop ≤ your risk %)
   - sector caps and market caps
   - your cash reserve
   - your target volatility

   If this mix would have broken your drawdown limit last year, exposure is scaled down.
5. **Trade list:** target weights become share counts in your currency. They're compared with your holdings using a
   rebalance band to avoid churn, and new buys respect the daily limit (the rest is queued).
6. **Stress-test:** a 2008-style crash, a +2pp rate shock, a +60% oil spike, a tech bust and a +10% dollar surge, plus
   **2,000 Monte Carlo years**, VaR/CVaR, diversification ratio, effective positions, correlation, beta and each
   holding's share of total risk. Open **📊 Committee & risk** to read every agent's argument.

## Strategy settings

Presets are Safe, Balanced and Aggressive; changing any value switches to Custom. The settings are:

- risk per trade (%)
- max drawdown (%)
- target volatility (%)
- max per position (%) and max per sector (%)
- max positions
- cash reserve (%)
- holding horizon
- optimiser goal
- style (growth, value, dividend, momentum, quality, defensive)
- minimum committee conviction
- stop distance (× ATR)
- rebalance band
- minimum market cap
- sectors to exclude
- daily investment limit
- shorts and fractional shares

## Holdings

The **💼 Holdings** screen shows live prices, value in your currency, P/L, today's move, weight, the engine's signal and a
stop for each position. Quantity and cost can be edited inline and save instantly. It also has CSV import and export, and
a search box with autocomplete. Every plan action has a **✓ Add to holdings** (or **✓ Record sale**) button, plus an
**Add all** button. This is bookkeeping only; nothing is ever traded.

## One monitor or two

TradeScope detects your screens. With two monitors, double-clicking any stock opens the Research screen on the second
one. With one monitor it opens as a full popup over the Command screen (Esc closes it). Click selects; double-click
opens.

## Feature list

**Risk & settings**
- One **risk level dial (0–100)** that sets every risk rule. Any single rule can still be fine-tuned under Advanced.
- Custom tooltips on every ⓘ and button that work in any browser. Light and dark themes, compact density,
  keyboard shortcuts (press `?`), a searchable glossary of 41 terms and a guided tour.

**Research charts**
- Chart styles: candles, Heikin-Ashi, line, area, and a log scale.
- Overlays:
  - EMA 20/50/200 and SMA 50/200
  - Supertrend and Parabolic SAR
  - Bollinger, Keltner and Donchian channels
  - pivot points, auto support/resistance, Fibonacci levels and 52-week high/low
  - engine signals and 10 candlestick patterns
  - a 3-month volatility cone and a benchmark comparison line
- Panes you can switch on and off (RSI, MACD, ATR, Score), a line-drawing tool saved per stock, PNG screenshots, and
  timeframe keys 1–7.

**Research tabs**
- **Stats:**
  - returns from 1 day to 5 years, plus year-to-date
  - daily, weekly and monthly signal agreement
  - fair value (Graham number, Graham growth, market multiple, analysts)
  - analyst target range and a 9-point financial health checklist
  - ownership and short interest
  - seasonality by month and return distribution (skew, fat tails)
  - drawdown chart, rolling volatility and the engine's signal history with results
- **Levels:** expected weekly and monthly move, target-vs-stop odds (Monte Carlo), a volatility cone table,
  support/resistance with touch counts, pivots, Fibonacci levels and recent patterns.
- **Peers:** sector peers with performance and correlation, plus an AI peer comparison.
- **Tools:**
  - position sizer showing 1R/2R/3R profit targets (R = the amount at risk)
  - price and score alerts
  - private notes
  - dividend history, trailing-12-month yield and splits
  - copy a summary or a link
- **AI:** quick questions ("Why is it moving?", bull vs bear, long-term hold, explain simply, peers, how much to buy).

**Markets dashboard** (🌍 tab)
- Fear & Greed gauge (six components) and the US yield curve with an inversion warning.
- Breadth (share of stocks above their 200-day average, new highs/lows, average RSI) and currency strength.
- Sector rotation, top gainers and losers, 35 world indices, market headlines and an AI daily briefing.

**Scanner, watchlists and alerts**
- Screener filters with 7 presets, saved screens, CSV export and auto-rescan.
- Multiple named watchlists.
- Price and score alerts with a sound, desktop notification and banner, plus re-arming.
- World market clocks showing which of 12 exchanges are open.

**Tools menu** (🧰)
- Position size and reward/risk calculator (with fees and break-even win rate).
- Compound interest / monthly investing (with inflation) and a Monte Carlo goal planner.
- Currency converter, multi-stock compare with a correlation matrix, and a portfolio backtester with rebalancing
  vs the S&P 500.
- Backup and restore.

**Holdings**
- Analytics: volatility, VaR, beta, correlation, effective positions, dividend income, last-year curve, where the risk
  comes from, and sector and currency breakdown.
- A trade journal that logs automatically, with realised P/L.

**AI assistant**
- Floating ✨ chat on the Command screen with your plan as context.

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
[TradingView Lightweight Charts™](https://www.tradingview.com/lightweight-charts/) (bundled, Apache-2.0).

## Layout

```
backend/   app.py (API) · engine.py (algorithm) · portfolio.py (sizing/plan) · data.py (market data)
           markets.py (44 countries + presets) · scenario.py (what-if engine) · ai.py (Ollama) · store.py
frontend/  index.html (Command + What-If Lab) · research.html (Research) · report.html (stock / plan / scenario reports)
data/      local state & caches (git-ignored)
```
