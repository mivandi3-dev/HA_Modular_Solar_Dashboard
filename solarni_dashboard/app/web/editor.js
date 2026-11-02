// Editor rasporeda widgeta – ubacuje ga desktop/launcher.py u dashboard (uz overlay.js).
// Izvan cijelog zaslona desno je izbornik widgeta; widgeti se povlače na mrežu 12 × 5 ispod zaglavlja,
// premještaju, mijenjaju veličinu (kut dolje desno) i uklanjaju. Raspored se sprema preko
// pywebview.api.save_layout (provjera u solar/layout.py), a prikaz se odmah iscrta iznova.
// Rasporeda (stranica) može biti više: dok je izbornik otvoren prikazuje se stranica koja se uređuje,
// inače se stranice izmjenjuju svakih N sekundi (pages.js).
(() => {
  if (window.__solariEditor) return;
  window.__solariEditor = true;
  const opts = window.SOLARI_OPTIONS || {};
  const SIDEBAR_W = 340; // isto kao SIDEBAR_CSS_W u launcher.py
  const GAP = 14; // razmak u mreži (ui.GRID_GAP)
  const api = () => window.pywebview && window.pywebview.api;
  const T = window.T || ((s) => s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  let ed = null; // { catalog, categories, layout, pages, page, rotateS, cols, rows, hasMeter }
  let fullscreen = Boolean(opts.fullscreen);
  let open = true;
  let undo = [];
  let drag = null; // { mode: "move"|"resize"|"add", item, spec, ... }

  // ------------------------------------------------------------ stil
  const css = document.createElement("style");
  css.textContent = `
    html.se-on .stApp { right: ${SIDEBAR_W}px !important; width: auto !important; }
    html.se-on #solari-bar { right: ${SIDEBAR_W + 14}px; }
    #se-side { position: fixed; top: 0; right: 0; bottom: 0; width: ${SIDEBAR_W}px; z-index: 999990; display: flex;
      flex-direction: column; background: var(--card-solid, #1A2540); border-left: 1px solid var(--border, rgba(255,255,255,.08));
      box-shadow: -10px 0 30px rgba(0,0,0,.25); color: var(--text, #E6EAF2); font: 14px 'Plus Jakarta Sans', 'Segoe UI', sans-serif;
      transform: translateX(100%); transition: transform .2s ease; }
    html.se-on #se-side { transform: none; }
    #se-side header { padding: 18px 18px 10px; display: flex; align-items: center; justify-content: space-between; }
    #se-side h2 { margin: 0; font-size: 18px; } #se-side .hint { margin: 0 18px 10px; color: var(--muted, #94A3B8); font-size: 12.5px; line-height: 1.45; }
    #se-side input[type=search] { margin: 0 18px 8px; padding: 9px 12px; border-radius: 11px; border: 1px solid var(--line, rgba(255,255,255,.1));
      background: rgba(0,0,0,.18); color: inherit; font: inherit; outline: none; }
    #se-side input[type=search]:focus { border-color: #71BF43; }
    #se-pages { margin: 0 18px 10px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
    #se-pages .lbl { font-size: 11.5px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted, #94A3B8); margin-right: 2px; }
    #se-pages button { min-width: 32px; height: 30px; border-radius: 9px; cursor: pointer; font: 700 12.5px 'Plus Jakarta Sans', sans-serif;
      color: inherit; background: rgba(255,255,255,.05); border: 1px solid var(--line, rgba(255,255,255,.1)); padding: 0 9px; }
    #se-pages button.on { background: #71BF43; border-color: #71BF43; color: #0B1120; }
    #se-pages button:hover:not(.on) { border-color: #71BF43; }
    #se-pages button.rm.confirm { background: #F87171; border-color: #F87171; color: #fff; }
    #se-pages select { margin-left: auto; font: 600 12px 'Plus Jakarta Sans', sans-serif; color: inherit; background: rgba(0,0,0,.18);
      border: 1px solid var(--line, rgba(255,255,255,.1)); border-radius: 9px; padding: 5px 6px; }
    #se-list { flex: 1; overflow-y: auto; padding: 4px 12px 12px; }
    #se-list h3 { font-size: 11.5px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted, #94A3B8); margin: 14px 6px 6px; }
    .se-item { display: grid; grid-template-columns: 38px 1fr auto; gap: 10px; align-items: center; padding: 9px 10px; margin-bottom: 6px;
      border-radius: 13px; border: 1px solid var(--line, rgba(255,255,255,.08)); background: rgba(0,0,0,.12); cursor: grab; user-select: none;
      transition: border-color .15s, background .15s, transform .1s; }
    .se-item:hover { border-color: #71BF43; background: rgba(113,191,67,.1); }
    .se-item:active { cursor: grabbing; transform: scale(.98); }
    .se-item .i { width: 38px; height: 38px; border-radius: 11px; display: grid; place-items: center; font-size: 19px; background: rgba(113,191,67,.14); }
    .se-item b { display: block; font-size: 13.5px; } .se-item small { display: block; color: var(--muted, #94A3B8); font-size: 11.5px; line-height: 1.35; }
    .se-item .sz { font-size: 11px; font-weight: 700; color: var(--muted, #94A3B8); }
    .se-item .add { border: 0; background: #71BF43; color: #0B1120; width: 26px; height: 26px; border-radius: 8px; font-weight: 800; cursor: pointer; margin-top: 4px; }
    .se-item.used { opacity: .55; }
    #se-side footer { padding: 12px 14px; border-top: 1px solid var(--line, rgba(255,255,255,.08)); display: flex; flex-wrap: wrap; gap: 8px; }
    #se-side footer button, #se-side header button { font: 600 12.5px 'Plus Jakarta Sans', 'Segoe UI', sans-serif; color: inherit;
      background: rgba(255,255,255,.05); border: 1px solid var(--line, rgba(255,255,255,.1)); border-radius: 10px; padding: 7px 11px; cursor: pointer; }
    #se-side footer button:hover, #se-side header button:hover { border-color: #71BF43; }
    #se-status { width: 100%; font-size: 12px; min-height: 16px; color: var(--muted, #94A3B8); }
    #se-status.err { color: #F87171; } #se-status.ok { color: #71BF43; }
    #se-tab { position: fixed; right: 0; top: 50%; transform: translateY(-50%); z-index: 999989; display: none; writing-mode: vertical-rl;
      padding: 14px 8px; border-radius: 12px 0 0 12px; background: #71BF43; color: #0B1120; font: 700 13px 'Plus Jakarta Sans', sans-serif; cursor: pointer; border: 0; }
    html.se-window:not(.se-on) #se-tab { display: block; }
    #se-frames { position: fixed; z-index: 999980; pointer-events: none; display: none; }
    html.se-window #se-frames { display: block; }
    .se-frame { position: absolute; pointer-events: auto; border-radius: 22px; border: 2px dashed transparent; cursor: move; transition: border-color .12s, background .12s; }
    .se-frame:hover, .se-frame.active { border-color: rgba(113,191,67,.9); background: rgba(113,191,67,.05); }
    .se-frame .tools { position: absolute; top: 8px; right: 8px; display: none; gap: 6px; }
    .se-frame:hover .tools { display: flex; }
    .se-frame .tools button { width: 30px; height: 30px; border-radius: 9px; border: 0; cursor: pointer; font-size: 14px;
      background: var(--card-solid, #1A2540); color: var(--text, #E6EAF2); box-shadow: 0 4px 12px rgba(0,0,0,.3); }
    .se-frame .tools button.rm:hover { background: #F87171; color: #fff; }
    .se-frame .label { position: absolute; left: 10px; bottom: 8px; display: none; font: 700 11.5px 'Plus Jakarta Sans', sans-serif;
      background: #71BF43; color: #0B1120; padding: 3px 9px; border-radius: 99px; }
    .se-frame:hover .label { display: block; }
    .se-frame .resize { position: absolute; right: 2px; bottom: 2px; width: 22px; height: 22px; cursor: nwse-resize; display: none;
      background: linear-gradient(135deg, transparent 50%, #71BF43 50%); border-radius: 0 0 20px 0; }
    .se-frame:hover .resize { display: block; }
    #se-cells { position: absolute; inset: 0; display: none; pointer-events: none; }
    html.se-dragging #se-cells { display: grid; }
    #se-cells i { border-radius: 14px; border: 1px dashed rgba(148,163,184,.35); }
    #se-ghost { position: fixed; z-index: 999995; pointer-events: none; display: none; border-radius: 22px; border: 2px solid #71BF43;
      background: rgba(113,191,67,.18); color: #fff; font: 700 13px 'Plus Jakarta Sans', sans-serif; place-items: center; text-align: center; }
    #se-ghost.bad { border-color: #F87171; background: rgba(248,113,113,.18); }
    #se-float { position: fixed; z-index: 999996; pointer-events: none; display: none; padding: 8px 12px; border-radius: 11px;
      background: #71BF43; color: #0B1120; font: 700 13px 'Plus Jakarta Sans', sans-serif; box-shadow: 0 10px 24px rgba(0,0,0,.35); }
    #se-pop { position: fixed; z-index: 999997; display: none; width: 300px; padding: 16px; border-radius: 16px; background: var(--card-solid, #1A2540);
      color: var(--text, #E6EAF2); border: 1px solid var(--border, rgba(255,255,255,.1)); box-shadow: 0 20px 50px rgba(0,0,0,.45);
      font: 13.5px 'Plus Jakarta Sans', 'Segoe UI', sans-serif; }
    #se-pop h4 { margin: 0 0 10px; font-size: 15px; }
    #se-pop label { display: flex; flex-direction: column; gap: 5px; margin-bottom: 10px; color: var(--muted, #94A3B8); font-weight: 600; font-size: 12px; }
    #se-pop select, #se-pop input, #se-pop textarea { font: 600 13.5px 'Plus Jakarta Sans', sans-serif; color: var(--text, #E6EAF2);
      background: rgba(0,0,0,.2); border: 1px solid var(--line, rgba(255,255,255,.12)); border-radius: 9px; padding: 8px 10px; }
    #se-pop textarea { min-height: 70px; resize: vertical; }
    #se-pop .row { display: flex; justify-content: flex-end; gap: 8px; }
    #se-pop button { font: 700 12.5px 'Plus Jakarta Sans', sans-serif; border-radius: 9px; padding: 8px 12px; cursor: pointer;
      border: 1px solid var(--line, rgba(255,255,255,.12)); background: transparent; color: inherit; }
    #se-pop button.primary { background: #71BF43; border-color: #71BF43; color: #0B1120; }
    #se-lock { position: fixed; inset: 0; z-index: 1000000; display: flex; align-items: center; justify-content: center;
      background: rgba(5,10,20,.62); font: 14px 'Plus Jakarta Sans', 'Segoe UI', sans-serif; color: var(--text, #E6EAF2); }
    #se-lock[hidden] { display: none; }
    #se-lock .box { width: min(380px, 92vw); background: var(--card-solid, #1A2540); border: 1px solid var(--border, rgba(255,255,255,.1));
      border-radius: 18px; padding: 20px 22px; box-shadow: 0 20px 50px rgba(0,0,0,.45); }
    #se-lock h3 { margin: 0 0 6px; font-size: 17px; } #se-lock p { margin: 0 0 14px; color: var(--muted, #94A3B8); font-size: 13px; line-height: 1.45; }
    #se-lock input { width: 100%; box-sizing: border-box; font: 700 20px 'Plus Jakarta Sans', sans-serif; letter-spacing: .3em; text-align: center;
      color: inherit; background: rgba(0,0,0,.22); border: 1px solid var(--line, rgba(255,255,255,.14)); border-radius: 11px; padding: 10px; outline: none; }
    #se-lock input:focus { border-color: #71BF43; }
    #se-lock .msg { min-height: 18px; margin: 8px 0 4px; color: #F87171; font-size: 12.5px; }
    #se-lock .row { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
    #se-lock button { font: 700 13px 'Plus Jakarta Sans', sans-serif; border-radius: 10px; padding: 9px 14px; cursor: pointer;
      border: 1px solid var(--line, rgba(255,255,255,.14)); background: transparent; color: inherit; }
    #se-lock button.primary { background: #71BF43; border-color: #71BF43; color: #0B1120; }`;
  document.head.appendChild(css);

  // ------------------------------------------------------------ elementi
  const side = document.createElement("aside");
  side.id = "se-side";
  side.setAttribute("aria-label", T("Widgeti"));
  side.innerHTML = `
    <header><h2>${T("Widgeti")}</h2><button type="button" data-se="close" title="${T("Sakrij izbornik")}">${T("Sakrij")} ›</button></header>
    <p class="hint">${T("Povucite widget na ekran ili kliknite <b>+</b>. Widget na ekranu premjestite povlačenjem, veličinu mijenjate kutom dolje desno, ⚙ su opcije, ✕ uklanja. U cijelom zaslonu (F11 ili Alt + Enter) izbornik se skriva.")}</p>
    <div id="se-pages" role="group" aria-label="${T("Stranice rasporeda")}"></div>
    <input type="search" placeholder="${T("Traži widget…")}" aria-label="${T("Traži widget")}">
    <div id="se-list"></div>
    <footer>
      <button type="button" data-se="undo">↶ ${T("Poništi")}</button>
      <button type="button" data-se="reset">↺ ${T("Zadani raspored")}</button>
      <button type="button" data-se="images">🖼 ${T("Slike…")}</button>
      <div id="se-status" role="status"></div>
    </footer>`;
  document.body.appendChild(side);
  const tab = document.createElement("button");
  tab.id = "se-tab";
  tab.type = "button";
  tab.textContent = "‹ " + T("Widgeti");
  document.body.appendChild(tab);
  const frames = document.createElement("div");
  frames.id = "se-frames";
  document.body.appendChild(frames);
  const ghost = document.createElement("div");
  ghost.id = "se-ghost";
  document.body.appendChild(ghost);
  const float = document.createElement("div");
  float.id = "se-float";
  document.body.appendChild(float);
  const pop = document.createElement("div");
  pop.id = "se-pop";
  document.body.appendChild(pop);

  const status = (msg, cls = "") => { const el = side.querySelector("#se-status"); el.textContent = msg; el.className = cls; };

  // ------------------------------------------------------------ 5.0.2 (audit W-02): raspored se mijenja samo uz PIN postavki
  const lock = document.createElement("div");
  lock.id = "se-lock";
  lock.hidden = true;
  lock.innerHTML = `<form class="box" autocomplete="off"><h3>${esc(T("Raspored je zaključan"))}</h3>
    <p>${esc(T("Za izmjenu rasporeda upišite PIN postavki. Otključano ostaje 10 minuta."))}</p>
    <input type="password" inputmode="numeric" maxlength="8" aria-label="${esc(T("PIN postavki"))}">
    <div class="msg" role="alert"></div>
    <div class="row"><button type="button" data-lock="cancel">${esc(T("Odustani"))}</button>
      <button type="submit" class="primary">${esc(T("Otključaj"))}</button></div></form>`;
  document.body.appendChild(lock);
  let lockWait = null;
  function askPin() {
    if (lockWait) return lockWait;
    lockWait = new Promise((resolve) => {
      const input = lock.querySelector("input"), msg = lock.querySelector(".msg"), form = lock.querySelector("form");
      const done = (ok) => { lock.hidden = true; input.value = ""; msg.textContent = ""; form.onsubmit = null; lockWait = null; resolve(ok); };
      lock.querySelector("[data-lock=cancel]").onclick = () => done(false);
      form.onsubmit = async (e) => {
        e.preventDefault();
        const r = await api().unlock_layout(input.value);
        if (r && r.ok) { done(true); return; }
        msg.textContent = (r && r.message) || T("Pogrešan PIN.");
        input.select();
      };
      lock.hidden = false;
      setTimeout(() => input.focus(), 30);
    });
    return lockWait;
  }
  // poziv mosta koji mijenja raspored: zaključan raspored → PIN, pa isti poziv još jednom
  async function guarded(call) {
    let res = await call();
    if (res && res.error === "layout_locked") {
      if (!(await askPin())) return { ok: false, message: T("Raspored nije promijenjen.") };
      res = await call();
    }
    return res;
  }
  const spec = (type) => ed.catalog.find((c) => c.key === type);

  // ------------------------------------------------------------ mreža
  function gridRect() {
    const g = document.querySelector(`.st-key-grid-p${ed ? ed.page : 0}`);
    return g ? g.getBoundingClientRect() : null;
  }
  function metrics() {
    const r = gridRect();
    if (!r || !r.width) return null;
    const cw = (r.width - GAP * (ed.cols - 1)) / ed.cols;
    const rh = (r.height - GAP * (ed.rows - 1)) / ed.rows;
    return { r, cw, rh };
  }
  function boxOf(m, it) {
    return { left: m.r.left + it.x * (m.cw + GAP), top: m.r.top + it.y * (m.rh + GAP),
             width: it.w * m.cw + (it.w - 1) * GAP, height: it.h * m.rh + (it.h - 1) * GAP };
  }
  function cellAt(m, px, py) {
    return { x: Math.floor((px - m.r.left + GAP / 2) / (m.cw + GAP)), y: Math.floor((py - m.r.top + GAP / 2) / (m.rh + GAP)) };
  }
  const overlaps = (a, b) => !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);
  function fits(cand, ignoreId) {
    if (cand.x < 0 || cand.y < 0 || cand.x + cand.w > ed.cols || cand.y + cand.h > ed.rows) return false;
    return !ed.layout.some((o) => o.id !== ignoreId && overlaps(cand, o));
  }
  function freeSlot(w, h) {
    for (let y = 0; y + h <= ed.rows; y++) for (let x = 0; x + w <= ed.cols; x++) if (fits({ x, y, w, h })) return { x, y };
    return null;
  }

  // ------------------------------------------------------------ stranice rasporeda
  const rotateLabel = (s) => (!s ? T("bez izmjene") : s < 60 ? T("svakih {n} s", { n: s }) : T("svakih {n} min", { n: s / 60 }));
  let confirmRemove = false;
  function renderPages() {
    const box = side.querySelector("#se-pages");
    const tabs = ed.pages.map((_, i) => `<button type="button" data-page="${i}" class="${i === ed.page ? "on" : ""}"
      title="${T("Stranica {n}", { n: i + 1 })}">${i + 1}</button>`).join("");
    const add = ed.pages.length < ed.maxPages ? `<button type="button" data-page-add title="${T("Dodaj stranicu")}">+</button>` : "";
    const rm = ed.pages.length > 1 ? `<button type="button" class="rm ${confirmRemove ? "confirm" : ""}" data-page-rm
      title="${T("Ukloni ovu stranicu")}">${confirmRemove ? T("Ukloniti?") : "🗑"}</button>` : "";
    const rotate = ed.pages.length > 1 ? `<select data-rotate aria-label="${T("Izmjena stranica")}" title="${T("Izmjena stranica")}">${
      ed.rotateChoices.map((s) => `<option value="${s}" ${s === ed.rotateS ? "selected" : ""}>${esc(rotateLabel(s))}</option>`).join("")}</select>` : "";
    box.innerHTML = `<span class="lbl">${T("Stranice")}</span>${tabs}${add}${rm}${rotate}`;
  }
  function syncEditing() {
    const sp = window.SolariPages;
    if (!sp || !ed) return;
    if (!fullscreen && open) sp.edit(ed.page); else sp.stopEdit();
  }
  function selectPage(n) {
    ed.page = Math.max(0, Math.min(ed.pages.length - 1, n));
    ed.layout = ed.pages[ed.page];
    confirmRemove = false;
    renderPages();
    renderList(side.querySelector("input[type=search]").value);
    syncEditing();
    setTimeout(renderFrames, 300);
  }
  async function addPage() {
    const res = await guarded(() => api().save_layout([], ed.pages.length));
    if (!res.ok) { status(res.message, "err"); return; }
    ed.pages = [...ed.pages, res.layout];
    selectPage(ed.pages.length - 1);
    status(T("Dodana je stranica {n} – povucite widgete na nju.", { n: ed.pages.length }), "ok");
    refreshDashboard();
  }
  async function removePage() {
    if (!confirmRemove) { confirmRemove = true; renderPages(); return; }
    const res = await guarded(() => api().remove_page(ed.page));
    if (!res.ok) { status(res.message, "err"); return; }
    undo = [];
    ed.pages = res.pages;
    selectPage(Math.min(ed.page, ed.pages.length - 1));
    status(T("Stranica je uklonjena."), "ok");
    refreshDashboard();
  }
  async function setRotation(seconds) {
    const res = await guarded(() => api().set_rotation(seconds));
    if (!res.ok) { status(res.message, "err"); return; }
    ed.rotateS = seconds;
    status(T("Izmjena stranica: {when}", { when: rotateLabel(seconds) }), "ok");
    refreshDashboard();
  }

  // ------------------------------------------------------------ iscrtavanje
  function renderList(filter = "") {
    const q = filter.trim().toLowerCase();
    const used = new Set(ed.layout.map((i) => i.type));
    side.querySelector("#se-list").innerHTML = ed.categories.map((cat) => {
      // widgeti uređaja (needs: battery, temperature, grid) samo kad ih odabrani uređaj podržava
      const items = ed.catalog.filter((c) => c.category === cat && (!c.needs || (ed.capabilities || []).includes(c.needs))
        && (!q || (T(c.title) + " " + T(c.description)).toLowerCase().includes(q)));
      if (!items.length) return "";
      return `<h3>${esc(T(cat))}</h3>` + items.map((c) => `
        <div class="se-item ${used.has(c.key) ? "used" : ""}" data-type="${esc(c.key)}" title="${used.has(c.key) ? T("Već je na ekranu – može se dodati još jednom") : ""}">
          <span class="i">${c.icon}</span>
          <span><b>${esc(T(c.title))}</b><small>${esc(T(c.description))}${c.needsMeter && !ed.hasMeter ? " (" + T("potreban mjerač") + ")" : ""}</small></span>
          <span style="text-align:center"><span class="sz">${c.size[0]}×${c.size[1]}</span><br>
            <button type="button" class="add" data-add="${esc(c.key)}" title="${T("Dodaj na prvo slobodno mjesto")}">+</button></span>
        </div>`).join("");
    }).join("") || `<p class="hint">${esc(T("Nema widgeta za „{q}”.", { q: filter }))}</p>`;
  }

  function renderFrames() {
    const m = ed && metrics();
    if (!m || fullscreen) { frames.innerHTML = ""; return; }
    frames.style.cssText = `left:0;top:0;width:100vw;height:100vh`;
    const cells = Array.from({ length: ed.cols * ed.rows }, () => "<i></i>").join("");
    frames.innerHTML = `<div id="se-cells" style="left:${m.r.left}px;top:${m.r.top}px;width:${m.r.width}px;height:${m.r.height}px;
        position:absolute;grid-template-columns:repeat(${ed.cols},1fr);grid-template-rows:repeat(${ed.rows},1fr);gap:${GAP}px">${cells}</div>`
      + ed.layout.map((it) => {
        const b = boxOf(m, it), s = spec(it.type);
        const hasOpts = s && s.options.length;
        return `<div class="se-frame" data-id="${esc(it.id)}" style="left:${b.left}px;top:${b.top}px;width:${b.width}px;height:${b.height}px">
          <div class="tools">${hasOpts ? `<button type="button" data-opt="${esc(it.id)}" title="${T("Opcije")}">⚙</button>` : ""}
            <button type="button" class="rm" data-rm="${esc(it.id)}" title="${T("Ukloni")}">✕</button></div>
          <span class="label">${esc(s ? T(s.title) : it.type)} · ${it.w}×${it.h}</span><span class="resize" data-resize="${esc(it.id)}" title="${T("Promijeni veličinu")}"></span></div>`;
      }).join("");
  }

  function setMode() {
    const root = document.documentElement;
    root.classList.toggle("se-window", !fullscreen);
    root.classList.toggle("se-on", !fullscreen && open);
    syncEditing();
    renderFrames();
  }

  // ------------------------------------------------------------ spremanje
  function refreshDashboard() {
    if (window.solariRender) window.solariRender(); // dashboard.js odmah iscrta novi raspored
  }
  async function commit(next, message) {
    const prev = ed.layout, page = ed.page;
    ed.layout = next; // odmah prikaži, provjera i spremanje u pozadini
    renderFrames();
    renderList(side.querySelector("input[type=search]").value);
    const res = await guarded(() => api().save_layout(next, page));
    if (!res.ok) {
      ed.layout = prev;
      renderFrames();
      status(res.message, "err");
      return false;
    }
    undo.push({ page, layout: prev });
    if (undo.length > 30) undo.shift();
    ed.pages[page] = res.layout;
    ed.layout = res.layout;
    status(message, "ok");
    refreshDashboard();
    setTimeout(renderFrames, 600);
    return true;
  }
  const newId = (type) => `${type.replace(/_/g, "-").slice(0, 24)}-${Math.random().toString(16).slice(2, 8)}`;
  const defaults = (s) => Object.fromEntries(s.options.map((o) => [o.key, o.default]));

  function addWidget(type, x, y, w, h) {
    const s = spec(type);
    return commit([...ed.layout, { id: newId(type), type, x, y, w, h, options: defaults(s) }], T("Dodano: {name}", { name: T(s.title) }));
  }
  function addToFreeSlot(type) {
    const s = spec(type);
    const slot = freeSlot(...s.size) ? [...s.size] : freeSlot(...s.minSize) ? [...s.minSize] : null;
    if (!slot) { status(T("Nema slobodnog mjesta – uklonite ili smanjite neki widget."), "err"); return; }
    const pos = freeSlot(...slot);
    addWidget(type, pos.x, pos.y, slot[0], slot[1]);
  }

  // ------------------------------------------------------------ povlačenje
  function showGhost(m, cand, ok, text) {
    const b = boxOf(m, cand);
    ghost.style.cssText = `display:grid;left:${b.left}px;top:${b.top}px;width:${b.width}px;height:${b.height}px`;
    ghost.className = ok ? "" : "bad";
    ghost.textContent = text;
  }
  function endDrag() {
    ghost.style.display = "none";
    float.style.display = "none";
    document.documentElement.classList.remove("se-dragging");
    frames.querySelectorAll(".se-frame.active").forEach((f) => f.classList.remove("active"));
    drag = null;
  }
  function onMove(e) {
    if (!drag) return;
    const m = metrics();
    if (!m) return;
    const c = cellAt(m, e.clientX, e.clientY);
    if (drag.mode === "add") {
      float.style.cssText = `display:block;left:${e.clientX + 14}px;top:${e.clientY + 10}px`;
      const inside = e.clientX >= m.r.left && e.clientX <= m.r.right && e.clientY >= m.r.top && e.clientY <= m.r.bottom;
      if (!inside) { ghost.style.display = "none"; drag.cand = null; return; }
      // zadana veličina, a ako ne stane – najmanja
      const sizes = [drag.spec.size, drag.spec.minSize];
      let cand = null;
      for (const [w, h] of sizes) {
        const x = Math.min(Math.max(0, c.x - Math.floor(w / 2)), ed.cols - w), y = Math.min(Math.max(0, c.y), ed.rows - h);
        cand = { x, y, w, h };
        if (fits(cand)) break;
      }
      drag.cand = cand;
      drag.ok = fits(cand);
      showGhost(m, cand, drag.ok, drag.ok ? `${T(drag.spec.title)} · ${cand.w}×${cand.h}` : T("Nema mjesta"));
      return;
    }
    const it = drag.item, s = spec(it.type);
    let cand;
    if (drag.mode === "move") {
      cand = { ...it, x: Math.min(Math.max(0, c.x - drag.dx), ed.cols - it.w), y: Math.min(Math.max(0, c.y - drag.dy), ed.rows - it.h) };
    } else {
      const w = Math.min(Math.max(s.minSize[0], c.x - it.x + 1), s.maxSize[0], ed.cols - it.x);
      const h = Math.min(Math.max(s.minSize[1], c.y - it.y + 1), s.maxSize[1], ed.rows - it.y);
      cand = { ...it, w, h };
    }
    drag.cand = cand;
    drag.ok = fits(cand, it.id);
    showGhost(m, cand, drag.ok, drag.ok ? `${cand.w}×${cand.h}` : T("Preklapa se"));
  }
  async function onUp() {
    if (!drag) return;
    const d = drag;
    endDrag();
    if (!d.cand || !d.ok) { if (d.cand) status(T("Widget se ne smije preklapati s drugim."), "err"); return; }
    if (d.mode === "add") { await addWidget(d.spec.key, d.cand.x, d.cand.y, d.cand.w, d.cand.h); return; }
    const it = d.item, c = d.cand;
    if (c.x === it.x && c.y === it.y && c.w === it.w && c.h === it.h) return;
    await commit(ed.layout.map((o) => (o.id === it.id ? { ...o, x: c.x, y: c.y, w: c.w, h: c.h } : o)),
      d.mode === "move" ? T("Widget premješten") : T("Veličina promijenjena"));
  }
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drag) { endDrag(); e.stopPropagation(); }
    if (e.ctrlKey && e.key.toLowerCase() === "z" && !fullscreen) { e.preventDefault(); doUndo(); }
  }, true);

  frames.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest("button")) return;
    const frame = e.target.closest(".se-frame");
    if (!frame) return;
    const it = ed.layout.find((o) => o.id === frame.dataset.id);
    const m = metrics();
    if (!it || !m) return;
    e.preventDefault();
    const c = cellAt(m, e.clientX, e.clientY);
    drag = { mode: e.target.dataset.resize ? "resize" : "move", item: it, dx: c.x - it.x, dy: c.y - it.y };
    frame.classList.add("active");
    document.documentElement.classList.add("se-dragging");
  });
  frames.addEventListener("click", (e) => {
    const rm = e.target.closest("[data-rm]"), opt = e.target.closest("[data-opt]");
    if (rm) {
      const it = ed.layout.find((o) => o.id === rm.dataset.rm);
      commit(ed.layout.filter((o) => o.id !== rm.dataset.rm), T("Uklonjeno: {name} (Ctrl + Z za povrat)", { name: T(spec(it.type).title) }));
    }
    if (opt) openOptions(opt.dataset.opt, opt.closest(".se-frame").getBoundingClientRect());
  });
  frames.addEventListener("dblclick", (e) => e.stopPropagation()); // dvoklik na widget ne mijenja cijeli zaslon

  side.addEventListener("pointerdown", (e) => {
    const item = e.target.closest(".se-item");
    if (!item || e.button !== 0 || e.target.closest("button")) return;
    e.preventDefault();
    const s = spec(item.dataset.type);
    drag = { mode: "add", spec: s };
    float.textContent = `${s.icon} ${s.title}`;
    document.documentElement.classList.add("se-dragging");
  });
  side.addEventListener("click", (e) => {
    const add = e.target.closest("[data-add]"), act = e.target.closest("[data-se]");
    const pg = e.target.closest("[data-page]");
    if (pg) selectPage(Number(pg.dataset.page));
    if (e.target.closest("[data-page-add]")) addPage();
    if (e.target.closest("[data-page-rm]")) removePage();
    if (add) addToFreeSlot(add.dataset.add);
    if (!act) return;
    ({
      close: () => setOpen(false),
      undo: doUndo,
      reset: async () => {
        const res = await guarded(() => api().reset_layout());
        if (res.ok === false) { status(res.message, "err"); return; }
        undo = [];
        ed.pages = res.pages;
        ed.rotateS = res.rotateS;
        selectPage(0);
        status(T("Vraćen je zadani raspored."), "ok");
        refreshDashboard();
      },
      images: () => api().open_settings("display"),
    })[act.dataset.se]();
  });
  side.querySelector("input[type=search]").addEventListener("input", (e) => renderList(e.target.value));
  side.addEventListener("change", (e) => { if (e.target.matches("[data-rotate]")) setRotation(Number(e.target.value)); });
  tab.addEventListener("click", () => setOpen(true));

  async function doUndo() {
    const prev = undo.pop();
    if (!prev) { status(T("Nema promjena za poništiti.")); return; }
    const res = await guarded(() => api().save_layout(prev.layout, prev.page));
    if (res.ok) {
      ed.pages[prev.page] = res.layout;
      selectPage(prev.page);
      status(T("Promjena poništena."), "ok");
      refreshDashboard();
    }
  }
  function setOpen(value) {
    open = value;
    setMode();
    api().set_sidebar(open);
    setTimeout(renderFrames, 350);
  }

  // ------------------------------------------------------------ opcije widgeta
  function openOptions(id, anchor) {
    const it = ed.layout.find((o) => o.id === id), s = spec(it.type);
    const field = (o) => {
      const v = it.options[o.key] ?? o.default;
      if (o.kind === "choice") {
        return `<label>${esc(T(o.label))}<select name="${esc(o.key)}">${o.choices.map(([val, lab]) =>
          `<option value="${esc(val)}" ${String(val) === String(v) ? "selected" : ""}>${esc(T(lab))}</option>`).join("")}</select></label>`;
      }
      return o.maxLen > 80
        ? `<label>${esc(T(o.label))}<textarea name="${esc(o.key)}" maxlength="${o.maxLen}">${esc(v)}</textarea></label>`
        : `<label>${esc(T(o.label))}<input name="${esc(o.key)}" maxlength="${o.maxLen}" value="${esc(v)}"></label>`;
    };
    pop.innerHTML = `<h4>${s.icon} ${esc(T(s.title))}</h4>${s.options.map(field).join("")}
      <div class="row"><button type="button" data-pop="cancel">${T("Odustani")}</button><button type="button" class="primary" data-pop="save">${T("Spremi")}</button></div>`;
    // uz gornji desni kut widgeta, unutar prozora
    const left = Math.max(8, Math.min(anchor.right - 308, window.innerWidth - 320)), top = Math.max(8, Math.min(anchor.top + 44, window.innerHeight - 320));
    pop.style.cssText = `display:block;left:${left}px;top:${top}px`;
    pop.onclick = (e) => {
      const b = e.target.closest("[data-pop]");
      if (!b) return;
      if (b.dataset.pop === "save") {
        const options = Object.fromEntries([...pop.querySelectorAll("[name]")].map((el) => [el.name, el.value]));
        commit(ed.layout.map((o) => (o.id === id ? { ...o, options: { ...o.options, ...options } } : o)), T("Opcije spremljene"));
      }
      pop.style.display = "none";
    };
  }

  // ------------------------------------------------------------ pokretanje
  document.addEventListener("solari-mode", (e) => { fullscreen = Boolean(e.detail.fullscreen); pop.style.display = "none"; setMode(); });
  window.addEventListener("resize", () => renderFrames());
  // Streamlit iscrtava mrežu nakon učitavanja i pri svakom osvježavanju – okviri prate stvarni položaj mreže.
  let lastRect = "";
  setInterval(() => {
    if (!ed || fullscreen || drag) return;
    const r = gridRect();
    const key = r ? `${r.left},${r.top},${r.width},${r.height}` : "";
    if (key !== lastRect) { lastRect = key; renderFrames(); }
  }, 500);

  (async function init() {
    for (let i = 0; i < 50 && !api(); i++) await new Promise((r) => setTimeout(r, 100));
    if (!api()) return;
    ed = await api().get_editor();
    ed.page = 0;
    ed.layout = ed.pages[0];
    fullscreen = ed.fullscreen;
    open = ed.sidebarOpen;
    renderPages();
    renderList();
    setMode();
    // pages.js se u Python verziji učita nakon editora – stranica koja se uređuje mora ostati prikazana
    setInterval(syncEditing, 1000);
  })();
})();
