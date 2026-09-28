// Screen 1: Command Center — markets, scanner, recommendations, budget and daily plan.
(() => {
  const $ = (s) => document.querySelector(s);
  const { api, esc, price, pct, cls, money, disp } = TS;
  let state, markets = [], riskCfg = {}, scan = null, tab = "long", sortKey = "score", sortDir = -1, selected = null, lastPlan = null;
  let researchAlive = 0, wi = null, planScenario = null;

  TS.setMode(TS.mode(), false);
  document.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () => TS.setMode(b.dataset.mode)));
  document.querySelectorAll("[data-close]").forEach((b) => (b.onclick = () => b.closest(".modal-bg").classList.remove("show")));

  // research-window heartbeat
  TS.on((m) => {
    if (m.type === "pong") researchAlive = Date.now();
    if (m.type === "select" && m.from === "research") highlight(m.symbol);
    if (m.type === "watch") { state.watchlist = m.watchlist; renderWatch(); }
  });
  setInterval(() => TS.send({ type: "ping" }), 3000);

  async function openResearch(symbol) {
    let features = "popup,width=1600,height=1000";
    try {
      if ("getScreenDetails" in window) { // Window Management API: put it on the other monitor automatically
        const sd = await window.getScreenDetails();
        const other = sd.screens.find((s) => s !== sd.currentScreen);
        if (other) features = `popup,left=${other.availLeft},top=${other.availTop},width=${other.availWidth},height=${other.availHeight}`;
      }
    } catch {}
    const url = "/research.html" + (symbol ? `?symbol=${encodeURIComponent(symbol)}&market=${state.lastMarket}` : "");
    const w = window.open(url, "tradescope-research", features);
    if (!w) TS.toast("Pop-up blocked. Allow pop-ups for this site to use the dual-screen layout.");
  }
  $("#openResearch").onclick = () => openResearch(selected);

  function select(symbol) {
    selected = symbol;
    highlight(symbol);
    TS.send({ type: "select", symbol, market: state.lastMarket, from: "command" });
    if (Date.now() - researchAlive > 7000) openResearch(symbol);
  }
  function highlight(symbol) {
    selected = symbol;
    document.querySelectorAll("tr.row").forEach((r) => r.classList.toggle("sel", r.dataset.s === symbol));
  }

  // ---------------- init
  async function init() {
    [state, { markets, risk: riskCfg }] = await Promise.all([api("/api/state"), api("/api/markets")]);
    state.planMarkets ||= [state.lastMarket || "us"];
    renderMarkets();
    mkLabel();
    fillProfile();
    renderWatch();
    loadScan();
    loadMacro();
    setInterval(loadMacro, 60000);
    setInterval(renderWatch, 60000);
    TS.aiStatus($("#aist"));
    TS.bindSearch($("#q"), $("#qres"), (s) => select(s));
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
    $("#strip").querySelectorAll(".tk").forEach((el) => (el.onclick = () => select(el.dataset.s)));
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
    $("#heat").querySelectorAll(".tile").forEach((t) => (t.onclick = () => select(t.dataset.s)));
  }

  document.querySelectorAll("#tabs button").forEach((b) => (b.onclick = () => {
    tab = b.dataset.t;
    document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
    const isWi = tab === "whatif";
    $("#whatif").style.display = isWi ? "" : "none";
    document.querySelectorAll(".scan-only").forEach((el) => (el.style.display = isWi ? "none" : ""));
    ["#filter", "#refresh", "#scanInfo"].forEach((s) => ($(s).style.visibility = isWi ? "hidden" : ""));
    if (isWi) { renderWhatIf(); return; }
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
    let rows = scan.rows.filter((r) => (tab === "all" || (tab === "long" ? r.score > 0 : r.score < 0)) && (!f || (r.symbol + r.name + r.setup + (r.sector || "")).toLowerCase().includes(f)));
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
    document.querySelectorAll("tr.row").forEach((tr) => (tr.onclick = () => select(tr.dataset.s)));
  }

  // ---------------- watchlist
  async function renderWatch() {
    const wl = state.watchlist || [];
    if (!wl.length) { $("#wl").innerHTML = `<tr><td class="empty">Empty. Select a symbol and press "＋ selected".</td></tr>`; return; }
    const q = await api("/api/quotes?symbols=" + encodeURIComponent(wl.join(","))).catch(() => []);
    $("#wl").innerHTML = q.map((x) => `<tr class="row" data-s="${esc(x.symbol)}"><td><div class="sym">${esc(disp(x.symbol))}<small>${esc(x.name)}</small></div></td>
      <td class="r num">${price(x.price)}</td><td class="r num ${cls(x.changePct)}">${pct(x.changePct)}</td>
      <td style="width:22px"><button class="btn sm ghost" data-rm="${esc(x.symbol)}" title="Remove">✕</button></td></tr>`).join("");
    $("#wl").querySelectorAll("tr.row").forEach((tr) => (tr.onclick = (e) => { if (!e.target.dataset.rm) select(tr.dataset.s); }));
    $("#wl").querySelectorAll("[data-rm]").forEach((b) => (b.onclick = () => saveWatch(wl.filter((s) => s !== b.dataset.rm))));
  }
  async function saveWatch(list) { state.watchlist = list; await api("/api/state", { body: { watchlist: list } }); renderWatch(); TS.send({ type: "watch", watchlist: list }); }
  $("#wlAdd").onclick = () => { if (selected && !state.watchlist.includes(selected)) saveWatch([...state.watchlist, selected]); };

  // ---------------- profile
  const P = { budget: "#pBudget", currency: "#pCcy", dailyLimit: "#pDaily", risk: "#pRisk", cash: "#pCash" };
  function fillProfile() {
    const p = state.profile;
    Object.entries(P).forEach(([k, s]) => ($(s).value = p[k] ?? ""));
    $("#pShort").checked = !!p.allowShorts; $("#pFrac").checked = !!p.fractional;
    $("#nHold").textContent = state.holdings.length;
    explainRisk();
  }
  function explainRisk() {
    const c = riskCfg[$("#pRisk").value]; if (!c) return;
    const b = +$("#pBudget").value || 0, ccy = $("#pCcy").value;
    $("#riskExplain").innerHTML = `<b>${c.label}:</b> each idea risks about <b>${money(b * c.risk, ccy)}</b> (${(c.risk * 100).toFixed(1)}% of budget) if its stop-loss is hit. No single position goes above ${(c.maxpos * 100).toFixed(0)}%, at most ${c.maxn} positions, max ${(c.sector * 100).toFixed(0)}% in one sector.`;
  }
  let saveH;
  document.querySelectorAll("#pBudget,#pCcy,#pDaily,#pRisk,#pCash,#pShort,#pFrac").forEach((el) => el.addEventListener("change", () => {
    clearTimeout(saveH);
    saveH = setTimeout(async () => {
      const p = { ...state.profile };
      Object.entries(P).forEach(([k, s]) => (p[k] = ["risk", "currency"].includes(k) ? $(s).value : $(s).value === "" ? null : +$(s).value));
      p.allowShorts = $("#pShort").checked; p.fractional = $("#pFrac").checked;
      state.profile = p;
      await api("/api/state", { body: { profile: p } });
      explainRisk();
      TS.send({ type: "profile" });
      loadScan();
    }, 300);
  }));

  // ---------------- holdings
  function holdRow(h = {}) {
    const d = document.createElement("div"); d.className = "hold-row";
    d.innerHTML = `<input class="in" placeholder="AAPL" value="${esc(h.symbol || "")}"><input class="in num" type="number" step="any" placeholder="10" value="${h.qty ?? ""}">
      <input class="in num" type="number" step="any" placeholder="150.00" value="${h.avgCost ?? ""}"><select class="in"><option value="long">Long</option><option value="short" ${h.side === "short" ? "selected" : ""}>Short</option></select>
      <button class="btn sm ghost">✕</button>`;
    d.querySelector("button").onclick = () => d.remove();
    $("#holdRows").appendChild(d);
  }
  $("#holdBtn").onclick = () => { $("#holdRows").innerHTML = ""; (state.holdings.length ? state.holdings : [{}]).forEach(holdRow); $("#holdModal").classList.add("show"); };
  $("#holdAdd").onclick = () => holdRow();
  $("#holdSave").onclick = async () => {
    const hs = [...document.querySelectorAll("#holdRows .hold-row")].map((r) => { const i = r.querySelectorAll("input,select"); return { symbol: i[0].value.trim().toUpperCase(), qty: +i[1].value, avgCost: +i[2].value || null, side: i[3].value }; }).filter((h) => h.symbol && h.qty > 0);
    hs.forEach((h) => { const m = scan?.rows.find((r) => disp(r.symbol) === h.symbol); if (m) h.symbol = m.symbol; });
    state.holdings = hs;
    await api("/api/state", { body: { holdings: hs } });
    $("#nHold").textContent = hs.length;
    $("#holdModal").classList.remove("show");
    TS.toast("Holdings saved");
  };

  // ---------------- plan
  const COLORS = ["#5b8cff", "#1fd286", "#9b7bff", "#f5b942", "#ff5470", "#38bdf8", "#f472b6", "#a3e635", "#fb923c", "#2dd4bf", "#c084fc", "#facc15"];
  function donut(alloc, ccy) {
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
    $("#plan").innerHTML = `<div class="empty"><span class="spin"></span> Building today's plan…</div>`;
    try { lastPlan = await api("/api/plan", { body: { markets: state.planMarkets, scenario: planScenario } }); }
    catch (e) { $("#plan").innerHTML = `<div class="empty">Plan failed: ${esc(e.message)}</div>`; return; }
    renderPlan();
    TS.send({ type: "plan", plan: lastPlan });
  };
  function renderPlan() {
    const p = lastPlan, c = p.currency;
    const buys = p.actions.filter((a) => ["BUY", "ADD", "SHORT"].includes(a.action)).reduce((s, a) => s + a.value, 0);
    $("#plan").innerHTML = `
      <div class="kv" style="grid-template-columns:repeat(3,1fr);margin-bottom:10px">
        <div><label>Deploy today</label><b>${money(buys, c)}</b></div><div><label>Cash after</label><b>${money(p.cashEnd, c)}</b></div>
        <div><label>Risk at stops</label><b class="down">${money(p.totalRisk, c)}</b></div></div>
      ${donut(p.allocation, c)}
      ${p.scenario ? `<div class="hint" style="margin:8px 0">🔮 Built for scenario: <b>${esc(p.scenario)}</b> <button class="btn sm ghost" id="clearScen">✕ back to normal</button></div>` : ""}
      ${p.byMarket.length > 1 ? `<div class="muted" style="font-size:11.5px;margin-top:8px">By market: ${p.byMarket.map((m) => `<b>${esc(m.market)}</b> ${((m.value / p.equity) * 100).toFixed(0)}%`).join(" · ")}</div>` : ""}
      <div style="display:flex;gap:6px;margin:10px 0 8px"><button class="btn sm" id="aiPlan">✨ AI explain plan</button><button class="btn sm" id="planReport">📄 Full report</button><span class="spacer"></span><span class="dim" style="font-size:11px">${esc(p.market)} · ${esc(p.profile)}</span></div>
      <div id="aiPlanOut" class="md" style="display:none;margin-bottom:10px;padding:10px;background:var(--panel2);border-radius:8px"></div>
      ${p.actions.map((a) => `<div class="act" data-s="${esc(a.symbol)}"><span class="tag ${a.action}">${a.action}</span>
        <div><b>${esc(disp(a.symbol))}</b> <span class="muted">${esc(a.name || "")}</span>${a.market && p.markets.length > 1 ? ` <span class="pill" style="padding:0 6px;font-size:10px">${esc(a.market)}</span>` : ""}<div class="why">${esc(a.reason)}</div>
        ${a.stop ? `<div class="dim num" style="font-size:11px">stop ${price(a.stop)}${a.target ? ` · target ${price(a.target)}` : ""}</div>` : ""}</div>
        <div class="r num" style="text-align:right"><b>${a.qty ?? ""}</b><div class="dim" style="font-size:11px">${money(a.value, c)}</div></div></div>`).join("") || '<div class="empty">No actions today. Sit tight; not trading is also a position.</div>'}
      ${p.watchlist.length ? `<div class="muted" style="margin:10px 0 4px;font-size:11px">ON DECK (no cash or slots left today)</div>` + p.watchlist.map((w) => `<span class="pill" style="margin:2px">${esc(disp(w.symbol))} <span class="${cls(w.score)}">${w.score > 0 ? "+" : ""}${w.score.toFixed(0)}</span></span>`).join("") : ""}
      <p class="disclaimer">Research tool only. TradeScope never places trades. Size and timing are suggestions; verify prices with your broker.</p>`;
    $("#plan").querySelectorAll(".act").forEach((d) => (d.onclick = () => select(d.dataset.s)));
    if ($("#clearScen")) $("#clearScen").onclick = () => { planScenario = null; $("#planBtn").click(); };
    $("#aiPlan").onclick = async () => {
      const out = $("#aiPlanOut"); out.style.display = "block"; out.classList.add("cursor"); out.innerHTML = "";
      await TS.stream("/api/ai/plan", { plan: lastPlan }, (t) => (out.innerHTML = TS.md(t)));
      out.classList.remove("cursor");
    };
    $("#planReport").onclick = () => { try { localStorage.setItem("ts-plan", JSON.stringify(lastPlan)); } catch {} window.open("/report.html?plan=1", "_blank"); };
  }

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
  function openPicker(anchor) {
    const pop = $("#mkpop");
    const sel = new Set(state.planMarkets || []);
    const groups = [...new Set(markets.map((m) => m.group))];
    pop.innerHTML = `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap"><b>Portfolio markets</b><span class="muted" style="font-size:11px">used by the plan, What-If Lab, AI and reports (max 12)</span></div>
      <div class="chips" style="margin:8px 0">${Object.keys(PRESET_SETS).map((k) => `<span class="chip" data-set="${k}">${k}</span>`).join("")}<span class="chip" data-set="__clear">Clear</span></div>
      ${groups.map((g) => `<h5>${esc(g)}</h5><div class="opts">${markets.filter((m) => m.group === g).map((m) => `<label title="${esc(m.name)}"><input type="checkbox" value="${m.id}" ${sel.has(m.id) ? "checked" : ""}> ${m.flag} ${esc(m.name)}</label>`).join("")}</div>`).join("")}
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px"><span class="muted" id="mkCount" style="align-self:center;font-size:11.5px"></span><button class="btn primary sm" id="mkDone">Done</button></div>`;
    const r = anchor.getBoundingClientRect();
    pop.style.top = Math.min(r.bottom + 6, innerHeight - 200) + "px";
    pop.style.left = Math.max(10, Math.min(r.left, innerWidth - 580)) + "px";
    pop.classList.add("show");
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
    $("#wiRes").querySelectorAll("tr.row").forEach((tr) => (tr.onclick = () => select(tr.dataset.s)));
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
