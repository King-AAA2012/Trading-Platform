// Screen 1: Command Center — markets, scanner, recommendations, budget and daily plan.
(() => {
  const $ = (s) => document.querySelector(s);
  const { api, esc, price, pct, cls, money, disp } = TS;
  let state, markets = [], riskCfg = {}, scan = null, tab = "long", sortKey = "score", sortDir = -1, selected = null, lastPlan = null;
  let wi = null, planScenario = null;

  TS.setMode(TS.mode(), false);
  document.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () => TS.setMode(b.dataset.mode)));
  document.querySelectorAll("[data-close]").forEach((b) => (b.onclick = () => b.closest(".modal-bg").classList.remove("show")));

  // ---------------- research: second-monitor window, or an in-page popup on single-monitor setups
  let researchWin = 0, overlayOpen = false, multiScreen = null;
  TS.on((m) => {
    if (m.type === "pong" && m.from !== "overlay") researchWin = Date.now();
    if (m.type === "select" && m.from === "research") highlight(m.symbol);
    if (m.type === "watch") { state.watchlist = m.watchlist; renderWatch(); }
  });
  setInterval(() => TS.send({ type: "ping" }), 3000);
  // Chrome/Edge report screen.isExtended = true when more than one monitor is connected
  const detectScreens = () => {
    multiScreen = "isExtended" in screen ? !!screen.isExtended : null;
    $("#openResearch").textContent = multiScreen === false ? "⧉ Research (popup)" : "⧉ Open Research Screen";
    $("#openResearch").title = multiScreen === false ? "Only one monitor detected: research opens as a popup on this screen" : "Opens on your second monitor when the browser allows it";
  };
  detectScreens();
  try { screen.addEventListener("change", detectScreens); } catch {}
  const winOpen = () => Date.now() - researchWin < 7000;

  async function openResearch(symbol) {
    if (multiScreen === false) return openOverlay(symbol);
    let features = "popup,width=1600,height=1000";
    try {
      if ("getScreenDetails" in window) { // Window Management API: put it on the other monitor automatically
        const sd = await window.getScreenDetails();
        const other = sd.screens.find((s) => s !== sd.currentScreen);
        if (other) features = `popup,left=${other.availLeft},top=${other.availTop},width=${other.availWidth},height=${other.availHeight}`;
        else return openOverlay(symbol);
      }
    } catch {}
    const url = "/research.html" + (symbol ? `?symbol=${encodeURIComponent(symbol)}&market=${state.lastMarket}` : "");
    const w = window.open(url, "ch-research", features);
    if (!w) { TS.toast("Pop-up window blocked, so showing research here instead."); openOverlay(symbol); }
  }
  function openOverlay(symbol) {
    symbol = symbol || selected || (scan && scan.rows[0] && scan.rows[0].symbol);
    const f = $("#resFrame");
    if (overlayOpen) TS.send({ type: "select", symbol, market: state.lastMarket, from: "command" });
    else f.src = `/research.html?embed=1&symbol=${encodeURIComponent(symbol || "")}&market=${state.lastMarket}`;
    $("#resOverlay").classList.add("show");
    overlayOpen = true;
  }
  function closeOverlay() { $("#resOverlay").classList.remove("show"); overlayOpen = false; $("#resFrame").src = "about:blank"; }
  $("#resClose").onclick = closeOverlay;
  $("#resOverlay").onclick = (e) => { if (e.target.id === "resOverlay") closeOverlay(); };
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && overlayOpen) closeOverlay(); });
  window.addEventListener("message", (e) => { if (e.origin === location.origin && e.data === "ts-close") closeOverlay(); });
  $("#openResearch").onclick = () => openResearch(selected);

  function select(symbol) {
    selected = symbol;
    highlight(symbol);
    TS.send({ type: "select", symbol, market: state.lastMarket, from: "command" });
  }
  // double-click: follow on the research window if it is open, otherwise open research (2nd screen or popup)
  function openDetail(symbol) {
    select(symbol);
    if (winOpen() && !overlayOpen) return;
    if (multiScreen === true) openResearch(symbol);
    else openOverlay(symbol);
  }
  function bindRows(root, sel = "[data-s]") {
    root.querySelectorAll(sel).forEach((el) => {
      el.onclick = (e) => { if (!e.target.closest("button,input,select,a")) select(el.dataset.s); };
      el.ondblclick = (e) => { if (!e.target.closest("button,input,select,a")) openDetail(el.dataset.s); };
    });
  }
  function highlight(symbol) {
    selected = symbol;
    document.querySelectorAll("tr.row").forEach((r) => r.classList.toggle("sel", r.dataset.s === symbol));
  }

  // bridge for command-extra.js
  window.CMD = { get state() { return state; }, get scan() { return scan; }, get markets() { return markets; }, get plan() { return lastPlan; },
    select: (s) => select(s), openDetail: (s) => openDetail(s), loadScan: (f) => loadScan(f), renderRows: () => renderRows(), bindRows: (r, s) => bindRows(r, s),
    renderWatch: () => renderWatch(), refreshHoldings: () => refreshHoldings(), saveProfile: (p, c) => saveProfile(p, c), visibleRows: [] };

  // ---------------- init
  async function init() {
    [state, { markets, risk: riskCfg }, presets] = await Promise.all([api("/api/state"), api("/api/markets"), api("/api/presets")]);
    TS.remember((state.holdings || []).map((h) => ({ symbol: h.symbol, type: "Holding" })));
    TS.remember((state.watchlist || []).map((symbol) => ({ symbol, type: "Watchlist" })));
    state.planMarkets ||= [state.lastMarket || "us"];
    renderMarkets();
    mkLabel();
    fillProfile();
    renderWatch();
    loadScan();
    loadMacro();
    setInterval(loadMacro, 20000);          // near-live ticker strip
    setInterval(renderWatch, 20000);        // near-live watchlist
    api("/api/me").then((me) => {
      const a = me.access;
      $("#acctTxt").textContent = a.state === "trial" ? `Trial · ${a.trialDaysLeft}d left` : a.state === "paid" ? "Pro" : a.state === "comp" ? "Account" : "Subscribe";
      if (a.state === "trial" && a.trialDaysLeft <= 5) $("#acctBtn").classList.add("primary");
    }).catch(() => {});
    TS.aiStatus($("#aist"));
    TS.bindSearch($("#q"), $("#qres"), (s) => openDetail(s));
  }

  function renderMarkets() {
    const opt = (m) => `<option value="${m.id}">${m.flag} ${esc(m.name)}</option>`;
    const groups = [...new Set(markets.map((m) => m.group))];
    $("#market").innerHTML = groups.map((g) => `<optgroup label="${esc(g)}">${markets.filter((m) => m.group === g).map(opt).join("")}</optgroup>`).join("");
    $("#market").value = markets.some((m) => m.id === state.lastMarket) ? state.lastMarket : "us";
    state.lastMarket = $("#market").value;
    state.planMarkets = (state.planMarkets || []).filter((id) => markets.some((m) => m.id === id));
    if (!state.planMarkets.length) state.planMarkets = [state.lastMarket];
  }
  $("#market").onchange = async (e) => {
    state.lastMarket = e.target.value;
    api("/api/state", { body: { lastMarket: state.lastMarket } });
    loadScan();
  };

  // ---------------- macro strip
  async function loadMacro() {
    const q = await api("/api/macro").catch(() => []);
    if (!q.length) return;
    const html = q.map((x) => `<span class="tk" data-s="${esc(x.symbol)}"><b>${esc(x.label)}</b><span class="num">${price(x.price)}</span><span class="num ${cls(x.changePct)}">${pct(x.changePct)}</span></span>`).join("");
    $("#strip").innerHTML = html + html;
    bindRows($("#strip"), ".tk");
  }

  // ---------------- scan
  async function loadScan(force = false) {
    const mk = state.lastMarket;
    $("#rows").innerHTML = `<tr><td colspan="13" class="empty"><span class="spin"></span> Running the algorithm on ${esc(markets.find((m) => m.id === mk)?.name || mk)}…</td></tr>`;
    try {
      scan = await api(`/api/scan/${mk}${force ? "?force=true" : ""}`);
    } catch (e) {
      $("#rows").innerHTML = `<tr><td colspan="13" class="empty">Scan failed: ${esc(e.message)}</td></tr>`;
      return;
    }
    if (mk !== state.lastMarket) return;
    TS.remember(scan.rows.map((r) => ({ symbol: r.symbol, name: r.name, exchange: r.marketName, type: r.sector || "Stock" })));
    $("#scanInfo").textContent = `${scan.rows.length} instruments · updated ${new Date().toLocaleTimeString()}`;
    renderPulse();
    renderHeat();
    renderRows();
    if (!selected && scan.rows[0]) { selected = scan.rows[0].symbol; }
  }
  $("#refresh").onclick = () => loadScan(true);

  function renderPulse() {
    const b = scan.breadth, n = scan.rows.length || 1;
    $("#pulseName").textContent = scan.name;
    $("#avgScore").innerHTML = `<span class="${cls(b.avgScore)}">${b.avgScore > 0 ? "+" : ""}${b.avgScore.toFixed(0)}</span>`;
    $("#nBull").textContent = b.bull; $("#nBear").textContent = b.bear;
    $("#gauge").innerHTML = `<i style="width:${(b.bull / n) * 100}%;background:var(--up)"></i><i style="width:${(b.neutral / n) * 100}%;background:#39425a"></i><i style="width:${(b.bear / n) * 100}%;background:var(--down)"></i>`;
    $("#advdec").innerHTML = `Today: <span class="up">${b.advancers} up</span> · <span class="down">${b.decliners} down</span> · regime: <b>${b.avgScore > 15 ? "Risk-on 🟢" : b.avgScore < -15 ? "Risk-off 🔴" : "Mixed 🟡"}</b>`;
  }

  function heatColor(p) {
    const a = Math.min(Math.abs(p) / 4, 1);
    return p >= 0 ? `rgba(31,210,134,${0.12 + a * 0.6})` : `rgba(255,84,112,${0.12 + a * 0.6})`;
  }
  function renderHeat() {
    const by = {};
    scan.rows.forEach((r) => (by[r.sector || "Other"] ||= []).push(r));
    const secs = Object.entries(by).sort((a, b) => b[1].length - a[1].length);
    $("#heat").innerHTML = secs.map(([s, rs]) => {
      const avg = rs.reduce((x, r) => x + r.changePct, 0) / rs.length;
      return `<div class="sec"><h4>${esc(s)} <span class="${cls(avg)}">${pct(avg)}</span></h4><div class="tiles">${rs.sort((a, b) => b.changePct - a.changePct).map((r) =>
        `<div class="tile" data-s="${esc(r.symbol)}" style="background:${heatColor(r.changePct)}" title="${esc(r.name)} · score ${r.score}"><b>${esc(disp(r.symbol).replace(/\.(NS|L|T|HK|TO|AX|PA|DE|AS|MI|MC|SW|CO)$/, ""))}</b>${pct(r.changePct, 1)}</div>`).join("")}</div></div>`;
    }).join("");
    bindRows($("#heat"), ".tile");
  }

  document.querySelectorAll("#tabs button").forEach((b) => (b.onclick = () => {
    tab = b.dataset.t;
    document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
    const isWi = tab === "whatif", isMk = tab === "markets";
    $("#whatif").style.display = isWi ? "" : "none";
    $("#overview").style.display = isMk ? "" : "none";
    document.querySelectorAll(".scan-only").forEach((el) => (el.style.display = isWi || isMk ? "none" : ""));
    if (!isWi && !isMk && window.CX) CX.syncFilterBar();
    ["#filter", "#refresh", "#scanInfo"].forEach((s) => ($(s).style.visibility = isWi || isMk ? "hidden" : ""));
    if (isWi) { renderWhatIf(); return; }
    if (isMk) { CX.renderOverview(); return; }
    sortKey = "score"; sortDir = tab === "short" ? 1 : -1;
    renderRows();
  }));
  document.querySelectorAll("th[data-k]").forEach((th) => (th.onclick = () => {
    const k = th.dataset.k;
    if (k === "spark") return;
    sortDir = sortKey === k ? -sortDir : -1; sortKey = k; renderRows();
  }));
  $("#filter").oninput = () => renderRows();

  function renderRows() {
    if (!scan) return;
    const f = $("#filter").value.toLowerCase();
    const cf = window.CX && CX.filter;
    let rows = scan.rows.filter((r) => (tab === "all" || (tab === "long" ? r.score > 0 : r.score < 0)) && (!f || (r.symbol + r.name + r.setup + (r.sector || "")).toLowerCase().includes(f)) && (!cf || cf(r)));
    window.CMD.visibleRows = rows;
    const val = (r) => (sortKey === "sizing" ? r.sizing.cost : r[sortKey]);
    rows.sort((a, b) => { const x = val(a), y = val(b); return (typeof x === "string" ? x.localeCompare(y) : (x ?? -1e9) - (y ?? -1e9)) * sortDir; });
    const ccy = state.profile.currency;
    $("#rows").innerHTML = rows.map((r) => `<tr class="row ${r.symbol === selected ? "sel" : ""}" data-s="${esc(r.symbol)}">
      <td><div class="sym">${esc(disp(r.symbol))}<small>${esc(r.name)}</small></div></td>
      <td class="r num">${price(r.price)}<div class="dim" style="font-size:10px">${esc(r.currency)}</div></td>
      <td class="r num ${cls(r.changePct)}">${pct(r.changePct)}</td>
      <td>${TS.spark(r.spark)}</td>
      <td>${TS.scoreBar(r.score)} <span class="num ${cls(r.score)}" style="margin-left:4px">${r.score > 0 ? "+" : ""}${r.score.toFixed(0)}</span></td>
      <td><span class="sig ${TS.sigClass(r.signal)}">${r.signal}</span></td>
      <td class="muted" style="font-size:12px">${esc(r.setup)}</td>
      <td>${TS.confRing(r.confidence)}</td>
      <td class="r num" style="font-size:12px" title="Typical daily move: ${price(r.atr)} ${esc(r.currency)}"><span class="${r.atrPct > 0.04 ? "warn" : ""}">${(r.atrPct * 100).toFixed(1)}%</span><div class="dim" style="font-size:10px">${price(r.atr)}</div></td>
      <td class="r num" style="font-size:12px">${r.sizing.qty ? `<b>${r.bias === "short" ? "Short " : "Buy "}${r.sizing.qty}</b><div class="dim">≈ ${money(r.sizing.cost, ccy)}</div>` : '<span class="dim">–</span>'}</td>
      <td class="r num p-only ${cls(r.ret3m)}">${r.ret3m == null ? "–" : pct(r.ret3m * 100, 1)}</td>
      <td class="r num p-only">${r.rsi.toFixed(0)}</td>
      <td class="r num p-only">${r.hitRate == null ? "–" : (r.hitRate * 100).toFixed(0) + "%"}</td></tr>`).join("") || `<tr><td colspan="13" class="empty">Nothing matches.</td></tr>`;
    bindRows($("#rows"), "tr.row");
  }

  // ---------------- watchlist
  async function renderWatch() {
    const wl = (window.CX && CX.currentList()) || state.watchlist || [];
    if (!wl.length) { $("#wl").innerHTML = `<tr><td class="empty">Empty. Select a symbol and press "＋ selected".</td></tr>`; return; }
    const q = await api("/api/quotes?symbols=" + encodeURIComponent(wl.join(","))).catch(() => []);
    $("#wl").innerHTML = q.map((x) => `<tr class="row" data-s="${esc(x.symbol)}"><td><div class="sym">${esc(disp(x.symbol))}<small>${esc(x.name)}</small></div></td>
      <td class="r num">${price(x.price)}</td><td class="r num ${cls(x.changePct)}">${pct(x.changePct)}</td>
      <td style="width:22px"><button class="btn sm ghost" data-rm="${esc(x.symbol)}" title="Remove">✕</button></td></tr>`).join("");
    bindRows($("#wl"), "tr.row");
    $("#wl").querySelectorAll("[data-rm]").forEach((b) => (b.onclick = () => saveWatch(wl.filter((s) => s !== b.dataset.rm))));
  }
  async function saveWatch(list) {
    if (window.CX && CX.listName() !== "Main") { await CX.saveList(list); renderWatch(); return; }
    state.watchlist = list; await api("/api/state", { body: { watchlist: list } }); renderWatch(); TS.send({ type: "watch", watchlist: list });
  }
  $("#wlAdd").onclick = () => { const cur = (window.CX && CX.currentList()) || state.watchlist; if (selected && !cur.includes(selected)) saveWatch([...cur, selected]); };

  // ---------------- strategy settings (risk as %, plus the optimiser's parameters)
  let presets = { presets: {}, defaults: {}, sectors: [] };
  const numKeys = new Set(["budget", "riskPerTrade", "maxDrawdown", "dailyLimit", "targetVol", "maxPosition", "maxSector", "maxPositions", "cashReserve",
    "minConviction", "stopAtr", "rebalanceBand", "minMarketCap", "cash"]);
  const effective = () => ({ ...presets.defaults, ...(presets.presets[state.profile.risk] || {}), ...Object.fromEntries(Object.entries(state.profile).filter(([, v]) => v !== null && v !== "")) });
  function fillProfile() {
    const p = effective();
    document.querySelectorAll("[data-k]").forEach((el) => {
      const v = p[el.dataset.k];
      if (el.type === "checkbox") el.checked = !!v; else el.value = v ?? "";
    });
    document.querySelectorAll("[data-r]").forEach((r) => (r.value = p[r.dataset.r] ?? r.value));
    document.querySelectorAll("#presets button").forEach((b) => b.classList.toggle("on", b.dataset.p === (presets.presets[state.profile.risk] ? state.profile.risk : "custom")));
    const score = state.profile.riskScore ?? { conservative: 25, balanced: 50, aggressive: 75 }[state.profile.risk] ?? 50;
    $("#riskDial").value = score; $("#riskNum").textContent = Math.round(score); $("#riskLbl").textContent = riskLabel(score);
    const ex = new Set(p.excludeSectors || []);
    $("#exSectors").innerHTML = presets.sectors.map((s) => `<span class="chip ${ex.has(s) ? "on" : ""}" data-sec="${esc(s)}" style="${ex.has(s) ? "border-color:var(--down);color:var(--down);text-decoration:line-through" : ""}">${esc(s)}</span>`).join("");
    $("#exSectors").querySelectorAll("[data-sec]").forEach((c) => (c.onclick = () => {
      const cur = new Set(effective().excludeSectors || []);
      cur.has(c.dataset.sec) ? cur.delete(c.dataset.sec) : cur.add(c.dataset.sec);
      saveProfile({ excludeSectors: [...cur] }, true);
    }));
    $("#nHold").textContent = state.holdings.length;
    explainRisk();
  }
  function explainRisk() {
    const p = effective(), b = +p.budget || 0, c = p.currency;
    $("#riskExplain").innerHTML = `Each idea risks at most <b>${money(b * p.riskPerTrade / 100, c)}</b> (${p.riskPerTrade}% of budget) if its stop is hit. The portfolio aims for ≤ <b>${p.targetVol}%</b> yearly swings and is scaled down if it could fall more than <b>${p.maxDrawdown}%</b>. Up to ${p.maxPositions} positions, ≤ ${p.maxPosition}% each, ≤ ${p.maxSector}% per sector, ${p.cashReserve}% kept in cash, ${p.horizon}-term horizon.`;
  }
  let saveH;
  function saveProfile(patch, custom) {
    state.profile = { ...state.profile, ...patch };
    if (custom && patch.risk === undefined) {   // hand-edited parameters make the profile "custom", keeping every current value
      const eff = effective();
      Object.keys(presets.defaults).forEach((k) => { if (state.profile[k] === undefined || state.profile[k] === null) state.profile[k] = eff[k]; });
      state.profile.risk = "custom";
    }
    fillProfile();
    clearTimeout(saveH);
    saveH = setTimeout(async () => { await api("/api/state", { body: { profile: state.profile } }); TS.send({ type: "profile" }); loadScan(); }, 450);
  }
  document.querySelectorAll("#presets button").forEach((b) => (b.onclick = () => {
    const pr = presets.presets[b.dataset.p];
    if (!pr) return saveProfile({ risk: "custom" }, true);
    saveProfile({ ...pr, risk: b.dataset.p, riskScore: { conservative: 25, balanced: 50, aggressive: 75 }[b.dataset.p] });
  }));
  // ---- one 0-100 risk dial drives every parameter (interpolated between anchor profiles)
  const riskLabel = (v) => (v < 15 ? "Very safe" : v < 35 ? "Safe" : v < 55 ? "Moderate" : v < 75 ? "Growth" : v < 90 ? "Aggressive" : "Very aggressive");
  function riskParams(v) {
    const P = presets.presets;
    const anchors = [
      [0, { riskPerTrade: 0.25, targetVol: 6, maxDrawdown: 8, maxPosition: 8, maxSector: 20, maxPositions: 20, minPositions: 10, cashReserve: 30, minConviction: 35, stopAtr: 3, rebalanceBand: 2, objective: "minvol", horizon: "long", style: "defensive" }],
      [25, P.conservative], [50, P.balanced], [75, P.aggressive],
      [100, { riskPerTrade: 3.5, targetVol: 40, maxDrawdown: 50, maxPosition: 35, maxSector: 60, maxPositions: 5, minPositions: 3, cashReserve: 0, minConviction: 15, stopAtr: 1.6, rebalanceBand: 5, objective: "return", horizon: "short", style: "momentum" }],
    ];
    let i = 0;
    while (i < anchors.length - 2 && v > anchors[i + 1][0]) i++;
    const [v0, a] = anchors[i], [v1, b] = anchors[i + 1], f = (v - v0) / (v1 - v0);
    const out = {};
    for (const k of Object.keys(b)) {
      if (typeof b[k] === "number") {
        const x = a[k] + (b[k] - a[k]) * f;
        out[k] = ["maxPositions", "minPositions", "maxSector", "maxPosition", "maxDrawdown", "targetVol", "cashReserve", "minConviction"].includes(k) ? Math.round(x) : +x.toFixed(2);
      } else out[k] = f < 0.5 ? a[k] : b[k];
    }
    return out;
  }
  $("#riskDial").addEventListener("input", () => { const v = +$("#riskDial").value; $("#riskNum").textContent = v; $("#riskLbl").textContent = riskLabel(v); });
  $("#riskDial").addEventListener("change", () => { const v = +$("#riskDial").value; saveProfile({ ...riskParams(v), riskScore: v, risk: "score" }); });
  document.querySelectorAll("[data-k]").forEach((el) => el.addEventListener("change", () => {
    const k = el.dataset.k;
    let v = el.type === "checkbox" ? el.checked : el.value;
    if (numKeys.has(k)) v = v === "" ? null : +v;
    const r = document.querySelector(`[data-r="${k}"]`);
    if (r && v != null) r.value = v;
    saveProfile({ [k]: v, ...(["budget", "currency", "cash", "dailyLimit", "allowShorts", "fractional"].includes(k) ? {} : { riskScore: null }) }, !["budget", "currency", "cash", "dailyLimit", "allowShorts", "fractional"].includes(k));
  }));
  document.querySelectorAll("[data-r]").forEach((r) => r.addEventListener("input", () => {
    const n = document.querySelector(`[data-k="${r.dataset.r}"]`); n.value = r.value;
  }));
  document.querySelectorAll("[data-r]").forEach((r) => r.addEventListener("change", () => saveProfile({ [r.dataset.r]: +r.value }, true)));

  // ---------------- holdings
  let hsum = null, haPick = null, haPrice = null;
  async function refreshHoldings() {
    $("#hRows").innerHTML = `<tr><td colspan="11" class="empty"><span class="spin"></span> Loading live prices…</td></tr>`;
    hsum = await api("/api/holdings/summary").catch(() => null);
    renderHoldings();
  }
  function renderHoldings() {
    const c = state.profile.currency;
    if (!hsum) { $("#hRows").innerHTML = `<tr><td colspan="11" class="empty">Couldn't load holdings.</td></tr>`; return; }
    $("#hsVal").textContent = money(hsum.total, c);
    $("#hsPnl").innerHTML = `<span class="${cls(hsum.pnl)}">${hsum.pnl >= 0 ? "+" : ""}${money(hsum.pnl, "")}</span> <span style="font-size:13px" class="${cls(hsum.pnl)}">${hsum.cost ? pct((hsum.pnl / Math.abs(hsum.cost)) * 100, 1) : ""}</span>`;
    $("#hsDay").innerHTML = `<span class="${cls(hsum.day)}">${hsum.day >= 0 ? "+" : ""}${money(hsum.day, "")}</span>`;
    $("#hsN").textContent = hsum.rows.length;
    $("#hRows").innerHTML = hsum.rows.map((h, i) => `<tr class="row" data-s="${esc(h.symbol)}">
      <td><div class="sym">${esc(disp(h.symbol))}${h.side === "short" ? ' <span class="pill" style="padding:0 6px;font-size:10px">SHORT</span>' : ""}<small>${esc(h.name)}${h.sector ? " · " + esc(h.sector) : ""}</small></div></td>
      <td class="r"><input class="num" type="number" step="any" min="0" data-i="${i}" data-f="qty" value="${h.qty}"></td>
      <td class="r"><input class="num" type="number" step="any" min="0" data-i="${i}" data-f="avgCost" value="${h.avgCost ?? ""}" placeholder="–"></td>
      <td class="r num">${price(h.price)}<div class="dim" style="font-size:10px">${esc(h.quoteCurrency || "")}</div></td>
      <td class="r num">${money(h.value, c)}</td>
      <td class="r num ${cls(h.pnl)}">${h.pnl >= 0 ? "+" : ""}${money(h.pnl, "")}<div style="font-size:10.5px">${h.pnlPct != null ? pct(h.pnlPct * 100, 1) : ""}</div></td>
      <td class="r num ${cls(h.changePct)}">${pct(h.changePct)}</td>
      <td><span class="wbar"><i style="width:${Math.min(100, Math.abs(h.weight) * 100)}%"></i></span><span class="num dim">${(h.weight * 100).toFixed(1)}%</span></td>
      <td>${h.signal ? `<span class="sig ${TS.sigClass(h.signal)}">${h.signal}</span>` : '<span class="dim">–</span>'}</td>
      <td class="r num down">${h.stop ? price(h.stop) : "–"}</td>
      <td style="white-space:nowrap"><button class="btn sm ghost" data-open="${esc(h.symbol)}" title="Research">🔍</button><button class="btn sm ghost" data-del="${i}" title="Remove">🗑</button></td></tr>`).join("")
      || `<tr><td colspan="11" class="empty">No holdings yet. Add one above, or press <b>✓ Add</b> on any plan action.</td></tr>`;
    bindRows($("#hRows"), "tr.row");
    $("#hRows").querySelectorAll("[data-open]").forEach((b) => (b.onclick = () => openDetail(b.dataset.open)));
    $("#hRows").querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => {
      const h = state.holdings[+b.dataset.del];
      if (h && confirm(`Remove ${disp(h.symbol)} from your holdings?`)) saveHoldings(state.holdings.filter((_, j) => j !== +b.dataset.del));
    }));
    $("#hRows").querySelectorAll("input[data-f]").forEach((inp) => (inp.onchange = () => {
      const hs = state.holdings.map((x) => ({ ...x }));
      const v = inp.value === "" ? null : +inp.value;
      hs[+inp.dataset.i][inp.dataset.f] = v;
      saveHoldings(hs.filter((x) => x.qty > 0));
    }));
  }
  async function saveHoldings(hs, quiet) {
    state.holdings = hs;
    $("#nHold").textContent = hs.length;
    await api("/api/state", { body: { holdings: hs } });
    if (!quiet && $("#holdModal").classList.contains("show")) refreshHoldings();
  }
  $("#holdBtn").onclick = () => { $("#holdModal").classList.add("show"); refreshHoldings(); setTimeout(() => $("#haSym").focus(), 50); };
  TS.bindSearch($("#haSym"), $("#haRes"), async (sym) => {
    haPick = sym; haPrice = null;
    $("#haNow").textContent = "…";
    const q = (await api("/api/quotes?symbols=" + encodeURIComponent(sym)).catch(() => []))[0];
    if (q) { haPrice = q.price; $("#haNow").textContent = `now ${price(q.price)} ${q.currency || ""}`; $("#haCost").placeholder = price(q.price); }
    else $("#haNow").textContent = "";
    $("#haQty").focus();
  }, { keepValue: true, global: false });
  $("#haSym").addEventListener("input", () => { haPick = null; });
  function addHolding(symbol, qty, cost, side = "long") {
    const hs = state.holdings.map((x) => ({ ...x }));
    const ex = hs.find((x) => x.symbol === symbol && (x.side || "long") === side);
    if (ex) {
      const tq = ex.qty + qty;
      ex.avgCost = ex.avgCost && cost ? +(((ex.avgCost * ex.qty) + cost * qty) / tq).toFixed(6) : ex.avgCost || cost;
      ex.qty = +tq.toFixed(6);
    } else hs.push({ symbol, qty, avgCost: cost, side, added: Math.floor(Date.now() / 1000) });
    state.journal = [...(state.journal || []), { t: Math.floor(Date.now() / 1000), symbol, action: side === "short" ? "SHORT" : "BUY", qty, price: cost, value: cost ? cost * qty : null, realized: null, manual: true }];
    api("/api/state", { body: { journal: state.journal } });
    return saveHoldings(hs);
  }
  $("#haAdd").onclick = async () => {
    const symbol = haPick || $("#haSym").value.trim().toUpperCase();
    const qty = +$("#haQty").value;
    if (!symbol) return TS.toast("Pick a stock first");
    if (!(qty > 0)) { $("#haQty").focus(); return TS.toast("Enter a quantity"); }
    let cost = $("#haCost").value === "" ? haPrice : +$("#haCost").value;
    if (cost == null) cost = (await api("/api/quotes?symbols=" + encodeURIComponent(symbol)).catch(() => []))[0]?.price ?? null;
    await addHolding(symbol, qty, cost, $("#haSide").value);
    TS.toast(`Added ${qty} ${disp(symbol)}`);
    ["#haSym", "#haQty", "#haCost"].forEach((s) => ($(s).value = ""));
    $("#haNow").textContent = ""; haPick = null; haPrice = null;
    $("#haSym").focus();
  };
  $("#haQty").addEventListener("keydown", (e) => e.key === "Enter" && $("#haAdd").click());
  $("#haCost").addEventListener("keydown", (e) => e.key === "Enter" && $("#haAdd").click());
  $("#hImport").onclick = async () => {
    const t = $("#hCsv");
    if (t.style.display === "none") { t.style.display = ""; t.focus(); $("#hImport").textContent = "✓ Import these rows"; return; }
    const rows = t.value.split(/\r?\n/).map((l) => l.split(/[,;\t]/).map((x) => x.trim())).filter((r) => r[0] && !/^symbol$/i.test(r[0]) && +r[1] > 0);
    for (const r of rows) await addHolding(r[0].toUpperCase(), +r[1], r[2] ? +r[2] : null, /short/i.test(r[3] || "") ? "short" : "long");
    t.value = ""; t.style.display = "none"; $("#hImport").textContent = "⬆ Import CSV";
    TS.toast(`Imported ${rows.length} holding(s)`);
  };
  $("#hExport").onclick = () => {
    const csv = "symbol,qty,avg_cost,side\n" + state.holdings.map((h) => [h.symbol, h.qty, h.avgCost ?? "", h.side || "long"].join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "casuallyhedge-holdings.csv";
    a.click();
  };

  // ---------------- plan
  const COLORS = ["#5b8cff", "#1fd286", "#9b7bff", "#f5b942", "#ff5470", "#38bdf8", "#f472b6", "#a3e635", "#fb923c", "#2dd4bf", "#c084fc", "#facc15"];
  function donut(alloc) {
    const tot = alloc.reduce((s, a) => s + a.value, 0) || 1;
    let acc = 0;
    const segs = alloc.map((a, i) => {
      const col = a.symbol === "CASH" ? "#39425a" : COLORS[i % COLORS.length];
      const s = acc / tot * 360; acc += a.value; const e = acc / tot * 360;
      return { ...a, col, s, e };
    });
    const grad = segs.map((s) => `${s.col} ${s.s}deg ${s.e}deg`).join(",");
    return `<div id="donut"><div style="width:120px;height:120px;border-radius:50%;background:conic-gradient(${grad});position:relative;flex:none">
      <div style="position:absolute;inset:22px;border-radius:50%;background:var(--panel);display:grid;place-items:center;text-align:center"><div><div class="muted" style="font-size:10px">EQUITY</div><b class="num">${money(tot, "")}</b></div></div></div>
      <div class="lg">${segs.map((s) => `<div><span><span class="sw" style="background:${s.col}"></span>${esc(disp(s.symbol))}</span><span class="num muted">${((s.value / tot) * 100).toFixed(1)}%</span></div>`).join("")}</div></div>`;
  }
  $("#planBtn").onclick = async () => {
    $("#mkpop").classList.remove("show");
    if (!(state.planMarkets || []).length) return TS.toast("Pick at least one market with 🌍 first");
    const t0 = Date.now();
    $("#plan").innerHTML = `<div class="empty"><span class="spin"></span> <b>The investment committee is in session…</b><div class="dim" id="planStage" style="margin-top:6px">Screening ${state.planMarkets.length} market(s)</div></div>`;
    const stages = ["Screening every stock in your markets", "Pulling fundamentals, analyst data and a year of prices", "Ten agents are debating each candidate", "Devil's advocate is attacking the majority view", "Estimating how the stocks move together", "Optimising weights under your risk limits", "Stress-testing and running 2,000 simulations"];
    const tick = setInterval(() => { const el = $("#planStage"); if (el) el.textContent = `${stages[Math.min(stages.length - 1, Math.floor((Date.now() - t0) / 2500))]}… ${Math.round((Date.now() - t0) / 1000)}s`; }, 500);
    try { lastPlan = await api("/api/plan", { body: { markets: state.planMarkets, scenario: planScenario } }); }
    catch (e) { clearInterval(tick); $("#plan").innerHTML = `<div class="empty">Plan failed: ${esc(e.message)}</div>`; return; }
    clearInterval(tick);
    renderPlan();
    TS.send({ type: "plan", plan: lastPlan });
  };
  const APPLY = { BUY: "✓ Add to holdings", ADD: "✓ Add to holdings", SHORT: "✓ Record short", SELL: "✓ Record sale", TRIM: "✓ Record trim", COVER: "✓ Record cover" };
  function renderPlan() {
    const p = lastPlan, c = p.currency, a = p.analytics || {};
    const buys = p.actions.filter((x) => ["BUY", "ADD", "SHORT"].includes(x.action)).reduce((s, x) => s + x.value, 0);
    const actionable = p.actions.filter((x) => APPLY[x.action] && x.qty > 0);
    $("#plan").innerHTML = `
      <div class="kv" style="grid-template-columns:repeat(3,1fr);margin-bottom:8px">
        <div><label>Deploy today</label><b>${money(buys, c)}</b></div><div><label>Cash after</label><b>${money(p.cashEnd, c)}</b></div>
        <div><label>Risk at stops</label><b class="down">${money(p.totalRisk, c)}</b></div>
        ${a.empty ? "" : `<div><label>Expected / yr</label><b class="${cls(a.expReturn)}">${pct(a.expReturn * 100, 1)}</b></div><div><label>Volatility</label><b>${(a.vol * 100).toFixed(1)}%</b></div><div><label>Chance of loss (1y)</label><b>${(a.mc.probLoss * 100).toFixed(0)}%</b></div>`}</div>
      ${donut(p.allocation)}
      ${p.scenario ? `<div class="hint" style="margin:8px 0">🔮 Built for scenario: <b>${esc(p.scenario)}</b> <button class="btn sm ghost" id="clearScen">✕ back to normal</button></div>` : ""}
      ${p.byMarket.length > 1 ? `<div class="muted" style="font-size:11.5px;margin-top:8px">By market: ${p.byMarket.map((m) => `<b>${esc(m.market)}</b> ${((m.value / p.equity) * 100).toFixed(0)}%`).join(" · ")}</div>` : ""}
      <div style="display:flex;gap:6px;margin:10px 0 8px;flex-wrap:wrap">
        ${actionable.length ? `<button class="btn sm primary" id="applyAll">✅ Add all ${actionable.length} to holdings</button>` : ""}
        <button class="btn sm" id="anaBtn">📊 Committee & risk</button><button class="btn sm" id="aiPlan">✨ AI explain</button><button class="btn sm" id="planReport">📄 Report</button></div>
      <div id="aiPlanOut" class="md" style="display:none;margin-bottom:10px;padding:10px;background:var(--panel2);border-radius:8px"></div>
      ${p.actions.map((x, i) => `<div class="act" data-s="${esc(x.symbol)}" data-i="${i}"><span class="tag ${x.action}">${x.action}</span>
        <div><b>${esc(disp(x.symbol))}</b> <span class="muted">${esc(x.name || "")}</span>${x.market && p.markets.length > 1 ? ` <span class="pill" style="padding:0 6px;font-size:10px">${esc(x.market)}</span>` : ""}
          <div class="why">${esc(x.reason)}</div>
          <div class="tagline dim num" style="font-size:11px">${x.conviction != null ? `<span>conviction ${(x.conviction * 100).toFixed(0)}%</span>` : ""}${x.targetWeight ? `<span>target ${(x.targetWeight * 100).toFixed(1)}%</span>` : ""}${x.stop ? `<span class="down">stop ${price(x.stop)}</span>` : ""}${x.target ? `<span class="up">target ${price(x.target)}</span>` : ""}${x.partial ? `<span class="warn">partial (daily limit)</span>` : ""}</div>
          ${APPLY[x.action] && x.qty > 0 ? `<button class="btn sm ok" data-apply="${i}">${APPLY[x.action]}</button>` : ""}</div>
        <div class="r num" style="text-align:right"><b>${x.qty ?? ""}</b><div class="dim" style="font-size:11px">${money(x.value, c)}</div><div class="dim" style="font-size:10.5px">@ ${price(x.price)}</div></div></div>`).join("") || '<div class="empty">No actions today. Sit tight; not trading is also a position.</div>'}
      ${(p.queued || []).length ? `<div class="muted" style="margin:10px 0 4px;font-size:11px">QUEUED FOR NEXT SESSIONS (daily limit / cash)</div>` + p.queued.map((q) => `<span class="pill" style="margin:2px">${esc(q.action)} ${q.qty} ${esc(disp(q.symbol))}</span>`).join("") : ""}
      <p class="disclaimer">Research tool only. CasuallyHedge never places trades. "Add to holdings" only records the position here for tracking.</p>`;
    bindRows($("#plan"), ".act");
    $("#plan").querySelectorAll("[data-apply]").forEach((b) => (b.onclick = () => applyActions([+b.dataset.apply])));
    if ($("#applyAll")) $("#applyAll").onclick = () => {
      if (confirm(`Record all ${actionable.length} actions in your holdings? (Tracking only, nothing is traded.)`)) applyActions(p.actions.map((x, i) => (APPLY[x.action] && x.qty > 0 ? i : -1)).filter((i) => i >= 0));
    };
    if ($("#clearScen")) $("#clearScen").onclick = () => { planScenario = null; $("#planBtn").click(); };
    $("#anaBtn").onclick = openAnalysis;
    $("#aiPlan").onclick = async () => {
      const out = $("#aiPlanOut"); out.style.display = "block"; out.classList.add("cursor"); out.innerHTML = '<span class="muted">Thinking…</span>';
      try { await TS.stream("/api/ai/plan", { plan: slimPlan() }, (t) => (out.innerHTML = TS.md(t))); } catch (e) { out.innerHTML = `<span class="down">AI failed: ${esc(e.message)}</span>`; }
      out.classList.remove("cursor");
    };
    $("#planReport").onclick = () => { try { localStorage.setItem("ts-plan", JSON.stringify(lastPlan)); } catch {} window.open("/report.html?plan=1", "_blank"); };
  }
  const slimPlan = () => ({ ...lastPlan, debates: undefined, analytics: { ...lastPlan.analytics, curve: undefined, mc: lastPlan.analytics.mc ? { ...lastPlan.analytics.mc, fan: undefined } : undefined } });
  async function applyActions(idx) {
    const acts = idx.map((i) => lastPlan.actions[i]).filter((x) => x && !x._done);
    if (!acts.length) return;
    // record in the user's currency-neutral terms: qty at the instrument's own price
    const res = await api("/api/holdings/apply", { body: { actions: acts.map((x) => ({ symbol: x.symbol, action: x.action, qty: x.qty, price: x.price, value: x.value })) } });
    state.holdings = res.holdings;
    $("#nHold").textContent = state.holdings.length;
    acts.forEach((x) => (x._done = true));
    idx.forEach((i) => {
      const card = $(`#plan .act[data-i="${i}"]`);
      if (card) { card.classList.add("done"); const b = card.querySelector("[data-apply]"); if (b) { b.textContent = "✓ Recorded"; b.disabled = true; } }
    });
    TS.toast(`Recorded: ${res.applied.join(", ")}`);
  }

  // ---------------- committee & risk analysis
  function fanChart(fan, equity) {
    const W = 560, H = 190, pad = 30;
    const keys = ["5", "25", "50", "75", "95"];
    const n = fan["50"].length;
    const all = keys.flatMap((k) => fan[k]);
    const mn = Math.min(...all, 1), mx = Math.max(...all, 1);
    const x = (i) => pad + (i / (n - 1)) * (W - pad - 8), y = (v) => H - 20 - ((v - mn) / (mx - mn || 1)) * (H - 34);
    const line = (k) => fan[k].map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const band = (a, b) => line(a) + fan[b].map((v, i) => `L${x(n - 1 - i).toFixed(1)},${y(fan[b][n - 1 - i]).toFixed(1)}`).join("") + "Z";
    const lab = (v) => `<text x="4" y="${y(v) + 4}" font-size="10" fill="var(--muted)">${money(v * equity, "")}</text>`;
    return `<svg viewBox="0 0 ${W} ${H}" width="100%"><path d="${band("95", "5")}" fill="rgba(91,140,255,.12)"/><path d="${band("75", "25")}" fill="rgba(91,140,255,.22)"/>
      <line x1="${pad}" x2="${W - 8}" y1="${y(1)}" y2="${y(1)}" stroke="var(--line2)" stroke-dasharray="4 4"/><path d="${line("50")}" fill="none" stroke="#5b8cff" stroke-width="2"/>
      ${lab(fan["95"][n - 1])}${lab(fan["50"][n - 1])}${lab(fan["5"][n - 1])}<text x="${W - 8}" y="${H - 4}" font-size="10" fill="var(--muted)" text-anchor="end">12 months →</text></svg>`;
  }
  function openAnalysis() {
    const p = lastPlan, a = p.analytics, c = p.currency;
    const card = (label, val, cl = "", tip = "") => `<div title="${esc(tip)}"><label>${label}</label><b class="${cl}">${val}</b></div>`;
    const deb = Object.entries(p.debates || {});
    $("#anaBody").innerHTML = `<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px"><h3 style="margin:0">📊 Investment committee & risk report</h3><span class="muted" style="font-size:12px">${esc(p.market)} · ${esc(p.profile)} · regime <b>${esc(p.regime.label)}</b> (breadth ${p.regime.breadth.toFixed(0)}, VIX ${p.regime.vix.toFixed(0)})</span><span class="spacer"></span><button class="btn sm ghost" data-close2>✕ Close</button></div>
      ${a.empty ? `<div class="empty">${esc(p.log[p.log.length - 1] || "No portfolio today.")}</div>` : `
      <div class="agrid kv">
        ${card("Expected return", pct(a.expReturn * 100, 1) + "/yr", cls(a.expReturn), "From committee consensus x conviction, before costs")}
        ${card("Volatility", (a.vol * 100).toFixed(1) + "%", "", "Expected yearly swing of the whole portfolio")}
        ${card("Sharpe ratio", a.sharpe.toFixed(2), "", "Return per unit of risk above a 3% cash rate")}
        ${card("1-day VaR 95%", money(a.var95 * p.equity, c), "down", "On 1 day in 20 you could lose at least this much")}
        ${card("1-day CVaR 95%", money(a.cvar95 * p.equity, c), "down", "Average loss on those worst 1-in-20 days")}
        ${card("Beta to S&P 500", a.beta != null ? a.beta.toFixed(2) : "–", "", "1.0 = moves with the US market")}
        ${card("Chance of loss (1y)", (a.mc.probLoss * 100).toFixed(0) + "%", "", "Share of 2,000 simulated years that end below the start")}
        ${card("Drawdown-limit breach", (a.mc.probDDBreach * 100).toFixed(0) + "%", a.mc.probDDBreach > 0.2 ? "down" : "", "Chance of falling more than your max-loss setting at some point in the year")}
        ${card("Median worst dip", pct(a.mc.medianMaxDD * 100, 1), "down", "Typical deepest peak-to-trough fall within a year")}
        ${card("Diversification ratio", a.divRatio.toFixed(2), "", "Above 1.5 means holdings offset each other well")}
        ${card("Effective positions", a.effN.toFixed(1), "", "How many equally-sized bets this portfolio is equivalent to")}
        ${card("Avg correlation", a.avgCorr.toFixed(2), "", "Lower is better diversified")}
      </div>
      <div class="wi-cols" style="margin-bottom:12px">
        <div><h4 class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.6px">Monte Carlo: range of outcomes over 12 months</h4>${fanChart(a.mc.fan, p.equity)}
          <div class="dim" style="font-size:11px">Bands: 5–95% and 25–75% of 2,000 simulated years. Median ${pct(a.mc.p["50"] * 100, 1)}, bad year (5%) ${pct(a.mc.p["5"] * 100, 1)}, great year (95%) ${pct(a.mc.p["95"] * 100, 1)}.</div></div>
        <div><h4 class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.6px">Stress tests (instant shock)</h4>
          ${p.stress.map((s) => `<div class="bars"><div class="b" style="grid-template-columns:150px 1fr 110px"><span>${esc(s.name)}</span><span class="track"><i style="${s.impact >= 0 ? "left:50%" : `left:${50 - Math.min(50, Math.abs(s.impact) * 250)}%`};width:${Math.min(50, Math.abs(s.impact) * 250)}%;background:${s.impact >= 0 ? "var(--up)" : "var(--down)"}"></i></span><span class="num ${cls(s.impact)}" style="text-align:right">${pct(s.impact * 100, 1)} · ${money(s.value, "")}</span></div></div>
            <div class="dim" style="font-size:10.5px;margin:-4px 0 6px 0">hit hardest: ${esc(disp(s.worst))} (${pct(s.worstMove * 100, 1)})</div>`).join("")}
          <div class="dim" style="font-size:11px">Hindsight check: this exact mix returned ${pct(a.backtestReturn * 100, 1)} over the past year (max dip ${pct(a.backtestMaxDD * 100, 1)}). Optimistic, because it was picked knowing that history.</div></div>
      </div>
      <h4 class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.6px">Where the risk comes from</h4>
      <div class="bars">${p.allocation.filter((x) => x.riskShare != null).map((x) => `<div class="b" style="grid-template-columns:150px 1fr 120px"><span>${esc(disp(x.symbol))}</span><span class="track" style="background:#1a2130"><i style="left:0;width:${Math.max(0, x.riskShare * 100)}%;background:var(--warn)"></i></span><span class="num dim" style="text-align:right">${(x.targetWeight * 100).toFixed(1)}% wt · ${(x.riskShare * 100).toFixed(0)}% risk</span></div>`).join("")}</div>`}
      <h4 class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.6px;margin-top:14px">Committee scoreboard (votes across all finalists)</h4>
      <div class="chips">${(p.committee || []).map((v) => `<span class="pill">${esc(v.agent)}: <span class="up">${v.bull}▲</span> <span class="down">${v.bear}▼</span> <span class="dim">${v.abstain}–</span></span>`).join("")}</div>
      <h4 class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.6px;margin-top:14px">The debates</h4>
      ${deb.map(([s, d]) => `<details style="border:1px solid var(--line);border-radius:9px;padding:8px 10px;margin-bottom:6px;background:var(--panel2)">
        <summary style="cursor:pointer"><b>${esc(disp(s))}</b> <span class="${cls(d.consensus)} num">${d.consensus >= 0 ? "+" : ""}${(d.consensus * 100).toFixed(0)}</span> <span class="muted">· ${esc(d.verdict)}</span></summary>
        <div style="margin-top:8px">${d.votes.map((v) => `<div class="vote"><b>${esc(v.agent)}</b><span>${TS.scoreBar(v.stance * 100)} <span class="dim num">${(v.conf * 100).toFixed(0)}%</span></span><span class="muted">${esc(v.arg)}</span></div>`).join("")}
        <div class="wi-cols" style="margin-top:8px"><div><b class="up">Bull case</b><ul style="margin:4px 0;padding-left:18px;font-size:12px">${d.bull.map((x) => `<li>${esc(x)}</li>`).join("") || "<li class='dim'>none</li>"}</ul></div>
        <div><b class="down">Bear case</b><ul style="margin:4px 0;padding-left:18px;font-size:12px">${d.bear.map((x) => `<li>${esc(x)}</li>`).join("") || "<li class='dim'>none</li>"}</ul></div></div>
        ${d.stats && d.stats.vol ? `<div class="dim num" style="font-size:11px">vol ${(d.stats.vol * 100).toFixed(0)}% · 1y max DD ${(d.stats.maxdd * 100).toFixed(0)}% · Sharpe ${d.stats.sharpe.toFixed(2)} · trend R² ${d.stats.trendR2.toFixed(2)} · disagreement ${(d.disagreement).toFixed(2)}</div>` : ""}</div></details>`).join("")}
      <h4 class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.6px;margin-top:14px">How this plan was built</h4>
      <ol style="font-size:12px;color:var(--muted);margin:4px 0;padding-left:18px">${p.log.map((l) => `<li>${esc(l)}</li>`).join("")}</ol>`;
    $("#anaModal").classList.add("show");
    $("#anaBody").querySelector("[data-close2]").onclick = () => $("#anaModal").classList.remove("show");
  }
  $("#anaModal").addEventListener("click", (e) => { if (e.target.id === "anaModal") $("#anaModal").classList.remove("show"); });

  // ---------------- portfolio market picker (shared by the plan, What-If Lab, AI and reports)
  const PRESET_SETS = { "Majors": ["us", "r-gb", "r-de", "r-fr", "r-jp", "r-in", "r-ca"], "US only": ["us"], "Asia": ["r-jp", "r-cn", "r-hk", "r-in", "r-kr", "r-tw", "r-au", "r-sg"],
    "Europe": ["r-gb", "r-de", "r-fr", "r-ch", "r-nl", "r-es", "r-it", "r-se"], "Emerging": ["r-in", "r-br", "r-mx", "r-za", "r-id", "r-tr", "r-sa", "r-pl"], "Multi-asset": ["us", "etfs", "bonds", "commodities", "crypto"] };
  function mkLabel() {
    const n = (state.planMarkets || []).length;
    const names = (state.planMarkets || []).map((id) => markets.find((m) => m.id === id)).filter(Boolean);
    const txt = n === 0 ? "Pick markets" : n <= 2 ? names.map((m) => m.flag + " " + m.name.split(" ·")[0]).join(", ") : `${n} markets`;
    document.querySelectorAll(".mk-label").forEach((el) => (el.textContent = txt));
    $("#planMk span").textContent = txt;
  }
  // fit a popover on screen: below the button if there's room, else above, else centred; never taller than the window
  function placePop(pop, anchor) {
    const r = anchor.getBoundingClientRect();
    const W = Math.min(560, innerWidth - 20);
    pop.style.width = W + "px";
    pop.style.maxHeight = "none";
    pop.style.top = "0px";
    pop.classList.add("show");
    const want = Math.min(pop.scrollHeight, innerHeight - 20);
    const below = innerHeight - r.bottom - 12, above = r.top - 12;
    const top = want <= below ? r.bottom + 6 : want <= above ? r.top - 6 - want : Math.max(10, (innerHeight - want) / 2);
    pop.style.top = top + "px";
    pop.style.maxHeight = innerHeight - top - 10 + "px";
    pop.style.left = Math.max(10, Math.min(r.left, innerWidth - W - 10)) + "px";
  }
  window.addEventListener("resize", () => $("#mkpop").classList.remove("show"));
  function openPicker(anchor) {
    const pop = $("#mkpop");
    const sel = new Set(state.planMarkets || []);
    const groups = [...new Set(markets.map((m) => m.group))];
    pop.innerHTML = `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap"><b>Portfolio markets</b><span class="muted" style="font-size:11px">used by the plan, What-If Lab, AI and reports (max 12)</span></div>
      <div class="chips" style="margin:8px 0">${Object.keys(PRESET_SETS).map((k) => `<span class="chip" data-set="${k}">${k}</span>`).join("")}<span class="chip" data-set="__clear">Clear</span></div>
      ${groups.map((g) => `<h5>${esc(g)}</h5><div class="opts">${markets.filter((m) => m.group === g).map((m) => `<label title="${esc(m.name)}"><input type="checkbox" value="${m.id}" ${sel.has(m.id) ? "checked" : ""}> ${m.flag} ${esc(m.name)}</label>`).join("")}</div>`).join("")}
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px"><span class="muted" id="mkCount" style="align-self:center;font-size:11.5px"></span><button class="btn primary sm" id="mkDone">Done</button></div>`;
    placePop(pop, anchor);
    // every change is saved immediately, so closing the picker any way (Done, clicking away, Build plan) keeps it
    let saveT;
    const count = () => {
      const picked = [...pop.querySelectorAll("input:checked")].map((i) => i.value);
      $("#mkCount").textContent = `${picked.length} selected` + (picked.length > 12 ? " (only the first 12 are used)" : "");
      state.planMarkets = picked;
      mkLabel();
      clearTimeout(saveT);
      saveT = setTimeout(() => api("/api/state", { body: { planMarkets: picked } }), 250);
    };
    $("#mkCount").textContent = `${sel.size} selected`;
    pop.querySelectorAll("input").forEach((i) => (i.onchange = count));
    pop.querySelectorAll("[data-set]").forEach((c) => (c.onclick = () => {
      const set = PRESET_SETS[c.dataset.set] || [];
      pop.querySelectorAll("input").forEach((i) => (i.checked = set.includes(i.value)));
      count();
    }));
    $("#mkDone").onclick = () => pop.classList.remove("show");
  }
  document.addEventListener("mousedown", (e) => { const pop = $("#mkpop"); if (pop.classList.contains("show") && !pop.contains(e.target) && !e.target.closest("#planMk,.mk-btn")) pop.classList.remove("show"); });
  $("#planMk").onclick = (e) => openPicker(e.currentTarget);

  // ---------------- What-If Lab
  const EXAMPLES = ["China invades Taiwan", "The Fed cuts rates by 1% as a recession hits", "Oil spikes to $150 after Middle East war",
    "AI boom accelerates: data-center spending doubles", "US slaps 60% tariffs on all Chinese imports", "Bitcoin ETF mania sends crypto up 80%",
    "Global pandemic lockdowns return", "China launches a massive stimulus package", "US banking crisis: regional banks fail", "Dollar crashes 15%"];
  function renderWhatIf() {
    const el = $("#whatif");
    if (el.dataset.ready) { mkLabel(); return; }
    el.dataset.ready = 1;
    el.innerHTML = `<div class="hint b-only" style="margin-bottom:10px">Describe any event. The local AI turns it into moves in oil, rates, the dollar, volatility and other market drivers. The algorithm then measures how every stock in your chosen markets has historically reacted to those drivers and ranks who wins and who loses.</div>
      <textarea class="in" id="wiText" placeholder="What if… e.g. 'Oil jumps to $140 after Iran closes the Strait of Hormuz'"></textarea>
      <div style="display:flex;gap:8px;align-items:center;margin:8px 0;flex-wrap:wrap">
        <button class="btn mk-btn" id="wiMk">🌍 <span class="mk-label"></span></button>
        <label class="check"><input type="checkbox" id="wiAi" checked> Use local AI to interpret</label>
        <span class="spacer"></span><button class="btn primary" id="wiRun">🔮 Run scenario</button></div>
      <div class="chips">${EXAMPLES.map((x) => `<span class="chip" data-ex="${esc(x)}">${esc(x)}</span>`).join("")}</div>
      <div id="wiSpec"></div><div id="wiRes"></div>`;
    mkLabel();
    $("#wiMk").onclick = (e) => openPicker(e.currentTarget);
    el.querySelectorAll("[data-ex]").forEach((c) => (c.onclick = () => { $("#wiText").value = c.dataset.ex; }));
    $("#wiRun").onclick = () => runWhatIf();
    $("#wiText").onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) runWhatIf(); };
  }
  async function runWhatIf(spec) {
    const text = $("#wiText").value.trim();
    if (!text && !spec) return TS.toast("Describe an event first");
    if (!(state.planMarkets || []).length) return TS.toast("Pick at least one market");
    $("#wiRes").innerHTML = `<div class="empty"><span class="spin"></span> ${spec ? "Re-running" : $("#wiAi").checked ? "The AI is interpreting your scenario, then" : "Interpreting, then"} scoring ${state.planMarkets.length} market(s)… the first run of a new market takes a little longer.</div>`;
    if (!spec) $("#wiSpec").innerHTML = "";
    try { wi = await api("/api/scenario/run", { body: { text, spec, markets: state.planMarkets, ai: $("#wiAi").checked } }); }
    catch (e) { $("#wiRes").innerHTML = `<div class="empty">Scenario failed: ${esc(e.message)}</div>`; return; }
    renderSpec(); renderWiResults();
  }
  function renderSpec() {
    const s = wi.spec, lv = wi.levels;
    $("#wiSpec").innerHTML = `<h4>How the model reads it <span class="dim" style="text-transform:none;letter-spacing:0">· ${esc(s.source || "")}</span></h4>
      <div style="margin-bottom:8px"><b>${esc(s.title)}</b><div class="muted" style="font-size:12px">${esc(s.summary)}</div></div>
      <div class="drv">${Object.entries(lv).map(([k, d]) => `<div class="field"><label title="now ${d.level != null ? price(d.level) : "–"}">${esc(d.label)} <span class="dim">(${d.unit})</span></label><input class="in num" type="number" step="any" data-drv="${k}" value="${s.moves[k] || 0}"></div>`).join("")}</div>
      <div class="chips" style="margin-top:8px">${Object.entries(s.sectors).map(([k, v]) => `<span class="pill ${v > 0 ? "up" : "down"}">${esc(k)} ${v > 0 ? "▲" : "▼"} ${Math.abs(v).toFixed(1)}</span>`).join("")}
        ${s.themes.map((t) => `<span class="pill ${t.impact > 0 ? "up" : "down"}">#${esc(t.keyword)} ${t.impact > 0 ? "▲" : "▼"}</span>`).join("")}
        ${Object.entries(s.countries).map(([k, v]) => `<span class="pill ${v > 0 ? "up" : "down"}">${esc(k.toUpperCase())} ${v > 0 ? "▲" : "▼"}</span>`).join("")}</div>
      <div style="margin-top:8px"><button class="btn sm" id="wiRerun">↻ Re-run with my edited moves</button></div>`;
    $("#wiRerun").onclick = () => {
      const moves = { ...wi.spec.moves };
      document.querySelectorAll("[data-drv]").forEach((i) => (moves[i.dataset.drv] = +i.value || 0));
      runWhatIf({ ...wi.spec, moves });
    };
  }
  function wiTable(rows, ccy) {
    return `<table class="t"><thead><tr><th>Symbol</th><th class="r">Projected</th><th>Score</th><th>Conf.</th><th class="r">Size</th></tr></thead><tbody>${rows.map((r) => `
      <tr class="row" data-s="${esc(r.symbol)}" title="${esc(r.drivers.map((d) => `${d.label}: ${(d.contrib * 100).toFixed(1)}%`).join("\n"))}">
      <td><div class="sym">${esc(disp(r.symbol))}<small>${esc(r.name)}</small><small>${esc(r.marketName)} · ${esc(r.sector || "")}</small></div></td>
      <td class="r num ${cls(r.expected)}"><b>${pct(r.expected * 100, 1)}</b><div class="dim" style="font-size:10px;max-width:190px;overflow:hidden;text-overflow:ellipsis">${esc(r.drivers[0]?.label || "")}</div></td>
      <td>${TS.scoreBar(r.score)} <span class="num ${cls(r.score)}">${r.score > 0 ? "+" : ""}${r.score.toFixed(0)}</span></td>
      <td>${TS.confRing(r.confidence)}</td>
      <td class="r num" style="font-size:12px">${r.sizing.qty ? `${r.bias === "short" ? "Short" : "Buy"} ${r.sizing.qty}<div class="dim">≈ ${money(r.sizing.cost, ccy)}</div>` : '<span class="dim">–</span>'}</td></tr>`).join("")}</tbody></table>`;
  }
  function renderWiResults() {
    const rows = wi.rows, ccy = state.profile.currency;
    const win = rows.filter((r) => r.score > 0).slice(0, 15), lose = rows.filter((r) => r.score < 0).sort((a, b) => a.score - b.score).slice(0, 15);
    $("#wiRes").innerHTML = `<div style="display:flex;gap:6px;margin:14px 0 4px;flex-wrap:wrap">
        <button class="btn primary sm" id="wiPlan">📋 Build my plan for this scenario</button><button class="btn sm" id="wiAiBtn">✨ AI scenario briefing</button>
        <button class="btn sm" id="wiRep">📄 Scenario report</button><span class="spacer"></span><span class="dim" style="font-size:11px;align-self:center">${rows.length} stocks · ${esc(wi.markets.join(", "))}</span></div>
      <div id="wiAiOut" class="md" style="display:none;padding:10px;background:var(--panel2);border-radius:8px;margin:8px 0"></div>
      <div class="wi-cols"><div><h4 class="up">▲ Best positioned</h4>${wiTable(win, ccy)}</div><div><h4 class="down">▼ Most exposed</h4>${wiTable(lose, ccy)}</div></div>
      <p class="disclaimer">Projections come from each stock's historical sensitivity to the drivers plus sector/theme views. They are rough, directional estimates, not forecasts. Hover a row to see its drivers.</p>`;
    bindRows($("#wiRes"), "tr.row");
    $("#wiPlan").onclick = () => { planScenario = wi.spec; $("#planBtn").click(); };
    $("#wiAiBtn").onclick = async () => {
      const out = $("#wiAiOut"); out.style.display = "block"; out.classList.add("cursor"); out.innerHTML = "";
      await TS.stream("/api/ai/scenario", { spec: wi.spec, rows: wi.rows.slice(0, 20).concat(wi.rows.slice(-12)), markets: wi.markets }, (t) => (out.innerHTML = TS.md(t)));
      out.classList.remove("cursor");
    };
    $("#wiRep").onclick = () => { try { localStorage.setItem("ts-scenario", JSON.stringify(wi)); } catch {} window.open("/report.html?scenario=1", "_blank"); };
  }

  init();
})();
