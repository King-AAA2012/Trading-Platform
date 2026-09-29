// Command screen extras: Markets overview, screener, watchlists, alerts, world clocks, tools (calculators, compare,
// backtester, goal planner, FX converter, backup), holdings analytics & journal, AI assistant, guided tour, shortcuts.
window.CX = (() => {
  const $ = (s) => document.querySelector(s);
  const { api, esc, price, pct, cls, money } = TS;
  const C = window.CMD;
  const ls = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
  const lss = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };
  const H = (t, extra = "") => `<h4>${t}${extra}</h4>`;
  const COLORS = ["#5b8cff", "#1fd286", "#f5b942", "#ff5470", "#9b7bff", "#38bdf8"];

  // ---------------------------------------------------------------- SVG helpers
  function lines(t, series, { w = 640, h = 220, names = [], pctAxis = true } = {}) {
    const all = series.flat().filter((v) => v != null && isFinite(v));
    if (!all.length) return "";
    const mn = Math.min(...all), mx = Math.max(...all), pad = 36;
    const x = (i, n) => pad + (i / (n - 1)) * (w - pad - 8), y = (v) => h - 18 - ((v - mn) / (mx - mn || 1)) * (h - 30);
    const ticks = [mn, (mn + mx) / 2, mx].map((v) => `<text x="2" y="${y(v) + 3}" font-size="10" fill="var(--muted)">${pctAxis ? pct((v - 1) * 100, 0) : price(v)}</text><line x1="${pad}" x2="${w - 8}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)" stroke-dasharray="3 4"/>`).join("");
    const paths = series.map((s, k) => `<path d="${s.map((v, i) => `${i ? "L" : "M"}${x(i, s.length).toFixed(1)},${y(v).toFixed(1)}`).join("")}" fill="none" stroke="${COLORS[k % 6]}" stroke-width="${k === 0 ? 2 : 1.5}"/>`).join("");
    const lg = names.map((n, k) => `<span style="color:${COLORS[k % 6]};margin-right:10px">━ ${esc(n)}</span>`).join("");
    const dates = t && t.length ? `<text x="${pad}" y="${h - 3}" font-size="10" fill="var(--muted)">${new Date(t[0] * 1000).toLocaleDateString()}</text><text x="${w - 8}" y="${h - 3}" font-size="10" fill="var(--muted)" text-anchor="end">${new Date(t[t.length - 1] * 1000).toLocaleDateString()}</text>` : "";
    return `<svg viewBox="0 0 ${w} ${h}" width="100%">${ticks}${paths}${dates}</svg><div style="font-size:11.5px">${lg}</div>`;
  }
  function gauge(score, label) {
    const a = Math.PI * (1 - score / 100), cx = 110, cy = 105, r = 88;
    const seg = (from, to, col) => { const a0 = Math.PI * (1 - from / 100), a1 = Math.PI * (1 - to / 100); return `<path d="M${cx + r * Math.cos(a0)},${cy - r * Math.sin(a0)} A${r},${r} 0 0 1 ${cx + r * Math.cos(a1)},${cy - r * Math.sin(a1)}" stroke="${col}" stroke-width="16" fill="none"/>`; };
    return `<svg viewBox="0 0 220 125" width="220">${seg(0, 25, "#ff5470")}${seg(25, 45, "#ff9f6e")}${seg(45, 55, "#aab3c6")}${seg(55, 75, "#7fe0a7")}${seg(75, 100, "#1fd286")}
      <line x1="${cx}" y1="${cy}" x2="${cx + (r - 18) * Math.cos(a)}" y2="${cy - (r - 18) * Math.sin(a)}" stroke="var(--text)" stroke-width="3" stroke-linecap="round"/><circle cx="${cx}" cy="${cy}" r="6" fill="var(--text)"/>
      <text x="${cx}" y="${cy - 26}" text-anchor="middle" font-size="26" font-weight="700" fill="var(--text)" font-family="var(--mono)">${score}</text></svg><div style="text-align:center;font-weight:700" class="${score < 45 ? "down" : score > 55 ? "up" : ""}">${esc(label)}</div>`;
  }

  // ---------------------------------------------------------------- screener
  const PRESETS = {
    "🚀 Momentum leaders": { scoreMin: 30, ret3mMin: 10, above200: true },
    "📈 Fresh breakouts": { scoreMin: 20, newHigh: true },
    "🎯 Buy the dip (uptrend)": { rsiMax: 42, above200: true, scoreMin: 0 },
    "🧊 Low volatility": { atrMax: 1.8, scoreMin: 10 },
    "💎 High conviction": { scoreMin: 45, confMin: 65 },
    "🩸 Oversold bounce": { rsiMax: 30 },
    "🐻 Breakdowns": { scoreMax: -30, newLow: true },
  };
  let F = ls("ts-filter", {});
  function filter(r) {
    if (F.scoreMin != null && r.score < F.scoreMin) return false;
    if (F.scoreMax != null && r.score > F.scoreMax) return false;
    if (F.rsiMin != null && r.rsi < F.rsiMin) return false;
    if (F.rsiMax != null && r.rsi > F.rsiMax) return false;
    if (F.atrMax != null && r.atrPct * 100 > F.atrMax) return false;
    if (F.ret3mMin != null && (r.ret3m ?? -9) * 100 < F.ret3mMin) return false;
    if (F.confMin != null && r.confidence < F.confMin) return false;
    if (F.sector && r.sector !== F.sector) return false;
    if (F.above200 && !r.above200) return false;
    if (F.newHigh && !r.newHigh52 && !(r.setup || "").includes("Breakout")) return false;
    if (F.newLow && !r.newLow52 && !(r.setup || "").includes("Breakdown")) return false;
    return true;
  }
  const active = () => Object.values(F).some((v) => v !== null && v !== undefined && v !== "" && v !== false);
  function syncFilterBar() {
    const el = $("#filters");
    const sectors = [...new Set((C.scan?.rows || []).map((r) => r.sector).filter(Boolean))].sort();
    const saved = C.state?.screens || {};
    const num = (k, label, step = 1) => `<div class="field"><label>${label}</label><input class="in num" type="number" step="${step}" data-f="${k}" value="${F[k] ?? ""}"></div>`;
    el.innerHTML = `<div style="width:100%;display:flex;gap:5px;flex-wrap:wrap">${Object.keys(PRESETS).map((k) => `<span class="chip" data-pre="${esc(k)}">${esc(k)}</span>`).join("")}
        ${Object.keys(saved).map((k) => `<span class="chip on" data-saved="${esc(k)}">⭐ ${esc(k)}</span>`).join("")}</div>
      ${num("scoreMin", "Score ≥")}${num("scoreMax", "Score ≤")}${num("rsiMin", "RSI ≥")}${num("rsiMax", "RSI ≤")}${num("atrMax", "ATR% ≤", 0.1)}${num("ret3mMin", "3M return % ≥")}${num("confMin", "Confidence ≥")}
      <div class="field"><label>Sector</label><select class="in" data-f="sector"><option value="">Any</option>${sectors.map((s) => `<option ${F.sector === s ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></div>
      <label class="check"><input type="checkbox" data-f="above200" ${F.above200 ? "checked" : ""}> Above 200-day avg</label>
      <label class="check"><input type="checkbox" data-f="newHigh" ${F.newHigh ? "checked" : ""}> New highs</label>
      <label class="check"><input type="checkbox" data-f="newLow" ${F.newLow ? "checked" : ""}> New lows</label>
      <button class="btn sm" id="fSave">⭐ Save screen</button><button class="btn sm ghost" id="fClear">Clear</button>
      <span class="dim" style="font-size:11.5px" id="fCount"></span>`;
    el.querySelectorAll("[data-f]").forEach((i) => (i.onchange = i.oninput = () => {
      const k = i.dataset.f;
      F[k] = i.type === "checkbox" ? i.checked : i.value === "" ? null : i.tagName === "SELECT" ? i.value : +i.value;
      applyF();
    }));
    el.querySelectorAll("[data-pre]").forEach((c) => (c.onclick = () => { F = { ...PRESETS[c.dataset.pre] }; applyF(true); }));
    el.querySelectorAll("[data-saved]").forEach((c) => (c.onclick = () => { F = { ...saved[c.dataset.saved] }; applyF(true); }));
    $("#fClear").onclick = () => { F = {}; applyF(true); };
    $("#fSave").onclick = async () => {
      const name = prompt("Name this screen:");
      if (!name) return;
      const screens = { ...(C.state.screens || {}), [name]: F };
      C.state.screens = screens;
      await api("/api/state", { body: { screens } });
      syncFilterBar();
    };
    count();
  }
  function count() { const n = C.visibleRows?.length ?? 0; const c = $("#fCount"); if (c) c.textContent = active() ? `${n} match${n === 1 ? "" : "es"}` : ""; $("#fltBtn").classList.toggle("primary", active()); }
  function applyF(resync) { lss("ts-filter", F); C.renderRows(); if (resync) syncFilterBar(); else count(); }
  $("#fltBtn").onclick = () => { $("#filters").classList.toggle("show"); syncFilterBar(); };
  if (active()) setTimeout(() => $("#fltBtn").classList.add("primary"), 500);
  $("#csvBtn").onclick = () => {
    const rows = C.visibleRows || [];
    const cols = ["symbol", "name", "price", "currency", "changePct", "score", "signal", "setup", "confidence", "rsi", "atrPct", "ret1m", "ret3m", "ret1y", "sector"];
    UX.download(`tradescope-${C.state.lastMarket}-${new Date().toISOString().slice(0, 10)}.csv`, cols.join(",") + "\n" + rows.map((r) => cols.map((k) => JSON.stringify(r[k] ?? "")).join(",")).join("\n"), "text/csv");
  };
  let autoT = null;
  $("#autoBtn").onclick = () => {
    if (autoT) { clearInterval(autoT); autoT = null; $("#autoBtn").classList.remove("primary"); TS.toast("Auto-rescan off"); return; }
    autoT = setInterval(() => C.loadScan(true), 5 * 60 * 1000);
    $("#autoBtn").classList.add("primary"); TS.toast("Auto-rescan every 5 minutes");
  };

  // ---------------------------------------------------------------- markets overview
  async function renderOverview() {
    const el = $("#overview");
    el.innerHTML = `<div class="empty"><span class="spin"></span> Loading global markets…</div>`;
    let o;
    try { o = await api(`/api/overview?market=${C.state.lastMarket}`); } catch (e) { el.innerHTML = `<div class="empty">Couldn't load: ${esc(e.message)}</div>`; return; }
    const fg = o.fearGreed, yc = o.yieldCurve, b = o.breadth;
    const ycSvg = () => {
      const pts = yc.points; if (!pts.length) return "";
      const w = 300, h = 120, xs = (i) => 24 + (i / (pts.length - 1)) * (w - 34);
      const all = pts.flatMap((p) => [p.now, p.yearAgo]), mn = Math.min(...all) - 0.2, mx = Math.max(...all) + 0.2, y = (v) => h - 18 - ((v - mn) / (mx - mn)) * (h - 30);
      const path = (k) => pts.map((p, i) => `${i ? "L" : "M"}${xs(i)},${y(p[k])}`).join("");
      return `<svg viewBox="0 0 ${w} ${h}" width="100%"><path d="${path("yearAgo")}" fill="none" stroke="var(--dim)" stroke-dasharray="4 3"/><path d="${path("now")}" fill="none" stroke="#5b8cff" stroke-width="2"/>
        ${pts.map((p, i) => `<circle cx="${xs(i)}" cy="${y(p.now)}" r="3" fill="#5b8cff"/><text x="${xs(i)}" y="${h - 4}" font-size="10" text-anchor="middle" fill="var(--muted)">${p.tenor}</text><text x="${xs(i)}" y="${y(p.now) - 7}" font-size="10" text-anchor="middle" fill="var(--text)">${p.now.toFixed(2)}</text>`).join("")}</svg>
        <div style="font-size:11.5px"><span style="color:#5b8cff">━ now</span> <span class="dim">┅ a year ago</span> · 10Y–3M spread <b class="${yc.spread10y3m < 0 ? "down" : "up"}">${yc.spread10y3m?.toFixed(2)}pp</b> ${yc.inverted ? '<span class="down">(inverted: historically a recession warning)</span>' : '<span class="muted">(normal)</span>'}</div>`;
    };
    const hb = (rows, key, lab) => { const mx = Math.max(...rows.map((r) => Math.abs(r[key] || 0)), 1e-9); return `<div class="hbars">${rows.map((r) => `<div class="row"><span>${esc(r[lab])}</span><span style="position:relative;height:10px"><span class="bar" style="position:absolute;${(r[key] || 0) >= 0 ? "left:50%" : `right:50%`};width:${(Math.abs(r[key] || 0) / mx) * 50}%;background:${(r[key] || 0) >= 0 ? "var(--up)" : "var(--down)"}"></span></span><span class="num ${cls(r[key])}" style="text-align:right">${pct((r[key] || 0) * 100, 1)}</span></div>`).join("")}</div>`; };
    const mv = (rs) => rs.map((m) => `<tr class="row" data-s="${esc(m.symbol)}"><td><div class="sym">${esc(m.symbol)}<small>${esc(m.name)}</small></div></td><td class="r num">${price(m.price)}</td><td class="r num ${cls(m.changePct)}">${pct(m.changePct)}</td><td class="r num ${cls(m.score)}">${m.score?.toFixed(0)}</td></tr>`).join("");
    el.innerHTML = `<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px"><b>🌍 Global market dashboard</b><span class="muted" style="font-size:12px">breadth & movers for ${esc(o.market)}</span><span class="spacer"></span><button class="btn sm primary" id="brief">📰 AI market briefing</button></div>
      <div id="briefOut" class="md card" style="display:none;margin-bottom:10px"></div>
      <div class="mini-grid">
        <div class="card">${H("Fear & Greed", ` <span class="q" data-tip="Composite of VIX, market momentum, stocks vs bonds, junk-bond demand, gold vs stocks and breadth. Below 25 = extreme fear (often a buying opportunity), above 75 = extreme greed (be careful).">ⓘ</span>`)}${gauge(fg.score, fg.label)}
          ${fg.components.map((c) => `<div style="display:flex;justify-content:space-between;font-size:11.5px;padding:2px 0" data-tip="${esc(c.detail)}"><span class="muted">${esc(c.name)}</span><b class="num ${c.score < 45 ? "down" : c.score > 55 ? "up" : ""}">${c.score}</b></div>`).join("")}</div>
        <div class="card">${H("US yield curve", ` <span class="q" data-tip="Interest rates on US government debt from 3 months to 30 years. An inverted curve (short rates above long) has preceded most US recessions.">ⓘ</span>`)}${ycSvg()}</div>
        <div class="card">${H("Market breadth", ` <span class="q" data-tip="How many stocks are participating. Healthy rallies have most stocks above their 200-day average.">ⓘ</span>`)}
          <div class="kv"><div><label>Above 200-day avg</label><b>${((b.above200 || 0) * 100).toFixed(0)}%</b></div><div><label>Model bullish</label><b class="up">${((b.bull || 0) * 100).toFixed(0)}%</b></div>
          <div><label>52-week highs / lows</label><b><span class="up">${b.newHighs}</span> / <span class="down">${b.newLows}</span></b></div><div><label>Average RSI</label><b>${b.avgRsi}</b></div></div></div>
        <div class="card">${H("Currency strength (1 month)")}${hb(o.currencies, "1M", "ccy")}</div>
        <div class="card">${H("Sector rotation (3 months)")}${hb(o.sectors.map((s) => ({ ...s, label: s.sector.split(" ")[0] })), "3M", "label")}</div>
        <div class="card">${H("Top gainers")}<table class="t"><tbody>${mv(o.movers.gainers)}</tbody></table></div>
        <div class="card">${H("Top losers")}<table class="t"><tbody>${mv(o.movers.losers)}</tbody></table></div>
      </div>
      <div class="card" style="margin-top:10px">${H("World indices")}<table class="t"><thead><tr><th>Index</th><th class="r">Level</th><th class="r">Day</th><th class="r">1M</th><th class="r">YTD</th><th class="r">1Y</th></tr></thead><tbody>
        ${o.indices.map((i) => `<tr class="row" data-s="${esc(i.symbol)}"><td>${esc(i.name)}</td><td class="r num">${price(i.price)}</td>${["day", "1M", "YTD", "1Y"].map((k) => `<td class="r num ${cls(i[k])}">${i[k] == null ? "–" : pct(i[k] * 100, 1)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <div class="card" style="margin-top:10px">${H("Market headlines")}<div id="mNews" class="muted">Loading…</div></div>`;
    C.bindRows(el, "tr.row");
    $("#brief").onclick = async () => {
      const out = $("#briefOut"); out.style.display = "block"; out.classList.add("cursor"); out.innerHTML = '<span class="muted">Writing today\'s briefing…</span>';
      try { await TS.stream("/api/ai/briefing", { market: C.state.lastMarket }, (t) => (out.innerHTML = TS.md(t))); } catch (e) { out.innerHTML = `<span class="down">${esc(e.message)}</span>`; }
      out.classList.remove("cursor");
    };
    api("/api/news/market").then((n) => { const m = $("#mNews"); if (m) m.innerHTML = n.slice(0, 12).map((x) => `<div style="padding:5px 0;border-bottom:1px dashed var(--line)"><a href="${esc(x.link)}" target="_blank" rel="noopener noreferrer" style="color:var(--text)">${esc(x.title)}</a> <span class="dim" style="font-size:11px">${esc(x.publisher || "")} · ${x.time ? new Date(x.time * 1000).toLocaleString() : ""}</span></div>`).join("") || "No headlines."; }).catch(() => {});
  }

  // ---------------------------------------------------------------- world clocks
  const EXCH = [["🇺🇸 New York", "America/New_York", "09:30", "16:00"], ["🇨🇦 Toronto", "America/Toronto", "09:30", "16:00"], ["🇧🇷 São Paulo", "America/Sao_Paulo", "10:00", "17:00"],
    ["🇬🇧 London", "Europe/London", "08:00", "16:30"], ["🇩🇪 Frankfurt", "Europe/Berlin", "09:00", "17:30"], ["🇿🇦 Johannesburg", "Africa/Johannesburg", "09:00", "17:00"],
    ["🇸🇦 Riyadh", "Asia/Riyadh", "10:00", "15:00", [0, 1, 2, 3, 4]], ["🇮🇳 Mumbai", "Asia/Kolkata", "09:15", "15:30"], ["🇨🇳 Shanghai", "Asia/Shanghai", "09:30", "15:00"],
    ["🇭🇰 Hong Kong", "Asia/Hong_Kong", "09:30", "16:00"], ["🇯🇵 Tokyo", "Asia/Tokyo", "09:00", "15:30"], ["🇦🇺 Sydney", "Australia/Sydney", "10:00", "16:00"]];
  function clocks() {
    const now = new Date();
    let open = 0;
    const rows = EXCH.map(([n, tz, o, c, days]) => {
      const parts = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", weekday: "short", hour12: false }).formatToParts(now).map((p) => [p.type, p.value]));
      const wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(parts.weekday), hm = `${parts.hour === "24" ? "00" : parts.hour}:${parts.minute}`;
      const isOpen = (days || [1, 2, 3, 4, 5]).includes(wd) && hm >= o && hm < c;
      if (isOpen) open++;
      return `<div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0"><span>${n}</span><span class="num">${hm} <span class="${isOpen ? "up" : "dim"}">${isOpen ? "● open" : "○ closed"}</span></span></div>`;
    });
    $("#clkTxt").textContent = `${open} open`;
    $("#clkPop").innerHTML = `<div class="muted" style="font-size:11px;margin-bottom:4px">Local exchange time · regular sessions (holidays not shown) · crypto trades 24/7</div>${rows.join("")}`;
  }
  clocks(); setInterval(clocks, 30000);
  $("#clkBtn").onclick = (e) => { e.stopPropagation(); $("#clkPop").classList.toggle("show"); };
  document.addEventListener("click", (e) => { if (!e.target.closest("#clkPop,#clkBtn")) $("#clkPop").classList.remove("show"); });

  // ---------------------------------------------------------------- watchlists
  let listSel = ls("ts-wl", "Main");
  const lists = () => ({ Main: C.state?.watchlist || [], ...(C.state?.watchlists || {}) });
  function currentList() { return listSel === "Main" ? null : lists()[listSel] || []; }
  function listName() { return listSel; }
  async function saveList(list) { const w = { ...(C.state.watchlists || {}), [listSel]: list }; C.state.watchlists = w; await api("/api/state", { body: { watchlists: w } }); }
  function renderLists() {
    const names = Object.keys(lists());
    if (!names.includes(listSel)) listSel = "Main";
    $("#wlSel").innerHTML = names.map((n) => `<option ${n === listSel ? "selected" : ""}>${esc(n)}</option>`).join("");
  }
  $("#wlSel").onchange = () => { listSel = $("#wlSel").value; lss("ts-wl", listSel); C.renderWatch(); };
  $("#wlNew").onclick = async () => {
    const n = (prompt("New watchlist name:") || "").trim();
    if (!n || lists()[n]) return;
    const w = { ...(C.state.watchlists || {}), [n]: [] };
    C.state.watchlists = w; await api("/api/state", { body: { watchlists: w } });
    listSel = n; lss("ts-wl", n); renderLists(); C.renderWatch();
  };

  // ---------------------------------------------------------------- alerts
  function alertCount() { const a = (C.state?.alerts || []).filter((x) => x.active); $("#alertN").textContent = a.length; }
  async function checkAlerts() {
    const al = (C.state?.alerts || []).filter((x) => x.active);
    if (!al.length) return;
    const syms = [...new Set(al.map((a) => a.symbol))];
    const q = Object.fromEntries((await api("/api/quotes?symbols=" + encodeURIComponent(syms.join(","))).catch(() => [])).map((x) => [x.symbol, x]));
    const rows = Object.fromEntries((C.scan?.rows || []).map((r) => [r.symbol, r]));
    let changed = false;
    for (const a of al) {
      const px = q[a.symbol]?.price, sc = rows[a.symbol]?.score;
      const hit = (a.kind === "above" && px >= a.value) || (a.kind === "below" && px != null && px <= a.value) || (a.kind === "score_above" && sc != null && sc >= a.value) || (a.kind === "score_below" && sc != null && sc <= a.value);
      if (hit) {
        a.active = false; a.triggered = Date.now(); changed = true;
        const msg = `${a.symbol} ${a.kind.startsWith("score") ? `score ${sc?.toFixed(0)}` : `price ${price(px)}`} is ${a.kind.includes("above") ? "above" : "below"} ${price(a.value)}`;
        UX.notify("🔔 TradeScope alert", msg);
        TS.toast("🔔 " + msg, 6000);
      }
    }
    if (changed) { await api("/api/state", { body: { alerts: C.state.alerts } }); alertCount(); }
  }
  setInterval(checkAlerts, 60000);
  TS.on(async (m) => { if (m.type === "alerts") { const st = await api("/api/state"); C.state.alerts = st.alerts; C.state.notes = st.notes; alertCount(); } });
  function openAlerts() {
    const al = C.state.alerts || [];
    const body = UX.modal("🔔 Alerts", `<div class="hint" style="margin-bottom:10px">Alerts are checked every minute while this screen is open. You'll get a sound, a desktop notification and a banner. Add alerts here or from a stock's <b>Tools</b> tab.</div>
      <div style="display:flex;gap:6px;align-items:end;margin-bottom:10px"><div class="field" style="flex:1"><label>Symbol</label><div class="search" style="width:100%"><span class="ico">⌕</span><input id="alS" class="in" autocomplete="off" placeholder="e.g. AAPL"><div id="alR" class="results"></div></div></div>
        <div class="field"><label>When</label><select class="in" id="alK2"><option value="above">Price rises above</option><option value="below">Price falls below</option><option value="score_above">Score rises above</option><option value="score_below">Score falls below</option></select></div>
        <div class="field" style="width:120px"><label>Value</label><input class="in num" id="alV2" type="number" step="any"></div><button class="btn primary" id="alGo" style="height:34px">Add</button></div>
      <table class="t"><thead><tr><th>Symbol</th><th>Condition</th><th>Status</th><th></th></tr></thead><tbody>${al.map((a) => `<tr><td><b>${esc(a.symbol)}</b></td><td>${esc(a.kind.replace("_", " "))} <b class="num">${price(a.value)}</b></td>
        <td>${a.active ? '<span class="up">● watching</span>' : a.triggered ? `<span class="warn">✓ triggered ${new Date(a.triggered).toLocaleString()}</span>` : "paused"}</td>
        <td style="white-space:nowrap">${a.active ? "" : `<button class="btn sm ghost" data-re="${esc(a.id)}">↻ Re-arm</button>`}<button class="btn sm ghost" data-rm="${esc(a.id)}">✕</button></td></tr>`).join("") || '<tr><td colspan="4" class="empty">No alerts yet.</td></tr>'}</tbody></table>`);
    let pick = null;
    TS.bindSearch(body.querySelector("#alS"), body.querySelector("#alR"), async (s) => { pick = s; const q = (await api("/api/quotes?symbols=" + encodeURIComponent(s)).catch(() => []))[0]; if (q) body.querySelector("#alV2").value = +(q.price * 1.05).toFixed(2); }, { keepValue: true, global: false });
    const save = async (alerts) => { C.state.alerts = alerts; await api("/api/state", { body: { alerts } }); alertCount(); openAlerts(); };
    body.querySelector("#alGo").onclick = () => {
      const s = pick || body.querySelector("#alS").value.trim().toUpperCase(), v = +body.querySelector("#alV2").value;
      if (!s || !isFinite(v) || !body.querySelector("#alV2").value) return TS.toast("Symbol and value needed");
      try { if ("Notification" in window && Notification.permission === "default") Notification.requestPermission(); } catch {}
      save([...(C.state.alerts || []), { id: Math.random().toString(36).slice(2, 9), symbol: s, kind: body.querySelector("#alK2").value, value: v, active: true, created: Date.now() }]);
    };
    body.querySelectorAll("[data-rm]").forEach((b) => (b.onclick = () => save(al.filter((a) => a.id !== b.dataset.rm))));
    body.querySelectorAll("[data-re]").forEach((b) => (b.onclick = () => save(al.map((a) => (a.id === b.dataset.re ? { ...a, active: true, triggered: null } : a)))));
  }
  $("#alertBtn").onclick = openAlerts;

  // ---------------------------------------------------------------- tools
  const TOOLS = { size: "📐 Position size", compound: "📈 Compound & SIP", goal: "🎯 Goal planner", fx: "💱 Currency converter", compare: "⚖️ Compare", backtest: "🧪 Backtest", backup: "💾 Backup", glossary: "📖 Glossary", keys: "⌨ Shortcuts" };
  function openTools(which = "size") {
    const body = UX.modal("🧰 Tools", `<div class="tabs" id="tTabs" style="margin-bottom:12px;flex-wrap:wrap">${Object.entries(TOOLS).map(([k, v]) => `<button data-tool="${k}" class="${k === which ? "on" : ""}">${v}</button>`).join("")}</div><div id="tBody"></div>`, true);
    body.querySelectorAll("[data-tool]").forEach((b) => (b.onclick = () => openTools(b.dataset.tool)));
    const tb = body.querySelector("#tBody");
    const prof = C.state.profile;
    const f = (id, label, val, step = "any") => `<div class="field"><label>${label}</label><input class="in num" id="${id}" type="number" step="${step}" value="${val}"></div>`;
    if (which === "glossary") return UX.showGlossary();
    if (which === "keys") return UX.showShortcuts();
    if (which === "size") {
      tb.innerHTML = `<div class="form" style="grid-template-columns:repeat(4,1fr)">${f("sE", "Entry price", 100)}${f("sS", "Stop-loss", 95)}${f("sT", "Target (optional)", 110)}${f("sB", `Account (${prof.currency})`, prof.budget || 10000)}${f("sR", "Risk per trade %", prof.riskPerTrade || 1, 0.1)}${f("sF", "Fees per trade", 0)}</div><div class="card" id="sOut" style="margin-top:10px"></div>`;
      const calc = () => {
        const e = +$("#sE").value, s = +$("#sS").value, t = +$("#sT").value, b = +$("#sB").value, r = +$("#sR").value / 100, fee = +$("#sF").value || 0;
        const risk = Math.abs(e - s); if (!(risk > 0 && b > 0 && r > 0)) return;
        const q = Math.floor((b * r - 2 * fee) / risk), rr = t ? Math.abs(t - e) / risk : null;
        $("#sOut").innerHTML = `<div style="font-size:16px"><b class="num">${Math.max(q, 0).toLocaleString()}</b> shares · position ${money(q * e, prof.currency)} (${((q * e) / b * 100).toFixed(1)}% of account)</div>
          <div class="muted num" style="margin-top:4px">Max loss at stop ${money(q * risk + 2 * fee, prof.currency)} · stop ${((risk / e) * 100).toFixed(2)}% away${rr ? ` · reward/risk <b class="${rr >= 2 ? "up" : rr < 1 ? "down" : "warn"}">${rr.toFixed(2)} : 1</b> · profit at target ${money(q * Math.abs(t - e) - 2 * fee, prof.currency)} · break-even win rate ${(100 / (1 + rr)).toFixed(0)}%` : ""}</div>`;
      };
      tb.querySelectorAll("input").forEach((i) => (i.oninput = calc)); calc();
    }
    if (which === "compound") {
      tb.innerHTML = `<div class="form" style="grid-template-columns:repeat(5,1fr)">${f("cP", "Starting amount", 10000)}${f("cM", "Monthly contribution", 500)}${f("cR", "Annual return %", 10, 0.1)}${f("cY", "Years", 20, 1)}${f("cI", "Inflation %", 3, 0.1)}</div><div id="cOut" style="margin-top:10px"></div>`;
      const calc = () => {
        const P = +$("#cP").value, M = +$("#cM").value, r = +$("#cR").value / 100 / 12, Y = Math.max(1, Math.round(+$("#cY").value)), inf = +$("#cI").value / 100;
        let v = P, contrib = P; const yearly = [];
        for (let m = 1; m <= Y * 12; m++) { v = v * (1 + r) + M; contrib += M; if (m % 12 === 0) yearly.push({ y: m / 12, v, contrib }); }
        const real = v / Math.pow(1 + inf, Y);
        $("#cOut").innerHTML = `<div class="kv" style="grid-template-columns:repeat(4,1fr)"><div><label>Final value</label><b class="up">${money(v, prof.currency)}</b></div><div><label>You contributed</label><b>${money(contrib, prof.currency)}</b></div><div><label>Growth earned</label><b class="up">${money(v - contrib, prof.currency)}</b></div><div><label>In today's money</label><b>${money(real, prof.currency)}</b></div></div>
          ${lines(null, [yearly.map((x) => x.v), yearly.map((x) => x.contrib)], { names: ["Portfolio value", "Money put in"], pctAxis: false })}`;
      };
      tb.querySelectorAll("input").forEach((i) => (i.oninput = calc)); calc();
    }
    if (which === "goal") {
      tb.innerHTML = `<div class="form" style="grid-template-columns:repeat(6,1fr)">${f("gC", "Have now", prof.budget || 10000)}${f("gM", "Add monthly", 500)}${f("gT", "Goal", 250000)}${f("gY", "Years", 15, 1)}${f("gR", "Expected return %", 9, 0.1)}${f("gV", "Volatility %", 16, 0.5)}</div><div id="gOut" style="margin-top:10px"></div>`;
      const calc = () => {
        const C0 = +$("#gC").value, M = +$("#gM").value, T = +$("#gT").value, Y = Math.max(1, Math.round(+$("#gY").value)), mu = +$("#gR").value / 100, sd = +$("#gV").value / 100;
        const sims = 2000, months = Y * 12, mm = mu / 12 - (sd * sd) / 24, ms = sd / Math.sqrt(12), ends = [], paths = [];
        for (let s = 0; s < sims; s++) {
          let v = C0; const p = [];
          for (let m = 0; m < months; m++) { const z = Math.sqrt(-2 * Math.log(Math.random() || 1e-9)) * Math.cos(2 * Math.PI * Math.random()); v = v * Math.exp(mm + ms * z) + M; if (m % 12 === 11) p.push(v); }
          ends.push(v); if (s < 400) paths.push(p);
        }
        ends.sort((a, b) => a - b);
        const q = (p) => ends[Math.floor(p * (sims - 1))], prob = ends.filter((e) => e >= T).length / sims;
        const band = (p) => Array.from({ length: Y }, (_, i) => { const col = paths.map((x) => x[i]).sort((a, b) => a - b); return col[Math.floor(p * (col.length - 1))]; });
        $("#gOut").innerHTML = `<div class="kv" style="grid-template-columns:repeat(4,1fr)"><div><label>Chance of reaching goal</label><b class="${prob >= 0.7 ? "up" : prob < 0.4 ? "down" : "warn"}" style="font-size:22px">${(prob * 100).toFixed(0)}%</b></div><div><label>Median outcome</label><b>${money(q(0.5), prof.currency)}</b></div><div><label>Bad case (10%)</label><b class="down">${money(q(0.1), prof.currency)}</b></div><div><label>Good case (90%)</label><b class="up">${money(q(0.9), prof.currency)}</b></div></div>
          ${lines(null, [band(0.5), band(0.1), band(0.9), Array(Y).fill(T)], { names: ["Median", "Bad 10%", "Good 90%", "Goal"], pctAxis: false })}<div class="dim" style="font-size:11px">2,000 simulated futures with random yearly swings of ${(sd * 100).toFixed(0)}%.</div>`;
      };
      tb.querySelectorAll("input").forEach((i) => (i.onchange = calc)); calc();
    }
    if (which === "fx") {
      const cc = ["USD", "EUR", "GBP", "INR", "JPY", "CNY", "HKD", "SGD", "AUD", "CAD", "CHF", "KRW", "BRL", "ZAR", "SAR", "AED", "MXN", "SEK"];
      const sel = (id, v) => `<div class="field"><label>${id === "fF" ? "From" : "To"}</label><select class="in" id="${id}">${cc.map((c) => `<option ${c === v ? "selected" : ""}>${c}</option>`).join("")}</select></div>`;
      tb.innerHTML = `<div class="form" style="grid-template-columns:2fr 1fr 1fr">${f("fA", "Amount", 1000)}${sel("fF", "USD")}${sel("fT", prof.currency === "USD" ? "INR" : prof.currency)}</div><div class="card" id="fOut" style="margin-top:10px;font-size:18px"></div>`;
      const calc = async () => { const r = await api(`/api/fx?frm=${$("#fF").value}&to=${$("#fT").value}`).catch(() => null); if (r) $("#fOut").innerHTML = `<b class="num">${(+$("#fA").value).toLocaleString()} ${r.from}</b> = <b class="num up">${(+$("#fA").value * r.rate).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${r.to}</b><div class="dim" style="font-size:12px">1 ${r.from} = ${r.rate.toFixed(5)} ${r.to} (latest market rate)</div>`; };
      tb.querySelectorAll("input,select").forEach((i) => (i.onchange = calc)); calc();
    }
    if (which === "compare") {
      tb.innerHTML = `<div style="display:flex;gap:6px"><input class="in" id="cmS" value="${esc([C.state.watchlist?.[0], C.state.watchlist?.[1], "^GSPC"].filter(Boolean).join(", "))}" placeholder="Up to 6 symbols, comma separated"><select class="in" id="cmD" style="width:110px"><option value="126">6 months</option><option value="252" selected>1 year</option><option value="756">3 years</option><option value="1260">5 years</option></select><button class="btn primary" id="cmGo">Compare</button><button class="btn" id="cmAi">✨ AI verdict</button></div><div id="cmOut" style="margin-top:10px"></div>`;
      const run = async () => {
        $("#cmOut").innerHTML = '<div class="empty"><span class="spin"></span></div>';
        let r; try { r = await api(`/api/compare?symbols=${encodeURIComponent($("#cmS").value)}&days=${$("#cmD").value}`); } catch (e) { $("#cmOut").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
        $("#cmOut").innerHTML = `${lines(r.t, r.symbols.map((s) => r.series[s]), { names: r.symbols })}
          <table class="t" style="margin-top:8px"><thead><tr><th>Symbol</th><th class="r">Return</th><th class="r">Volatility</th><th class="r">Sharpe</th><th class="r">Max drawdown</th></tr></thead><tbody>${r.stats.map((s, k) => `<tr><td><span style="color:${COLORS[k % 6]}">●</span> <b>${esc(s.symbol)}</b> <span class="dim">${esc(s.name)}</span></td><td class="r num ${cls(s.ret)}">${pct(s.ret * 100, 1)}</td><td class="r num">${(s.vol * 100).toFixed(1)}%</td><td class="r num">${s.sharpe.toFixed(2)}</td><td class="r num down">${pct(s.maxdd * 100, 1)}</td></tr>`).join("")}</tbody></table>
          ${r.symbols.length > 1 ? `<h4 style="margin:10px 0 4px;font-size:11px;color:var(--muted)">CORRELATION</h4><table class="t"><tr><th></th>${r.symbols.map((s) => `<th class="r">${esc(s)}</th>`).join("")}</tr>${r.corr.map((row, i) => `<tr><td><b>${esc(r.symbols[i])}</b></td>${row.map((v) => `<td class="r num" style="background:rgba(${v > 0 ? "91,140,255" : "255,84,112"},${Math.abs(v) * 0.35})">${v.toFixed(2)}</td>`).join("")}</tr>`).join("")}</table>` : ""}<div id="cmAiOut" class="md" style="margin-top:10px"></div>`;
      };
      $("#cmGo").onclick = run; run();
      $("#cmAi").onclick = async () => { const out = $("#cmAiOut") || $("#cmOut"); out.classList.add("cursor"); try { await TS.stream("/api/ai/compare", { symbols: $("#cmS").value.split(",").map((x) => x.trim()).filter(Boolean) }, (t) => (out.innerHTML = TS.md(t))); } catch (e) { out.innerHTML = esc(e.message); } out.classList.remove("cursor"); };
    }
    if (which === "backtest") {
      const plan = C.plan;
      const fromPlan = plan && plan.allocation ? Object.fromEntries(plan.allocation.filter((a) => a.symbol !== "CASH" && a.targetWeight).map((a) => [a.symbol, +a.targetWeight.toFixed(4)])) : {};
      const hs = C.state.holdings || [];
      tb.innerHTML = `<div class="hint" style="margin-bottom:8px">Backtest a set of weights with periodic rebalancing against the S&P 500. It starts from your latest plan's target weights (or edit them: one <code>SYMBOL weight</code> per line, weights as fractions).</div>
        <div style="display:grid;grid-template-columns:260px 1fr;gap:12px"><div><textarea class="in mono" id="btW" rows="12">${Object.entries(fromPlan).map(([k, v]) => `${k} ${v}`).join("\n") || hs.map((h) => `${h.symbol} ${(1 / Math.max(hs.length, 1)).toFixed(3)}`).join("\n") || "AAPL 0.3\nMSFT 0.3\nGLD 0.2"}</textarea>
          <div class="form" style="margin-top:6px"><div class="field"><label>Period</label><select class="in" id="btD"><option value="252">1 year</option><option value="756" selected>3 years</option><option value="1250">5 years</option></select></div><div class="field"><label>Rebalance</label><select class="in" id="btR"><option value="21" selected>Monthly</option><option value="63">Quarterly</option><option value="252">Yearly</option><option value="100000">Never</option></select></div></div>
          <button class="btn primary" id="btGo" style="margin-top:6px;width:100%">Run backtest</button></div><div id="btOut"></div></div>`;
      $("#btGo").onclick = async () => {
        const w = Object.fromEntries($("#btW").value.split(/\n/).map((l) => l.trim().split(/[\s,]+/)).filter((p) => p[0] && +p[1]).map((p) => [p[0].toUpperCase(), +p[1]]));
        $("#btOut").innerHTML = '<div class="empty"><span class="spin"></span></div>';
        let r; try { r = await api("/api/backtest/weights", { body: { weights: w, days: +$("#btD").value, rebalance: +$("#btR").value } }); } catch (e) { $("#btOut").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
        const s = r.stats, b = r.benchStats, row = (k, a, bb, fmt) => `<tr><td>${k}</td><td class="r num">${fmt(a)}</td><td class="r num">${fmt(bb)}</td></tr>`;
        $("#btOut").innerHTML = `${lines(r.t, [r.portfolio, r.benchmark], { names: ["Your weights", "S&P 500"] })}<table class="t"><thead><tr><th>${r.years} years</th><th class="r">Portfolio</th><th class="r">S&P 500</th></tr></thead><tbody>
          ${row("Total return", s.total, b.total, (v) => pct(v * 100, 1))}${row("CAGR", s.cagr, b.cagr, (v) => pct(v * 100, 1))}${row("Volatility", s.vol, b.vol, (v) => (v * 100).toFixed(1) + "%")}${row("Sharpe", s.sharpe, b.sharpe, (v) => v.toFixed(2))}${row("Max drawdown", s.maxdd, b.maxdd, (v) => pct(v * 100, 1))}</tbody></table>
          <div class="dim" style="font-size:11px">Hindsight warning: weights chosen today look good on the past they were chosen from.</div>`;
      };
      $("#btGo").click();
    }
    if (which === "backup") {
      tb.innerHTML = `<div class="hint">Everything (settings, holdings, watchlists, alerts, notes, journal, saved screens) lives in <code>data/state.json</code> on this PC. Download a backup or restore one here.</div>
        <div style="display:flex;gap:8px;margin:10px 0"><button class="btn primary" id="bkDl">⬇ Download backup</button><button class="btn" id="bkUp">⬆ Restore from pasted backup</button></div><textarea class="in mono" id="bkTxt" rows="8" placeholder="Paste a backup JSON here to restore"></textarea>`;
      $("#bkDl").onclick = async () => UX.download(`tradescope-backup-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(await api("/api/state"), null, 1), "application/json");
      $("#bkUp").onclick = async () => {
        let j; try { j = JSON.parse($("#bkTxt").value); } catch { return TS.toast("That isn't valid JSON"); }
        if (!confirm("Replace your current settings, holdings and lists with this backup?")) return;
        await api("/api/state", { body: j }); TS.toast("Restored. Reloading…"); setTimeout(() => location.reload(), 800);
      };
    }
  }
  $("#toolsBtn").onclick = () => openTools();

  // ---------------------------------------------------------------- holdings: analytics & journal tabs
  document.querySelectorAll("#hTabs button").forEach((b) => (b.onclick = () => {
    document.querySelectorAll("#hTabs button").forEach((x) => x.classList.toggle("on", x === b));
    const k = b.dataset.h;
    $("#hPos").style.display = k === "pos" ? "" : "none";
    $("#hAna").style.display = k === "ana" ? "" : "none";
    $("#hJr").style.display = k === "jr" ? "" : "none";
    if (k !== "pos") holdingsExtra(k);
  }));
  async function holdingsExtra(k) {
    const el = k === "ana" ? $("#hAna") : $("#hJr");
    el.innerHTML = '<div class="empty"><span class="spin"></span> Analysing your portfolio…</div>';
    const a = await api("/api/holdings/analytics").catch(() => null);
    const c = C.state.profile.currency;
    if (!a || a.empty) { el.innerHTML = '<div class="empty">Add some holdings first.</div>'; return; }
    if (k === "jr") {
      el.innerHTML = `<div class="kv" style="grid-template-columns:repeat(3,1fr);margin-bottom:10px"><div><label>Recorded trades</label><b>${a.journal.length}</b></div><div><label>Realised P/L (instrument currency)</label><b class="${cls(a.realized)}">${money(a.realized, "")}</b></div><div><label>Tip</label><b style="font-size:12px;font-family:var(--sans)">Plan buttons and manual adds are logged here</b></div></div>
        <div style="max-height:55vh;overflow:auto"><table class="t"><thead><tr><th>Date</th><th>Action</th><th>Symbol</th><th class="r">Qty</th><th class="r">Price</th><th class="r">Realised P/L</th></tr></thead><tbody>${a.journal.map((j) => `<tr><td>${new Date(j.t * 1000).toLocaleString()}</td><td><span class="tag ${j.action}" style="padding:1px 6px;font-size:10px">${j.action}</span></td><td><b>${esc(j.symbol)}</b></td><td class="r num">${j.qty}</td><td class="r num">${price(j.price)}</td><td class="r num ${cls(j.realized)}">${j.realized == null ? "–" : money(j.realized, "")}</td></tr>`).join("") || '<tr><td colspan="6" class="empty">No trades recorded yet.</td></tr>'}</tbody></table></div>`;
      return;
    }
    const r = a.risk || {}, bd = a.breakdown;
    const donutRows = (rows) => rows.map((x, i) => `<div style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0"><span><span class="sw" style="background:${COLORS[i % 6]}"></span>${esc(x.name)}</span><span class="num muted">${(x.weight * 100).toFixed(1)}%</span></div>`).join("");
    el.innerHTML = `${r.empty ? "" : `<div class="agrid kv" style="grid-template-columns:repeat(6,1fr);margin-bottom:10px">
        <div data-tip="Based on the last year's behaviour of what you hold now"><label>Volatility</label><b>${(r.vol * 100).toFixed(1)}%</b></div><div data-tip="On 1 day in 20 you could lose at least this share of your holdings' value"><label>1-day VaR 95%</label><b class="down">${(r.var95 * 100).toFixed(2)}%</b></div>
        <div><label>Beta to S&P</label><b>${r.beta != null ? r.beta.toFixed(2) : "–"}</b></div><div><label>Avg correlation</label><b>${r.avgCorr.toFixed(2)}</b></div>
        <div><label>Effective positions</label><b>${r.effN.toFixed(1)}</b></div><div data-tip="Estimated yearly dividends at current yields"><label>Dividend income / yr</label><b class="up">${money(a.dividends, c)}</b></div></div>
      <div class="wi-cols"><div class="card">${H("Last year, if you'd held this mix")}${lines(null, [r.curve], { names: ["Your current holdings"] })}<div class="dim" style="font-size:11px">Return ${pct(r.backtestReturn * 100, 1)} · worst dip ${pct(r.backtestMaxDD * 100, 1)} · chance of a losing year ${(r.mc.probLoss * 100).toFixed(0)}% (Monte Carlo)</div></div>
      <div class="card">${H("Where the risk comes from")}${(r.symbols || []).map((s, i) => `<div class="bars"><div class="b" style="grid-template-columns:110px 1fr 50px"><span>${esc(s)}</span><span class="track"><i style="left:0;width:${Math.max(0, r.riskContrib[i] * 100)}%;background:var(--warn)"></i></span><span class="num dim">${(r.riskContrib[i] * 100).toFixed(0)}%</span></div></div>`).join("")}</div></div>`}
      <div class="wi-cols" style="margin-top:10px"><div class="card">${H("By sector")}${donutRows(bd.sector)}</div><div class="card">${H("By currency")}${donutRows(bd.quoteCurrency)}</div></div>`;
  }

  // ---------------------------------------------------------------- AI assistant
  const chat = [];
  $("#fab").onclick = () => { $("#assist").classList.toggle("show"); if ($("#assist").classList.contains("show")) $("#asIn").focus(); };
  $("#asX").onclick = () => $("#assist").classList.remove("show");
  const slimPlan = () => C.plan ? { market: C.plan.market, profile: C.plan.profile, actions: C.plan.actions.slice(0, 15).map((a) => ({ action: a.action, symbol: a.symbol, qty: a.qty, reason: a.reason })), sectors: C.plan.sectors, analytics: C.plan.analytics ? { expReturn: C.plan.analytics.expReturn, vol: C.plan.analytics.vol } : null } : null;
  async function assistAsk(q, path = "/api/ai/chat") {
    const log = $("#asLog");
    if (q) { chat.push({ role: "user", content: q }); log.insertAdjacentHTML("beforeend", `<div class="msg user md">${TS.md(q)}</div>`); }
    log.insertAdjacentHTML("beforeend", `<div class="msg assistant md cursor" id="asPend"><span class="muted">Thinking…</span></div>`);
    log.scrollTop = log.scrollHeight;
    let ans = "";
    try { ans = await TS.stream(path, path.endsWith("chat") ? { messages: chat, plan: slimPlan() } : { market: C.state.lastMarket }, (t) => { const p = $("#asPend"); if (p) { p.innerHTML = TS.md(t); log.scrollTop = log.scrollHeight; } }); }
    catch (e) { ans = "⚠️ " + e.message; }
    if (path.endsWith("chat")) chat.push({ role: "assistant", content: ans });
    const p = $("#asPend"); if (p) { p.classList.remove("cursor"); p.removeAttribute("id"); if (!p.textContent.trim()) p.innerHTML = TS.md(ans); }
  }
  $("#asGo").onclick = () => { const q = $("#asIn").value.trim(); if (q) { $("#asIn").value = ""; assistAsk(q); } };
  $("#asIn").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#asGo").click(); } });
  $("#asBrief").onclick = () => assistAsk("", "/api/ai/briefing");

  // ---------------------------------------------------------------- guided tour
  const STEPS = [
    ["#market", "Pick any market", "Choose from 44 countries plus crypto, FX, commodities, bonds and ETFs. The scanner scores every instrument instantly."],
    ["#rows", "The opportunity scanner", "Each row is scored −100 to +100. Click to select, double-click for the full research screen with charts, levels, stats and the AI."],
    ["#fltBtn", "Screener", "Filter by score, RSI, volatility, momentum and sector, use a preset like 'Buy the dip', or save your own screens."],
    ["#riskDial", "Your risk level", "One dial from 0 (very safe) to 100 (very aggressive) sets every risk rule. Fine-tune under Advanced."],
    ["#planBtn", "Build today's plan", "A ten-agent committee debates the best ideas, then an optimiser sizes them to your risk and budget. Add them to your holdings with one click."],
    ["#tabs", "What-If Lab & Markets", "Ask 'what if oil hits $150?' and see winners and losers. The Markets tab shows fear & greed, the yield curve, currencies and world indices."],
    ["#toolsBtn", "Tools", "Position sizing, compound interest, goal planner, currency converter, compare, backtester, glossary and backups."],
    ["#fab", "Your AI assistant", "Ask anything about markets or your plan. It runs locally and privately on your PC."],
  ];
  function tour(i = 0) {
    document.querySelectorAll(".tour-hi,.tour-box").forEach((x) => x.remove());
    if (i >= STEPS.length) { lss("ts-tour", 1); return; }
    const [sel, title, text] = STEPS[i], el = $(sel);
    if (!el) return tour(i + 1);
    const r = el.getBoundingClientRect();
    const hi = document.createElement("div"); hi.className = "tour-hi";
    Object.assign(hi.style, { left: r.left - 6 + "px", top: r.top - 6 + "px", width: r.width + 12 + "px", height: Math.min(r.height, innerHeight * 0.6) + 12 + "px" });
    const box = document.createElement("div"); box.className = "tour-box";
    box.innerHTML = `<div class="dim" style="font-size:11px">Step ${i + 1} of ${STEPS.length}</div><h3 style="margin:4px 0 6px">${esc(title)}</h3><div class="muted" style="font-size:12.5px">${esc(text)}</div>
      <div style="display:flex;gap:6px;margin-top:10px"><button class="btn sm ghost" id="tSkip">Skip tour</button><span class="spacer"></span>${i ? '<button class="btn sm" id="tBack">Back</button>' : ""}<button class="btn sm primary" id="tNext">${i === STEPS.length - 1 ? "Finish" : "Next"}</button></div>`;
    document.body.append(hi, box);
    const bx = Math.min(Math.max(10, r.left), innerWidth - 340), by = r.bottom + 12 + 190 > innerHeight ? Math.max(10, r.top - 200) : r.bottom + 12;
    Object.assign(box.style, { left: bx + "px", top: by + "px" });
    box.querySelector("#tNext").onclick = () => tour(i + 1);
    box.querySelector("#tSkip").onclick = () => tour(STEPS.length);
    if (i) box.querySelector("#tBack").onclick = () => tour(i - 1);
  }
  $("#helpBtn").onclick = () => {
    const b = UX.modal("❓ Help", `<div style="display:flex;gap:8px;margin-bottom:12px"><button class="btn primary" id="hTour">🧭 Take the guided tour</button><button class="btn" id="hKeys">⌨ Keyboard shortcuts</button><button class="btn" id="hGlo">📖 Glossary</button></div>
      <div class="muted" style="font-size:12.5px">TradeScope is a research tool. It never places trades. Everything runs on your PC with free public data and a local AI.</div>`);
    b.querySelector("#hTour").onclick = () => { document.getElementById("ux-modal").classList.remove("show"); tour(0); };
    b.querySelector("#hKeys").onclick = () => UX.showShortcuts();
    b.querySelector("#hGlo").onclick = () => UX.showGlossary();
  };
  $("#themeBtn").onclick = () => UX.toggleTheme();

  // ---------------------------------------------------------------- shortcuts
  const tabBtn = (t) => document.querySelector(`#tabs button[data-t="${t}"]`)?.click();
  UX.shortcut("p", "Build today's plan", () => $("#planBtn").click());
  UX.shortcut("h", "Open holdings", () => $("#holdBtn").click());
  UX.shortcut("w", "What-If Lab", () => tabBtn("whatif"));
  UX.shortcut("m", "Markets dashboard", () => tabBtn("markets"));
  UX.shortcut("b", "Top buys", () => tabBtn("long"));
  UX.shortcut("f", "Screener filters", () => { tabBtn("long"); $("#fltBtn").click(); });
  UX.shortcut("r", "Rescan the market", () => $("#refresh").click());
  UX.shortcut("t", "Tools", () => openTools());
  UX.shortcut("a", "AI assistant", () => $("#fab").click());
  UX.shortcut("n", "Alerts", () => openAlerts());
  UX.shortcut("g", "Glossary", () => UX.showGlossary());
  UX.shortcut("d", "Toggle compact density", () => UX.toggleDensity());

  // ---------------------------------------------------------------- boot (after command.js has loaded state)
  const boot = setInterval(() => {
    if (!C.state) return;
    clearInterval(boot);
    renderLists(); alertCount(); C.renderWatch();
    if (!ls("ts-tour", 0) && TS.mode() === "beginner") setTimeout(() => tour(0), 1500);
  }, 200);

  return { filter, syncFilterBar, renderOverview, currentList, listName, saveList, openTools, openAlerts, tour };
})();
