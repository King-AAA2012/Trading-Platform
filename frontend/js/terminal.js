// Pro mode: the CasuallyHedge Terminal. A Bloomberg-style Launchpad of linked panels, driven by function codes typed in
// the command line ("AAPL GP", "WEI", "NVDA DES", "SECT", "ECO" + Enter = <GO>). Built only from free, public data.
(() => {
  const root = document.getElementById("term");
  if (!root) return;
  const { api, esc, price, pct, cls, big } = TS;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  // ---------------------------------------------------------------- formatting
  const fx = (v, d = 2) => (v == null || !isFinite(v) ? "–" : Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
  const pf = (v, d = 2) => (v == null || !isFinite(v) ? "–" : pct(v * 100, d));          // fraction -> "+1.23%"
  const pp = (v, d = 2) => (v == null || !isFinite(v) ? "–" : pct(+v, d));               // percent -> "+1.23%"
  const heat = (v, s = 3) => {                                                            // v in percent
    if (v == null || !isFinite(v)) return "";
    const a = Math.min(Math.abs(v) / s, 1);
    return `background:rgba(${v >= 0 ? "31,210,134" : "255,84,112"},${(0.1 + a * 0.5).toFixed(2)})`;
  };
  const fill = (v, s = 3) => {
    const a = v == null ? 0 : Math.min(Math.abs(v) / s, 1);
    return v == null ? "rgba(135,145,166,.25)" : `rgba(${v >= 0 ? "31,210,134" : "255,84,112"},${(0.22 + a * 0.68).toFixed(2)})`;
  };
  const hms = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const dmy = (t) => new Date(typeof t === "number" ? t * 1000 : t).toLocaleDateString([], { day: "2-digit", month: "short", year: "2-digit" });
  const sym = (s, name) => `<span class="tsym" data-sym="${esc(s)}">${esc(s)}</span>${name ? `<small class="tname">${esc(name)}</small>` : ""}`;
  const seg = (id, opts, on) => `<span class="tseg" data-seg="${id}">${opts.map(([v, l]) => `<button data-v="${esc(v)}" class="${String(v) === String(on) ? "on" : ""}">${esc(l)}</button>`).join("")}</span>`;
  const empty = (m) => `<div class="empty">${m}</div>`;
  const market = () => (window.CMD && CMD.state && CMD.state.lastMarket) || "us";

  // ---------------------------------------------------------------- settings (per browser, mirrored to the account)
  const DEF = { page: "launchpad", sec: "AAPL", pages: {}, opts: {}, ws: [], hist: [] };
  let cfg = (() => { try { return { ...DEF, ...JSON.parse(localStorage.getItem("ch-term") || "{}") }; } catch { return { ...DEF }; } })();
  function save() {
    try { localStorage.setItem("ch-term", JSON.stringify(cfg)); } catch {}
    clearTimeout(save.t);
    save.t = setTimeout(() => api("/api/state", { body: { terminal: cfg } }).catch(() => {}), 1500);
  }

  // ---------------------------------------------------------------- tiny SVG charts
  function lines(series, opts = {}) {            // series: [{name, color, values:[...], dash}], x labels optional
    const W = opts.w || 600, H = opts.h || 240, P = { l: 40, r: 10, t: 10, b: 22 };
    const all = series.flatMap((s) => s.values.filter((v) => v != null && isFinite(v)));
    if (!all.length) return empty("No data");
    let mn = Math.min(...all), mx = Math.max(...all);
    if (opts.zero) { mn = Math.min(mn, 0); mx = Math.max(mx, 0); }
    const pad = (mx - mn) * 0.08 || 1;
    mn -= pad; mx += pad;
    const n = Math.max(...series.map((s) => s.values.length));
    const X = (i) => P.l + (i / Math.max(n - 1, 1)) * (W - P.l - P.r), Y = (v) => P.t + (1 - (v - mn) / (mx - mn)) * (H - P.t - P.b);
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => mn + f * (mx - mn));
    const grid = ticks.map((v) => `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)" stroke-width="1"/><text x="${P.l - 5}" y="${Y(v) + 3}" text-anchor="end" font-size="10" fill="var(--dim)">${(opts.fmt || ((x) => x.toFixed(1)))(v)}</text>`).join("");
    const zero = opts.zero && mn < 0 && mx > 0 ? `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--line2)" stroke-width="1.2"/>` : "";
    const xl = (opts.labels || []).map((l, i, a) => (i % Math.ceil(a.length / 6) === 0 || i === a.length - 1) ? `<text x="${X(i)}" y="${H - 6}" text-anchor="middle" font-size="10" fill="var(--dim)">${esc(l)}</text>` : "").join("");
    const paths = series.map((s, k) => {
      const pts = s.values.map((v, i) => (v == null || !isFinite(v) ? null : `${X(i).toFixed(1)},${Y(v).toFixed(1)}`)).filter(Boolean).join(" ");
      return `<polyline data-k="${k}" points="${pts}" fill="none" stroke="${s.color}" stroke-width="${s.width || 1.8}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ""} opacity="${s.dim ? 0.18 : 1}"/>`;
    }).join("");
    return `<svg class="tsvg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" data-n="${n}" data-l="${P.l}" data-r="${P.r}" data-w="${W}">${grid}${zero}${paths}${xl}<line class="tcross" x1="0" x2="0" y1="${P.t}" y2="${H - P.b}" stroke="var(--muted)" stroke-dasharray="3,3" opacity="0"/></svg>`;
  }
  function drawLines(box, series, opts) {               // size the chart to its box so text never stretches
    box.innerHTML = lines(series, { ...opts, w: Math.max(260, box.clientWidth), h: Math.max(120, box.clientHeight) });
  }
  function hoverLines(box, series, labels, fmt) {        // crosshair + values tooltip over a lines() chart
    const svg = $(".tsvg", box);
    if (!svg) return;
    let tip = $(".ttip", box);
    if (!tip) { tip = document.createElement("div"); tip.className = "ttip"; box.appendChild(tip); }
    svg.onmousemove = (e) => {
      const r = svg.getBoundingClientRect(), W = +svg.dataset.w, L = +svg.dataset.l, R = +svg.dataset.r, n = +svg.dataset.n;
      const xv = ((e.clientX - r.left) / r.width) * W;
      const i = Math.max(0, Math.min(n - 1, Math.round(((xv - L) / (W - L - R)) * (n - 1))));
      const x = L + (i / Math.max(n - 1, 1)) * (W - L - R);
      const c = $(".tcross", svg); c.setAttribute("x1", x); c.setAttribute("x2", x); c.setAttribute("opacity", 1);
      const rows = series.map((s) => [s, s.values[i]]).filter(([s, v]) => v != null && !s.dim).sort((a, b) => b[1] - a[1]);
      tip.innerHTML = `<b>${esc(labels ? labels[i] : "")}</b>` + rows.map(([s, v]) => `<div><span class="sw" style="background:${s.color}"></span>${esc(s.name)} <span class="${cls(v)}">${fmt(v)}</span></div>`).join("");
      tip.style.display = "block";
      const bx = box.getBoundingClientRect();
      tip.style.left = Math.min(e.clientX - bx.left + 14, bx.width - 190) + "px";
      tip.style.top = Math.max(4, e.clientY - bx.top - 20) + "px";
    };
    svg.onmouseleave = () => { tip.style.display = "none"; $(".tcross", svg).setAttribute("opacity", 0); };
  }
  function bars(items, opts = {}) {                      // horizontal bars: [{label, value, sub, sym}]
    const mx = Math.max(...items.map((i) => Math.abs(i.value || 0)), 1e-9);
    return `<div class="tbars">${items.map((i) => `<div class="tbr" ${i.sym ? `data-sym="${esc(i.sym)}"` : ""} ${i.key ? `data-key="${esc(i.key)}"` : ""}>
      <span class="tbl">${esc(i.label)}${i.sub ? `<small>${esc(i.sub)}</small>` : ""}</span>
      <span class="tbt"><i style="${(i.value || 0) >= 0 ? "left:50%" : `left:${50 - (Math.abs(i.value) / mx) * 50}%`};width:${(Math.abs(i.value || 0) / mx) * 50}%;background:${(i.value || 0) >= 0 ? "var(--up)" : "var(--down)"}"></i></span>
      <span class="tbv ${cls(i.value)}">${(opts.fmt || pf)(i.value)}</span></div>`).join("")}</div>`;
  }
  const PAL = ["#5b8cff", "#1fd286", "#f5b942", "#ff5470", "#9b7bff", "#38bdf8", "#f472b6", "#a3e635", "#fb923c", "#2dd4bf", "#e879f9", "#facc15", "#94a3b8"];

  // ---------------------------------------------------------------- lightweight-charts (price charts)
  const LWBASE = {
    layout: { background: { color: "transparent" }, textColor: "#8791a6", fontFamily: "Cascadia Mono, Consolas, ui-monospace, monospace", fontSize: 10, attributionLogo: false },
    grid: { vertLines: { color: "rgba(29,37,51,.6)" }, horzLines: { color: "rgba(29,37,51,.6)" } },
    rightPriceScale: { borderColor: "#1d2533" }, timeScale: { borderColor: "#1d2533", rightOffset: 3 }, crosshair: { mode: 1 }, autoSize: true,
  };
  function chartIn(el, extra = {}) { return LightweightCharts.createChart(el, { ...LWBASE, ...extra }); }
  const anCache = {};
  async function analyzeOf(s) {
    const hit = anCache[s];
    if (hit && Date.now() - hit.t < 60000) return hit.d;
    const d = await api(`/api/analyze/${encodeURIComponent(s)}?market=${market()}`);
    anCache[s] = { t: Date.now(), d };
    return d;
  }

  // ================================================================ function directory
  const F = {};
  const fn = (code, def) => (F[code] = { code, ...def });

  // ---------------------------------------------------------------- markets
  fn("WEI", { name: "World equity indices", group: "Markets", tip: "Every major stock index by region: today’s move, 1 week, 1 month, year to date and 1 year.", every: 30000,
    async run(b, x) {
      const d = await x.wrap(api("/api/t/wei"));
      x.sub(`${d.regions.reduce((n, g) => n + g.rows.length, 0)} indices`);
      b.innerHTML = `<table class="t tt"><thead><tr><th>Index</th><th class="r">Last</th><th class="r">Chg</th><th class="r">%Chg</th><th class="r">1W</th><th class="r">1M</th><th class="r">YTD</th><th class="r">1Y</th><th>30d</th></tr></thead><tbody>` +
        d.regions.map((g) => `<tr class="tgrp"><td colspan="9">${esc(g.region)} <span class="${cls(g.avg)}">${pp(g.avg)}</span></td></tr>` + g.rows.map((r) => `<tr class="row" data-sym="${esc(r.symbol)}">
          <td><b>${esc(r.name)}</b><small class="tname">${esc(r.country)} · ${esc(r.symbol)}${r.state === "REGULAR" ? ' · <span class="up">open</span>' : ""}</small></td>
          <td class="r">${fx(r.price)}</td><td class="r ${cls(r.change)}">${fx(r.change)}</td><td class="r" style="${heat(r.changePct, 2)}">${pp(r.changePct)}</td>
          <td class="r ${cls(r["1W"])}">${pf(r["1W"], 1)}</td><td class="r ${cls(r["1M"])}">${pf(r["1M"], 1)}</td><td class="r ${cls(r.YTD)}">${pf(r.YTD, 1)}</td><td class="r ${cls(r["1Y"])}">${pf(r["1Y"], 1)}</td>
          <td>${TS.spark(r.spark, 70, 18)}</td></tr>`).join("")).join("") + "</tbody></table>";
    } });

  fn("IMAP", { name: "Intraday market map", group: "Markets", tip: "Global market intraday return by region and country, or by sector and stock. Green is up, red is down; brighter means a bigger move. Click a slice to load it.", every: 30000,
    async run(b, x) {
      const mode = x.opt("by", "region");
      const ring = (inner, cx, cy) => {                  // inner: [{label, value, children:[{label, value, sym}]}]
        const n = inner.reduce((k, g) => k + Math.max(g.children.length, 1), 0);
        let a = 0, out = "";
        const P = (r, t) => [cx + r * Math.sin(t), cy - r * Math.cos(t)];
        const arc = (r0, r1, a0, a1) => {
          const L = a1 - a0 > Math.PI ? 1 : 0, [x0, y0] = P(r1, a0), [x1, y1] = P(r1, a1), [x2, y2] = P(r0, a1), [x3, y3] = P(r0, a0);
          return `M${x0},${y0} A${r1},${r1} 0 ${L} 1 ${x1},${y1} L${x2},${y2} A${r0},${r0} 0 ${L} 0 ${x3},${y3} Z`;
        };
        const lab = (r, t, txt, v, big2) => { const [lx, ly] = P(r, t); return `<text x="${lx}" y="${ly}" text-anchor="middle" font-size="${big2 ? 12 : 10}" fill="var(--text)" pointer-events="none">${esc(txt)}<tspan x="${lx}" dy="12" font-size="10" fill="var(--text)" opacity=".85">${pp(v)}</tspan></text>`; };
        inner.forEach((g) => {
          const span = (Math.max(g.children.length, 1) / n) * Math.PI * 2, a0 = a;
          out += `<path d="${arc(70, 128, a0, a0 + span)}" fill="${fill(g.value, 1.5)}" stroke="var(--panel)" stroke-width="2"><title>${esc(g.label)} ${pp(g.value)}</title></path>`;
          g.children.forEach((c, i) => {
            const c0 = a0 + (i / g.children.length) * span, c1 = c0 + span / g.children.length;
            out += `<path class="tslice" data-sym="${esc(c.sym || "")}" d="${arc(132, 205, c0, c1)}" fill="${fill(c.value, 2)}" stroke="var(--panel)" stroke-width="1.5"><title>${esc(c.label)} ${pp(c.value)}</title></path>`;
            if (c1 - c0 > 0.2) out += lab(168, (c0 + c1) / 2, c.label.length > 12 ? c.label.slice(0, 11) + "…" : c.label, c.value);
          });
          if (span > 0.35) out += lab(99, a0 + span / 2, g.label.length > 14 ? g.label.slice(0, 13) + "…" : g.label, g.value, true);
          a += span;
        });
        return out;
      };
      let inner, title, ctr;
      if (mode === "sector") {
        const d = await x.wrap(api(`/api/t/sectors?market=${market()}&days=10`));
        inner = d.sectors.map((s) => ({ label: s.sector, value: s.day * 100, children: (d.members[s.sector] || []).slice(0, 6).map((m) => ({ label: m.symbol, value: m.changePct, sym: m.symbol })) }));
        title = d.name + (d.fallback ? " (sectors from US large caps)" : "");
        const all = d.sectors.filter((s) => s.day != null);
        ctr = all.length ? all.reduce((k, s) => k + s.day * s.n, 0) / all.reduce((k, s) => k + s.n, 0) * 100 : null;
      } else {
        const d = await x.wrap(api("/api/t/wei"));
        inner = d.regions.map((g) => {
          const by = {};
          g.rows.forEach((r) => { (by[r.country] ||= []).push(r); });
          return { label: g.region, value: g.avg, children: Object.entries(by).map(([c, rs]) => ({ label: c, sym: rs[0].symbol, value: rs.reduce((k, r) => k + (r.changePct || 0), 0) / rs.length })) };
        });
        title = "Global market intraday return by region";
        const all = d.regions.flatMap((g) => g.rows).filter((r) => r.changePct != null);
        ctr = all.length ? all.reduce((k, r) => k + r.changePct, 0) / all.length : null;
      }
      x.sub(title);
      b.innerHTML = `<div class="ttool">${seg("by", [["region", "By region"], ["sector", "By sector"]], mode)}<span class="spacer"></span><span class="dim" style="font-size:11px">brighter = bigger move · click to load</span></div>
        <svg class="timap" viewBox="0 0 420 420" preserveAspectRatio="xMidYMid meet">${ring(inner, 210, 210)}
        <text x="210" y="204" text-anchor="middle" font-size="12" fill="var(--muted)">${mode === "sector" ? "Market" : "World"}</text>
        <text x="210" y="226" text-anchor="middle" font-size="20" font-weight="700" fill="${ctr == null ? "var(--muted)" : ctr >= 0 ? "var(--up)" : "var(--down)"}">${pp(ctr)}</text></svg>`;
      x.onSeg("by", (v) => x.setOpt("by", v));
    } });

  fn("MOST", { name: "Most active & movers", group: "Markets", tip: "Today’s biggest gainers and losers, the most traded, unusual volume (traded far more than usual) and new 52-week highs and lows in the market you picked.", every: 60000,
    async run(b, x) {
      const d = await x.wrap(api(`/api/t/most?market=${market()}`));
      const tab = x.opt("tab", "gainers");
      x.sub(`${d.name} · ${d.adv} up / ${d.dec} down`);
      const rows = d[tab] || [];
      b.innerHTML = `<div class="ttool">${seg("tab", [["gainers", "Gainers"], ["losers", "Losers"], ["active", "Most traded"], ["unusual", "Unusual volume"], ["highs", "52w highs"], ["lows", "52w lows"]], tab)}</div>
        ${rows.length ? `<table class="t tt"><thead><tr><th>Symbol</th><th class="r">Last</th><th class="r">%Chg</th><th class="r">Volume</th><th class="r">Rel vol</th><th class="r">Value</th><th>Signal</th></tr></thead><tbody>${rows.map((r) => `<tr class="row" data-sym="${esc(r.symbol)}">
          <td>${sym(r.symbol, r.name)}</td><td class="r">${price(r.price)}</td><td class="r" style="${heat(r.changePct)}">${pp(r.changePct)}</td><td class="r">${big(r.volume)}</td>
          <td class="r ${r.relVol >= 2 ? "warn" : ""}">${r.relVol == null ? "–" : r.relVol.toFixed(1) + "×"}</td><td class="r">${big(r.value)}</td><td><span class="sig ${TS.sigClass(r.signal)}">${esc(r.signal)}</span></td></tr>`).join("")}</tbody></table>` : empty("Nothing here today.")}`;
      x.onSeg("tab", (v) => x.setOpt("tab", v));
    } });

  fn("MOV", { name: "Index movers", group: "Markets", tip: "Which stocks pushed the market up or down today, weighted by company size (a 1% move in a giant counts more than in a small company).", every: 60000,
    async run(b, x) {
      const d = await x.wrap(api(`/api/t/most?market=${market()}`));
      x.sub(`${d.name} · ${d.adv} advancing, ${d.dec} declining`);
      const col = (rs, t) => `<div style="flex:1;min-width:0"><h4 class="th4">${t}</h4>${bars(rs.map((r) => ({ label: r.symbol, sub: pp(r.changePct), value: r.contrib, sym: r.symbol })), { fmt: (v) => (v == null ? "–" : (v > 0 ? "+" : "") + v.toFixed(3) + " pts") })}</div>`;
      const tot = d.adv + d.dec || 1;
      b.innerHTML = `<div class="tad"><span class="up">${d.adv} ▲</span><div class="tadbar"><i style="width:${(d.adv / tot) * 100}%"></i></div><span class="down">▼ ${d.dec}</span></div>
        <div style="display:flex;gap:14px">${col(d.contribUp, "Pushing up")}${col(d.contribDown, "Pulling down")}</div><div class="dim" style="font-size:10.5px;margin-top:6px">Contribution = company’s share of the group’s total market value × its % move.</div>`;
    } });

  fn("MKT", { name: "Market sentiment & breadth", group: "Markets", tip: "A fear-and-greed reading built from volatility, momentum, safe-haven demand, junk bonds, gold and breadth, plus how many stocks are above their 200-day average.", every: 300000,
    async run(b, x) {
      const d = await x.wrap(api(`/api/overview?market=${market()}`));
      const fg = d.fearGreed || {}, br = d.breadth || {};
      x.sub(d.market || "");
      const s = fg.score ?? 50;
      b.innerHTML = `<div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap"><div class="tgauge"><svg viewBox="0 0 200 110"><path d="M10,100 A90,90 0 0 1 190,100" fill="none" stroke="url(#tgg)" stroke-width="14" stroke-linecap="round"/>
        <defs><linearGradient id="tgg"><stop offset="0" stop-color="#ff5470"/><stop offset=".5" stop-color="#f5b942"/><stop offset="1" stop-color="#1fd286"/></linearGradient></defs>
        <line x1="100" y1="100" x2="${100 + 78 * Math.cos(Math.PI * (1 - s / 100))}" y2="${100 - 78 * Math.sin(Math.PI * (1 - s / 100))}" stroke="var(--text)" stroke-width="3" stroke-linecap="round"/><circle cx="100" cy="100" r="5" fill="var(--text)"/></svg>
        <div style="text-align:center;margin-top:-8px"><b style="font-size:22px" class="mono">${fx(s, 0)}</b><div class="muted">${esc(fg.label || "")}</div></div></div>
        <div style="flex:1;min-width:220px">${(fg.components || []).map((c) => `<div class="tkv"><span>${esc(c.name)}</span><b class="mono">${fx(c.score, 0)}</b><small class="dim">${esc(c.detail)}</small></div>`).join("")}</div></div>
        <div class="kv" style="grid-template-columns:repeat(4,1fr);margin-top:10px"><div><label>Above 200-day</label><b>${pf(br.above200, 0)}</b></div><div><label>Rated bullish</label><b class="up">${pf(br.bull, 0)}</b></div>
        <div><label>New highs / lows</label><b>${br.newHighs ?? "–"} / ${br.newLows ?? "–"}</b></div><div><label>Average RSI</label><b>${fx(br.avgRsi, 0)}</b></div></div>`;
    } });

  // ---------------------------------------------------------------- sectors
  const memo = {};                                     // panels on one page share a request (DES, ANR, EE, HDS all read the same data)
  const shared = (key, ttl, make) => { const h = memo[key]; if (h && Date.now() - h.t < ttl) return h.p; const pr = make(); memo[key] = { t: Date.now(), p: pr }; pr.catch(() => delete memo[key]); return pr; };
  const secData = (days) => shared(`secd:${market()}:${days}`, 20000, () => api(`/api/t/sectors?market=${market()}&days=${days}`));
  fn("SECT", { name: "Sector performance", group: "Sectors", tip: "How each sector did over the period you pick (equal-weighted across the sector’s stocks in this market). Click a sector to see its stocks.", every: 120000,
    async run(b, x) {
      const per = x.opt("per", "day"), drill = x.opt("drill", null);
      const d = await x.wrap(secData(30));
      x.sub(d.name + (d.fallback ? " · sectors from US large caps" : ""));
      if (drill && d.members[drill]) {
        b.innerHTML = `<div class="ttool"><button class="btn sm" data-back>← All sectors</button><b>${esc(drill)}</b></div>
          <table class="t tt"><thead><tr><th>Stock</th><th class="r">%Chg</th><th class="r">Score</th></tr></thead><tbody>${d.members[drill].map((m) => `<tr class="row" data-sym="${esc(m.symbol)}"><td>${sym(m.symbol, m.name)}</td><td class="r" style="${heat(m.changePct)}">${pp(m.changePct)}</td><td class="r">${fx(m.score, 0)}</td></tr>`).join("")}</tbody></table>`;
        $("[data-back]", b).onclick = () => x.setOpt("drill", null);
        return;
      }
      const key = { day: "day", "1W": "1W", "1M": "1M", "3M": "3M", "6M": "6M", YTD: "YTD" }[per];
      const items = d.sectors.map((s) => ({ label: s.sector, sub: `${s.n} stocks · ${s.adv}▲ ${s.dec}▼`, value: s[key], key: s.sector })).sort((a, b2) => (b2.value ?? -9) - (a.value ?? -9));
      b.innerHTML = `<div class="ttool">${seg("per", [["day", "1D"], ["1W", "1W"], ["1M", "1M"], ["3M", "3M"], ["6M", "6M"], ["YTD", "YTD"]], per)}</div>${bars(items)}`;
      x.onSeg("per", (v) => x.setOpt("per", v));
      $$(".tbr[data-key]", b).forEach((r) => (r.onclick = () => x.setOpt("drill", r.dataset.key)));
    } });

  fn("SECG", { name: "Sector returns day by day", group: "Sectors", tip: "Cumulative return of every sector, day by day, over the window you pick. Hover to read each day; click a name in the legend to hide or show it.", every: 300000,
    async run(b, x) {
      const days = +x.opt("days", 30), hidden = x.opt("hidden", []);
      const d = await x.wrap(secData(days));
      x.sub(`${d.name} · last ${days} trading days`);
      const series = d.sectors.map((s, i) => ({ name: s.sector, color: PAL[i % PAL.length], values: d.cum[s.sector] || [], dim: hidden.includes(s.sector) }));
      const labels = d.dates.map((t) => t.slice(5));
      b.innerHTML = `<div class="ttool">${seg("days", [[10, "10D"], [30, "30D"], [60, "60D"], [120, "6M"], [250, "1Y"]], days)}</div>
        <div class="tchart" style="height:calc(100% - 64px)"></div>
        <div class="tlegend">${series.map((s) => `<span data-n="${esc(s.name)}" class="${s.dim ? "off" : ""}"><i class="sw" style="background:${s.color}"></i>${esc(s.name)} <b class="${cls(s.values[s.values.length - 1])}">${pp(s.values[s.values.length - 1], 1)}</b></span>`).join("")}</div>`;
      drawLines($(".tchart", b), series, { zero: true, labels, fmt: (v) => v.toFixed(1) + "%" });
      hoverLines($(".tchart", b), series, d.dates, (v) => pp(v, 2));
      x.onSeg("days", (v) => x.setOpt("days", +v));
      $$(".tlegend span", b).forEach((s) => (s.onclick = () => { const n = s.dataset.n; x.setOpt("hidden", hidden.includes(n) ? hidden.filter((h) => h !== n) : [...hidden, n]); }));
    } });

  fn("SECD", { name: "Sector heat by day", group: "Sectors", tip: "Each sector’s move on each of the last trading days. Green squares are up days, red are down days; brighter means a bigger move.", every: 300000,
    async run(b, x) {
      const days = +x.opt("days", 10);
      const d = await x.wrap(secData(days));
      x.sub(`${d.name} · daily % change`);
      const dates = d.dates.slice(1);
      b.innerHTML = `<div class="ttool">${seg("days", [[5, "5D"], [10, "10D"], [15, "15D"], [20, "20D"]], days)}</div>
        <table class="t tt theat"><thead><tr><th>Sector</th>${dates.map((t) => `<th class="r">${t.slice(5)}</th>`).join("")}<th class="r">Total</th></tr></thead><tbody>${d.sectors.map((s) => {
          const v = d.daily[s.sector] || [], tot = (d.cum[s.sector] || []).slice(-1)[0];
          return `<tr><td><b>${esc(s.sector)}</b></td>${v.map((p) => `<td class="r" style="${heat(p, 2.5)}">${p == null ? "–" : p.toFixed(2)}</td>`).join("")}<td class="r" style="${heat(tot, 6)}"><b>${pp(tot, 1)}</b></td></tr>`;
        }).join("")}</tbody></table>`;
      x.onSeg("days", (v) => x.setOpt("days", +v));
    } });

  fn("RRG", { name: "Sector rotation map", group: "Sectors", tip: "Where each sector sits in the rotation cycle versus the whole market: Leading (strong and getting stronger), Weakening, Lagging, Improving. Tails show the last six weeks.", every: 600000,
    async run(b, x) {
      const d = await x.wrap(secData(30));
      x.sub(d.name + " · relative strength vs momentum, weekly");
      const pts = d.rotation.flatMap((r) => r.tail);
      const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
      const span = Math.max(...xs.map((v) => Math.abs(v - 100)), ...ys.map((v) => Math.abs(v - 100)), 2) * 1.15;
      const W = 460, H = 360, X = (v) => 30 + ((v - (100 - span)) / (2 * span)) * (W - 40), Y = (v) => 10 + (1 - (v - (100 - span)) / (2 * span)) * (H - 30);
      const q = (x1, y1, x2, y2, c, t, tx, ty) => `<rect x="${x1}" y="${y1}" width="${x2 - x1}" height="${y2 - y1}" fill="${c}" opacity=".07"/><text x="${tx}" y="${ty}" font-size="11" fill="${c}" opacity=".9">${t}</text>`;
      const mx = X(100), my = Y(100);
      b.innerHTML = `<svg class="tsvg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
        ${q(mx, 10, W - 10, my, "#1fd286", "Leading", W - 70, 24)}${q(mx, my, W - 10, H - 20, "#f5b942", "Weakening", W - 84, H - 26)}
        ${q(30, my, mx, H - 20, "#ff5470", "Lagging", 36, H - 26)}${q(30, 10, mx, my, "#5b8cff", "Improving", 36, 24)}
        <line x1="30" x2="${W - 10}" y1="${my}" y2="${my}" stroke="var(--line2)"/><line x1="${mx}" x2="${mx}" y1="10" y2="${H - 20}" stroke="var(--line2)"/>
        <text x="${W / 2}" y="${H - 4}" text-anchor="middle" font-size="10" fill="var(--dim)">relative strength →</text>
        ${d.rotation.map((r, i) => { const c = PAL[i % PAL.length], t = r.tail.filter((p) => p[0] != null && p[1] != null); if (!t.length) return ""; const h = t[t.length - 1];
          return `<polyline points="${t.map((p) => `${X(p[0])},${Y(p[1])}`).join(" ")}" fill="none" stroke="${c}" stroke-width="1.6" opacity=".75"/><circle cx="${X(h[0])}" cy="${Y(h[1])}" r="5" fill="${c}"><title>${esc(r.sector)}</title></circle>
            <text x="${X(h[0]) + 7}" y="${Y(h[1]) + 4}" font-size="10.5" fill="var(--text)">${esc(r.sector)}</text>`; }).join("")}</svg>`;
    } });

  // ---------------------------------------------------------------- portfolio & lists
  fn("MON", { name: "My portfolio monitor", group: "Portfolio", tip: "Your holdings (or your watchlist if you have none): weight in the portfolio, price, today’s change, profit/loss and year-to-date return.", every: 20000,
    async run(b, x) {
      const d = await x.wrap(api("/api/t/portfolio"));
      x.sub(d.source === "holdings" ? `${d.rows.length} holdings · ${d.base}` : "Watchlist (add holdings to see weights and P/L)");
      b.innerHTML = (d.total ? `<div class="tsum"><span>Value <b>${fx(d.total, 0)} ${esc(d.base)}</b></span><span>Today <b class="${cls(d.day)}">${fx(d.day, 0)}</b></span><span>Total P/L <b class="${cls(d.pnl)}">${fx(d.pnl, 0)}</b></span></div>` : "") +
        `<table class="t tt"><thead><tr><th>Ticker</th><th class="r">%Wgt</th><th class="r">Curr px</th><th class="r">1D chg</th><th class="r">1D %</th><th class="r">P/L</th><th class="r">YTD</th><th>30d</th></tr></thead><tbody>${d.rows.map((r) => `<tr class="row" data-sym="${esc(r.symbol)}">
          <td>${sym(r.symbol, r.name)}</td><td class="r">${pf(r.weight, 1).replace("+", "")}</td><td class="r">${price(r.price)}</td><td class="r ${cls(r.change)}">${price(r.change)}</td>
          <td class="r" style="${heat(r.changePct)}">${pp(r.changePct)}</td><td class="r ${cls(r.pnlBase)}">${r.pnlBase == null ? "–" : fx(r.pnlBase, 0)}</td><td class="r ${cls(r.YTD)}">${pf(r.YTD, 1)}</td><td>${TS.spark(r.spark, 64, 16)}</td></tr>`).join("")}</tbody></table>`;
    } });

  fn("WS", { name: "Worksheet monitor", group: "Portfolio", tip: "Your own monitor: add any symbol from any market and watch price, bid/ask, volume, valuation and returns side by side.", every: 15000,
    async run(b, x) {
      if (!cfg.ws.length) cfg.ws = ((window.CMD && CMD.state && CMD.state.watchlist) || ["AAPL", "MSFT", "NVDA"]).slice(0, 12);
      const d = await x.wrap(api(`/api/t/quotes?symbols=${encodeURIComponent(cfg.ws.join(","))}`));
      x.sub(`${cfg.ws.length} symbols`);
      b.innerHTML = `<div class="ttool"><div class="search" style="width:260px"><span class="ico">⌕</span><input class="in" id="wsAdd" placeholder="Add any symbol…" autocomplete="off"><div class="results" id="wsRes"></div></div></div>
        <table class="t tt"><thead><tr><th>Symbol</th><th class="r">Last</th><th class="r">%Chg</th><th class="r">Bid</th><th class="r">Ask</th><th class="r">Volume</th><th class="r">Mkt cap</th><th class="r">P/E</th><th class="r">Div%</th><th>52-week range</th><th class="r">1M</th><th class="r">YTD</th><th></th></tr></thead><tbody>${d.rows.map((r) => {
          const pos = r.hi52 && r.lo52 && r.hi52 > r.lo52 ? ((r.price - r.lo52) / (r.hi52 - r.lo52)) * 100 : null;
          return `<tr class="row" data-sym="${esc(r.symbol)}"><td>${sym(r.symbol, r.name)}</td><td class="r">${price(r.price)}</td><td class="r" style="${heat(r.changePct)}">${pp(r.changePct)}</td><td class="r">${price(r.bid)}</td><td class="r">${price(r.ask)}</td>
            <td class="r">${big(r.volume)}</td><td class="r">${big(r.marketCap)}</td><td class="r">${fx(r.pe, 1)}</td><td class="r">${fx(r.divYield, 2)}</td>
            <td>${pos == null ? "–" : `<span class="trange"><i style="left:${Math.max(0, Math.min(100, pos))}%"></i></span>`}</td><td class="r ${cls(r["1M"])}">${pf(r["1M"], 1)}</td><td class="r ${cls(r.YTD)}">${pf(r.YTD, 1)}</td>
            <td><button class="btn sm ghost" data-rm="${esc(r.symbol)}" title="Remove">✕</button></td></tr>`; }).join("")}</tbody></table>`;
      TS.bindSearch($("#wsAdd", b), $("#wsRes", b), (s) => { if (!cfg.ws.includes(s)) cfg.ws.push(s); save(); x.refresh(); }, { global: false });
      $$("[data-rm]", b).forEach((btn) => (btn.onclick = (e) => { e.stopPropagation(); cfg.ws = cfg.ws.filter((s) => s !== btn.dataset.rm); save(); x.refresh(); }));
    } });

  fn("CORR", { name: "Correlation matrix", group: "Portfolio", tip: "How closely your symbols move together (1 = in lockstep, 0 = unrelated, −1 = opposite). Low correlations mean better diversification.", every: 900000,
    async run(b, x) {
      const days = +x.opt("days", 126);
      const list = (cfg.ws.length ? cfg.ws : []).slice(0, 16);
      const d = await x.wrap(api(`/api/t/corr?days=${days}${list.length ? "&symbols=" + encodeURIComponent(list.join(",")) : ""}`));
      x.sub(`${d.symbols.length} symbols · ${d.days} trading days`);
      b.innerHTML = `<div class="ttool">${seg("days", [[63, "3M"], [126, "6M"], [252, "1Y"]], days)}</div><div style="overflow:auto"><table class="t tt theat"><thead><tr><th></th>${d.symbols.map((s) => `<th class="r">${esc(s)}</th>`).join("")}<th class="r">Vol/yr</th></tr></thead><tbody>${d.symbols.map((s, i) => `<tr><td>${sym(s)}</td>${d.matrix[i].map((v, j) => `<td class="r" style="${i === j ? "" : heat(v * 100, 100)}">${i === j ? "1" : v.toFixed(2)}</td>`).join("")}<td class="r">${pf(d.vol[i], 0).replace("+", "")}</td></tr>`).join("")}</tbody></table></div>`;
      x.onSeg("days", (v) => x.setOpt("days", +v));
    } });

  // ---------------------------------------------------------------- security: charts & prices
  fn("GP", { name: "Price chart", group: "Security", sec: true, tip: "Candlestick chart with 20/50/200-day averages, Bollinger bands, volume, RSI and the algorithm’s buy/short/exit signals.", every: 60000,
    async run(b, x) {
      const rng = x.opt("rng", "1Y"), ov = x.opt("ov", ["ema", "sig", "vol"]);
      const a = await x.wrap(analyzeOf(x.sec));
      const s = a.series;
      x.sub(`${a.name || x.sec} · ${esc(a.signal)} · score ${fx(a.score, 0)}`);
      const n = { "1M": 22, "3M": 66, "6M": 130, YTD: null, "1Y": 252, "2Y": 504, "5Y": 1300 }[rng];
      let from = Math.max(0, s.t.length - (n || 252));
      if (rng === "YTD") { const y = new Date().getFullYear(); from = s.t.findIndex((t) => new Date(t * 1000).getFullYear() === y); if (from < 0) from = 0; }
      const T = (i) => s.t[i];
      const rows = (arr) => arr.slice(from).map((v, k) => ({ time: T(from + k), value: v })).filter((p) => p.value != null && isFinite(p.value) && p.value !== 0);
      const candles = s.t.slice(from).map((t, k) => ({ time: t, open: s.o[from + k], high: s.h[from + k], low: s.l[from + k], close: s.c[from + k] }));
      const volume = s.t.slice(from).map((t, k) => ({ time: t, value: s.v[from + k], color: s.c[from + k] >= s.o[from + k] ? "rgba(31,210,134,.35)" : "rgba(255,84,112,.35)" }));
      const key = [x.sec, rng, ov.join()].join("|");
      if (x.state.chart && x.state.key === key) {            // live refresh: update the data, keep the user's zoom
        x.state.cs.setData(candles);
        if (x.state.vs) x.state.vs.setData(volume);
        x.state.rs.setData(rows(s.rsi));
        return;
      }
      b.innerHTML = `<div class="ttool">${seg("rng", ["1M", "3M", "6M", "YTD", "1Y", "2Y", "5Y"].map((v) => [v, v]), rng)}<span class="spacer"></span>
        ${[["ema", "MAs 20/50/200"], ["bb", "Bollinger"], ["sig", "Signals"], ["vol", "Volume"]].map(([k, l]) => `<label class="check"><input type="checkbox" data-ov="${k}" ${ov.includes(k) ? "checked" : ""}> ${l}</label>`).join("")}</div>
        <div class="tlw" style="height:calc(72% - 30px)"></div><div class="tlw2" style="height:28%"></div>`;
      x.dispose();
      const c1 = chartIn($(".tlw", b)), c2 = chartIn($(".tlw2", b), { timeScale: { visible: false, borderColor: "#1d2533" } });
      const cs = c1.addCandlestickSeries({ upColor: "#1fd286", downColor: "#ff5470", borderVisible: false, wickUpColor: "#1fd286", wickDownColor: "#ff5470" });
      cs.setData(candles);
      const ln = (data2, color, w = 1.3, style = 0) => { const l = c1.addLineSeries({ color, lineWidth: w, lineStyle: style, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }); l.setData(data2); };
      if (ov.includes("ema")) { ln(rows(s.e20), "#5b8cff"); ln(rows(s.e50), "#f5b942"); ln(rows(s.e200), "#9b7bff", 1.6); }
      if (ov.includes("bb")) { ln(rows(s.bbu), "rgba(135,145,166,.6)", 1, 2); ln(rows(s.bbl), "rgba(135,145,166,.6)", 1, 2); }
      let vs = null;
      if (ov.includes("vol")) {
        vs = c1.addHistogramSeries({ priceScaleId: "v", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
        c1.priceScale("v").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
        vs.setData(volume);
      }
      if (ov.includes("sig")) cs.setMarkers(s.marks.filter((m) => m.t >= s.t[from]).map((m) => ({ time: m.t, position: m.type === "buy" ? "belowBar" : "aboveBar", color: m.type === "buy" ? "#1fd286" : m.type === "short" ? "#ff5470" : "#8791a6", shape: m.type === "buy" ? "arrowUp" : m.type === "short" ? "arrowDown" : "circle", text: m.type === "buy" ? "B" : m.type === "short" ? "S" : "x" })));
      const rs = c2.addLineSeries({ color: "#38bdf8", lineWidth: 1.4, priceLineVisible: false });
      rs.setData(rows(s.rsi));
      [70, 30].forEach((lv) => rs.createPriceLine({ price: lv, color: "rgba(135,145,166,.5)", lineWidth: 1, lineStyle: 2, axisLabelVisible: true }));
      c1.timeScale().fitContent();
      c1.timeScale().subscribeVisibleLogicalRangeChange((rg) => rg && c2.timeScale().setVisibleLogicalRange(rg));
      x.state = { chart: c1, chart2: c2, key, cs, vs, rs };
      x.onSeg("rng", (v) => x.setOpt("rng", v));
      $$("[data-ov]", b).forEach((c) => (c.onchange = () => x.setOpt("ov", $$("[data-ov]", b).filter((k) => k.checked).map((k) => k.dataset.ov))));
    } });

  fn("GIP", { name: "Intraday chart", group: "Security", sec: true, tip: "Today’s price in 5-minute steps (or the last 5 days in 15-minute steps), with yesterday’s close as a dotted line.", every: 30000,
    async run(b, x) {
      const span = x.opt("span", "1d");
      const h = await x.wrap(api(`/api/history/${encodeURIComponent(x.sec)}?range=${span}&interval=${span === "1d" ? "5m" : "15m"}`));
      const last = h.c[h.c.length - 1], pc = h.meta.prevClose;
      x.sub(`${h.meta.name} · ${price(last)} ${esc(h.meta.currency)} ${pc ? `(${pp((last / pc - 1) * 100)})` : ""}`);
      b.innerHTML = `<div class="ttool">${seg("span", [["1d", "Today"], ["5d", "5 days"]], span)}</div><div class="tlw" style="height:calc(100% - 30px)"></div>`;
      x.dispose();
      const c = chartIn($(".tlw", b), { timeScale: { timeVisible: true, borderColor: "#1d2533" } });
      const up = !pc || last >= pc;
      const ar = c.addAreaSeries({ lineColor: up ? "#1fd286" : "#ff5470", topColor: up ? "rgba(31,210,134,.25)" : "rgba(255,84,112,.25)", bottomColor: "rgba(0,0,0,0)", lineWidth: 2, priceLineVisible: false });
      ar.setData(h.t.map((t, i) => ({ time: t, value: h.c[i] })));
      if (pc) ar.createPriceLine({ price: pc, color: "#8791a6", lineWidth: 1, lineStyle: 2, title: "prev close" });
      const v = c.addHistogramSeries({ priceScaleId: "v", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false, color: "rgba(91,140,255,.35)" });
      c.priceScale("v").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
      v.setData(h.t.map((t, i) => ({ time: t, value: h.v[i] })));
      c.timeScale().fitContent();
      x.state = { chart: c };
      x.onSeg("span", (vv) => x.setOpt("span", vv));
    } });

  fn("HP", { name: "Historical prices", group: "Security", sec: true, tip: "Open, high, low, close and volume for each day, week or month, newest first.", every: 300000,
    async run(b, x) {
      const per = x.opt("per", "1d");
      const h = await x.wrap(api(`/api/history/${encodeURIComponent(x.sec)}?range=${{ "1d": "6mo", "1wk": "2y", "1mo": "10y" }[per]}&interval=${per}`));
      x.sub(`${h.meta.name} · ${esc(h.meta.currency)}`);
      const n = h.t.length;
      b.innerHTML = `<div class="ttool">${seg("per", [["1d", "Daily"], ["1wk", "Weekly"], ["1mo", "Monthly"]], per)}</div><table class="t tt"><thead><tr><th>Date</th><th class="r">Open</th><th class="r">High</th><th class="r">Low</th><th class="r">Close</th><th class="r">%Chg</th><th class="r">Volume</th></tr></thead><tbody>${
        h.t.map((t, i) => i).reverse().slice(0, 150).map((i) => `<tr><td>${dmy(h.t[i])}</td><td class="r">${price(h.o[i])}</td><td class="r">${price(h.h[i])}</td><td class="r">${price(h.l[i])}</td><td class="r"><b>${price(h.c[i])}</b></td>
          <td class="r ${cls(i ? h.c[i] - h.c[i - 1] : 0)}">${i ? pp((h.c[i] / h.c[i - 1] - 1) * 100) : "–"}</td><td class="r">${big(h.v[i])}</td></tr>`).join("")}</tbody></table>${n > 150 ? '<div class="dim" style="font-size:11px">Showing the latest 150 rows.</div>' : ""}`;
      x.onSeg("per", (v) => x.setOpt("per", v));
    } });

  // ---------------------------------------------------------------- security: fundamentals
  const secOf = (s) => shared("sec:" + s, 30000, () => api(`/api/t/sec/${encodeURIComponent(s)}`));
  const kv = (pairs) => `<div class="tkvg">${pairs.filter(([, v]) => v !== undefined).map(([l, v, c]) => `<div><label>${esc(l)}</label><b class="${c || ""}">${v ?? "–"}</b></div>`).join("")}</div>`;
  fn("DES", { name: "Company description", group: "Security", sec: true, tip: "What the company does, its key numbers (valuation, margins, debt, ownership, short interest) and its leadership.", every: 600000,
    async run(b, x) {
      const d = await x.wrap(secOf(x.sec));
      const p = d.price || {}, a = d.assetProfile || {}, sd = d.summaryDetail || {}, ks = d.defaultKeyStatistics || {}, f = d.financialData || {}, ce = d.calendarEvents || {};
      x.sub(`${p.longName || p.shortName || x.sec} · ${p.exchangeName || ""}`);
      const ed = ((ce.earnings || {}).earningsDate || [])[0];
      b.innerHTML = `<div class="tdes"><div class="tdh"><b style="font-size:15px">${esc(p.longName || p.shortName || x.sec)}</b><span class="muted">${esc([a.sector, a.industry, a.country].filter(Boolean).join(" · "))}</span>
          <span class="dim">${a.fullTimeEmployees ? fx(a.fullTimeEmployees, 0) + " employees · " : ""}${a.website ? `<a href="${esc(a.website)}" target="_blank" rel="noopener noreferrer">${esc(a.website.replace(/^https?:\/\//, ""))}</a>` : ""}</span></div>
        ${a.longBusinessSummary ? `<p class="tsumm">${esc(a.longBusinessSummary)}</p>` : ""}
        ${kv([["Price", `${price(p.regularMarketPrice)} ${esc(p.currency || "")}`], ["Market cap", big(p.marketCap)], ["Enterprise value", big(ks.enterpriseValue)], ["P/E (ttm)", fx(sd.trailingPE, 1)],
          ["Forward P/E", fx(sd.forwardPE ?? ks.forwardPE, 1)], ["PEG", fx(ks.pegRatio, 2)], ["Price / book", fx(ks.priceToBook, 2)], ["Price / sales", fx(sd.priceToSalesTrailing12Months, 2)],
          ["EV / EBITDA", fx(ks.enterpriseToEbitda, 1)], ["Dividend yield", sd.dividendYield != null ? pf(sd.dividendYield).replace("+", "") : "–"], ["Payout ratio", sd.payoutRatio != null ? pf(sd.payoutRatio, 0).replace("+", "") : "–"],
          ["Beta", fx(sd.beta ?? ks.beta, 2)], ["52-week range", `${price(sd.fiftyTwoWeekLow)} – ${price(sd.fiftyTwoWeekHigh)}`], ["50 / 200-day avg", `${price(sd.fiftyDayAverage)} / ${price(sd.twoHundredDayAverage)}`],
          ["Shares out", big(ks.sharesOutstanding)], ["Float", big(ks.floatShares)], ["Short % of float", ks.shortPercentOfFloat != null ? pf(ks.shortPercentOfFloat, 1).replace("+", "") : "–"], ["Days to cover", fx(ks.shortRatio, 1)],
          ["Insiders own", ks.heldPercentInsiders != null ? pf(ks.heldPercentInsiders, 1).replace("+", "") : "–"], ["Institutions own", ks.heldPercentInstitutions != null ? pf(ks.heldPercentInstitutions, 1).replace("+", "") : "–"],
          ["Gross margin", pf(f.grossMargins, 1), cls(f.grossMargins)], ["Operating margin", pf(f.operatingMargins, 1), cls(f.operatingMargins)], ["Net margin", pf(f.profitMargins, 1), cls(f.profitMargins)],
          ["Return on equity", pf(f.returnOnEquity, 1), cls(f.returnOnEquity)], ["Revenue growth", pf(f.revenueGrowth, 1), cls(f.revenueGrowth)], ["Earnings growth", pf(f.earningsGrowth, 1), cls(f.earningsGrowth)],
          ["Cash", big(f.totalCash)], ["Debt", big(f.totalDebt)], ["Debt / equity", fx(f.debtToEquity, 0)], ["Current ratio", fx(f.currentRatio, 2)], ["Free cash flow", big(f.freeCashflow)],
          ["Next earnings", ed ? dmy(ed) : "–"], ["Ex-dividend", sd.exDividendDate ? dmy(sd.exDividendDate) : "–"]])}
        ${(a.companyOfficers || []).length ? `<h4 class="th4">Management</h4><table class="t tt"><tbody>${a.companyOfficers.map((o) => `<tr><td><b>${esc(o.name)}</b></td><td class="muted">${esc(o.title || "")}</td><td class="r">${o.totalPay ? big(o.totalPay) : ""}</td></tr>`).join("")}</tbody></table>` : ""}</div>`;
    } });

  fn("FA", { name: "Financial analysis", group: "Security", sec: true, tip: "Income statement, cash flow and balance sheet for the last years or quarters, with margins, growth and returns worked out for you.", every: 3600000,
    async run(b, x) {
      const per = x.opt("per", "annual");
      const d = await x.wrap(api(`/api/t/fa/${encodeURIComponent(x.sec)}?period=${per}`));
      x.sub(`${per === "annual" ? "Annual" : "Quarterly"} · ${esc(d.currency || "")}`);
      const hd = d.dates.map((t) => `<th class="r">${per === "annual" ? "FY" + t.slice(0, 4) : t.slice(0, 7)}</th>`).join("");
      const sp = (vals) => { const v = vals.filter((z) => z != null); return v.length > 1 ? TS.spark(vals.map((z) => z ?? 0), 50, 14) : ""; };
      b.innerHTML = `<div class="ttool">${seg("per", [["annual", "Annual"], ["quarterly", "Quarterly"]], per)}</div><table class="t tt"><thead><tr><th>${esc(d.currency || "")}</th>${hd}<th>Trend</th></tr></thead><tbody>
        ${d.rows.map((r) => `<tr><td>${esc(r.label)}</td>${r.values.map((v) => `<td class="r ${v < 0 ? "down" : ""}">${r.key.includes("EPS") ? fx(v, 2) : big(v)}</td>`).join("")}<td>${sp(r.values)}</td></tr>`).join("")}
        <tr class="tgrp"><td colspan="${d.dates.length + 2}">Ratios</td></tr>
        ${d.ratios.map((r) => `<tr><td>${esc(r.label)}</td>${r.values.map((v) => `<td class="r ${r.pct ? cls(v) : ""}">${r.pct ? pf(v, 1) : fx(v, 2)}</td>`).join("")}<td>${sp(r.values)}</td></tr>`).join("")}</tbody></table>`;
      x.onSeg("per", (v) => x.setOpt("per", v));
    } });

  const RVC = [["cap", "Mkt cap", big], ["pe", "P/E", (v) => fx(v, 1)], ["fpe", "Fwd P/E", (v) => fx(v, 1)], ["pb", "P/B", (v) => fx(v, 1)], ["evEbitda", "EV/EBITDA", (v) => fx(v, 1)],
    ["evRev", "EV/Sales", (v) => fx(v, 1)], ["gm", "Gross mgn", (v) => pf(v, 1)], ["om", "Op mgn", (v) => pf(v, 1)], ["nm", "Net mgn", (v) => pf(v, 1)], ["roe", "ROE", (v) => pf(v, 1)],
    ["revG", "Rev growth", (v) => pf(v, 1)], ["divY", "Div %", (v) => fx(v, 2)], ["chg52", "52w %", (v) => pp(v, 1)], ["beta", "Beta", (v) => fx(v, 2)]];
  fn("RV", { name: "Relative valuation (comparables)", group: "Security", sec: true, tip: "The company next to its closest peers on valuation, profitability and growth, with the peer median and how far above or below it the company trades.", every: 1800000,
    async run(b, x) {
      const peers = x.opt("peers", "");
      const sort = x.opt("sort", "cap");
      const d = await x.wrap(api(`/api/t/comps/${encodeURIComponent(x.sec)}${peers ? "?peers=" + encodeURIComponent(peers) : ""}`));
      x.sub(`Comparable valuation analysis · ${d.rows.length - 1} peers`);
      const rows = [...d.rows].sort((a, b2) => (a.symbol === x.sec ? -1 : b2.symbol === x.sec ? 1 : (b2[sort] ?? -1e18) - (a[sort] ?? -1e18)));
      b.innerHTML = `<div class="ttool"><input class="in" id="rvPeers" style="width:300px;padding:3px 8px" placeholder="Custom peers, e.g. MSFT, GOOGL, META (blank = automatic)" value="${esc(peers)}"><button class="btn sm" id="rvGo">Use peers</button></div>
        <div style="overflow:auto"><table class="t tt trv"><thead><tr><th>Company</th><th class="r">Price</th>${RVC.map(([k, l]) => `<th class="r" data-sort="${k}">${l}${sort === k ? " ▼" : ""}</th>`).join("")}<th>Rating</th></tr></thead><tbody>
        ${rows.map((r) => `<tr class="row ${r.symbol === x.sec ? "tsubj" : ""}" data-sym="${esc(r.symbol)}"><td>${sym(r.symbol, r.name)}</td><td class="r">${price(r.price)}</td>${RVC.map(([k, , f]) => `<td class="r">${f(r[k])}</td>`).join("")}<td class="dim">${esc(r.rating || "")}</td></tr>`).join("")}
        <tr class="tgrp"><td>Peer median</td><td></td>${RVC.map(([k, , f]) => `<td class="r">${f(d.median[k])}</td>`).join("")}<td></td></tr>
        <tr class="tgrp"><td>Peer mean</td><td></td>${RVC.map(([k, , f]) => `<td class="r">${f(d.mean[k])}</td>`).join("")}<td></td></tr>
        <tr><td><b>${esc(x.sec)} vs median</b></td><td></td>${RVC.map(([k]) => `<td class="r ${["pe", "fpe", "pb", "evEbitda", "evRev", "beta"].includes(k) ? cls(-(d.premium[k] || 0)) : cls(d.premium[k])}">${k === "cap" ? "" : pf(d.premium[k], 0)}</td>`).join("")}<td></td></tr></tbody></table></div>
        <div class="dim" style="font-size:10.5px;margin-top:4px">For valuation multiples (P/E, P/B, EV/…) a positive premium means more expensive than peers; for margins and growth it means better.</div>`;
      $("#rvGo", b).onclick = () => x.setOpt("peers", $("#rvPeers", b).value.trim());
      $$("[data-sort]", b).forEach((h) => (h.onclick = () => x.setOpt("sort", h.dataset.sort)));
    } });

  fn("ANR", { name: "Analyst recommendations", group: "Security", sec: true, tip: "What analysts covering the stock recommend, how that changed over the last months, their price targets and the latest upgrades and downgrades.", every: 1800000,
    async run(b, x) {
      const d = await x.wrap(secOf(x.sec));
      const f = d.financialData || {}, tr = ((d.recommendationTrend || {}).trend || []), ud = ((d.upgradeDowngradeHistory || {}).history || []), px = f.currentPrice || (d.price || {}).regularMarketPrice;
      x.sub(`${f.numberOfAnalystOpinions || "–"} analysts · consensus ${esc((f.recommendationKey || "–").replace("_", " "))}`);
      const K = [["strongBuy", "Strong buy", "#1fd286"], ["buy", "Buy", "#7fe0b3"], ["hold", "Hold", "#8791a6"], ["sell", "Sell", "#ff9aa9"], ["strongSell", "Strong sell", "#ff5470"]];
      const lbl = { "0m": "Now", "-1m": "1 mo ago", "-2m": "2 mo ago", "-3m": "3 mo ago" };
      const tgt = (v) => (v && px ? `${price(v)} <small class="${cls(v - px)}">${pp((v / px - 1) * 100, 1)}</small>` : "–");
      b.innerHTML = `${kv([["Price", price(px)], ["Mean target", tgt(f.targetMeanPrice)], ["High target", tgt(f.targetHighPrice)], ["Low target", tgt(f.targetLowPrice)], ["Score (1 = strong buy, 5 = sell)", fx(f.recommendationMean, 2)]])}
        <h4 class="th4">Recommendation trend</h4>${tr.map((t) => { const tot = K.reduce((k, [c]) => k + (t[c] || 0), 0) || 1;
          return `<div class="tstack"><span>${lbl[t.period] || t.period}</span><div>${K.map(([c, l, col]) => t[c] ? `<i style="width:${(t[c] / tot) * 100}%;background:${col}" title="${l}: ${t[c]}">${t[c]}</i>` : "").join("")}</div></div>`; }).join("")}
        <div class="tlegend">${K.map(([, l, col]) => `<span><i class="sw" style="background:${col}"></i>${l}</span>`).join("")}</div>
        <h4 class="th4">Latest rating changes</h4><table class="t tt"><tbody>${ud.slice(0, 15).map((u) => `<tr><td>${u.epochGradeDate ? dmy(u.epochGradeDate) : ""}</td><td><b>${esc(u.firm)}</b></td>
          <td class="${u.action === "up" ? "up" : u.action === "down" ? "down" : "muted"}">${esc({ up: "Upgrade", down: "Downgrade", main: "Maintain", init: "Initiate", reit: "Reiterate" }[u.action] || u.action || "")}</td><td>${esc(u.fromGrade ? u.fromGrade + " → " : "")}${esc(u.toGrade || "")}</td>
          <td class="r">${u.currentPriceTarget ? price(u.currentPriceTarget) : ""}</td></tr>`).join("") || '<tr><td class="empty">No recent changes.</td></tr>'}</tbody></table>`;
    } });

  fn("EE", { name: "Earnings estimates & surprises", group: "Security", sec: true, tip: "Reported earnings per share versus what analysts expected (beats and misses), and the forecasts for the coming quarters and years.", every: 1800000,
    async run(b, x) {
      const d = await x.wrap(secOf(x.sec));
      const hist = ((d.earningsHistory || {}).history || []), trend = ((d.earningsTrend || {}).trend || []), ce = d.calendarEvents || {};
      const ed = ((ce.earnings || {}).earningsDate || [])[0];
      x.sub(`Next report ${ed ? dmy(ed) : "–"}`);
      const mx = Math.max(...hist.flatMap((h) => [Math.abs(h.epsActual || 0), Math.abs(h.epsEstimate || 0)]), 0.01);
      const P = { "0q": "This quarter", "+1q": "Next quarter", "0y": "This year", "+1y": "Next year" };
      b.innerHTML = `<h4 class="th4">Last four quarters (EPS)</h4><div class="tee">${hist.map((h) => `<div><div class="teb"><i class="est" style="height:${(Math.abs(h.epsEstimate || 0) / mx) * 100}%"></i><i class="act ${(h.surprisePercent || 0) >= 0 ? "beat" : "miss"}" style="height:${(Math.abs(h.epsActual || 0) / mx) * 100}%"></i></div>
          <b class="mono">${fx(h.epsActual, 2)}</b><small class="dim">est ${fx(h.epsEstimate, 2)}</small><small class="${cls(h.surprisePercent)}">${h.surprisePercent != null ? pf(h.surprisePercent, 1) : ""}</small><small class="dim">${h.quarter ? dmy(h.quarter) : ""}</small></div>`).join("") || empty("No history")}</div>
        <div class="tlegend"><span><i class="sw" style="background:#3a4560"></i>Estimate</span><span><i class="sw" style="background:var(--up)"></i>Beat</span><span><i class="sw" style="background:var(--down)"></i>Miss</span></div>
        <h4 class="th4">Forecasts</h4><table class="t tt"><thead><tr><th>Period</th><th class="r">EPS est.</th><th class="r">Low–high</th><th class="r">Analysts</th><th class="r">Growth</th><th class="r">Revenue est.</th><th class="r">EPS 90d ago</th><th class="r">Revisions ↑/↓ (30d)</th></tr></thead><tbody>
        ${trend.filter((t) => P[t.period]).map((t) => { const e = t.earningsEstimate || {}, rv = t.revenueEstimate || {}, et = t.epsTrend || {}, rr = t.epsRevisions || {};
          return `<tr><td>${P[t.period]}<small class="tname">${esc(t.endDate || "")}</small></td><td class="r"><b>${fx(e.avg, 2)}</b></td><td class="r">${fx(e.low, 2)}–${fx(e.high, 2)}</td><td class="r">${e.numberOfAnalysts ?? "–"}</td>
            <td class="r ${cls(t.growth)}">${pf(t.growth, 1)}</td><td class="r">${big(rv.avg)}</td><td class="r">${fx(et["90daysAgo"], 2)}</td><td class="r"><span class="up">${rr.upLast30days ?? 0}</span> / <span class="down">${rr.downLast30days ?? 0}</span></td></tr>`; }).join("")}</tbody></table>`;
    } });

  fn("HDS", { name: "Holders & insiders", group: "Security", sec: true, tip: "Who owns the stock: the biggest institutions and funds, the split between insiders and institutions, and recent insider buying and selling.", every: 3600000,
    async run(b, x) {
      const d = await x.wrap(secOf(x.sec));
      const tab = x.opt("tab", "inst");
      const mh = d.majorHoldersBreakdown || {}, inst = ((d.institutionOwnership || {}).ownershipList || []), fund = ((d.fundOwnership || {}).ownershipList || []), ins = ((d.insiderTransactions || {}).transactions || []);
      x.sub(`${mh.institutionsCount ? fx(mh.institutionsCount, 0) + " institutions" : ""}`);
      const own = (rs) => `<table class="t tt"><thead><tr><th>Holder</th><th class="r">% held</th><th class="r">Shares</th><th class="r">Value</th><th class="r">Change</th><th>Reported</th></tr></thead><tbody>${rs.map((o) => `<tr><td><b>${esc(o.organization)}</b></td><td class="r">${pf(o.pctHeld, 2).replace("+", "")}</td><td class="r">${big(o.position)}</td><td class="r">${big(o.value)}</td><td class="r ${cls(o.pctChange)}">${pf(o.pctChange, 1)}</td><td class="dim">${o.reportDate ? dmy(o.reportDate) : ""}</td></tr>`).join("") || '<tr><td class="empty">No data</td></tr>'}</tbody></table>`;
      b.innerHTML = `${kv([["Insiders", pf(mh.insidersPercentHeld, 1).replace("+", "")], ["Institutions", pf(mh.institutionsPercentHeld, 1).replace("+", "")], ["Institutions (of float)", pf(mh.institutionsFloatPercentHeld, 1).replace("+", "")]])}
        <div class="ttool" style="margin-top:6px">${seg("tab", [["inst", "Institutions"], ["fund", "Funds"], ["ins", "Insider trades"]], tab)}</div>
        ${tab === "inst" ? own(inst) : tab === "fund" ? own(fund) : `<table class="t tt"><thead><tr><th>Date</th><th>Insider</th><th>Role</th><th>Transaction</th><th class="r">Shares</th><th class="r">Value</th></tr></thead><tbody>${ins.map((t) => `<tr><td>${t.startDate ? dmy(t.startDate) : ""}</td><td><b>${esc(t.filerName)}</b></td><td class="muted">${esc(t.filerRelation || "")}</td><td class="${/sale|sold/i.test(t.transactionText || "") ? "down" : /purchase|buy/i.test(t.transactionText || "") ? "up" : ""}" style="white-space:normal">${esc(t.transactionText || "")}</td><td class="r">${big(t.shares)}</td><td class="r">${big(t.value)}</td></tr>`).join("") || '<tr><td class="empty">No insider trades reported.</td></tr>'}</tbody></table>`}`;
      x.onSeg("tab", (v) => x.setOpt("tab", v));
    } });

  fn("DVD", { name: "Dividends & splits", group: "Security", sec: true, tip: "Every dividend paid over the last ten years, the yearly total, the current yield, five-year growth and stock splits.", every: 3600000,
    async run(b, x) {
      const d = await x.wrap(api(`/api/t/dvd/${encodeURIComponent(x.sec)}`));
      x.sub(`${esc(d.currency || "")} · yield ${d.yield != null ? pf(d.yield, 2).replace("+", "") : "–"}`);
      const mx = Math.max(...d.yearly.map((y) => y.total), 1e-9);
      b.innerHTML = `${kv([["Last 12 months", fx(d.ttm, 3)], ["Yield", d.yield != null ? pf(d.yield, 2).replace("+", "") : "–"], ["5-year growth / yr", pf(d.cagr5, 1), cls(d.cagr5)], ["Payments shown", d.dividends.length]])}
        ${d.yearly.length ? `<div class="tvb">${d.yearly.map((y) => `<div title="${y.year}: ${fx(y.total, 3)}"><i style="height:${(y.total / mx) * 100}%"></i><small>${String(y.year).slice(2)}</small></div>`).join("")}</div>` : empty("No dividends in the last ten years.")}
        <table class="t tt"><thead><tr><th>Ex-date</th><th class="r">Amount</th></tr></thead><tbody>${d.dividends.map((v) => `<tr><td>${dmy(v.date)}</td><td class="r">${fx(v.amount, 4)}</td></tr>`).join("")}</tbody></table>
        ${d.splits.length ? `<h4 class="th4">Splits</h4>${d.splits.map((s) => `<div>${dmy(s.date)} · <b>${esc(s.ratio)}</b></div>`).join("")}` : ""}`;
    } });

  fn("SEAG", { name: "Seasonality", group: "Security", sec: true, tip: "How the price did in each calendar month over the last ten years, the average month and how often each month was positive.", every: 3600000,
    async run(b, x) {
      const d = await x.wrap(api(`/api/t/seas/${encodeURIComponent(x.sec)}`));
      x.sub(`${d.years[0]}–${d.years[d.years.length - 1]} monthly returns`);
      const M = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      b.innerHTML = `<div style="overflow:auto"><table class="t tt theat"><thead><tr><th>Year</th>${M.map((m) => `<th class="r">${m}</th>`).join("")}</tr></thead><tbody>
        ${[...d.years].reverse().map((y) => `<tr><td>${y}</td>${d.grid[y].map((v) => `<td class="r" style="${heat(v == null ? null : v * 100, 8)}">${v == null ? "" : (v * 100).toFixed(1)}</td>`).join("")}</tr>`).join("")}
        <tr class="tgrp"><td>Average</td>${d.avg.map((v) => `<td class="r ${cls(v)}">${v == null ? "" : (v * 100).toFixed(1)}</td>`).join("")}</tr>
        <tr class="tgrp"><td>% up</td>${d.hit.map((v) => `<td class="r">${v == null ? "" : Math.round(v * 100)}</td>`).join("")}</tr></tbody></table></div>`;
    } });

  fn("BETA", { name: "Beta & regression", group: "Security", sec: true, tip: "How much the stock tends to move with its market (beta 1.2 = 20% more than the market), from two years of weekly returns.", every: 3600000,
    async run(b, x) {
      const d = await x.wrap(api(`/api/t/beta/${encodeURIComponent(x.sec)}`));
      x.sub(`vs ${d.bench} · ${d.n} weeks`);
      const pts = d.points.filter((p) => p[0] != null && p[1] != null), W = 320, H = 220;
      const m = Math.max(...pts.flatMap((p) => [Math.abs(p[0]), Math.abs(p[1])]), 0.01) * 1.1;
      const X = (v) => 20 + ((v + m) / (2 * m)) * (W - 30), Y = (v) => 10 + (1 - (v + m) / (2 * m)) * (H - 20);
      b.innerHTML = `<div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center"><svg class="tsvg" viewBox="0 0 ${W} ${H}" style="max-width:340px;flex:1">
        <line x1="20" x2="${W - 10}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--line2)"/><line x1="${X(0)}" x2="${X(0)}" y1="10" y2="${H - 10}" stroke="var(--line2)"/>
        ${pts.map((p) => `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="2.4" fill="var(--accent)" opacity=".55"/>`).join("")}
        <line x1="${X(-m)}" y1="${Y(-m * d.beta)}" x2="${X(m)}" y2="${Y(m * d.beta)}" stroke="var(--warn)" stroke-width="2"/></svg>
        <div style="flex:1;min-width:180px">${kv([["Beta", fx(d.beta, 2)], ["Alpha / yr", pf(d.alpha, 1), cls(d.alpha)], ["R²", fx(d.r2, 2)], ["Correlation", fx(d.corr, 2)], ["Volatility / yr", pf(d.vol, 0).replace("+", "")], [`${d.bench} vol / yr`, pf(d.benchVol, 0).replace("+", "")]])}</div></div>`;
    } });

  // ---------------------------------------------------------------- options
  fn("OMON", { name: "Option monitor", group: "Options", sec: true, tip: "The option chain: calls on the left, puts on the right, around the current price. Shows volume, open interest, implied volatility, put/call ratio and max pain. US-listed stocks and ETFs.", every: 60000,
    async run(b, x) {
      const date = x.opt("date", null), all = x.opt("all", false);
      const d = await x.wrap(api(`/api/t/options/${encodeURIComponent(x.sec)}${date ? "?date=" + date : ""}`));
      x.state.opt = d;
      const s = d.summary;
      x.sub(`${price(d.spot)} ${esc(d.currency || "")} · exp ${dmy(d.expiry)}`);
      const strikes = [...new Set([...d.calls, ...d.puts].map((o) => o.strike))].sort((a, b2) => a - b2);
      const ci = strikes.findIndex((k) => k >= d.spot);
      const show = all ? strikes : strikes.slice(Math.max(0, ci - 12), ci + 12);
      const C = Object.fromEntries(d.calls.map((o) => [o.strike, o])), Pm = Object.fromEntries(d.puts.map((o) => [o.strike, o]));
      const leg = (o, side) => (o ? `<td class="r ${o.itm ? "titm" : ""}">${price(o.last)}</td><td class="r ${o.itm ? "titm" : ""} ${cls(o.chg)}">${o.chg == null ? "–" : o.chg.toFixed(1)}</td><td class="r ${o.itm ? "titm" : ""}">${big(o.vol)}</td><td class="r ${o.itm ? "titm" : ""}">${big(o.oi)}</td><td class="r ${o.itm ? "titm" : ""}">${o.iv > 0.005 ? (o.iv * 100).toFixed(1) : "–"}</td>` : '<td></td><td></td><td></td><td></td><td></td>');
      b.innerHTML = `<div class="ttool"><select class="in" id="omExp" style="width:auto;padding:2px 6px">${d.expiries.map((e) => `<option value="${e}" ${e === d.expiry ? "selected" : ""}>${dmy(e)}</option>`).join("")}</select>
          <label class="check"><input type="checkbox" id="omAll" ${all ? "checked" : ""}> All strikes</label><span class="spacer"></span>
          <span class="pill">P/C vol <b>${fx(s.pcrVol, 2)}</b></span><span class="pill">P/C OI <b>${fx(s.pcrOI, 2)}</b></span><span class="pill">Max pain <b>${price(s.maxPain)}</b></span></div>
        <table class="t tt tom"><thead><tr><th colspan="5" class="r up">CALLS</th><th class="r">Strike</th><th colspan="5" class="down">PUTS</th></tr>
          <tr><th class="r">Last</th><th class="r">%Chg</th><th class="r">Vol</th><th class="r">OI</th><th class="r">IV%</th><th class="r"></th><th class="r">Last</th><th class="r">%Chg</th><th class="r">Vol</th><th class="r">OI</th><th class="r">IV%</th></tr></thead><tbody>
        ${show.map((k) => `<tr class="${k === s.atmStrike ? "tatm" : ""}">${leg(C[k], "c")}<td class="r tstrike"><b>${price(k)}</b></td>${leg(Pm[k], "p")}</tr>`).join("")}</tbody></table>
        <div class="dim" style="font-size:10.5px;margin-top:4px">Shaded = in the money. IV = implied volatility (the move the option price expects, per year). Volume ${big(s.callVol)} calls / ${big(s.putVol)} puts.</div>`;
      $("#omExp", b).onchange = (e) => x.setOpt("date", +e.target.value);
      $("#omAll", b).onchange = (e) => x.setOpt("all", e.target.checked);
    } });

  fn("SKEW", { name: "Volatility smile & OI profile", group: "Options", sec: true, tip: "Implied volatility at each strike (the ‘smile’ or ‘skew’) and where open interest is concentrated, for the nearest expiry.", every: 120000,
    async run(b, x) {
      const d = await x.wrap(api(`/api/t/options/${encodeURIComponent(x.sec)}`));
      x.sub(`exp ${dmy(d.expiry)} · spot ${price(d.spot)}`);
      const strikes = [...new Set([...d.calls, ...d.puts].map((o) => o.strike))].sort((a, b2) => a - b2).filter((k) => k > d.spot * 0.7 && k < d.spot * 1.3);
      const C = Object.fromEntries(d.calls.map((o) => [o.strike, o])), Pm = Object.fromEntries(d.puts.map((o) => [o.strike, o]));
      const iv = (m, k) => (m[k] && m[k].iv > 0.01 ? m[k].iv * 100 : null);
      const series = [{ name: "Call IV", color: "#1fd286", values: strikes.map((k) => iv(C, k)) }, { name: "Put IV", color: "#ff5470", values: strikes.map((k) => iv(Pm, k)) }];
      const mo = Math.max(...strikes.map((k) => Math.max((C[k] || {}).oi || 0, (Pm[k] || {}).oi || 0)), 1);
      b.innerHTML = `<div class="tchart" style="height:52%"></div>
        <h4 class="th4">Open interest by strike <span class="up">calls ▲</span> <span class="down">puts ▼</span></h4>
        <div class="toi">${strikes.map((k) => `<div title="${price(k)}: ${big((C[k] || {}).oi || 0)} calls / ${big((Pm[k] || {}).oi || 0)} puts" class="${Math.abs(k - d.spot) / d.spot < 0.01 ? "atm" : ""}"><i class="c" style="height:${(((C[k] || {}).oi || 0) / mo) * 50}%"></i><i class="p" style="height:${(((Pm[k] || {}).oi || 0) / mo) * 50}%"></i></div>`).join("")}</div>`;
      drawLines($(".tchart", b), series, { labels: strikes.map((k) => price(k)), fmt: (v) => v.toFixed(0) + "%" });
      hoverLines($(".tchart", b), series, strikes.map((k) => "Strike " + price(k)), (v) => v.toFixed(1) + "%");
    } });

  fn("OVH", { name: "Option volume heat map", group: "Options", tip: "Where options are busiest today: total option volume, open interest, volume as a share of open interest (heat cells), put/call ratio and at-the-money implied volatility.", every: 180000,
    async run(b, x) {
      const st = (window.CMD && CMD.state) || {};
      const mine = [...new Set([...(st.holdings || []).map((h) => h.symbol), ...(st.watchlist || []), ...cfg.ws])].filter((s) => s && !/[.=^-]/.test(s));
      const d = await x.wrap(api(`/api/t/optheat${mine.length >= 3 ? "?symbols=" + encodeURIComponent(mine.slice(0, 20).join(",")) : ""}`));
      x.sub(mine.length >= 3 ? "Your US symbols" : "Most active US optionables");
      const lv = [20, 50, 100, 200, 300];
      b.innerHTML = `<table class="t tt"><thead><tr><th>Ticker</th><th class="r">Last</th><th class="r">%Chg</th><th class="r">Opt vol</th><th class="r">OI</th>${lv.map((l) => `<th class="r">${l}%</th>`).join("")}<th class="r">P/C</th><th class="r">ATM IV</th></tr></thead><tbody>${d.rows.map((r) => {
          const v = (r.volOI || 0) * 100, col = (r.pcr || 1) < 1 ? "31,210,134" : "255,84,112";
          return `<tr class="row" data-sym="${esc(r.symbol)}"><td>${sym(r.symbol)}</td><td class="r">${price(r.price)}</td><td class="r ${cls(r.changePct)}">${pp(r.changePct)}</td><td class="r">${big(r.totVol)}</td><td class="r">${big(r.totOI)}</td>
            ${lv.map((l, i) => `<td class="hcell" style="${v >= l ? `background:rgba(${col},${0.25 + i * 0.15})` : ""}">${v >= l ? (i === lv.length - 1 || v < lv[i + 1] ? Math.round(v) + "%" : "") : ""}</td>`).join("")}
            <td class="r ${(r.pcr || 0) > 1 ? "down" : "up"}">${fx(r.pcr, 2)}</td><td class="r">${r.atmIV > 0.01 ? (r.atmIV * 100).toFixed(1) + "%" : "–"}</td></tr>`; }).join("")}</tbody></table>
        <div class="dim" style="font-size:10.5px;margin-top:4px">Heat cells light up as today’s option volume reaches 20%…300% of open interest; green = call-heavy (P/C below 1), red = put-heavy.</div>`;
    } });

  // ---------------------------------------------------------------- FX & rates
  fn("FXC", { name: "Currency cross rates", group: "FX & Rates", tip: "How many units of the column currency one unit of the row currency buys, with today’s % change.", every: 20000,
    async run(b, x) {
      const d = await x.wrap(api("/api/t/fx"));
      x.sub(`${d.ccys.length} currencies`);
      b.innerHTML = `<div style="overflow:auto"><table class="t tt tfx"><thead><tr><th>1 ↓ buys →</th>${d.ccys.map((c) => `<th class="r">${c}</th>`).join("")}</tr></thead><tbody>${d.ccys.map((r, i) => `<tr><td><b>${r}</b></td>${d.matrix[i].map((c, j) => i === j ? '<td class="r dim">—</td>' : `<td class="r" style="${heat(c.chg, 0.8)}" title="${r}/${d.ccys[j]} ${pp(c.chg, 3)} today">${c.rate >= 100 ? fx(c.rate, 2) : c.rate >= 1 ? fx(c.rate, 4) : fx(c.rate, 5)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    } });

  fn("WCRS", { name: "World currency ranking", group: "FX & Rates", tip: "Which currencies are strongest today against the US dollar, and over the last week and month against everyone else.", every: 30000,
    async run(b, x) {
      const d = await x.wrap(api("/api/t/fx"));
      x.sub("vs US dollar today");
      b.innerHTML = bars(d.vsUsd.map((c) => ({ label: c.ccy, sub: `$${fx(c.usdPer, 4)}`, value: c.chg })), { fmt: (v) => pp(v, 2) }) +
        `<h4 class="th4">Strength vs every other currency</h4><table class="t tt"><thead><tr><th>Currency</th><th class="r">1 week</th><th class="r">1 month</th></tr></thead><tbody>${d.strength.map((s) => `<tr><td><b>${s.ccy}</b></td><td class="r ${cls(s["1W"])}">${pf(s["1W"], 2)}</td><td class="r ${cls(s["1M"])}">${pf(s["1M"], 2)}</td></tr>`).join("")}</tbody></table>`;
    } });

  fn("GC", { name: "US Treasury yield curve", group: "FX & Rates", tip: "Official US Treasury yields from 1 month to 30 years, today versus a week, a month and a year ago, plus the 2s10s spread (negative = inverted curve, often a recession warning).", every: 900000,
    async run(b, x) {
      const d = await x.wrap(api("/api/t/curve"));
      x.sub(`${d.curves.Today.date} · 2s10s ${d.s2s10 >= 0 ? "+" : ""}${fx(d.s2s10 * 100, 0)} bp`);
      const cols = { Today: "#5b8cff", "1 week ago": "#38bdf8", "1 month ago": "#f5b942", "1 year ago": "#8791a6" };
      const series = Object.entries(d.curves).map(([k, c]) => ({ name: `${k} (${c.date})`, color: cols[k], values: c.values, dash: k === "Today" ? null : "4,3", width: k === "Today" ? 2.4 : 1.4 }));
      const labels = d.tenors.map((t) => t.label.replace(" Mo", "M").replace(" Yr", "Y"));
      const T = d.curves.Today.values, M = d.curves["1 month ago"].values;
      b.innerHTML = `<div class="tchart" style="height:52%"></div>
        <div class="tlegend">${series.map((s) => `<span><i class="sw" style="background:${s.color}"></i>${esc(s.name)}</span>`).join("")}</div>
        <table class="t tt"><thead><tr><th></th>${labels.map((l) => `<th class="r">${l}</th>`).join("")}</tr></thead><tbody><tr><td>Yield</td>${T.map((v) => `<td class="r">${fx(v, 2)}</td>`).join("")}</tr>
        <tr><td>1M chg (bp)</td>${T.map((v, i) => `<td class="r ${cls((v ?? 0) - (M[i] ?? 0))}">${v != null && M[i] != null ? fx((v - M[i]) * 100, 0) : "–"}</td>`).join("")}</tr></tbody></table>
        <div class="tsum"><span>2s10s <b class="${cls(d.s2s10)}">${fx(d.s2s10 * 100, 0)} bp</b> ${TS.spark(d.hist.map((h) => h.s2s10), 90, 18)}</span><span>3m10y <b class="${cls(d.s3m10)}">${fx(d.s3m10 * 100, 0)} bp</b></span>
        ${d.live.map((l) => `<span>${esc(l.label)} <b>${fx(l.yield, 3)}%</b></span>`).join("")}</div>`;
      drawLines($(".tchart", b), series, { labels, fmt: (v) => v.toFixed(2) + "%" });
      hoverLines($(".tchart", b), series, labels, (v) => v.toFixed(2) + "%");
    } });

  fn("WIRP", { name: "Fed rate expectations", group: "FX & Rates", tip: "What fed funds futures say the market expects the Fed’s policy rate to average each month, and how many quarter-point cuts or hikes that implies.", every: 300000,
    async run(b, x) {
      const d = await x.wrap(api("/api/t/wirp"));
      x.sub(`Now ${fx(d.base, 3)}% implied`);
      const mn = Math.min(...d.points.map((p) => p.rate)), mx2 = Math.max(...d.points.map((p) => p.rate)), rg = mx2 - mn || 0.25;
      b.innerHTML = `<div class="tvb tall">${d.points.map((p) => `<div title="${p.month}: ${fx(p.rate, 3)}%"><b class="mono" style="font-size:10px">${fx(p.rate, 2)}</b><i style="height:${20 + ((p.rate - mn) / rg) * 75}%;background:${p.chgBp < 0 ? "var(--up)" : p.chgBp > 0 ? "var(--down)" : "var(--accent)"}"></i><small>${p.month.slice(0, 3)}</small></div>`).join("")}</div>
        <table class="t tt"><thead><tr><th>Month</th><th class="r">Implied rate</th><th class="r">vs now</th><th class="r">25bp moves priced</th></tr></thead><tbody>${d.points.map((p) => `<tr><td>${esc(p.month)}</td><td class="r">${fx(p.rate, 3)}%</td><td class="r ${cls(-p.chgBp)}">${p.chgBp > 0 ? "+" : ""}${fx(p.chgBp, 1)} bp</td><td class="r">${p.moves === 0 ? "–" : `${Math.abs(p.moves).toFixed(2)} ${p.moves < 0 ? "cuts" : "hikes"}`}</td></tr>`).join("")}</tbody></table>
        <div class="dim" style="font-size:10.5px">${esc(d.source)}.</div>`;
    } });

  // ---------------------------------------------------------------- commodities, crypto, futures
  fn("CMDTY", { name: "Commodities monitor", group: "Commodities", tip: "Energy, metals, grains, softs and livestock futures: price, moves over a day, week, month and year, and the cost to roll a long position to the next contract.", every: 20000,
    async run(b, x) {
      const d = await x.wrap(api("/api/t/cmdty"));
      x.sub("Front-month futures");
      b.innerHTML = `<table class="t tt"><thead><tr><th>Commodity</th><th class="r">Last</th><th class="r">Chg</th><th class="r">%Chg</th><th class="r">1W</th><th class="r">1M</th><th class="r">YTD</th><th>30d</th><th class="r" title="Annualised roll cost to the next contract">Roll / yr</th></tr></thead><tbody>${d.groups.map((g) => `<tr class="tgrp"><td colspan="9">${esc(g.group)}</td></tr>` + g.rows.map((r) => `<tr class="row" data-sym="${esc(r.symbol)}">
          <td><b>${esc(r.name)}</b><small class="tname">${esc(r.symbol)}</small></td><td class="r">${price(r.price)}</td><td class="r ${cls(r.change)}">${price(r.change)}</td><td class="r" style="${heat(r.changePct, 3)}">${pp(r.changePct)}</td>
          <td class="r ${cls(r["1W"])}">${pf(r["1W"], 1)}</td><td class="r ${cls(r["1M"])}">${pf(r["1M"], 1)}</td><td class="r ${cls(r.YTD)}">${pf(r.YTD, 1)}</td><td>${TS.spark(r.spark, 60, 16)}</td>
          <td class="r" title="${r.roll ? `${r.roll.near}→${r.roll.next}: ${r.roll.ann >= 0 ? "contango (rolling a long costs money)" : "backwardation (rolling a long pays)"}` : ""}">${r.roll ? `<span class="${r.roll.ann >= 0 ? "down" : "up"}">${pp(r.roll.ann, 1)}</span>` : "–"}</td></tr>`).join("")).join("")}</tbody></table>`;
    } });

  fn("CRYP", { name: "Crypto monitor", group: "Commodities", tip: "The largest cryptocurrencies by market value: price, 24-hour, 7-day, 30-day and year-to-date moves, and trading volume.", every: 20000,
    async run(b, x) {
      const d = await x.wrap(api("/api/t/crypto"));
      x.sub(`Total ${big(d.totalCap)} · BTC ${pf(d.btcDominance, 1).replace("+", "")} dominance`);
      b.innerHTML = `<table class="t tt"><thead><tr><th>#</th><th>Coin</th><th class="r">Price</th><th class="r">24h</th><th class="r">7d</th><th class="r">30d</th><th class="r">YTD</th><th class="r">Mkt cap</th><th class="r">Volume</th><th>30d</th></tr></thead><tbody>${d.rows.map((r, i) => `<tr class="row" data-sym="${esc(r.symbol)}">
        <td class="dim">${i + 1}</td><td>${sym(r.symbol, r.name)}</td><td class="r">${price(r.price)}</td><td class="r" style="${heat(r.changePct, 5)}">${pp(r.changePct)}</td><td class="r ${cls(r["1W"])}">${pf(r["1W"], 1)}</td>
        <td class="r ${cls(r["1M"])}">${pf(r["1M"], 1)}</td><td class="r ${cls(r.YTD)}">${pf(r.YTD, 1)}</td><td class="r">${big(r.cap)}</td><td class="r">${big(r.volume)}</td><td>${TS.spark(r.spark, 60, 16)}</td></tr>`).join("")}</tbody></table>`;
    } });

  fn("ROLL", { name: "Futures roll cost", group: "Commodities", tip: "The Daily Desk’s morning roll-cost run: what it costs (or pays) to roll a long futures position from the near contract to the next, for global benchmarks and NSE indices.", every: 600000,
    async run(b, x) {
      const d = await x.wrap(api("/api/t/roll"));
      const tab = x.opt("tab", "bench");
      const rows = tab === "bench" ? d.global.filter((r) => d.benchmarks.includes(r.id)) : tab === "all" ? d.global : d.nse;
      x.sub(Object.entries(d.sessions || {}).map(([k, v]) => `${k.split(" (")[0]} ${v.slice(5)}`).join(" · ") || "Run the Daily Desk to fill this");
      b.innerHTML = `<div class="ttool">${seg("tab", [["bench", "Benchmarks"], ["all", "All international"], ["nse", "NSE indices"]], tab)}<a class="btn sm ghost" href="/desk.html#roll" target="_blank">Daily Desk ↗</a></div>
        ${rows.length ? `<table class="t tt"><thead><tr><th>Contract</th><th>Near → next</th><th class="r">Roll</th><th class="r">Roll %</th><th class="r">Annualised</th><th class="r">Rollover</th><th class="r">Days</th></tr></thead><tbody>${rows.map((r) => `<tr>
          <td><b>${esc(r.symbol)}</b><small class="tname">${esc(r.name || r.kind || "")}${r.exchange ? " · " + esc(r.exchange) : ""}</small></td><td>${esc(r.near.month || r.near.expiry)} → ${esc(r.next.month || r.next.expiry)}</td>
          <td class="r ${cls(r.rollPts)}">${fx(r.rollPts, r.decimals ?? 2)}</td><td class="r ${cls(r.rollPct)}">${pp(r.rollPct, 2)}</td><td class="r ${cls(r.rollAnn)}"><b>${pp(r.rollAnn, 1)}</b></td>
          <td class="r">${r.rollover == null ? "–" : r.rollover.toFixed(0) + "%"}</td><td class="r ${r.daysNear <= 7 ? "warn" : ""}">${r.daysNear}</td></tr>`).join("")}</tbody></table>` : empty("No roll-cost run yet. It runs every morning at 09:01 IST.")}`;
      x.onSeg("tab", (v) => x.setOpt("tab", v));
    } });

  // ---------------------------------------------------------------- news & events
  const TOPICS = [["top", "Top stories"], ["world", "Worldwide"], ["us", "United States"], ["india", "India"], ["europe", "Europe"], ["asia", "Asia"], ["fed", "Central banks"], ["earnings", "Earnings"],
    ["bonds", "Bonds"], ["fx", "Currencies"], ["commodities", "Commodities"], ["crypto", "Crypto"], ["mna", "M&A"], ["ipo", "IPOs"], ["my", "My news"]];
  fn("N", { name: "News: top stories by importance", group: "News", tip: "Headlines ranked by importance (source quality, market-moving words and freshness) or by time. Pick a topic on the left; ‘My news’ follows your holdings and watchlist.", every: 300000,
    async run(b, x) {
      const topic = x.opt("topic", "top"), sort = x.opt("sort", "importance");
      const d = await x.wrap(api(`/api/t/news?topic=${topic}&sort=${sort}`));
      x.sub(TOPICS.find((t) => t[0] === topic)[1]);
      b.innerHTML = `<div class="tnews"><div class="tntop">${TOPICS.map(([k, l]) => `<button data-t="${k}" class="${k === topic ? "on" : ""}">${l}</button>`).join("")}</div>
        <div class="tnlist"><div class="ttool">${seg("sort", [["importance", "By importance"], ["time", "Latest"]], sort)}</div>${newsList(d.items)}</div></div>`;
      $$(".tntop button", b).forEach((t) => (t.onclick = () => x.setOpt("topic", t.dataset.t)));
      x.onSeg("sort", (v) => x.setOpt("sort", v));
    } });
  const newsList = (items) => items.map((n, i) => `<a class="tn" href="${esc(n.link)}" target="_blank" rel="noopener noreferrer"><span class="tnn">${i + 1}.</span><span class="tnt">${esc(n.title)}</span>
    <span class="tnm">${n.symbol ? `<b class="tsym" data-sym="${esc(n.symbol)}">${esc(n.symbol)}</b> · ` : ""}${esc(n.source || "")}${n.time ? " · " + agoT(n.time) : ""}</span></a>`).join("") || empty("No headlines right now.");
  const agoT = (t) => { const m = (Date.now() / 1000 - t) / 60; return m < 60 ? Math.max(1, Math.round(m)) + "m" : m < 1440 ? Math.round(m / 60) + "h" : Math.round(m / 1440) + "d"; };
  fn("CN", { name: "Company news", group: "News", sec: true, tip: "The latest headlines about the loaded company.", every: 300000,
    async run(b, x) {
      const d = await x.wrap(api(`/api/t/news?topic=company&symbol=${encodeURIComponent(x.sec)}&sort=time`));
      x.sub(`${d.items.length} headlines`);
      b.innerHTML = `<div class="tnlist">${newsList(d.items)}</div>`;
    } });

  const FLAG = { USD: "🇺🇸", EUR: "🇪🇺", GBP: "🇬🇧", JPY: "🇯🇵", CNY: "🇨🇳", AUD: "🇦🇺", NZD: "🇳🇿", CAD: "🇨🇦", CHF: "🇨🇭", INR: "🇮🇳", All: "🌐" };
  fn("ECO", { name: "Economic calendar", group: "News", tip: "This week’s and next week’s economic releases and central-bank events: the market’s forecast (survey), the previous reading and the actual once released. Red = high impact.", every: 900000,
    async run(b, x) {
      const f = x.opt("f", "high");
      const d = await x.wrap(api("/api/t/eco"));
      const now = Date.now() / 1000;
      const ev = d.events.filter((e) => f === "all" || (f === "high" ? e.impact === "High" : ["USD", "INR", "EUR"].includes(e.country) && e.impact !== "Holiday"));
      x.sub(`${ev.length} events · times in your time zone`);
      let day = "";
      const nextI = ev.findIndex((e) => e.ts > now);
      b.innerHTML = `<div class="ttool">${seg("f", [["high", "High impact"], ["mine", "USD · INR · EUR"], ["all", "All"]], f)}<span class="spacer"></span><span class="dim" style="font-size:10.5px">${esc(d.source)}</span></div>
        <table class="t tt teco"><thead><tr><th>Time</th><th></th><th>Event</th><th class="r">Survey</th><th class="r">Actual</th><th class="r">Prior</th></tr></thead><tbody>${ev.map((e, i) => {
          const dd = new Date(e.ts * 1000), lbl = dd.toLocaleDateString([], { weekday: "short", day: "2-digit", month: "short" });
          const hdr = lbl !== day ? ((day = lbl), `<tr class="tgrp"><td colspan="6">${lbl}</td></tr>`) : "";
          return `${hdr}<tr class="${e.ts < now ? "tpast" : ""} ${i === nextI ? "tnext" : ""}"><td>${dd.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</td><td title="${esc(e.country)}">${FLAG[e.country] || ""} ${esc(e.country || "")}</td>
            <td style="white-space:normal"><i class="timp ${esc((e.impact || "").toLowerCase())}"></i>${esc(e.title)}</td><td class="r">${esc(e.forecast || "")}</td><td class="r"><b>${esc(e.actual || "")}</b></td><td class="r dim">${esc(e.previous || "")}</td></tr>`; }).join("")}</tbody></table>`;
      x.onSeg("f", (v) => x.setOpt("f", v));
      const nx = $(".tnext", b); if (nx && !x.state.scrolled) { nx.scrollIntoView({ block: "center" }); x.state.scrolled = true; }
    } });

  fn("EVTS", { name: "Corporate events", group: "News", tip: "Upcoming earnings, calls, board meetings and ex-dividend dates for the companies on your Daily Desk portfolio.", every: 900000,
    async run(b, x) {
      const d = await x.wrap(api("/api/t/events?days=60"));
      x.sub(`${d.tracked} companies tracked`);
      b.innerHTML = d.events.length ? `<table class="t tt"><thead><tr><th>Date</th><th>Company</th><th>Event</th></tr></thead><tbody>${d.events.map((e) => `<tr class="row" data-sym="${esc(e.symbol)}"><td>${dmy(e.date)}</td><td>${sym(e.symbol, e.name)}</td><td style="white-space:normal"><b>${esc(e.what)}</b> <span class="dim">${esc(e.desc || "")}</span></td></tr>`).join("")}</tbody></table>`
        : empty('Nothing scheduled yet. Add companies on the <a href="/desk.html#portfolio" target="_blank">Daily Desk portfolio</a>.');
    } });

  // ---------------------------------------------------------------- actions (open something rather than fill a panel)
  const A = {
    RES: { name: "Open full research screen", run: (s) => window.CMD && CMD.openDetail(s || cfg.sec) },
    SPLC: { name: "Supply chain explorer", sec: true, run: (s) => window.open(`/chain.html?symbol=${encodeURIComponent(s || cfg.sec)}`, "_blank") },
    DESK: { name: "Daily Desk (results, calls, dividends, roll cost)", run: () => window.open("/desk.html", "_blank") },
    PORT: { name: "Holdings & portfolio analytics", run: () => { const h = document.getElementById("holdBtn"); if (h) h.click(); } },
    ALRT: { name: "Price & signal alerts", run: () => { const a = document.getElementById("alertBtn"); if (a) a.click(); } },
    TOOL: { name: "Tools: calculators, compare, backtester, goal planner", run: () => { const t = document.getElementById("toolsBtn"); if (t) t.click(); } },
    EQS: { name: "Screener and today’s plan (Advanced view)", run: () => TS.setMode("advanced") },
    AI: { name: "Ask the AI analyst (type AI followed by your question)", run: (s, q) => askAI(q || (s ? `Give me a quick view on ${s}` : "")) },
    HELP: { name: "Function directory", run: () => help() },
  };
  function askAI(q) {
    const as = document.getElementById("assist");
    if (!as) return;
    as.classList.add("show");
    if (q) { document.getElementById("asIn").value = q; document.getElementById("asGo").click(); } else document.getElementById("asIn").focus();
  }

  // ================================================================ launchpad pages ("row/col/row/col" on a 12 × 12 grid)
  const PAGES = [
    { id: "launchpad", name: "Launchpad", panels: [["MON", "1/1/7/5"], ["IMAP", "1/5/7/9"], ["GP", "1/9/7/13"], ["OVH", "7/1/9/5"], ["N", "9/1/11/5"], ["ECO", "11/1/13/5"], ["RV", "7/5/13/13"]] },
    { id: "global", name: "Global Mkt", key: "F10", panels: [["WEI", "1/1/13/7"], ["IMAP", "1/7/7/13"], ["MOV", "7/7/13/10"], ["MKT", "7/10/13/13"]] },
    { id: "sectors", name: "Sectors", panels: [["SECT", "1/1/7/5"], ["SECG", "1/5/7/13"], ["SECD", "7/1/13/8"], ["RRG", "7/8/13/13"]] },
    { id: "movers", name: "Movers", panels: [["MOST", "1/1/13/7"], ["MOV", "1/7/7/13"], ["MKT", "7/7/13/13"]] },
    { id: "equity", name: "Equity", key: "F8", panels: [["GP", "1/1/8/8"], ["DES", "1/8/8/13"], ["FA", "8/1/13/6"], ["ANR", "8/6/13/9"], ["EE", "8/9/13/13"]] },
    { id: "analysis", name: "Analysis", panels: [["RV", "1/1/7/13"], ["HDS", "7/1/13/5"], ["DVD", "7/5/13/9"], ["SEAG", "7/9/13/13"]] },
    { id: "options", name: "Options", panels: [["OMON", "1/1/13/8"], ["OVH", "1/8/7/13"], ["SKEW", "7/8/13/13"]] },
    { id: "fx", name: "FX & Rates", key: "F11", panels: [["FXC", "1/1/7/8"], ["WCRS", "1/8/7/13"], ["GC", "7/1/13/8"], ["WIRP", "7/8/13/13"]] },
    { id: "cmdty", name: "Commodities", key: "F9", panels: [["CMDTY", "1/1/13/8"], ["CRYP", "1/8/8/13"], ["ROLL", "8/8/13/13"]] },
    { id: "news", name: "News & Events", panels: [["N", "1/1/13/8"], ["ECO", "1/8/8/13"], ["EVTS", "8/8/13/13"]] },
    { id: "worksheet", name: "Worksheet", panels: [["WS", "1/1/8/9"], ["CORR", "1/9/8/13"], ["BETA", "8/1/13/5"], ["CN", "8/5/13/9"], ["HP", "8/9/13/13"]] },
  ];
  const FKEYS = { F2: "fx", F8: "equity", F9: "cmdty", F10: "global" };

  // ================================================================ shell
  root.innerHTML = `<div class="tbar">
      <span class="tgo" data-tip="Type a ticker and/or a function code, then press Enter (that’s Bloomberg’s &lt;GO&gt;). Examples: AAPL GP · NVDA DES · RELIANCE IN FA · WEI · SECT · ECO · AI why is gold up?">GO ▸</span>
      <div class="tcmdw"><input id="tcmd" class="in" autocomplete="off" spellcheck="false" placeholder="Ticker + function, e.g.  AAPL GP · NVDA DES · WEI · SECT · ECO · TOP   (HELP for all)"><div class="tsug" id="tsug"></div></div>
      <button class="btn sm primary" id="tgoBtn">GO</button>
      <span class="tsec-chip" id="tsecChip" data-tip="Linked security: panels marked 🔗 follow it. Click any ticker in any panel to load it everywhere; double-click to open full research."></span>
      <button class="btn sm ghost" id="thelp" data-tip="Function directory (or type HELP)">⌘ Functions</button>
      <span class="spacer"></span><span class="mono dim" id="tclock"></span>
    </div>
    <div class="tpages" id="tpages"></div>
    <div class="tgrid" id="tgrid"></div>`;
  const grid = $("#tgrid"), input = $("#tcmd"), sug = $("#tsug");
  let panels = [], focusI = 0, live = false;

  function renderTabs() {
    $("#tpages").innerHTML = PAGES.map((p, i) => `<button data-p="${p.id}" class="${p.id === cfg.page ? "on" : ""}" title="${p.key ? p.key + " · " : ""}Alt+${i + 1 < 10 ? i + 1 : 0}">${esc(p.name)}${p.key ? ` <kbd>${p.key}</kbd>` : ""}</button>`).join("") +
      `<button data-reset title="Put this page’s panels back to their default functions">↺ Reset page</button>`;
    $$("#tpages [data-p]").forEach((b) => (b.onclick = () => showPage(b.dataset.p)));
    $("#tpages [data-reset]").onclick = () => { delete cfg.pages[cfg.page]; Object.keys(cfg.opts).filter((k) => k.startsWith(cfg.page + ":")).forEach((k) => delete cfg.opts[k]); save(); showPage(cfg.page); };
  }
  function secChip() {
    const name = (window.TS_NAMES || {})[cfg.sec] || "";
    $("#tsecChip").innerHTML = `🔗 <b>${esc(cfg.sec)}</b>${name ? ` <span class="muted">${esc(name)}</span>` : ""}`;
  }
  function stopAll() { panels.forEach((p) => { clearTimeout(p.timer); p.ctx && p.ctx.dispose(); }); }
  function showPage(id) {
    stopAll();
    cfg.page = PAGES.some((p) => p.id === id) ? id : "launchpad";
    save();
    renderTabs();
    const pg = PAGES.find((p) => p.id === cfg.page);
    const over = cfg.pages[cfg.page] || {};
    grid.classList.remove("hasmax");
    grid.innerHTML = "";
    panels = pg.panels.map(([code, area], i) => makePanel(over[i] || code, area, i));
    focus(Math.min(focusI, panels.length - 1));
  }
  function makePanel(code, area, i) {
    const el = document.createElement("section");
    el.className = "panel tp";
    el.style.gridArea = area;
    el.innerHTML = `<div class="ph"><span class="fcode"></span><b class="ftitle"></b><span class="tsec"></span><span class="sub fsub"></span><span class="spacer"></span><span class="asof dim"></span>
      <span class="q" data-tip=""></span><button class="btn sm ghost" data-a="fn" data-tip="Change this panel’s function">⚙</button><button class="btn sm ghost" data-a="ref" data-tip="Refresh">↻</button><button class="btn sm ghost" data-a="max" data-tip="Maximise / restore (Esc)">⤢</button></div><div class="pb tpb"></div>`;
    grid.appendChild(el);
    const p = { el, i, code, timer: null, ctx: null, body: $(".tpb", el) };
    el.addEventListener("mousedown", () => focus(i));
    $("[data-a=ref]", el).onclick = () => run(p, true);
    $("[data-a=max]", el).onclick = () => toggleMax(p);
    $(".ph", el).ondblclick = (e) => { if (!e.target.closest("button,input,select")) toggleMax(p); };
    $("[data-a=fn]", el).onclick = () => pickFn(p);
    setCode(p, code);
    return p;
  }
  function setCode(p, code) {
    p.code = code;
    const f = F[code];
    $(".fcode", p.el).textContent = code;
    $(".ftitle", p.el).textContent = f ? f.name : "Unknown function";
    $(".q", p.el).dataset.tip = f ? f.tip : "";
    $(".q", p.el).textContent = f && f.tip ? "ⓘ" : "";
    run(p);
  }
  function focus(i) {
    focusI = i;
    panels.forEach((p) => p.el.classList.toggle("focus", p.i === i));
  }
  function toggleMax(p) {
    const on = !p.el.classList.contains("max");
    panels.forEach((q) => q.el.classList.remove("max"));
    p.el.classList.toggle("max", on);
    grid.classList.toggle("hasmax", on);
    focus(p.i);
    if (!(p.ctx && p.ctx.state.chart)) run(p, true);       // SVG charts redraw at the new size (canvas charts resize themselves)
  }
  function pickFn(p) {
    const h = $(".ftitle", p.el);
    const old = p.code;
    h.innerHTML = `<input class="in tfin" list="tfl" value="${esc(old)}" style="width:110px;padding:1px 6px;font-family:var(--mono)"><datalist id="tfl">${Object.values(F).map((f) => `<option value="${f.code}">${esc(f.name)}</option>`).join("")}</datalist>`;
    const inp = $("input", h);
    inp.focus(); inp.select();
    const done = (ok) => {
      const v = inp.value.trim().toUpperCase();
      if (ok && F[v]) { (cfg.pages[cfg.page] ||= {})[p.i] = v; save(); setCode(p, v); } else setCode(p, old);
    };
    inp.onkeydown = (e) => { if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); };
    inp.onblur = () => setTimeout(() => document.activeElement !== inp && done(true), 150);
  }

  const STALE = new Error("stale");
  async function run(p, force) {
    clearTimeout(p.timer);
    const my = (p.seq = (p.seq || 0) + 1);
    const f = F[p.code];
    if (!f) { p.body.innerHTML = empty(`Unknown function “${esc(p.code)}”. Click ⚙ or type HELP.`); return; }
    const okey = `${cfg.page}:${p.i}:${p.code}`;
    const sec = f.sec ? cfg.sec : null;
    $(".tsec", p.el).textContent = sec ? "🔗 " + sec : "";
    if (!p.ctx || p.ctx.code !== p.code) {
      p.ctx && p.ctx.dispose();
      p.ctx = { code: p.code, state: {}, dispose() { try { this.state.chart && this.state.chart.remove(); this.state.chart2 && this.state.chart2.remove(); } catch {} this.state = {}; } };
    }
    const ctx = Object.assign(p.ctx, {
      sec,
      sub: (t) => ($(".fsub", p.el).textContent = t || ""),
      opt: (k, dflt) => ((cfg.opts[okey] || {})[k] ?? dflt),
      setOpt: (k, v) => { (cfg.opts[okey] ||= {})[k] = v; save(); run(p, true); },
      onSeg: (id, cb) => $$(`[data-seg="${id}"] button`, p.body).forEach((b) => (b.onclick = () => cb(b.dataset.v))),
      refresh: () => run(p, true),
      wrap: async (pr) => { const d = await pr; if (my !== p.seq) throw STALE; return d; },   // drop results of superseded runs
    });
    if (!p.body.innerHTML) p.body.innerHTML = '<div class="empty"><span class="spin"></span></div>';
    try {
      await f.run(p.body, ctx);
      $(".asof", p.el).textContent = hms(Date.now() / 1000);
    } catch (e) {
      if (e === STALE) return;
      ctx.dispose();
      p.body.innerHTML = empty(`<span class="warn">${esc(e.message || "Couldn’t load this.")}</span>${f.sec ? `<br><span class="dim">Loaded security: ${esc(cfg.sec)}. Type another ticker above.</span>` : ""}`);
    }
    const tick = () => { if (!live) return; if (document.hidden) { p.timer = setTimeout(tick, f.every); return; } run(p); };   // background tabs wait
    if (live && f.every) p.timer = setTimeout(tick, f.every);
  }

  // ---------------------------------------------------------------- security linking
  function setSec(s, quiet) {
    if (!s) return;
    cfg.sec = s;
    save();
    secChip();
    panels.forEach((p) => { if (F[p.code] && F[p.code].sec) run(p, true); });
    if (!quiet && window.CMD) CMD.select(s);
    api(`/api/quotes?symbols=${encodeURIComponent(s)}`).then((q) => { if (q[0]) { (window.TS_NAMES ||= {})[s] = q[0].name; secChip(); } }).catch(() => {});
  }
  root.addEventListener("click", (e) => {
    const t = e.target.closest("[data-sym]");
    if (t && t.dataset.sym && !e.target.closest("a,button,input,select")) setSec(t.dataset.sym);
  });
  root.addEventListener("dblclick", (e) => {
    const t = e.target.closest("[data-sym]");
    if (t && t.dataset.sym && window.CMD) CMD.openDetail(t.dataset.sym);
  });

  // ---------------------------------------------------------------- command line
  const IDX = { SPX: "^GSPC", INDU: "^DJI", CCMP: "^IXIC", NDX: "^NDX", RTY: "^RUT", VIX: "^VIX", NKY: "^N225", HSI: "^HSI", UKX: "^FTSE", DAX: "^GDAXI", CAC: "^FCHI",
    SX5E: "^STOXX50E", NIFTY: "^NSEI", SENSEX: "^BSESN", AS51: "^AXJO", SPTSX: "^GSPTSE", IBOV: "^BVSP", KOSPI: "^KS11", TWSE: "^TWII", SHCOMP: "000001.SS",
    CL1: "CL=F", CO1: "BZ=F", GC1: "GC=F", SI1: "SI=F", HG1: "HG=F", NG1: "NG=F", XBT: "BTC-USD", BTC: "BTC-USD", ETH: "ETH-USD", DXY: "DX-Y.NYB" };
  const EXCH = { US: "", UN: "", UW: "", IN: ".NS", IS: ".NS", IB: ".BO", JP: ".T", JT: ".T", HK: ".HK", LN: ".L", GR: ".DE", GY: ".DE", FP: ".PA", NA: ".AS", SW: ".SW", SE: ".SW",
    IM: ".MI", SM: ".MC", CN: ".TO", CT: ".TO", AU: ".AX", AT: ".AX", KS: ".KS", TT: ".TW", SP: ".SI", BZ: ".SA", SS: ".ST", DC: ".CO", NO: ".OL" };
  const CCY = new Set(["USD", "EUR", "JPY", "GBP", "CHF", "CAD", "AUD", "NZD", "CNY", "INR", "HKD", "SGD", "SEK", "NOK", "MXN", "BRL", "ZAR", "KRW"]);
  const YELLOW = new Set(["EQUITY", "EQUITIES", "INDEX", "CURNCY", "CRNCY", "COMDTY", "CMDTY", "CORP", "GOVT", "GO", "<GO>"]);
  function ticker(toks) {
    toks = toks.filter((t) => !YELLOW.has(t));
    if (!toks.length) return null;
    if (toks.length === 1) {
      const t = toks[0];
      if (IDX[t]) return IDX[t];
      if (t.length === 6 && CCY.has(t.slice(0, 3)) && CCY.has(t.slice(3))) return t + "=X";
      return t;
    }
    const [s, ex] = toks;
    if (ex in EXCH) return (ex === "HK" ? s.padStart(4, "0") : s) + EXCH[ex];
    return toks.join("");
  }
  function exec(raw) {
    const s = raw.trim();
    if (!s) return;
    cfg.hist = [s, ...cfg.hist.filter((h) => h !== s)].slice(0, 40);
    save();
    if (/^AI\b/i.test(s)) return askAI(s.replace(/^AI\s*/i, ""));
    const toks = s.toUpperCase().replace(/<GO>$/, "").split(/\s+/).filter(Boolean);
    let code = null;
    const last = toks[toks.length - 1];
    if (F[last] || A[last]) code = toks.pop();
    else if (toks.length && (F[toks[0]] || A[toks[0]])) code = toks.shift();
    const tk = toks.length ? ticker(toks) : null;
    if (tk) setSec(tk);
    if (!code) { if (tk) TS.toast(`${tk} loaded into the linked panels 🔗`); else TS.toast("Unknown function. Type HELP to see them all."); return; }
    if (A[code]) return A[code].run(tk || (A[code].sec ? cfg.sec : null), toks.join(" "));
    const p = panels[focusI] || panels[0];
    (cfg.pages[cfg.page] ||= {})[p.i] = code;
    save();
    setCode(p, code);
    p.el.scrollIntoView({ block: "nearest" });
  }
  let sel = -1, items = [], seq = 0;
  function suggest() {
    const v = input.value.trim().toUpperCase();
    const all = [...Object.values(F).map((f) => ({ code: f.code, name: f.name, group: f.group })), ...Object.entries(A).map(([code, a]) => ({ code, name: a.name, group: "Actions" }))];
    const word = v.split(/\s+/).pop() || "";
    let fs = !v ? cfg.hist.slice(0, 6).map((h) => ({ hist: h })) : all.filter((f) => f.code.startsWith(word) || (word.length > 2 && f.name.toUpperCase().includes(word))).slice(0, 8);
    items = fs;
    sel = items.length ? 0 : -1;
    paint();
    const my = ++seq;
    if (v && !F[word] && !A[word] && word.length >= 2 && !v.includes(" ")) {
      setTimeout(async () => {
        const res = await api("/api/search?q=" + encodeURIComponent(input.value.trim())).catch(() => []);
        if (my !== seq) return;
        items = [...items, ...res.slice(0, 6).map((r) => ({ sym: r.symbol, name: r.name, ex: r.exchange }))];
        if (sel < 0 && items.length) sel = 0;
        paint();
      }, 180);
    }
  }
  function paint() {
    sug.innerHTML = items.map((it, i) => `<div data-i="${i}" class="${i === sel ? "sel" : ""}">${it.hist ? `<span class="dim">↺</span><span>${esc(it.hist)}</span>` : it.sym ? `<span class="fc" style="color:var(--accent)">${esc(it.sym)}</span><span>${esc(it.name)}</span><span class="dim">${esc(it.ex || "")}</span>` : `<span class="fc">${esc(it.code)}</span><span>${esc(it.name)}</span><span class="dim">${esc(it.group)}</span>`}</div>`).join("") +
      (items.length ? '<div class="dim" style="display:block;font-size:10.5px;cursor:default;border-top:1px solid var(--line)">↑↓ choose · Tab complete · Enter = GO · Esc close</div>' : "");
    sug.classList.toggle("show", items.length > 0 && document.activeElement === input);
  }
  function complete(it) {
    if (!it) return;
    const parts = input.value.trim().split(/\s+/);
    if (it.hist) input.value = it.hist;
    else if (it.sym) input.value = it.sym + " ";
    else { parts[parts.length - 1] = it.code; input.value = parts.join(" ").replace(/^\s+/, ""); }
  }
  input.addEventListener("input", suggest);
  input.addEventListener("focus", suggest);
  input.addEventListener("blur", () => setTimeout(() => sug.classList.remove("show"), 150));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { sel = Math.min(sel + 1, items.length - 1); paint(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { sel = Math.max(sel - 1, 0); paint(); e.preventDefault(); }
    else if (e.key === "Tab" && items[sel]) { e.preventDefault(); complete(items[sel]); suggest(); }
    else if (e.key === "Enter") {
      e.preventDefault();
      const it = items[sel], typed = input.value.trim();
      if (it && (it.hist || (it.code && !typed.includes(" ") && it.code.startsWith(typed.toUpperCase()) && typed.length < it.code.length))) complete(it);
      else if (it && it.sym && !typed.includes(" ") && !F[typed.toUpperCase()] && !A[typed.toUpperCase()]) { complete(it); exec(input.value); input.value = ""; sug.classList.remove("show"); return; }
      exec(input.value); input.value = ""; sug.classList.remove("show");
    } else if (e.key === "Escape") { input.blur(); }
  });
  sug.addEventListener("mousedown", (e) => { const d = e.target.closest("[data-i]"); if (!d) return; e.preventDefault(); const it = items[+d.dataset.i]; complete(it); if (it.sym || it.hist) { exec(input.value); input.value = ""; } else input.focus(); suggest(); });
  $("#tgoBtn").onclick = () => { exec(input.value); input.value = ""; };
  $("#thelp").onclick = () => help();

  function help() {
    const groups = {};
    Object.values(F).forEach((f) => (groups[f.group] ||= []).push(f));
    const body = UX.modal("⌘ CasuallyHedge Terminal · function directory", `<p class="muted" style="margin-top:0">Type a code in the command line and press Enter (<b>&lt;GO&gt;</b>). Put a ticker first to load it: <code>AAPL GP</code>, <code>RELIANCE IN FA</code>, <code>700 HK DES</code>, <code>EURUSD</code>, <code>SPX</code>. Functions marked 🔗 follow the loaded security. The function opens in the highlighted panel; click any ticker to load it everywhere, double-click for full research. Keys: <kbd>/</kbd> command line · <kbd>Alt</kbd>+<kbd>1–9</kbd> pages · <kbd>F8</kbd> Equity · <kbd>F9</kbd> Commodities · <kbd>F10</kbd> Global · <kbd>F2</kbd>/<kbd>F11</kbd> FX &amp; Rates · <kbd>Esc</kbd> restore.</p>
      <div class="thelp">${Object.entries(groups).map(([g, fs]) => `<div><h4 class="th4">${esc(g)}</h4>${fs.map((f) => `<div class="thf" data-c="${f.code}"><span class="fc">${f.code}</span><span><b>${esc(f.name)}</b>${f.sec ? " 🔗" : ""}<small class="dim">${esc(f.tip)}</small></span></div>`).join("")}</div>`).join("")}
      <div><h4 class="th4">Actions</h4>${Object.entries(A).map(([c, a]) => `<div class="thf" data-c="${c}"><span class="fc">${c}</span><span><b>${esc(a.name)}</b></span></div>`).join("")}</div></div>`, true);
    $$(".thf", body).forEach((r) => (r.onclick = () => { document.getElementById("ux-modal").classList.remove("show"); exec(r.dataset.c); }));
  }

  // ---------------------------------------------------------------- keys, clock, lifecycle
  window.addEventListener("keydown", (e) => {
    if (!document.body.classList.contains("term")) return;
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
    if ((e.key === "/" && !typing) || (e.key.toLowerCase() === "k" && (e.ctrlKey || e.metaKey))) { e.preventDefault(); e.stopImmediatePropagation(); input.focus(); return; }
    if (FKEYS[e.key] || e.key === "F11") { e.preventDefault(); showPage(FKEYS[e.key] || "fx"); return; }
    if (e.altKey && /^[0-9]$/.test(e.key)) { const p = PAGES[(+e.key || 10) - 1]; if (p) { e.preventDefault(); showPage(p.id); } return; }
    if (e.key === "Escape" && grid.classList.contains("hasmax") && !typing && !document.querySelector(".modal-bg.show")) { panels.forEach((q) => q.el.classList.remove("max")); grid.classList.remove("hasmax"); }
  }, true);
  let rsz;
  window.addEventListener("resize", () => { clearTimeout(rsz); rsz = setTimeout(() => live && panels.forEach((p) => { if ($(".tsvg", p.body) && !(p.ctx && p.ctx.state.chart)) run(p, true); }), 400); });
  setInterval(() => { if (live) $("#tclock").textContent = new Date().toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" }); }, 1000);
  document.addEventListener("visibilitychange", () => { if (live && !document.hidden) panels.forEach((p) => run(p)); });

  async function start() {
    if (live) return;
    live = true;
    if (!localStorage.getItem("ch-term")) {                       // first time on this browser: bring the account's saved layout
      try { const st = await api("/api/state"); if (st.terminal && st.terminal.page) cfg = { ...DEF, ...st.terminal }; } catch {}
    }
    secChip();
    setSec(cfg.sec, true);
    showPage(cfg.page);
  }
  function stop() { live = false; stopAll(); }
  window.addEventListener("ts-mode", (e) => (e.detail === "terminal" ? start() : stop()));
  window.TERM = { exec, setSec, show: showPage, get sec() { return cfg.sec; } };
  if (TS.mode() === "terminal") setTimeout(start, 50);
})();
