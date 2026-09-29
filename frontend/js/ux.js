// Shared UX layer for every page: custom tooltips, light/dark theme, compact density, keyboard shortcuts,
// glossary, notifications (desktop + sound) and clipboard helpers.
const UX = (() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------- tooltips: any element with data-tip (or a title, which is converted) gets a styled, instant tooltip
  const tip = document.createElement("div");
  tip.className = "ux-tip";
  document.addEventListener("DOMContentLoaded", () => document.body.appendChild(tip));
  if (document.body) document.body.appendChild(tip);
  let tipEl = null;
  function place(e) {
    const pad = 14, r = tip.getBoundingClientRect();
    let x = e.clientX + pad, y = e.clientY + pad;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - pad;
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - pad;
    tip.style.left = Math.max(6, x) + "px";
    tip.style.top = Math.max(6, y) + "px";
  }
  document.addEventListener("mouseover", (e) => {
    const el = e.target.closest("[data-tip],[title]");
    if (!el || el.tagName === "IFRAME") return;
    if (el.hasAttribute("title")) { const t = el.getAttribute("title"); if (t) el.dataset.tip = t; el.removeAttribute("title"); }
    if (!el.dataset.tip) return;
    tipEl = el;
    tip.innerHTML = esc(el.dataset.tip).replace(/\n/g, "<br>");
    tip.classList.add("show");
    place(e);
  });
  document.addEventListener("mousemove", (e) => { if (tipEl) { if (!document.contains(tipEl)) { tip.classList.remove("show"); tipEl = null; } else place(e); } });
  document.addEventListener("scroll", () => { tip.classList.remove("show"); tipEl = null; }, true);
  document.addEventListener("mouseout", (e) => { if (tipEl && !tipEl.contains(e.relatedTarget)) { tip.classList.remove("show"); tipEl = null; } });
  document.addEventListener("mousedown", () => { tip.classList.remove("show"); tipEl = null; });

  // ---------- theme + density (shared across windows via storage)
  const get = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
  const set = (k, v) => { try { localStorage.setItem(k, v); } catch {} };
  function applyTheme() {
    document.documentElement.dataset.theme = get("ts-theme", "dark");
    document.documentElement.dataset.density = get("ts-density", "comfy");
  }
  applyTheme();
  window.addEventListener("storage", (e) => { if (e.key === "ts-theme" || e.key === "ts-density") applyTheme(); });
  const toggleTheme = () => { set("ts-theme", get("ts-theme", "dark") === "dark" ? "light" : "dark"); applyTheme(); };
  const toggleDensity = () => { set("ts-density", get("ts-density", "comfy") === "comfy" ? "compact" : "comfy"); applyTheme(); };

  // ---------- keyboard shortcuts
  const keys = [];
  function shortcut(combo, label, fn) { keys.push({ combo, label, fn }); }
  document.addEventListener("keydown", (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) || e.ctrlKey || e.metaKey || e.altKey) return;
    const k = keys.find((x) => x.combo === e.key);
    if (k) { e.preventDefault(); k.fn(e); }
  });
  shortcut("?", "Show keyboard shortcuts", () => showShortcuts());

  // ---------- simple modal
  function modal(title, html, wide) {
    let bg = document.getElementById("ux-modal");
    if (!bg) {
      bg = document.createElement("div");
      bg.id = "ux-modal";
      bg.className = "modal-bg";
      bg.innerHTML = `<div class="modal"><div style="display:flex;align-items:center;gap:10px;margin-bottom:10px"><h3 style="margin:0" id="ux-mt"></h3><span class="spacer"></span><button class="btn sm ghost" id="ux-mx">✕ Close</button></div><div id="ux-mb"></div></div>`;
      document.body.appendChild(bg);
      bg.addEventListener("click", (e) => { if (e.target === bg) bg.classList.remove("show"); });
      bg.querySelector("#ux-mx").onclick = () => bg.classList.remove("show");
      document.addEventListener("keydown", (e) => { if (e.key === "Escape") bg.classList.remove("show"); });
    }
    bg.querySelector(".modal").style.width = wide ? "min(1180px,96vw)" : "";
    bg.querySelector("#ux-mt").textContent = title;
    bg.querySelector("#ux-mb").innerHTML = html;
    bg.classList.add("show");
    return bg.querySelector("#ux-mb");
  }
  function showShortcuts() {
    modal("⌨ Keyboard shortcuts", `<table class="t">${[{ combo: "/", label: "Search any symbol" }, ...keys, { combo: "Esc", label: "Close popups" }]
      .map((k) => `<tr><td style="width:90px"><kbd class="kbd">${esc(k.combo)}</kbd></td><td>${esc(k.label)}</td></tr>`).join("")}</table>`);
  }

  // ---------- glossary
  const GLOSSARY = {
    "ATR (Average True Range)": "How far a price typically moves in a day. Used to set stops so normal noise doesn't knock you out.",
    "Beta": "How much a stock moves with the overall market. 1.5 means it tends to move 50% more than the market.",
    "Bollinger Bands": "A band 2 standard deviations around the 20-day average. Touching the edges means the price is stretched.",
    "Breakout": "Price closing above a recent high (or below a recent low), often the start of a new move.",
    "CAGR": "Compound annual growth rate: the steady yearly return that would produce the same total result.",
    "Conviction": "How strongly TradeScope's ten-agent committee agrees on an idea, adjusted for data quality.",
    "Correlation": "How closely two investments move together, from -1 (opposite) to +1 (identical). Low correlation diversifies.",
    "CVaR / Expected shortfall": "The average loss on the worst days (for example, the worst 5%).",
    "Diversification ratio": "Weighted average risk of the holdings divided by portfolio risk. Higher means they offset each other.",
    "Dividend yield": "Yearly dividends divided by the share price.",
    "Drawdown": "The fall from a previous peak to a later low. Max drawdown is the worst such fall.",
    "EMA": "Exponential moving average: an average price that weights recent days more.",
    "EPS": "Earnings per share: company profit divided by the number of shares.",
    "EV/EBITDA": "Company value (including debt) divided by operating profit. Lower can mean cheaper.",
    "Fair value": "An estimate of what a share is worth based on earnings, assets or analyst targets.",
    "Fear & Greed": "A 0–100 gauge of market mood from volatility, momentum, safe-haven demand, junk bonds, gold and breadth.",
    "Fibonacci retracement": "Levels (38.2%, 50%, 61.8%) where pullbacks often pause within a bigger move.",
    "Free cash flow": "Cash a business generates after paying for its operations and investments.",
    "Hit rate": "How often a signal was right in the past.",
    "Leverage (D/E)": "Debt divided by shareholders' equity. High debt raises risk.",
    "Long / Short": "Long = you profit if the price rises. Short = you profit if it falls (unlimited risk).",
    "MACD": "The gap between a fast and slow moving average. Rising MACD means building momentum.",
    "Market cap": "Share price × number of shares: the company's total stock-market value.",
    "Mean reversion": "The tendency of stretched prices to snap back toward their average.",
    "Momentum": "The tendency of recent winners to keep winning for a while.",
    "Monte Carlo": "Running thousands of randomised futures to see the range of possible outcomes.",
    "P/E ratio": "Share price divided by yearly earnings per share. How many years of profit you pay for.",
    "PEG ratio": "P/E divided by earnings growth. Below 1 can mean growth is cheap.",
    "Pivot points": "Support and resistance levels calculated from yesterday's high, low and close.",
    "Position sizing": "Deciding how many shares to buy so that a stop-loss hit costs only a set % of your money.",
    "Rebalancing": "Trading back to your target weights after prices drift.",
    "Relative strength": "How a stock performs compared with its market benchmark.",
    "Risk parity": "Sizing positions so each contributes the same amount of risk.",
    "ROE": "Return on equity: profit as a % of shareholders' money. Higher is usually better.",
    "RSI": "Relative Strength Index (0–100). Above 70 is over-bought, below 30 over-sold.",
    "Sharpe ratio": "Return above cash divided by volatility: return per unit of risk. Above 1 is good.",
    "Stop-loss": "A price at which you exit to cap your loss.",
    "Supertrend": "A trailing line from ATR that flips when the trend changes.",
    "Support / Resistance": "Price areas where buying (support) or selling (resistance) has repeatedly appeared.",
    "VaR (Value at Risk)": "A loss you'd exceed only on a small share of days (for example, 1 in 20).",
    "Volatility": "How much a price swings, usually as a yearly %.",
    "Yield curve": "Interest rates across maturities. When short rates exceed long rates (inverted), recessions often follow.",
  };
  function showGlossary(filter = "") {
    const body = modal("📖 Glossary", `<input class="in" id="gq" placeholder="Search terms…" value="${esc(filter)}" style="margin-bottom:10px"><div id="gl"></div>`);
    const render = () => {
      const q = body.querySelector("#gq").value.toLowerCase();
      body.querySelector("#gl").innerHTML = Object.entries(GLOSSARY).filter(([k, v]) => !q || (k + v).toLowerCase().includes(q))
        .map(([k, v]) => `<div style="padding:7px 0;border-bottom:1px dashed var(--line)"><b>${esc(k)}</b><div class="muted" style="font-size:12.5px">${esc(v)}</div></div>`).join("") || '<div class="empty">No match.</div>';
    };
    body.querySelector("#gq").oninput = render;
    render();
    body.querySelector("#gq").focus();
  }

  // ---------- notifications
  function beep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [880, 1175].forEach((f, i) => {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.frequency.value = f; o.connect(g); g.connect(ctx.destination);
        g.gain.setValueAtTime(0.08, ctx.currentTime + i * 0.16);
        g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i * 0.16 + 0.15);
        o.start(ctx.currentTime + i * 0.16); o.stop(ctx.currentTime + i * 0.16 + 0.16);
      });
    } catch {}
  }
  async function notify(title, body) {
    beep();
    try {
      if ("Notification" in window) {
        if (Notification.permission === "default") await Notification.requestPermission();
        if (Notification.permission === "granted") new Notification(title, { body });
      }
    } catch {}
  }
  async function copy(text, msg = "Copied") {
    try { await navigator.clipboard.writeText(text); window.TS?.toast(msg); } catch { window.TS?.toast("Copy failed"); }
  }
  function download(name, text, type = "text/plain") {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = name;
    a.click();
  }

  return { esc, modal, shortcut, showShortcuts, showGlossary, toggleTheme, toggleDensity, notify, beep, copy, download, GLOSSARY };
})();
