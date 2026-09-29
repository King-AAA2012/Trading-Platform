// Screen 2: Research — follows the symbol picked on the Command screen.
(() => {
  const $ = (s) => document.querySelector(s);
  const { api, esc, price, pct, cls, money, big, disp } = TS;
  const LW = window.LightweightCharts;
  const params = new URLSearchParams(location.search);
  let sym = params.get("symbol"), market = params.get("market"), A = null, state = null, tab = "why", tf = "1Y";
  let chat = [], aiReport = "", newsCache = null, plan = null, pending = null;
  const EMBED = params.get("embed") === "1";      // shown inside the Command screen's popup on single-monitor setups
  if (EMBED) document.body.classList.add("embed");
  if (EMBED) document.addEventListener("keydown", (e) => { if (e.key === "Escape") parent.postMessage("ts-close", location.origin); });
  const pong = () => TS.send({ type: "pong", from: EMBED ? "overlay" : "window" });

  TS.setMode(TS.mode(), false);
  document.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () => { TS.setMode(b.dataset.mode); setTimeout(draw, 80); }));
  TS.on((m) => {
    if (m.type === "ping") pong();
    if (m.type === "select" && m.from !== "research") { market = m.market || market; load(m.symbol); }
    if (m.type === "profile" && sym) load(sym, true);
    if (m.type === "refresh" && sym) load(sym, true);
    if (m.type === "plan") plan = m.plan;
    if (m.type === "watch" && state) { state.watchlist = m.watchlist; watchBtn(); }
    if (m.type === "mode") setTimeout(draw, 80);
  });
  pong();
  TS.bindSearch($("#q"), $("#qres"), (s) => { load(s); TS.send({ type: "select", symbol: s, from: "research" }); });
  TS.aiStatus($("#aist"));

  // ---------------- charts
  const base = {
    autoSize: true,
    layout: { background: { color: "#0e1219" }, textColor: "#8791a6", fontFamily: "Cascadia Mono, Consolas, ui-monospace, monospace", fontSize: 11 },
    grid: { vertLines: { color: "#141b27" }, horzLines: { color: "#141b27" } },
    rightPriceScale: { borderColor: "#1d2533", minimumWidth: 70 },
    timeScale: { borderColor: "#1d2533", rightOffset: 4 },
    crosshair: { mode: 0 },
  };
  const mk = (id, extra = {}) => {
    let el = document.getElementById(id);
    if (!el) { // a stale/edited page without this pane must not crash the whole screen
      el = document.createElement("div");
      el.id = id;
      el.style.display = "none";
      document.body.appendChild(el);
    }
    return LW.createChart(el, { ...base, ...extra, layout: { ...base.layout, attributionLogo: id === "cMain" } });
  };
  const cMain = mk("cMain"), cRsi = mk("cRsi", { timeScale: { visible: false } }), cMacd = mk("cMacd", { timeScale: { visible: false } }), cAtr = mk("cAtr", { timeScale: { visible: false } }), cScore = mk("cScore");
  const all = [cMain, cRsi, cMacd, cAtr, cScore];
  const candle = cMain.addCandlestickSeries({ upColor: "#1fd286", downColor: "#ff5470", borderVisible: false, wickUpColor: "#1fd286", wickDownColor: "#ff5470" });
  const vol = cMain.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
  cMain.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  const line = (c, color, w = 1.5, style = 0) => c.addLineSeries({ color, lineWidth: w, lineStyle: style, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
  const e20 = line(cMain, "#f5b942"), e50 = line(cMain, "#5b8cff"), e200 = line(cMain, "#c084fc", 2);
  const bbu = line(cMain, "rgba(135,145,166,.55)", 1, 2), bbl = line(cMain, "rgba(135,145,166,.55)", 1, 2);
  const rsiS = line(cRsi, "#9b7bff", 1.5);
  const atrS = cAtr.addLineSeries({ color: "#38bdf8", lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true });
  const chand = line(cMain, "#38bdf8", 1.5, 1);
  rsiS.createPriceLine({ price: 70, color: "#ff547066", lineStyle: 2, axisLabelVisible: false });
  rsiS.createPriceLine({ price: 30, color: "#1fd28666", lineStyle: 2, axisLabelVisible: false });
  const mH = cMacd.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false }), mL = line(cMacd, "#5b8cff"), mS = line(cMacd, "#f5b942");
  const scoreS = cScore.addBaselineSeries({ baseValue: { type: "price", price: 0 }, topLineColor: "#1fd286", bottomLineColor: "#ff5470",
    topFillColor1: "rgba(31,210,134,.28)", topFillColor2: "rgba(31,210,134,.02)", bottomFillColor1: "rgba(255,84,112,.02)", bottomFillColor2: "rgba(255,84,112,.28)", lineWidth: 1.5, priceLineVisible: false });
  scoreS.createPriceLine({ price: 20, color: "#1fd28655", lineStyle: 2, axisLabelVisible: false });
  scoreS.createPriceLine({ price: -20, color: "#ff547055", lineStyle: 2, axisLabelVisible: false });
  // bridge for research-extra.js (overlays, extra tabs, drawing, tools)
  window.RES = { LW, cMain, candle, vol, all, line, base, get A() { return A; }, get sym() { return sym; }, get market() { return market; },
    get state() { return state; }, set state(v) { state = v; }, get tf() { return tf; }, draw: () => draw(), setRange: () => setRange(), renderTab: () => renderTab() };
  let syncing = false;
  all.forEach((c) => c.timeScale().subscribeVisibleLogicalRangeChange((r) => {
    if (syncing || !r) return; syncing = true;
    all.forEach((o) => o !== c && o.timeScale().setVisibleLogicalRange(r));
    syncing = false;
  }));
  let priceLines = [];

  const S = (t, v) => t.map((x, i) => ({ time: x, value: v[i] }));
  function drawDaily() {
    const s = A.series, t = s.t;
    candle.setData(t.map((x, i) => ({ time: x, open: s.o[i], high: s.h[i], low: s.l[i], close: s.c[i] })));
    vol.setData(t.map((x, i) => ({ time: x, value: s.v[i], color: s.c[i] >= s.o[i] ? "rgba(31,210,134,.28)" : "rgba(255,84,112,.28)" })));
    const ema = $("#oEma").checked, bb = $("#oBb").checked;
    e20.setData(ema ? S(t, s.e20) : []); e50.setData(ema ? S(t, s.e50) : []); e200.setData(ema ? S(t, s.e200) : []);
    bbu.setData(bb ? S(t, s.bbu) : []); bbl.setData(bb ? S(t, s.bbl) : []);
    rsiS.setData(S(t, s.rsi));
    atrS.setData(S(t, s.atr));
    chand.setData($("#oAtr").checked ? S(t, A.bias === "short" ? s.chandS : s.chandL).slice(22) : []);
    mH.setData(t.map((x, i) => ({ time: x, value: s.macdh[i], color: s.macdh[i] >= 0 ? "rgba(31,210,134,.6)" : "rgba(255,84,112,.6)" })));
    mL.setData(S(t, s.macd)); mS.setData(S(t, s.macds));
    scoreS.setData(S(t, s.score));
    const extraMarks = (window.RX && RX.markers && RX.markers()) || [];
    candle.setMarkers(($("#oSig").checked ? s.marks.map((m) => ({ time: m.t, position: m.type === "buy" ? "belowBar" : "aboveBar",
      color: m.type === "buy" ? "#1fd286" : m.type === "short" ? "#b9a4ff" : "#8791a6", shape: m.type === "buy" ? "arrowUp" : m.type === "short" ? "arrowDown" : "circle",
      text: m.type === "buy" ? "BUY" : m.type === "short" ? "SHORT" : "EXIT" })) : []).concat(extraMarks).sort((a, b) => a.time - b.time));
    priceLines.forEach((p) => candle.removePriceLine(p)); priceLines = [];
    if ($("#oLv").checked && A.bias !== "neutral") {
      const L = A.levels, add = (price, color, title) => priceLines.push(candle.createPriceLine({ price, color, lineWidth: 1, lineStyle: 2, title }));
      add(L.stop, "#ff5470", "STOP"); add(L.t1, "#1fd286", "T1"); add(L.t2, "#1fd286", "T2"); add(L.entry, "#5b8cff", "ENTRY");
    }
    all.forEach((c) => c.applyOptions({ timeScale: { timeVisible: false } }));
    if (window.RX && RX.afterDraw) RX.afterDraw(false);
    setRange();
  }
  function setRange() {
    const n = A.series.t.length, bars = { "3M": 63, "6M": 126, "1Y": 252, "2Y": 504, "5Y": n }[tf] || 252;
    const r = { from: Math.max(0, n - bars), to: n + 3 };
    all.forEach((c) => c.timeScale().setVisibleLogicalRange(r));
  }
  async function drawIntraday() {
    const h = await api(`/api/history/${encodeURIComponent(sym)}?range=${tf === "1D" ? "1d" : "5d"}&interval=${tf === "1D" ? "5m" : "15m"}`).catch(() => null);
    if (!h || !h.t.length) { TS.toast("No intraday data for this instrument."); tf = "1Y"; setTf(); return drawDaily(); }
    candle.setData(h.t.map((x, i) => ({ time: x, open: h.o[i], high: h.h[i], low: h.l[i], close: h.c[i] })));
    vol.setData(h.t.map((x, i) => ({ time: x, value: h.v[i], color: h.c[i] >= h.o[i] ? "rgba(31,210,134,.28)" : "rgba(255,84,112,.28)" })));
    [e20, e50, e200, bbu, bbl, rsiS, mL, mS, mH, scoreS, atrS, chand].forEach((x) => x.setData([]));
    candle.setMarkers([]);
    cMain.applyOptions({ timeScale: { timeVisible: true } });
    if (window.RX && RX.afterDraw) RX.afterDraw(true, h);
    cMain.timeScale().fitContent();
  }
  function draw() { if (!A) return; tf === "1D" || tf === "5D" ? drawIntraday() : drawDaily(); }
  function setTf() { document.querySelectorAll("#tf button").forEach((b) => b.classList.toggle("on", b.dataset.tf === tf)); }
  document.querySelectorAll("#tf button").forEach((b) => (b.onclick = () => { tf = b.dataset.tf; setTf(); draw(); }));
  ["#oEma", "#oBb", "#oSig", "#oLv", "#oAtr"].forEach((s) => ($(s).onchange = draw));

  cMain.subscribeCrosshairMove((p) => {
    if (!A) return;
    const d = p.time && p.seriesData.get(candle);
    const s = A.series, i = d ? s.t.indexOf(p.time) : s.t.length - 1;
    const o = d || { open: s.o[i], high: s.h[i], low: s.l[i], close: s.c[i] };
    const ch = i > 0 && s.c[i - 1] ? (o.close / s.c[i - 1] - 1) * 100 : 0;
    $("#legend").innerHTML = `<span class="muted">O</span>${price(o.open)} <span class="muted">H</span>${price(o.high)} <span class="muted">L</span>${price(o.low)} <span class="muted">C</span>${price(o.close)} <span class="${cls(ch)}">${pct(ch)}</span>` +
      (i >= 0 && s.atr[i] != null ? ` <span class="muted">ATR</span><span style="color:#38bdf8">${price(s.atr[i])} (${((s.atr[i] / o.close) * 100).toFixed(1)}%)</span>` : "") +
      (i >= 0 && s.score[i] != null ? ` <span class="muted">Score</span><span class="${cls(s.score[i])}">${s.score[i].toFixed(0)}</span>` : "") +
      ($("#oEma").checked ? ` <span style="color:#f5b942">EMA20</span> <span style="color:#5b8cff">EMA50</span> <span style="color:#c084fc">EMA200</span>` : "");
  });

  // ---------------- load
  async function load(symbol, quiet = false) {
    if (!symbol) return;
    const changed = symbol !== sym;
    sym = symbol;
    history.replaceState(null, "", `?symbol=${encodeURIComponent(sym)}${market ? "&market=" + market : ""}`);
    if (changed) { chat = []; aiReport = ""; newsCache = null; }
    if (!quiet) $("#rec").innerHTML = `<div class="empty"><span class="spin"></span> Analysing ${esc(disp(sym))}…</div>`;
    try {
      [A, state] = await Promise.all([api(`/api/analyze/${encodeURIComponent(sym)}${market ? "?market=" + market : ""}`), api("/api/state")]);
    } catch (e) {
      $("#rec").innerHTML = `<div class="empty">Couldn't analyse ${esc(sym)}: ${esc(e.message)}</div>`;
      return;
    }
    document.title = `${disp(sym)} · TradeScope Research`;
    renderQuote(); renderRec();
    if (window.RX && RX.onLoad) await RX.onLoad(changed);
    draw(); renderTab(); watchBtn();
  }

  function renderQuote() {
    $("#quote").innerHTML = `<h1>${esc(disp(A.symbol))}</h1><span class="nm">${esc(A.name)} · ${esc(A.exchange || A.marketName)}</span>
      <span class="px">${price(A.price)}</span><span class="num ${cls(A.changePct)}">${pct(A.changePct)}</span><span class="dim">${esc(A.currency)}</span>
      <span class="sig ${TS.sigClass(A.signal)}">${A.signal}</span>${A.stale ? '<span class="stale" data-tip="Yahoo was unreachable, so this uses the last saved copy of the price history">offline data</span>' : ""}`;
  }

  const ACTION = { "STRONG BUY": ["Strong Buy", "var(--up)"], BUY: ["Buy", "var(--up)"], HOLD: ["Hold / Wait", "#aab3c6"], SELL: ["Avoid / Reduce", "var(--down)"], "STRONG SELL": ["Avoid · Short candidate", "var(--down)"] };
  function renderRec() {
    const L = A.levels, z = A.sizing, ccy = state.profile.currency, [act, col] = ACTION[A.signal];
    const sc = A.score, ringCol = sc >= 20 ? "var(--up)" : sc <= -20 ? "var(--down)" : "#8791a6";
    const verb = A.bias === "short" ? "Short" : "Buy";
    const howmuch = A.bias === "neutral" ? `<span class="muted">No position suggested. Wait for the score to move above +20 (buy) or below −20 (sell).</span>`
      : z.qty ? `${verb} <b class="num">${z.qty}</b> ${A.symbol.endsWith("=X") ? "units" : "shares/units"} ≈ <b class="num">${money(z.cost, ccy)}</b> <span class="muted">(${(z.pct * 100).toFixed(1)}% of your ${money(state.profile.budget, ccy)} budget)</span>`
      : `<span class="warn">${esc(z.note)}</span>`;
    $("#rec").innerHTML = `<div class="rec">
      <div style="display:flex;gap:14px;align-items:center">
        <div class="ring-score" style="background:conic-gradient(${ringCol} ${Math.abs(sc) * 3.6}deg,#1a2130 0)"><div class="${cls(sc)}">${sc > 0 ? "+" : ""}${sc.toFixed(0)}</div></div>
        <div style="flex:1"><div class="action" style="color:${col}">${act}</div>
          <div class="muted">${esc(A.setup)} · confidence ${TS.confRing(A.confidence)}</div></div>
      </div>
      <div class="howmuch">${howmuch}</div>
      ${A.bias !== "neutral" ? `<div class="ladder">
        <span class="l">Entry zone</span><span class="num">${price(L.entryLow)} – ${price(L.entryHigh)}</span><span></span>
        <span class="l">Stop-loss</span><span class="num down">${price(L.stop)}</span><span class="num down">${z.qty ? "−" + money(z.riskAmount, ccy) : pct(-L.riskPct * 100, 1)}</span>
        <span class="l">Target 1 (2R)</span><span class="num up">${price(L.t1)}</span><span class="num up">${z.qty ? "+" + money(z.gainT1, ccy) : ""}</span>
        <span class="l">Target 2 (3.5R)</span><span class="num up">${price(L.t2)}</span><span class="num up">${z.qty ? "+" + money(z.gainT2, ccy) : ""}</span>
        <span class="l">ATR trailing stop</span><span class="num" style="color:#38bdf8">${price(L.atrStop)}</span><span class="dim">3×ATR</span>
      </div>` : `<div class="ladder"><span class="l">Support</span><span class="num">${price(L.support)}</span><span></span><span class="l">Resistance</span><span class="num">${price(L.resistance)}</span><span></span></div>`}
      <div class="ladder" style="margin-top:6px"><span class="l">ATR (14)</span><span class="num" style="color:#38bdf8">${price(A.atr)} · ${(A.atrPct * 100).toFixed(2)}%/day</span><span class="dim">${A.atrPct > 0.04 ? "high volatility" : A.atrPct < 0.015 ? "calm" : "normal"}</span></div>
      <div class="b-only dim" style="font-size:11.5px;margin-top:4px">ATR (Average True Range) is how much ${esc(disp(A.symbol))} typically moves in a day, about ${price(A.atr)}. The stop is placed about 2 ATR away so normal daily noise doesn't knock you out. As the price rises, the <span style="color:#38bdf8">ATR trailing stop</span> rises with it to lock in gains.</div>
      <div class="hint b-only" style="margin-top:10px">${A.bias === "long" ? `<b>How to use this:</b> buy near the entry zone. If the price closes below the <b>stop</b>, sell to cap your loss. Sell half at Target 1 and move your stop to your buy price, then let the rest run to Target 2.`
        : A.bias === "short" ? `<b>Shorting</b> profits when the price falls but has unlimited risk. It's for experienced traders only. Most beginners should simply <b>avoid buying</b> this right now.`
        : `<b>No edge right now.</b> The signals disagree. Keep it on your watchlist and check back; patience is a strategy.`}</div>
      <div class="p-only muted num" style="font-size:11px;margin-top:8px">tech ${A.techScore} · fund ${A.fundScore ?? "n/a"} · RSI ${A.rsi.toFixed(0)} · ADX ${A.adx.toFixed(0)} · ATR ${(A.atrPct * 100).toFixed(2)}% · 52w pos ${(A.pos52 * 100).toFixed(0)}% · hit ${A.hitRate != null ? (A.hitRate * 100).toFixed(0) + "% (n=" + A.backtestN + ")" : "n/a"}</div>
    </div>`;
  }

  // ---------------- tabs
  document.querySelectorAll("#rtabs button").forEach((b) => (b.onclick = () => {
    tab = b.dataset.t; document.querySelectorAll("#rtabs button").forEach((x) => x.classList.toggle("on", x === b)); renderTab();
  }));
  function renderTab() {
    $("#aiFooter").style.display = tab === "ai" ? "" : "none";
    if (tab === "ai") return tabAi();
    if (window.RX && RX.tabs && RX.tabs[tab]) return RX.tabs[tab]();                 // the AI works even before (or without) a loaded analysis
    if (A) ({ why: tabWhy, fund: tabFund, bt: tabBt, news: tabNews })[tab]();
  }

  function factorBars() {
    return `<div class="bars">${A.factors.map((f) => {
      const w = Math.abs(f.value) * 50, col = f.value > 0.1 ? "var(--up)" : f.value < -0.1 ? "var(--down)" : "#8791a6";
      return `<div class="b" title="${esc(f.explain)}"><span>${esc(f.label)}</span><span class="track"><i style="${f.value >= 0 ? "left:50%" : `left:${50 - w}%`};width:${w}%;background:${col}"></i></span><span class="num ${cls(f.value)}" style="text-align:right">${f.value > 0 ? "+" : ""}${f.value.toFixed(2)}</span></div>`;
    }).join("")}</div>`;
  }
  function tabWhy() {
    $("#tabBody").innerHTML = `<div class="rsection"><h4>Factor breakdown</h4>${factorBars()}<div class="b-only dim" style="font-size:11px">Hover a factor to see what it measures. Right = bullish, left = bearish.</div></div>
      <div class="rsection"><h4>Why the algorithm says ${esc(A.signal)}</h4>${A.reasons.map((r) => `<div class="reason ${r.tone}"><span class="ic">${r.tone === "bull" ? "▲" : r.tone === "bear" ? "▼" : "•"}</span><div>${esc(r.text)}<span class="pro">${esc(r.pro)}</span></div></div>`).join("")}</div>
      <div class="rsection"><h4>Risks</h4>${A.risks.map((r) => `<div class="reason bear"><span class="ic">!</span><div>${esc(r)}</div></div>`).join("")}</div>`;
  }
  function tabFund() {
    const f = A.fundamentals || {};
    if (!Object.keys(f).length) { $("#tabBody").innerHTML = `<div class="empty">No fundamentals for this instrument (index, FX, crypto, futures or imaginary market). The rating is purely technical.</div>`; return; }
    const P = (x) => (x == null ? "–" : (x * 100).toFixed(1) + "%"), N = (x, d = 2) => (x == null ? "–" : x.toFixed(d));
    const kv = [["Market cap", big(f.marketCap)], ["P/E (ttm)", N(f.trailingPE, 1)], ["Forward P/E", N(f.forwardPE, 1)], ["PEG", N(f.peg)],
      ["Price/Book", N(f.priceToBook)], ["EV/EBITDA", N(f.evToEbitda, 1)], ["Revenue growth", P(f.revenueGrowth)], ["Earnings growth", P(f.earningsGrowth)],
      ["Gross margin", P(f.grossMargin)], ["Profit margin", P(f.profitMargin)], ["ROE", P(f.roe)], ["Debt/Equity", f.debtToEquity == null ? "–" : (f.debtToEquity / 100).toFixed(2) + "x"],
      ["Dividend yield", P(f.dividendYield)], ["Beta", N(f.beta)], ["Free cash flow", big(f.freeCashflow)], ["Next earnings", f.nextEarnings || "–"]];
    const r = f.ratings, tot = r ? Object.values(r).reduce((a, b) => a + b, 0) : 0;
    $("#tabBody").innerHTML = `<div class="rsection"><h4>${esc(f.sector || "")} · ${esc(f.industry || "")} ${f.country ? "· " + esc(f.country) : ""}</h4>
      <div class="kv" style="grid-template-columns:repeat(2,1fr)">${kv.map(([k, v]) => `<div><label>${k}</label><b>${v}</b></div>`).join("")}</div></div>
      ${A.fundParts.length ? `<div class="rsection"><h4>Fundamental score ${A.fundScore > 0 ? "+" : ""}${A.fundScore}</h4><div class="bars">${A.fundParts.map((p) => `<div class="b" title="${esc(p.text)}"><span>${esc(p.label)}</span><span class="track"><i style="${p.value >= 0 ? "left:50%" : `left:${50 - Math.abs(p.value) * 50}%`};width:${Math.abs(p.value) * 50}%;background:${p.value >= 0 ? "var(--up)" : "var(--down)"}"></i></span><span class="num ${cls(p.value)}">${p.value.toFixed(2)}</span></div>`).join("")}</div></div>` : ""}
      ${f.targetMean ? `<div class="rsection"><h4>Wall Street view</h4><div>Average target <b class="num">${price(f.targetMean)}</b> (<span class="${cls(f.targetMean - A.price)}">${pct((f.targetMean / A.price - 1) * 100, 1)}</span>), range ${price(f.targetLow)} to ${price(f.targetHigh)} · ${f.analysts || "?"} analysts · consensus <b>${esc(f.recommendationKey || "n/a")}</b></div>
        ${tot ? `<div class="gauge" style="display:flex;height:10px;border-radius:5px;overflow:hidden;margin-top:8px">${[["strongBuy", "#1fd286"], ["buy", "#63d9a4"], ["hold", "#6b7489"], ["sell", "#ff8a9c"], ["strongSell", "#ff5470"]].map(([k, c]) => `<i title="${k}: ${r[k]}" style="width:${(r[k] / tot) * 100}%;background:${c}"></i>`).join("")}</div><div class="dim" style="font-size:11px;margin-top:3px">Strong buy ${r.strongBuy} · Buy ${r.buy} · Hold ${r.hold} · Sell ${r.sell} · Strong sell ${r.strongSell}</div>` : ""}</div>` : ""}
      ${f.summary ? `<div class="rsection"><h4>Business</h4><div class="muted" style="font-size:12px">${esc(f.summary)}</div></div>` : ""}`;
  }
  let btChart = null;
  function tabBt() {
    const b = A.backtest;
    if (!b || !b.ok) { $("#tabBody").innerHTML = `<div class="empty">Not enough history to backtest.</div>`; return; }
    const s = b.strategy, h = b.buyhold, P = (x) => (x == null ? "–" : pct(x * 100, 1));
    $("#tabBody").innerHTML = `<div class="hint b-only" style="margin-bottom:10px">This replays the algorithm on ${esc(disp(A.symbol))}'s last ${b.years} years with no look-ahead: buy when score ≥ +20, exit below +5${A.series.marks.some((m) => m.type === "short") ? ", short when ≤ −20" : ""}, 0.1% cost per trade. It shows whether the model has worked on <i>this</i> instrument.</div>
      <div class="kv" style="grid-template-columns:repeat(3,1fr)">
        <div><label>Model return</label><b class="${cls(s.total)}">${P(s.total)}</b></div><div><label>Buy & hold</label><b class="${cls(h.total)}">${P(h.total)}</b></div><div><label>Model CAGR</label><b>${P(s.cagr)}</b></div>
        <div><label>Max drawdown</label><b class="down">${P(s.maxdd)}</b></div><div><label>B&H drawdown</label><b class="down">${P(h.maxdd)}</b></div><div><label>Sharpe</label><b>${s.sharpe.toFixed(2)}</b></div>
        <div><label>Trades</label><b>${s.trades}</b></div><div><label>Win rate</label><b>${P(s.winrate)}</b></div><div><label>Time in market</label><b>${P(s.exposure)}</b></div></div>
      <div id="btc" style="height:200px;margin:12px 0;border:1px solid var(--line);border-radius:8px;overflow:hidden"></div>
      <div class="dim" style="font-size:11px;margin-bottom:10px"><span style="color:#5b8cff">━ Model</span> &nbsp; <span style="color:#8791a6">━ Buy & hold</span> (growth of 1)</div>
      <div class="kv"><div><label>Buy signals: 10-day hit rate</label><b>${b.longs.n ? (b.longs.hit * 100).toFixed(0) + "%" : "–"}</b> <span class="dim">n=${b.longs.n}, avg ${P(b.longs.avg)}</span></div>
        <div><label>Sell signals: 10-day hit rate</label><b>${b.shorts.n ? (b.shorts.hit * 100).toFixed(0) + "%" : "–"}</b> <span class="dim">n=${b.shorts.n}, avg ${P(b.shorts.avg)}</span></div>
        <div style="grid-column:1/3"><label>Signals similar to today's score</label><b>${b.similar.n ? (b.similar.hit * 100).toFixed(0) + "% right" : "–"}</b> <span class="dim">n=${b.similar.n}, avg 10-day move in signal direction ${P(b.similar.avg)}</span></div></div>`;
    btChart = LW.createChart($("#btc"), { ...base, rightPriceScale: { borderColor: "#1d2533" } });
    btChart.addLineSeries({ color: "#8791a6", lineWidth: 1.5, priceLineVisible: false }).setData(b.curve.t.map((t, i) => ({ time: t, value: b.curve.bh[i] })));
    btChart.addLineSeries({ color: "#5b8cff", lineWidth: 2, priceLineVisible: false }).setData(b.curve.t.map((t, i) => ({ time: t, value: b.curve.eq[i] })));
    btChart.timeScale().fitContent();
  }
  async function tabNews() {
    $("#tabBody").innerHTML = `<div class="empty"><span class="spin"></span></div>`;
    newsCache ||= await api(`/api/news/${encodeURIComponent(sym)}?name=${encodeURIComponent(A.name)}`).catch(() => []);
    if (tab !== "news") return;
    $("#tabBody").innerHTML = newsCache.length ? `<div class="news">${newsCache.map((n) => `<a ${n.link ? `href="${esc(n.link)}" target="_blank" rel="noopener noreferrer"` : ""}>
      <div class="tt">${n.move != null ? `<span class="${cls(n.move)}">${n.move > 0 ? "▲" : "▼"}</span> ` : ""}${esc(n.title)}</div>
      <div class="meta">${esc(n.publisher || "")} · ${n.time ? new Date(n.time * 1000).toLocaleString() : ""}</div></a>`).join("")}</div>` : `<div class="empty">No recent headlines.</div>`;
  }
  function tabAi() {
    const name = A ? disp(A.symbol) : sym ? disp(sym) : "the market";
    $("#tabBody").innerHTML = `<div style="display:flex;gap:8px;margin-bottom:10px"><button class="btn primary" id="genReport" ${A ? "" : "disabled"}>✨ Generate AI research note</button><span class="spacer"></span><span class="dim" style="font-size:11px;align-self:center">runs 100% locally</span></div>
      <div class="qchips">${["⚡ Why is it moving today?", "⚖️ Bull case vs bear case", "🏦 Good long-term hold?", "🧒 Explain it simply", "👥 How does it compare with peers?", "💰 How much should I buy?"].map((q) => `<span class="chip" data-q="${esc(q)}">${esc(q)}</span>`).join("")}</div>
      <div id="aiOut" class="md">${aiReport ? TS.md(aiReport) : `<div class="muted">Ask anything about ${esc(name)}: whether it's a good long-term hold, what the risks are, how it compares with peers, or how much to buy. The AI sees everything the engine computed plus the latest headlines and your budget.</div>`}</div>
      <div id="chat" style="margin-top:14px;display:flex;flex-direction:column;gap:8px">${chat.map((m) => `<div class="msg ${m.role} md">${TS.md(m.content)}</div>`).join("")}${pending ? `<div class="msg assistant md cursor" id="pending">${pending.text ? TS.md(pending.text) : `<span class="muted">Thinking… ${pending.secs}s</span>`}</div>` : ""}</div>`;
    $("#ask").placeholder = `Ask about ${name}… (Enter to send · Shift+Enter for a new line)`;
    document.querySelectorAll("#tabBody [data-q]").forEach((c) => (c.onclick = () => {
      const q = c.dataset.q;
      if (q.startsWith("⚡")) return window.RES.aiOutStream("/api/ai/why", { symbol: sym, market });
      window.RES.ask(q.replace(/^\S+\s/, "") + (q.startsWith("🧒") ? " Use very simple words, like explaining to a beginner." : ""));
    }));
    $("#genReport").onclick = async () => {
      const out = $("#aiOut"); out.classList.add("cursor"); out.innerHTML = `<span class="muted">Writing the note…</span>`;
      try { aiReport = await TS.stream("/api/ai/report", { symbol: sym, market }, (t) => { if ($("#aiOut")) $("#aiOut").innerHTML = TS.md(t); }); }
      catch (e) { if ($("#aiOut")) $("#aiOut").innerHTML = `<div class="down">AI request failed: ${esc(e.message)}</div>`; }
      $("#aiOut")?.classList.remove("cursor");
    };
    $("#tabBody").scrollTop = $("#tabBody").scrollHeight;
  }
  async function ask() {
    const box = $("#ask"), q = box.value.trim();
    if (!q || pending) return;
    if (tab !== "ai") document.querySelector('#rtabs button[data-t="ai"]').click();
    chat.push({ role: "user", content: q });
    box.value = "";
    pending = { text: "", secs: 0 };
    const t0 = Date.now();
    const tick = setInterval(() => { if (!pending) return; pending.secs = Math.round((Date.now() - t0) / 1000); const p = $("#pending"); if (p && !pending.text) p.innerHTML = `<span class="muted">Thinking… ${pending.secs}s${pending.secs > 15 ? " (the local model may still be loading)" : ""}</span>`; }, 1000);
    if (tab === "ai") tabAi();
    let ans = "";
    try {
      ans = await TS.stream("/api/ai/chat", { symbol: sym, market, messages: chat, plan }, (t) => { pending.text = t; const p = $("#pending"); if (p) { p.innerHTML = TS.md(t); $("#tabBody").scrollTop = $("#tabBody").scrollHeight; } });
    } catch (e) {
      ans = `⚠️ The AI request failed: ${e.message}. Make sure Ollama is running (rerun start.bat).`;
    }
    clearInterval(tick);
    chat.push({ role: "assistant", content: ans || "(no answer)" });
    pending = null;
    if (tab === "ai") tabAi();
    box.focus();
  }
  $("#askBtn").onclick = ask;
  window.RES.ask = (q) => { $("#ask").value = q; ask(); };
  window.RES.aiOutStream = async (path, body) => {
    if (tab !== "ai") document.querySelector('#rtabs button[data-t="ai"]').click();
    const out = $("#aiOut"); out.classList.add("cursor"); out.innerHTML = '<span class="muted">Thinking…</span>';
    try { aiReport = await TS.stream(path, body, (t) => { if ($("#aiOut")) $("#aiOut").innerHTML = TS.md(t); }); }
    catch (e) { if ($("#aiOut")) $("#aiOut").innerHTML = `<div class="down">AI request failed: ${esc(e.message)}</div>`; }
    $("#aiOut")?.classList.remove("cursor");
  };
  $("#ask").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(); } });

  // ---------------- watch + report
  function watchBtn() { const on = state?.watchlist?.includes(sym); $("#watchBtn").textContent = on ? "★ Watching" : "☆ Watch"; }
  $("#watchBtn").onclick = async () => {
    if (!sym) return;
    const wl = state.watchlist.includes(sym) ? state.watchlist.filter((s) => s !== sym) : [...state.watchlist, sym];
    state.watchlist = wl; await api("/api/state", { body: { watchlist: wl } }); watchBtn(); TS.send({ type: "watch", watchlist: wl });
  };
  $("#reportBtn").onclick = () => sym && window.open(`/report.html?symbol=${encodeURIComponent(sym)}${market ? "&market=" + market : ""}`, "_blank");

  if (sym) load(sym);
  else api("/api/state").then((s) => { state = s; if (s.watchlist[0]) load(s.watchlist[0]); });
})();
