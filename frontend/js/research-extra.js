// Research screen extras: chart types, log scale, overlays, panes, drawing, screenshots, compare, theme,
// and the Stats / Levels / Peers / Tools tabs. Hooks into research.js through window.RES.
window.RX = (() => {
  const $ = (s) => document.querySelector(s);
  const { api, esc, price, pct, cls, money, big } = TS;
  const R = window.RES;
  let EX = null, exFor = null, loading = null;
  const store = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
  const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };

  // ---------------- extra series (created once, filled on each draw)
  const L = (color, w = 1.2, style = 0, extra = {}) => R.cMain.addLineSeries({ color, lineWidth: w, lineStyle: style, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, ...extra });
  const S = {
    sma50: L("#22d3ee"), sma200: L("#f472b6", 1.8), kcU: L("rgba(56,189,248,.7)", 1, 2), kcL: L("rgba(56,189,248,.7)", 1, 2),
    dcU: L("rgba(245,185,66,.75)", 1, 1), dcL: L("rgba(245,185,66,.75)", 1, 1), stUp: L("#1fd286", 2), stDn: L("#ff5470", 2),
    psar: L("#e7ebf3", 1, 0, { lineVisible: false, pointMarkersVisible: true, pointMarkersRadius: 1.6 }),
    c5: L("rgba(155,123,255,.8)", 1, 2), c50: L("rgba(155,123,255,.9)", 1, 1), c95: L("rgba(155,123,255,.8)", 1, 2),
    cmp: L("#f5b942", 1.6), lineMain: L("#5b8cff", 2), area: R.cMain.addAreaSeries({ lineColor: "#5b8cff", topColor: "rgba(91,140,255,.35)", bottomColor: "rgba(91,140,255,.02)", lineWidth: 2, priceLineVisible: false }),
  };
  let pLines = [], drawLines = [];

  const on = (id) => !!document.getElementById(id)?.checked;
  const ser = (t, v, from = 0) => t.slice(from).map((x, i) => ({ time: x, value: v[i + from] })).filter((p) => p.value != null && isFinite(p.value));

  function heikin(s) {
    const out = [];
    let po = s.o[0], pc = s.c[0];
    for (let i = 0; i < s.t.length; i++) {
      const c = (s.o[i] + s.h[i] + s.l[i] + s.c[i]) / 4, o = (po + pc) / 2;
      out.push({ time: s.t[i], open: o, high: Math.max(s.h[i], o, c), low: Math.min(s.l[i], o, c), close: c });
      po = o; pc = c;
    }
    return out;
  }

  async function afterDraw(intraday) {
    const A = R.A;
    Object.values(S).forEach((x) => x.setData([]));
    pLines.forEach((p) => R.candle.removePriceLine(p));
    pLines = [];
    const type = $("#ctype").value;
    R.candle.applyOptions({ visible: type === "candle" || type === "ha" });
    if (!A || intraday) { applyType(type, null); return; }
    const s = A.series, t = s.t;
    if (type === "ha") R.candle.setData(heikin(s));
    applyType(type, s);
    const ex = EX && exFor === A.symbol ? EX : null;
    if (ex) {
      const o = ex.overlays;
      if (on("oSma")) { S.sma50.setData(ser(t, o.sma50, 49)); S.sma200.setData(ser(t, o.sma200, 199)); }
      if (on("oKc")) { S.kcU.setData(ser(t, o.kcU, 20)); S.kcL.setData(ser(t, o.kcL, 20)); }
      if (on("oDc")) { S.dcU.setData(ser(t, o.dcU, 20)); S.dcL.setData(ser(t, o.dcL, 20)); }
      if (on("oSt")) {
        S.stUp.setData(t.map((x, i) => (i > 10 && o.stDir[i] > 0 ? { time: x, value: o.supertrend[i] } : { time: x })));
        S.stDn.setData(t.map((x, i) => (i > 10 && o.stDir[i] < 0 ? { time: x, value: o.supertrend[i] } : { time: x })));
      }
      if (on("oPsar")) S.psar.setData(ser(t, o.psar, 5));
      const pl = (p, color, title, style = 2) => p != null && pLines.push(R.candle.createPriceLine({ price: p, color, lineWidth: 1, lineStyle: style, title, axisLabelVisible: true }));
      if (on("oPiv")) Object.entries(ex.pivots).forEach(([k, v]) => pl(v, k === "P" ? "#aab3c6" : k.startsWith("R") ? "#ff8a9c" : "#63d9a4", k, 3));
      if (on("oSr")) { ex.sr.resistance.forEach((x) => pl(x.price, "#ff5470", `R ×${x.touches}`, 0)); ex.sr.support.forEach((x) => pl(x.price, "#1fd286", `S ×${x.touches}`, 0)); }
      if (on("oFib")) Object.entries(ex.fib.levels).forEach(([k, v]) => pl(v, "#c084fc", `Fib ${k}`, 1));
      if (on("o52")) { pl(ex.hi52, "#f5b942", "52w high", 0); pl(ex.lo52, "#f5b942", "52w low", 0); }
      if (on("oCone")) {
        const last = { time: t[t.length - 1], value: s.c[s.c.length - 1] };
        S.c5.setData([last, ...ex.cone.path.map((p) => ({ time: p.t, value: p["5"] }))]);
        S.c50.setData([last, ...ex.cone.path.map((p) => ({ time: p.t, value: p["50"] }))]);
        S.c95.setData([last, ...ex.cone.path.map((p) => ({ time: p.t, value: p["95"] }))]);
      }
    }
    if (on("oCmp")) {
      const bench = A.symbol.endsWith(".NS") ? "^NSEI" : A.symbol.endsWith("-USD") ? "BTC-USD" : "^GSPC";
      const h = await api(`/api/history/${encodeURIComponent(bench)}?range=5y&interval=1d`).catch(() => null);
      if (h && h.t.length) {
        const n = t.length, bars = { "3M": 63, "6M": 126, "1Y": 252, "2Y": 504, "5Y": n }[R.tf] || 252, i0 = Math.max(0, n - bars);
        const bd = h.t.map((x) => Math.floor(x / 86400)), day0 = Math.floor(t[i0] / 86400);
        let j0 = bd.findIndex((d) => d >= day0); if (j0 < 0) j0 = 0;
        const k = s.c[i0] / h.c[j0];
        S.cmp.setData(h.t.slice(j0).map((x, j) => ({ time: x, value: h.c[j0 + j] * k })));
        S.cmp.applyOptions({ title: bench === "^GSPC" ? "S&P 500" : bench });
      }
    }
    drawLines = store("ts-lines", {})[A.symbol] || [];
    drawLines.forEach((p) => pLines.push(R.candle.createPriceLine({ price: p, color: "#e7ebf3", lineWidth: 1, lineStyle: 0, title: "✏", axisLabelVisible: true })));
  }
  function applyType(type, s) {
    if (!s) return;
    const closes = s.t.map((x, i) => ({ time: x, value: s.c[i] }));
    if (type === "line") S.lineMain.setData(closes);
    if (type === "area") S.area.setData(closes);
  }

  function markers() {
    const ex = EX && R.A && exFor === R.A.symbol ? EX : null;
    if (!ex || !on("oPat")) return [];
    return ex.patterns.map((p) => ({ time: p.t, position: p.bias === "bear" ? "aboveBar" : "belowBar", color: p.bias === "bull" ? "#63d9a4" : p.bias === "bear" ? "#ff8a9c" : "#aab3c6",
      shape: p.bias === "neutral" ? "square" : p.bias === "bull" ? "arrowUp" : "arrowDown", text: p.name.replace("Bullish ", "Bull ").replace("Bearish ", "Bear ") }));
  }

  async function onLoad(changed) {
    if (changed) EX = null;
    const sym = R.sym;
    if (exFor === sym && EX) return;
    const my = (loading = sym);
    api(`/api/extras/${encodeURIComponent(sym)}${R.market ? "?market=" + R.market : ""}`).then((ex) => {
      if (loading !== my) return;
      EX = ex; exFor = sym;
      if (document.querySelectorAll("[data-ov]:checked").length) R.draw();
      const t = document.querySelector("#rtabs .on")?.dataset.t;
      if (tabs[t]) tabs[t]();
    }).catch(() => {});
  }

  // ---------------- toolbar wiring
  document.querySelectorAll(".dd > button").forEach((b) => (b.onclick = (e) => { e.stopPropagation(); const d = b.parentNode; document.querySelectorAll(".dd.open").forEach((x) => x !== d && x.classList.remove("open")); d.classList.toggle("open"); }));
  document.addEventListener("click", (e) => { if (!e.target.closest(".dd")) document.querySelectorAll(".dd.open").forEach((x) => x.classList.remove("open")); });
  const ovState = store("ts-overlays", {});
  document.querySelectorAll("#ovDD input").forEach((i) => {
    if (ovState[i.id] !== undefined) i.checked = ovState[i.id];
    i.addEventListener("change", () => { ovState[i.id] = i.checked; save("ts-overlays", ovState); R.draw(); });
  });
  $("#ctype").value = store("ts-ctype", "candle");
  $("#ctype").onchange = () => { save("ts-ctype", $("#ctype").value); R.draw(); };
  let logMode = store("ts-log", false);
  const applyLog = () => { R.cMain.priceScale("right").applyOptions({ mode: logMode ? 1 : 0 }); $("#logBtn").classList.toggle("primary", logMode); };
  applyLog();
  $("#logBtn").onclick = () => { logMode = !logMode; save("ts-log", logMode); applyLog(); };

  function applyPanes() {
    const pro = document.body.classList.contains("pro");
    const saved = store("ts-panes", null);
    const rows = ["1fr"];
    document.querySelectorAll("[data-pane]").forEach((i) => {
      const id = i.dataset.pane;
      const want = saved ? !!saved[id] : pro || id === "cAtr" || id === "cScore";
      i.checked = want;
      const el = document.getElementById(id);
      el.style.display = want ? "" : "none";
      if (want) rows.push(id === "cScore" ? "90px" : "80px");
    });
    $(".charts").style.gridTemplateRows = rows.join(" ");
  }
  document.querySelectorAll("[data-pane]").forEach((i) => i.addEventListener("change", () => {
    const st = {};
    document.querySelectorAll("[data-pane]").forEach((x) => (st[x.dataset.pane] = x.checked));
    save("ts-panes", st); applyPanes(); setTimeout(() => R.setRange(), 50);
  }));
  applyPanes();
  new MutationObserver(applyPanes).observe(document.body, { attributes: true, attributeFilter: ["class"] });

  let drawing = false;
  $("#drawBtn").onclick = () => { drawing = !drawing; $("#drawBtn").classList.toggle("primary", drawing); $("#cMain").classList.toggle("drawing", drawing); if (drawing) TS.toast("Click the chart to place a horizontal line"); };
  R.cMain.subscribeClick((p) => {
    if (!drawing || !p.point || !R.A) return;
    const px = R.candle.coordinateToPrice(p.point.y);
    if (px == null) return;
    const all = store("ts-lines", {});
    (all[R.A.symbol] ||= []).push(+px.toFixed(6));
    save("ts-lines", all);
    drawing = false; $("#drawBtn").classList.remove("primary"); $("#cMain").classList.remove("drawing");
    R.draw();
  });
  $("#clearDraw").onclick = () => { if (!R.A) return; const all = store("ts-lines", {}); delete all[R.A.symbol]; save("ts-lines", all); R.draw(); };
  $("#shotBtn").onclick = () => {
    const c = R.cMain.takeScreenshot();
    const a = document.createElement("a");
    a.href = c.toDataURL("image/png");
    a.download = `${R.sym || "chart"}-${new Date().toISOString().slice(0, 10)}.png`;
    a.click();
  };

  // theme for the canvases
  function chartTheme() {
    const light = document.documentElement.dataset.theme === "light";
    const opt = { layout: { background: { color: light ? "#ffffff" : "#0e1219" }, textColor: light ? "#5d6679" : "#8791a6" },
      grid: { vertLines: { color: light ? "#eef1f6" : "#141b27" }, horzLines: { color: light ? "#eef1f6" : "#141b27" } } };
    R.all.forEach((c) => c.applyOptions(opt));
    S.psar.applyOptions({ color: light ? "#0f1522" : "#e7ebf3" });
  }
  chartTheme();
  new MutationObserver(chartTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  // shortcuts
  ["1D", "5D", "3M", "6M", "1Y", "2Y", "5Y"].forEach((k, i) => UX.shortcut(String(i + 1), `Timeframe ${k}`, () => document.querySelector(`#tf button[data-tf="${k}"]`)?.click()));
  UX.shortcut("l", "Toggle log scale", () => $("#logBtn").click());
  UX.shortcut("c", "Cycle chart type", () => { const o = ["candle", "ha", "line", "area"]; $("#ctype").value = o[(o.indexOf($("#ctype").value) + 1) % 4]; $("#ctype").onchange(); });
  UX.shortcut("d", "Draw a horizontal line", () => $("#drawBtn").click());
  UX.shortcut("a", "Open the AI analyst", () => document.querySelector('#rtabs button[data-t="ai"]').click());
  UX.shortcut("s", "Open Stats", () => document.querySelector('#rtabs button[data-t="stats"]').click());
  UX.shortcut("t", "Toggle light / dark theme", () => UX.toggleTheme());
  UX.shortcut("g", "Open the glossary", () => UX.showGlossary());

  // ---------------- small SVG helpers
  function bars(vals, labels, { w = 420, h = 110, fmt = (v) => pct(v * 100, 1) } = {}) {
    const mx = Math.max(...vals.map((v) => Math.abs(v || 0)), 1e-9), bw = w / vals.length;
    return `<svg viewBox="0 0 ${w} ${h + 16}" width="100%">${vals.map((v, i) => {
      const bh = (Math.abs(v || 0) / mx) * (h / 2 - 4), y = v >= 0 ? h / 2 - bh : h / 2;
      return `<rect x="${i * bw + 2}" y="${y}" width="${bw - 4}" height="${bh}" rx="2" fill="${v >= 0 ? "var(--up)" : "var(--down)"}" opacity=".85"><title>${labels[i]}: ${v == null ? "n/a" : fmt(v)}</title></rect>
        <text x="${i * bw + bw / 2}" y="${h + 12}" font-size="9" text-anchor="middle" fill="var(--muted)">${labels[i]}</text>`;
    }).join("")}<line x1="0" x2="${w}" y1="${h / 2}" y2="${h / 2}" stroke="var(--line2)"/></svg>`;
  }
  function area(vals, { w = 420, h = 90, color = "var(--down)", zeroTop = false } = {}) {
    if (!vals.length) return "";
    const mn = Math.min(...vals), mx = Math.max(...vals), r = mx - mn || 1;
    const pts = vals.map((v, i) => `${((i / (vals.length - 1)) * w).toFixed(1)},${(h - ((v - mn) / r) * (h - 4) - 2).toFixed(1)}`);
    const base = zeroTop ? 0 : h;
    return `<svg viewBox="0 0 ${w} ${h}" width="100%" preserveAspectRatio="none"><path d="M0,${base} L${pts.join(" L")} L${w},${base} Z" fill="${color}" opacity=".22"/><polyline points="${pts.join(" ")}" fill="none" stroke="${color}" stroke-width="1.4"/></svg>`;
  }
  const H = (t) => `<h4 style="margin:12px 0 6px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px">${t}</h4>`;
  const wait = () => { $("#tabBody").innerHTML = `<div class="empty"><span class="spin"></span> Crunching the numbers…</div>`; };
  const ready = () => EX && R.A && exFor === R.A.symbol;
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  // ---------------- tabs
  const tabs = {
    stats() {
      if (!ready()) return wait();
      const e = EX, A = R.A, f = A.fundamentals || {};
      const perf = ["1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y"].map((k) => `<div><label>${k}</label><b class="${cls(e.performance[k])}">${e.performance[k] == null ? "–" : pct(e.performance[k] * 100, 1)}</b></div>`).join("");
      const m = e.mtf, mtf = ["Daily", "Weekly", "Monthly"].map((k) => `<div class="card" style="text-align:center"><div class="muted" style="font-size:11px">${k}</div><b class="num ${cls(m[k])}" style="font-size:18px">${m[k] == null ? "–" : (m[k] > 0 ? "+" : "") + m[k].toFixed(0)}</b></div>`).join("");
      const hc = e.health, fv = e.fairValue, d = e.distribution;
      $("#tabBody").innerHTML = `${H("Performance")}<div class="perf">${perf}</div>
        ${H(`Multi-timeframe signal · <span class="${m.alignment === "All bullish" ? "up" : m.alignment === "All bearish" ? "down" : "warn"}">${m.alignment}</span>`)}<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px">${mtf}</div>
        ${fv ? `${H("Fair value")}<div class="card"><div style="display:flex;justify-content:space-between;align-items:baseline"><span><b class="num" style="font-size:18px">${price(fv.fair)}</b> <span class="muted">median estimate</span></span><b class="${fv.upside > 0.15 ? "up" : fv.upside < -0.15 ? "down" : "warn"}">${fv.verdict} ${pct(fv.upside * 100, 1)}</b></div>
          ${fv.estimates.map((x) => `<div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;border-top:1px dashed var(--line)" data-tip="${esc(x.note)}"><span class="muted">${esc(x.method)}</span><span class="num">${price(x.value)}</span></div>`).join("")}</div>` : ""}
        ${f.targetLow && f.targetHigh ? `${H("Analyst price-target range")}<div class="card">${targetBar(f, A.price)}</div>` : ""}
        ${hc ? `${H(`Financial health · ${hc.score}/${hc.of} · <span class="${hc.grade === "Strong" ? "up" : hc.grade === "Weak" ? "down" : "warn"}">${hc.grade}</span>`)}<div class="card">${hc.rows.map((r) => `<div style="font-size:12px;padding:2px 0"><span class="${r.pass === null ? "dim" : r.pass ? "up" : "down"}">${r.pass === null ? "○" : r.pass ? "✔" : "✘"}</span> ${esc(r.test)}</div>`).join("")}</div>` : ""}
        ${e.ownership.institutions != null || e.ownership.shortFloat != null ? `<div class="muted" style="font-size:12px;margin-top:6px">Institutions own ${e.ownership.institutions != null ? (e.ownership.institutions * 100).toFixed(0) + "%" : "n/a"} · short interest ${e.ownership.shortFloat != null ? (e.ownership.shortFloat * 100).toFixed(1) + "% of float" : "n/a"}</div>` : ""}
        ${H("Seasonality: average return by calendar month")}${bars(e.seasonality.map((x) => x.avg), MONTHS)}
        <div class="dim" style="font-size:11px">Best month: ${MONTHS[e.seasonality.reduce((b, x, i, a) => ((x.avg ?? -9) > (a[b].avg ?? -9) ? i : b), 0)]} · worst: ${MONTHS[e.seasonality.reduce((b, x, i, a) => ((x.avg ?? 9) < (a[b].avg ?? 9) ? i : b), 0)]} (${e.seasonality[0].n} years of data)</div>
        ${d ? `${H("Daily return distribution (3 years)")}${bars(d.counts.map((c) => c), d.bins.slice(0, -1).map((b, i) => (i % 5 === 0 ? (b * 100).toFixed(1) : "")), { fmt: (v) => v + " days" })}
          <div class="dim num" style="font-size:11px">up days ${(d.upDays * 100).toFixed(0)}% · best ${pct(d.best * 100, 1)} · worst ${pct(d.worst * 100, 1)} · skew ${d.skew} · excess kurtosis ${d.kurt} (fat tails if > 0) · annual vol ${(d.annVol * 100).toFixed(0)}%</div>` : ""}
        ${H(`Drawdown from peak · now ${pct(e.drawdown.current * 100, 1)} · worst ${pct(e.drawdown.max * 100, 1)} (${new Date(e.drawdown.maxDate * 1000).toLocaleDateString()})`)}${area(e.drawdown.dd, { zeroTop: true })}
        ${H(`Rolling 1-month volatility · now ${(e.rollingVol.now * 100).toFixed(0)}% vs average ${(e.rollingVol.avg * 100).toFixed(0)}%`)}${area(e.rollingVol.v, { color: "var(--warn)" })}
        ${H("Engine signal history on this stock")}${e.signals.length ? `<table class="t"><thead><tr><th>Date</th><th>Signal</th><th class="r">Entry</th><th class="r">Exit</th><th class="r">Result</th></tr></thead><tbody>${e.signals.map((x) => `<tr><td>${new Date(x.t * 1000).toLocaleDateString()}</td><td><span class="tag ${x.type === "buy" ? "BUY" : "SHORT"}" style="padding:1px 6px;font-size:10px">${x.type.toUpperCase()}</span>${x.open ? ' <span class="pill" style="font-size:10px;padding:0 5px">open</span>' : ""}</td><td class="r num">${price(x.entry)}</td><td class="r num">${price(x.exit)}</td><td class="r num ${cls(x.ret)}">${pct(x.ret * 100, 1)}</td></tr>`).join("")}</tbody></table>` : '<div class="dim">No signals in the period.</div>'}`;
    },
    levels() {
      if (!ready()) return wait();
      const e = EX, A = R.A, px = A.price, c = e.cone, hp = e.hitProb;
      const row = (k, v, cl = "") => `<div style="display:flex;justify-content:space-between;font-size:12.5px;padding:3px 0;border-bottom:1px dashed var(--line)"><span class="muted">${k}</span><span class="num ${cl}">${price(v)} <span class="dim" style="font-size:10.5px">${v ? pct((v / px - 1) * 100, 1) : ""}</span></span></div>`;
      $("#tabBody").innerHTML = `<div class="hint b-only" style="margin-bottom:8px">Levels are prices where the stock has tended to pause or turn. Tick them in <b>Overlays ▾</b> to draw them on the chart.</div>
        ${H("Expected move (from volatility)")}<div class="kv"><div><label>1 week (±1σ)</label><b>±${price(c.week)}</b></div><div><label>1 month (±1σ)</label><b>±${price(c.month)}</b></div></div>
        ${hp ? `${H(`Odds: target ${price(A.levels.t1)} vs stop ${price(A.levels.stop)} (60 days, 4,000 simulations)`)}<div style="display:flex;height:14px;border-radius:7px;overflow:hidden"><i style="width:${hp.target * 100}%;background:var(--up)" data-tip="Hits target first ${(hp.target * 100).toFixed(0)}%"></i><i style="width:${hp.neither * 100}%;background:#39425a" data-tip="Neither ${(hp.neither * 100).toFixed(0)}%"></i><i style="width:${hp.stop * 100}%;background:var(--down)" data-tip="Hits stop first ${(hp.stop * 100).toFixed(0)}%"></i></div>
          <div class="dim" style="font-size:11px;margin-top:3px"><span class="up">target first ${(hp.target * 100).toFixed(0)}%</span> · <span class="down">stop first ${(hp.stop * 100).toFixed(0)}%</span> · neither ${(hp.neither * 100).toFixed(0)}%. A 2:1 reward/risk only needs a win rate above 33% to pay off over time.</div>` : ""}
        ${H("Volatility cone: likely price ranges")}<table class="t"><thead><tr><th>Horizon</th><th class="r">5%</th><th class="r">25%</th><th class="r">Median</th><th class="r">75%</th><th class="r">95%</th></tr></thead><tbody>${c.table.map((r) => `<tr><td>${r.days} days</td>${["5", "25", "50", "75", "95"].map((k) => `<td class="r num">${price(r[k])}</td>`).join("")}</tr>`).join("")}</tbody></table>
        ${H("Auto support & resistance (swing clusters)")}${e.sr.resistance.slice().reverse().map((x) => row(`Resistance · ${x.touches} touches`, x.price, "down")).join("")}<div style="text-align:center;font-size:11px;padding:4px" class="muted">— price ${price(px)} —</div>${e.sr.support.map((x) => row(`Support · ${x.touches} touches`, x.price, "up")).join("")}
        ${H("Pivot points (from the last session)")}${["R3", "R2", "R1", "P", "S1", "S2", "S3"].map((k) => row(k === "P" ? "Pivot" : k, e.pivots[k], k.startsWith("R") ? "down" : k.startsWith("S") ? "up" : "")).join("")}
        ${H(`Fibonacci retracement (swing ${e.fib.direction}: ${price(e.fib.low)} → ${price(e.fib.high)})`)}${Object.entries(e.fib.levels).map(([k, v]) => row(k, v)).join("")}
        ${H("52-week range")}${row("52-week high", e.hi52, "down")}${row("52-week low", e.lo52, "up")}
        ${H("Recent candlestick patterns")}${e.patterns.slice(-10).reverse().map((p) => `<div style="font-size:12px;padding:2px 0"><span class="${p.bias === "bull" ? "up" : p.bias === "bear" ? "down" : "muted"}">${p.bias === "bull" ? "▲" : p.bias === "bear" ? "▼" : "■"}</span> ${esc(p.name)} <span class="dim">${new Date(p.t * 1000).toLocaleDateString()} @ ${price(p.price)}</span></div>`).join("") || '<div class="dim">None in the last 160 sessions.</div>'}`;
    },
    peers() {
      if (!ready()) return wait();
      const e = EX, A = R.A;
      const corr = Object.fromEntries((e.peerCorr || []).map((x) => [x.symbol, x.corr]));
      $("#tabBody").innerHTML = e.peers.length ? `${H(`${esc(A.sector || "Sector")} peers in this market`)}
        <table class="t"><thead><tr><th>Peer</th><th class="r">Score</th><th class="r">1M</th><th class="r">3M</th><th class="r">1Y</th><th class="r">Vol/day</th><th class="r" data-tip="Correlation of daily returns with ${esc(A.symbol)} over the past year">Corr</th></tr></thead><tbody>
        <tr style="background:var(--accent-bg)"><td><b>${esc(A.symbol)}</b> <span class="dim">(this)</span></td><td class="r num ${cls(A.score)}">${A.score.toFixed(0)}</td><td class="r num ${cls(A.ret1m)}">${pct((A.ret1m || 0) * 100, 1)}</td><td class="r num ${cls(A.ret3m)}">${pct((A.ret3m || 0) * 100, 1)}</td><td class="r num ${cls(A.ret1y)}">${A.ret1y == null ? "–" : pct(A.ret1y * 100, 1)}</td><td class="r num">${(A.atrPct * 100).toFixed(1)}%</td><td class="r">–</td></tr>
        ${e.peers.map((p) => `<tr class="row" data-s="${esc(p.symbol)}"><td><div class="sym">${esc(p.symbol)}<small>${esc(p.name)}</small></div></td><td class="r num ${cls(p.score)}">${p.score.toFixed(0)}</td><td class="r num ${cls(p.ret1m)}">${p.ret1m == null ? "–" : pct(p.ret1m * 100, 1)}</td><td class="r num ${cls(p.ret3m)}">${p.ret3m == null ? "–" : pct(p.ret3m * 100, 1)}</td><td class="r num ${cls(p.ret1y)}">${p.ret1y == null ? "–" : pct(p.ret1y * 100, 1)}</td><td class="r num">${(p.atrPct * 100).toFixed(1)}%</td><td class="r num">${corr[p.symbol] != null ? corr[p.symbol].toFixed(2) : "–"}</td></tr>`).join("")}</tbody></table>
        <div style="display:flex;gap:6px;margin-top:10px"><button class="btn sm" id="aiPeers">✨ AI: compare with top 2 peers</button><span class="dim" style="font-size:11px;align-self:center">Click a peer to open it.</span></div>`
        : `<div class="empty">Peers appear once this stock's market has been scanned on the Command screen.</div>`;
      document.querySelectorAll("#tabBody tr.row").forEach((tr) => (tr.onclick = () => { TS.send({ type: "select", symbol: tr.dataset.s, from: "research" }); location.search = `?symbol=${encodeURIComponent(tr.dataset.s)}${R.market ? "&market=" + R.market : ""}${document.body.classList.contains("embed") ? "&embed=1" : ""}`; }));
      if ($("#aiPeers")) $("#aiPeers").onclick = () => R.aiOutStream("/api/ai/compare", { symbols: [A.symbol, ...e.peers.slice(0, 2).map((p) => p.symbol)] });
    },
    tools() {
      const A = R.A;
      if (!A) return wait();
      const st = R.state || {}, prof = st.profile || {}, lv = A.levels;
      const notes = (st.notes || {})[A.symbol] || "";
      const al = (st.alerts || []).filter((x) => x.symbol === A.symbol);
      const dv = ready() ? EX.dividends : null;
      $("#tabBody").innerHTML = `${H("Position size calculator")}
        <div class="form"><div class="field"><label>Entry price</label><input class="in num" id="pcE" type="number" step="any" value="${+lv.entry.toFixed(4)}"></div>
          <div class="field"><label>Stop-loss</label><input class="in num" id="pcS" type="number" step="any" value="${+lv.stop.toFixed(4)}"></div>
          <div class="field"><label>Account size (${esc(A.currency)})</label><input class="in num" id="pcB" type="number" step="any" value="${Math.round((prof.budget || 10000) / (A.sizing?.fx || 1))}"></div>
          <div class="field"><label>Risk per trade %</label><input class="in num" id="pcR" type="number" step="0.1" value="${prof.riskPerTrade || 1}"></div></div>
        <div class="card" id="pcOut" style="margin-top:8px"></div>
        ${H("Price alerts")}<div style="display:flex;gap:6px"><select class="in" id="alK" style="width:170px"><option value="above">Price rises above</option><option value="below">Price falls below</option><option value="score_above">Score rises above</option><option value="score_below">Score falls below</option></select>
          <input class="in num" id="alV" type="number" step="any" value="${+(A.price * 1.05).toFixed(2)}" style="width:110px"><button class="btn sm primary" id="alAdd">🔔 Add alert</button></div>
        <div id="alList" style="margin-top:6px">${al.map((x) => `<div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;border-bottom:1px dashed var(--line)"><span>${x.triggered ? "✅" : "🔔"} ${esc(x.kind.replace("_", " "))} <b class="num">${price(x.value)}</b></span><button class="btn sm ghost" data-rmal="${esc(x.id)}">✕</button></div>`).join("") || '<div class="dim" style="font-size:12px">No alerts for this symbol. Alerts are checked every minute while the Command screen is open, with a sound and a desktop notification.</div>'}</div>
        ${H("My notes")}<textarea class="in" id="noteBox" rows="4" placeholder="Your thesis, reminders, what would make you sell… (saved automatically)">${esc(notes)}</textarea>
        ${dv ? `${H(`Dividends · trailing 12 months ${dv.ttm ? price(dv.ttm) : "none"}${dv.yield ? ` (${(dv.yield * 100).toFixed(2)}% yield)` : ""}`)}
          ${dv.dividends.length ? `<div style="max-height:160px;overflow:auto"><table class="t"><tbody>${dv.dividends.slice().reverse().map((d) => `<tr><td>${new Date(d.t * 1000).toLocaleDateString()}</td><td class="r num">${price(d.amount)}</td></tr>`).join("")}</tbody></table></div>` : '<div class="dim" style="font-size:12px">No dividends in the last 5 years.</div>'}
          ${dv.splits.length ? `<div class="muted" style="font-size:12px;margin-top:4px">Splits: ${dv.splits.map((s) => `${new Date(s.t * 1000).toLocaleDateString()} (${esc(s.ratio)})`).join(", ")}</div>` : ""}` : ""}
        ${H("Share")}<div style="display:flex;gap:6px"><button class="btn sm" id="cpSum">📋 Copy summary</button><button class="btn sm" id="cpLink">🔗 Copy link</button><button class="btn sm" id="glo">📖 Glossary</button></div>`;
      const calc = () => {
        const e = +$("#pcE").value, s = +$("#pcS").value, b = +$("#pcB").value, r = +$("#pcR").value / 100;
        const risk = Math.abs(e - s);
        if (!(e > 0 && s > 0 && b > 0 && r > 0 && risk > 0)) { $("#pcOut").innerHTML = '<span class="dim">Fill in all four fields.</span>'; return; }
        const q = Math.floor((b * r) / risk), long = s < e;
        $("#pcOut").innerHTML = `<div style="font-size:14px"><b class="num">${q.toLocaleString()}</b> shares ≈ <b class="num">${money(q * e, A.currency)}</b> <span class="muted">(${((q * e) / b * 100).toFixed(1)}% of account)</span></div>
          <div class="muted num" style="font-size:12px;margin-top:4px">Max loss at stop ${money(q * risk, A.currency)} · stop is ${((risk / e) * 100).toFixed(1)}% away = ${(risk / A.atr).toFixed(1)} × ATR</div>
          <div class="num" style="font-size:12px;margin-top:4px">${[1, 2, 3].map((m) => `<span class="up" style="margin-right:10px">${m}R: ${price(long ? e + m * risk : e - m * risk)} (+${money(q * risk * m, "")})</span>`).join("")}</div>`;
      };
      ["#pcE", "#pcS", "#pcB", "#pcR"].forEach((s) => ($(s).oninput = calc));
      calc();
      const saveState = async (patch) => { const st2 = await api("/api/state", { body: patch }); R.state = st2; TS.send({ type: "alerts" }); };
      $("#alAdd").onclick = async () => {
        const v = +$("#alV").value;
        if (!isFinite(v)) return;
        const alerts = [...(R.state.alerts || []), { id: Math.random().toString(36).slice(2, 9), symbol: A.symbol, kind: $("#alK").value, value: v, active: true, created: Date.now() }];
        await saveState({ alerts });
        TS.toast("Alert added");
        try { if ("Notification" in window && Notification.permission === "default") Notification.requestPermission(); } catch {}
        tabs.tools();
      };
      document.querySelectorAll("[data-rmal]").forEach((b) => (b.onclick = async () => { await saveState({ alerts: (R.state.alerts || []).filter((x) => x.id !== b.dataset.rmal) }); tabs.tools(); }));
      let nt;
      $("#noteBox").oninput = () => { clearTimeout(nt); nt = setTimeout(() => saveState({ notes: { ...(R.state.notes || {}), [A.symbol]: $("#noteBox").value } }), 600); };
      $("#cpSum").onclick = () => UX.copy(`${A.name} (${A.symbol}) ${price(A.price)} ${A.currency}\nSignal: ${A.signal} (score ${A.score.toFixed(0)}, confidence ${A.confidence.toFixed(0)}%) · ${A.setup}\nEntry ${price(lv.entryLow)}–${price(lv.entryHigh)} · stop ${price(lv.stop)} · targets ${price(lv.t1)} / ${price(lv.t2)}\n${A.reasons.slice(0, 4).map((r) => "• " + r.text).join("\n")}\n(TradeScope research, not financial advice)`, "Summary copied");
      $("#cpLink").onclick = () => UX.copy(`${location.origin}/research.html?symbol=${encodeURIComponent(A.symbol)}`, "Link copied");
      $("#glo").onclick = () => UX.showGlossary();
    },
  };
  function targetBar(f, px) {
    const lo = Math.min(f.targetLow, px), hi = Math.max(f.targetHigh, px), pos = (v) => ((v - lo) / (hi - lo || 1)) * 100;
    return `<div style="position:relative;height:30px;margin:6px 8px">
      <div style="position:absolute;top:12px;left:${pos(f.targetLow)}%;right:${100 - pos(f.targetHigh)}%;height:6px;border-radius:3px;background:linear-gradient(90deg,var(--down),var(--warn),var(--up))"></div>
      <div style="position:absolute;top:4px;left:calc(${pos(px)}% - 1px);width:2px;height:22px;background:var(--text)" data-tip="Price now ${price(px)}"></div>
      <div style="position:absolute;top:6px;left:calc(${pos(f.targetMean)}% - 6px);width:12px;height:18px;border-radius:3px;border:2px solid var(--accent)" data-tip="Average target ${price(f.targetMean)}"></div></div>
      <div style="display:flex;justify-content:space-between;font-size:11px" class="num"><span class="down">low ${price(f.targetLow)}</span><span>avg ${price(f.targetMean)} (${pct((f.targetMean / px - 1) * 100, 1)})</span><span class="up">high ${price(f.targetHigh)}</span></div>`;
  }

  return { afterDraw, markers, onLoad, tabs };
})();
