// Shared helpers for both screens. The two windows stay in sync over a BroadcastChannel,
// so the Command screen (monitor 1) drives the Research screen (monitor 2).
const TS = (() => {
  const bus = new BroadcastChannel("tradescope");
  const listeners = [];
  bus.onmessage = (e) => listeners.forEach((f) => f(e.data));

  async function api(path, opts = {}) {
    const init = { ...opts };
    if (opts.body && typeof opts.body !== "string") {
      init.body = JSON.stringify(opts.body);
      init.headers = { "Content-Type": "application/json" };
      init.method = init.method || "POST";
    }
    const r = await fetch(path, init);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  }

  async function stream(path, body, onChunk) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const rd = r.body.getReader(), dec = new TextDecoder();
    let all = "";
    for (;;) {
      const { done, value } = await rd.read();
      if (done) break;
      all += dec.decode(value, { stream: true });
      onChunk(all);
    }
    return all;
  }

  const nf = (d) => new Intl.NumberFormat(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  function price(x) {
    if (x == null || !isFinite(x)) return "–";
    const a = Math.abs(x);
    return nf(a >= 1000 ? 2 : a >= 1 ? 2 : a >= 0.01 ? 4 : 6).format(x);
  }
  const money = (x, ccy) => (x == null || !isFinite(x) ? "–" : nf(x >= 100 ? 0 : 2).format(x) + (ccy ? " " + ccy : ""));
  const pct = (x, d = 2) => (x == null || !isFinite(x) ? "–" : (x > 0 ? "+" : "") + x.toFixed(d) + "%");
  const cls = (x) => (x > 0 ? "up" : x < 0 ? "down" : "muted");
  const big = (x) => {
    if (x == null) return "–";
    const a = Math.abs(x);
    return a >= 1e12 ? (x / 1e12).toFixed(2) + "T" : a >= 1e9 ? (x / 1e9).toFixed(2) + "B" : a >= 1e6 ? (x / 1e6).toFixed(1) + "M" : a >= 1e3 ? (x / 1e3).toFixed(1) + "K" : x.toFixed(0);
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const disp = (sym) => (sym || "").replace(/^SIM:/, "").replace(/^CUS:[^:]+:/, "");
  const sigClass = (s) => (s || "").replace(" ", "-");

  function scoreBar(s) {
    const w = Math.min(Math.abs(s), 100) / 2;
    const col = s >= 20 ? "var(--up)" : s <= -20 ? "var(--down)" : "#8791a6";
    return `<span class="scorebar"><i style="${s >= 0 ? "left:50%" : `left:${50 - w}%`};width:${w}%;background:${col}"></i></span>`;
  }
  function confRing(c) {
    const col = c >= 65 ? "var(--up)" : c >= 45 ? "var(--warn)" : "var(--down)";
    return `<span class="conf"><span class="ring" style="background:conic-gradient(${col} ${c * 3.6}deg,#1a2130 0)"></span><span class="num">${c.toFixed(0)}%</span></span>`;
  }
  function spark(arr, w = 90, h = 26) {
    if (!arr || arr.length < 2) return "";
    const mn = Math.min(...arr), mx = Math.max(...arr), r = mx - mn || 1;
    const pts = arr.map((v, i) => `${((i / (arr.length - 1)) * w).toFixed(1)},${(h - ((v - mn) / r) * (h - 2) - 1).toFixed(1)}`).join(" ");
    const col = arr[arr.length - 1] >= arr[0] ? "var(--up)" : "var(--down)";
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline fill="none" stroke="${col}" stroke-width="1.5" points="${pts}"/></svg>`;
  }
  function md(src) { // tiny markdown renderer for AI output (escaped first, so it's safe)
    const lines = esc(src).split("\n");
    let html = "", inList = false;
    const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*(.+?)\*/g, "<em>$1</em>").replace(/`(.+?)`/g, "<code>$1</code>");
    for (const ln of lines) {
      const m = ln.match(/^\s*[-*•]\s+(.*)/) || ln.match(/^\s*\d+\.\s+(.*)/);
      if (m) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(m[1])}</li>`; continue; }
      if (inList) { html += "</ul>"; inList = false; }
      if (/^###\s/.test(ln)) html += `<h3>${inline(ln.slice(4))}</h3>`;
      else if (/^##?\s/.test(ln)) html += `<h2>${inline(ln.replace(/^##?\s/, ""))}</h2>`;
      else if (ln.trim()) html += `<p>${inline(ln)}</p>`;
    }
    return html + (inList ? "</ul>" : "");
  }
  function toast(msg, ms = 2600) {
    let t = document.querySelector(".toast");
    if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
    t.textContent = msg; t.classList.add("show");
    clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), ms);
  }

  // beginner / pro mode shared across windows
  function mode() { try { return localStorage.getItem("ts-mode") || "beginner"; } catch { return "beginner"; } }
  function setMode(m, broadcast = true) {
    try { localStorage.setItem("ts-mode", m); } catch {}
    document.body.classList.toggle("pro", m === "pro");
    document.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("on", b.dataset.mode === m));
    if (broadcast) bus.postMessage({ type: "mode", mode: m });
  }
  listeners.push((m) => m.type === "mode" && setMode(m.mode, false));

  function bindSearch(input, box, onPick) {
    let h, items = [], sel = -1;
    const render = () => { box.innerHTML = items.map((x, i) => `<div class="${i === sel ? "sel" : ""}" data-i="${i}"><span><b>${esc(disp(x.symbol))}</b> <span class="muted">${esc(x.name)}</span></span><span class="dim">${esc(x.exchange)} · ${esc(x.type)}</span></div>`).join(""); box.classList.toggle("show", items.length > 0); };
    input.addEventListener("input", () => {
      clearTimeout(h);
      const q = input.value.trim();
      if (!q) { items = []; render(); return; }
      h = setTimeout(async () => { items = await api("/api/search?q=" + encodeURIComponent(q)).catch(() => []); sel = -1; render(); }, 220);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { sel = Math.min(sel + 1, items.length - 1); render(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { sel = Math.max(sel - 1, 0); render(); e.preventDefault(); }
      else if (e.key === "Enter") {
        const pick = items[sel] || items[0] || { symbol: input.value.trim().toUpperCase() };
        if (pick.symbol) { onPick(pick.symbol); items = []; render(); input.value = ""; input.blur(); }
      } else if (e.key === "Escape") { items = []; render(); input.blur(); }
    });
    box.addEventListener("mousedown", (e) => {
      const d = e.target.closest("[data-i]");
      if (d) { onPick(items[+d.dataset.i].symbol); items = []; render(); input.value = ""; }
    });
    input.addEventListener("blur", () => setTimeout(() => box.classList.remove("show"), 150));
    document.addEventListener("keydown", (e) => { if (e.key === "/" && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") { e.preventDefault(); input.focus(); } });
  }

  async function aiStatus(el) {
    const s = await api("/api/ai/status").catch(() => ({ online: false }));
    el.innerHTML = `<span class="dot ${s.online ? "on" : "off"}"></span>${s.online ? "Local AI · " + esc(s.model) : "AI offline (start Ollama)"}`;
    return s;
  }

  return { api, stream, send: (m) => bus.postMessage(m), on: (f) => listeners.push(f), price, money, pct, cls, big, esc, disp, sigClass,
           scoreBar, confRing, spark, md, toast, mode, setMode, bindSearch, aiStatus };
})();
