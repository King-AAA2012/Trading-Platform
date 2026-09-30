// Shared helpers for both screens. The two windows stay in sync over a BroadcastChannel,
// so the Command screen (monitor 1) drives the Research screen (monitor 2).
const TS = (() => {
  const bus = new BroadcastChannel("tradescope");
  const listeners = [];
  bus.onmessage = (e) => listeners.forEach((f) => f(e.data));

  // ---- resilient networking: if the local server is briefly unreachable (restarting, start.bat closed), retry
  // quietly, then show a "reconnecting" banner and resume automatically once it's back, instead of failing.
  let down = false, waiters = [];
  function banner(show) {
    let b = document.getElementById("ts-down");
    if (show && !b) {
      b = document.createElement("div");
      b.id = "ts-down";
      b.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:9998;background:#3a2a08;color:#ffe3a3;border-bottom:1px solid #f5b942;padding:9px 14px;font-size:13px;display:flex;gap:10px;align-items:center;justify-content:center";
      b.innerHTML = `<span class="spin"></span><b>Can't reach the CasuallyHedge server.</b><span>Keep the <b>start.bat</b> window open (or double-click it again). Reconnecting automatically… your settings are safe.</span>`;
      document.body.appendChild(b);
    }
    if (!show && b) b.remove();
  }
  async function waitForServer() {
    if (!down) {
      down = true;
      banner(true);
      (async () => {
        for (;;) {
          await new Promise((r) => setTimeout(r, 2000));
          try { const r = await fetch("/api/ai/status", { cache: "no-store" }); if (r.ok) break; } catch {}
        }
        down = false;
        banner(false);
        toast("✅ Reconnected to the CasuallyHedge server");
        waiters.splice(0).forEach((f) => f());
      })();
    }
    return new Promise((r) => waiters.push(r));
  }
  async function netFetch(path, init) {
    for (let attempt = 0; ; attempt++) {
      try {
        return await fetch(path, init);
      } catch (e) {                              // TypeError "Failed to fetch" = server unreachable, not an HTTP error
        if (attempt < 2) { await new Promise((r) => setTimeout(r, 600 * (attempt + 1))); continue; }
        await waitForServer();
        attempt = -1;
      }
    }
  }

  async function api(path, opts = {}) {
    const init = { ...opts };
    if (opts.body && typeof opts.body !== "string") {
      init.body = JSON.stringify(opts.body);
      init.headers = { "Content-Type": "application/json" };
      init.method = init.method || "POST";
    }
    const r = await netFetch(path, init);
    if (r.status === 401 && !path.startsWith("/api/auth")) { location.replace("/login.html#login"); throw new Error("Please log in."); }
    if (r.status === 402) { location.replace("/account.html?expired=1"); throw new Error("Subscription needed."); }
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  }

  async function stream(path, body, onChunk) {
    const r = await netFetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status} ${r.statusText}`);
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
  const disp = (sym) => sym || "";
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

  // ---- smart search: recent + popular on focus, instant local matches, live API results, inline autofill (Tab / →)
  const known = new Map();          // symbols the app already knows (scans, watchlist, holdings) for instant matches
  function remember(list) { (list || []).forEach((x) => x && x.symbol && !known.has(x.symbol) && known.set(x.symbol, { symbol: x.symbol, name: x.name || x.symbol, exchange: x.exchange || x.marketName || "", type: x.type || "Stock" })); }
  const POPULAR = [["AAPL", "Apple"], ["NVDA", "NVIDIA"], ["MSFT", "Microsoft"], ["TSLA", "Tesla"], ["AMZN", "Amazon"], ["RELIANCE.NS", "Reliance Industries"],
    ["BTC-USD", "Bitcoin"], ["SPY", "S&P 500 ETF"], ["GC=F", "Gold"], ["EURUSD=X", "EUR/USD"]].map(([symbol, name]) => ({ symbol, name, exchange: "", type: "Popular" }));
  const recent = () => { try { return JSON.parse(localStorage.getItem("ts-recent") || "[]"); } catch { return []; } };
  const pushRecent = (x) => { try { localStorage.setItem("ts-recent", JSON.stringify([x, ...recent().filter((r) => r.symbol !== x.symbol)].slice(0, 8))); } catch {} };

  function bindSearch(input, box, onPick, opts = {}) {
    let h, items = [], sel = 0, seq = 0;
    const label = (x) => `<div class="${items.indexOf(x) === sel ? "sel" : ""}" data-i="${items.indexOf(x)}"><span><b>${esc(disp(x.symbol))}</b> <span class="muted">${esc(x.name)}</span></span><span class="dim">${esc([x.exchange, x.type].filter(Boolean).join(" · "))}</span></div>`;
    const render = (head) => {
      box.innerHTML = (head ? `<div class="dim" style="font-size:10.5px;padding:6px 11px 2px;cursor:default;text-transform:uppercase;letter-spacing:.5px">${head}</div>` : "") + items.map(label).join("") +
        (items.length ? `<div class="dim" style="font-size:10.5px;padding:5px 11px;cursor:default;border-top:1px solid var(--line)">↑↓ choose · Enter open · Tab autocomplete · Esc close</div>` : "");
      box.classList.toggle("show", items.length > 0);
    };
    const localMatches = (q) => {
      const ql = q.toLowerCase();
      const pool = [...recent(), ...known.values(), ...POPULAR];
      const seen = new Set(), out = [];
      for (const x of pool) {
        if (seen.has(x.symbol)) continue;
        const sym = disp(x.symbol).toLowerCase(), nm = (x.name || "").toLowerCase();
        const rank = sym.startsWith(ql) ? 0 : nm.startsWith(ql) ? 1 : sym.includes(ql) || nm.includes(ql) ? 2 : -1;
        if (rank >= 0) { seen.add(x.symbol); out.push([rank, x]); }
      }
      return out.sort((a, b) => a[0] - b[0]).slice(0, 8).map((r) => r[1]);
    };
    const autofill = (typed, e) => {   // complete the top symbol inline, leaving the completion selected
      if (!items.length || (e && e.inputType && e.inputType.startsWith("delete"))) return;
      const top = disp(items[0].symbol);
      if (top.toLowerCase().startsWith(typed.toLowerCase()) && top.length > typed.length && input.value === typed) {
        input.value = typed + top.slice(typed.length);
        input.setSelectionRange(typed.length, top.length);
      }
    };
    const showStart = () => {
      if (input.value.trim()) return;
      items = [...recent(), ...POPULAR.filter((p) => !recent().some((r) => r.symbol === p.symbol))].slice(0, 10);
      sel = 0; render(recent().length ? "Recent & popular" : "Popular");
    };
    input.addEventListener("focus", showStart);
    input.addEventListener("input", (e) => {
      clearTimeout(h);
      const typed = input.value.slice(0, input.selectionStart ?? input.value.length).trim();
      if (!typed) { showStart(); return; }
      items = localMatches(typed); sel = 0; render(items.length ? "Matches" : ""); autofill(typed, e);
      const my = ++seq;
      h = setTimeout(async () => {
        const res = await api("/api/search?q=" + encodeURIComponent(typed)).catch(() => []);
        if (my !== seq) return;
        const seen = new Set(items.map((x) => x.symbol));
        items = [...items, ...res.filter((x) => !seen.has(x.symbol))].slice(0, 12);
        render("Matches"); autofill(typed, e);
      }, 180);
    });
    const pick = (x) => {
      if (!x || !x.symbol) return;
      pushRecent({ symbol: x.symbol, name: x.name, exchange: x.exchange, type: x.type === "Popular" ? "" : x.type });
      items = []; render();
      if (!opts.keepValue) { input.value = ""; input.blur(); } else input.value = disp(x.symbol);
      onPick(x.symbol, x);
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { sel = Math.min(sel + 1, items.length - 1); render(input.value ? "Matches" : "Recent & popular"); e.preventDefault(); }
      else if (e.key === "ArrowUp") { sel = Math.max(sel - 1, 0); render(input.value ? "Matches" : "Recent & popular"); e.preventDefault(); }
      else if ((e.key === "Tab" || e.key === "ArrowRight") && input.selectionStart !== input.selectionEnd) {   // accept autofill
        input.setSelectionRange(input.value.length, input.value.length); e.preventDefault();
      } else if (e.key === "Enter") {
        e.preventDefault();
        const typed = input.value.trim().toUpperCase();
        pick(items[sel] || items.find((x) => disp(x.symbol).toUpperCase() === typed) || (typed ? { symbol: typed, name: typed } : null));
      } else if (e.key === "Escape") { items = []; render(); input.blur(); }
    });
    box.addEventListener("mousedown", (e) => { const d = e.target.closest("[data-i]"); if (d) { e.preventDefault(); pick(items[+d.dataset.i]); } });
    input.addEventListener("blur", () => setTimeout(() => box.classList.remove("show"), 150));
    if (opts.global !== false)
      document.addEventListener("keydown", (e) => { if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) { e.preventDefault(); input.focus(); } });
  }

  // ---- visible error banner: a broken page should say so, not silently stop responding
  function showError(msg) {
    let b = document.getElementById("ts-err");
    if (!b) {
      b = document.createElement("div");
      b.id = "ts-err";
      b.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:9999;background:#3a0f18;color:#ffd5dc;border-bottom:1px solid #ff5470;padding:8px 14px;font-size:12.5px;display:flex;gap:10px;align-items:center";
      document.body.appendChild(b);
    }
    b.innerHTML = `<b>Something went wrong:</b><span style="flex:1">${esc(msg)}</span><button class="btn sm" onclick="location.reload(true)">Reload page</button><button class="btn sm ghost" onclick="this.parentNode.remove()">✕</button>`;
  }
  window.addEventListener("error", (e) => { if (e.message && !/ResizeObserver loop/.test(e.message)) showError(e.message + (e.filename ? ` (${e.filename.split("/").pop()}:${e.lineno})` : "")); });
  window.addEventListener("unhandledrejection", (e) => { const m = String(e.reason?.message || e.reason); if (!/Failed to fetch|NetworkError|network error/i.test(m)) showError(m); });

  async function aiStatus(el) {
    const s = await api("/api/ai/status").catch(() => ({ online: false }));
    el.innerHTML = `<span class="dot ${s.online ? "on" : "off"}"></span>${s.online ? "Local AI · " + esc(s.model) : "AI offline (start Ollama)"}`;
    return s;
  }

  return { api, stream, send: (m) => bus.postMessage(m), on: (f) => listeners.push(f), price, money, pct, cls, big, esc, disp, sigClass,
           scoreBar, confRing, spark, md, toast, mode, setMode, bindSearch, aiStatus, remember, showError };
})();
