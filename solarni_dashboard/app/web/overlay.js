// Ubacuje ga desktop/launcher.py u dashboard (nakon svakog učitavanja stranice).
// Prečaci, traka s gumbima koja se pojavi kad se pomakne miš i skrivanje pokazivača kad miruje.
// Izgled dashboarda ostaje isti: traka je skrivena dok se miš ne pomakne.
(() => {
  if (window.__solariOverlay) return;
  window.__solariOverlay = true;
  const opts = window.SOLARI_OPTIONS || {};
  let fullscreen = Boolean(opts.fullscreen); // pokazivač se skriva samo preko cijelog zaslona
  const IDLE_MS = 3000;
  const api = () => (window.pywebview && window.pywebview.api) || null;
  const T = window.T || ((s) => s);
  const call = (name) => { const a = api(); if (a && a[name]) a[name](); };

  const css = document.createElement("style");
  css.textContent = `
    html:not(.solari-idle), html:not(.solari-idle) body, html:not(.solari-idle) .stApp { cursor: default !important; }
    html.solari-idle, html.solari-idle * { cursor: none !important; }
    #solari-bar { position: fixed; top: 14px; right: 14px; z-index: 999999; display: flex; gap: 6px; padding: 6px;
      background: var(--card, rgba(22,31,51,.85)); border: 1px solid var(--border, rgba(255,255,255,.08));
      border-radius: 16px; box-shadow: var(--shadow, 0 10px 30px rgba(0,0,0,.35));
      backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
      opacity: 0; transform: translateY(-8px); pointer-events: none; transition: opacity .2s, transform .2s; }
    #solari-bar.show { opacity: 1; transform: none; pointer-events: auto; }
    #solari-bar button { font: 600 14px 'Plus Jakarta Sans', 'Segoe UI', sans-serif; color: var(--text, #E6EAF2);
      background: transparent; border: 0; border-radius: 11px; padding: 9px 13px; cursor: pointer;
      display: flex; align-items: center; gap: 8px; }
    #solari-bar button:hover { background: rgba(113,191,67,.16); }
    #solari-bar button:focus-visible { outline: 2px solid #71BF43; outline-offset: 1px; }
    #solari-bar kbd { font: 600 11px 'Segoe UI', sans-serif; color: var(--muted, #94A3B8);
      border: 1px solid var(--line, rgba(255,255,255,.12)); border-radius: 6px; padding: 1px 5px; }
    #solari-help { position: fixed; inset: 0; z-index: 1000000; display: none; place-items: center;
      background: rgba(0,0,0,.45); }
    #solari-help.show { display: grid; }
    #solari-help .box { min-width: 420px; padding: 24px 28px; border-radius: 22px; color: var(--text, #E6EAF2);
      background: var(--card-solid, #1A2540); border: 1px solid var(--border, rgba(255,255,255,.08));
      font: 15px 'Plus Jakarta Sans', 'Segoe UI', sans-serif; box-shadow: 0 20px 60px rgba(0,0,0,.4); }
    #solari-help h2 { margin: 0 0 14px; font-size: 19px; }
    #solari-help table { border-collapse: collapse; width: 100%; }
    #solari-help td { padding: 7px 0; border-bottom: 1px solid var(--line, rgba(255,255,255,.08)); }
    #solari-help td:first-child { width: 150px; color: var(--muted, #94A3B8); }
    #solari-help .ver { margin-top: 14px; font-size: 12px; color: var(--muted, #94A3B8); }`;
  document.head.appendChild(css);

  const bar = document.createElement("div");
  bar.id = "solari-bar";
  bar.setAttribute("role", "toolbar");
  bar.setAttribute("aria-label", T("Upravljanje prikazom"));
  const button = (label, key, action) => {
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = `${label} <kbd>${key}</kbd>`;
    b.addEventListener("click", (e) => { e.stopPropagation(); action(); });
    bar.appendChild(b);
  };
  button("⛶ " + T("Cijeli zaslon"), "F11 / Alt+Enter", () => call("toggle_fullscreen"));
  button("⚙ " + T("Postavke"), "F2", () => call("open_settings"));
  button("? " + T("Prečaci"), "F1", () => toggleHelp());
  document.body.appendChild(bar);

  const help = document.createElement("div");
  help.id = "solari-help";
  help.innerHTML = `<div class="box" role="dialog" aria-label="${T("Prečaci")}"><h2>${T("Prečaci na tipkovnici")}</h2><table>
    <tr><td>${T("F11, Alt + Enter ili dvoklik")}</td><td>${T("Cijeli zaslon uključi / isključi")}</td></tr>
    <tr><td>Esc</td><td>${T("Izlaz iz cijelog zaslona")}</td></tr>
    <tr><td>${T("F2 ili Ctrl + ,")}</td><td>${T("Postavke (mreža, elektrana, prikaz, sustav)")}</td></tr>
    <tr><td>F5</td><td>${T("Ponovno učitaj prikaz")}</td></tr>
    <tr><td>F1</td><td>${T("Ova pomoć")}</td></tr>
    <tr><td>Ctrl + Z</td><td>${T("Poništi zadnju promjenu rasporeda widgeta")}</td></tr>
    <tr><td>Alt + F4</td><td>${T("Zatvori aplikaciju")}</td></tr>
    </table><div class="ver">Solarni monitor ${opts.version}</div></div>`;
  help.addEventListener("click", () => toggleHelp(false));
  document.body.appendChild(help);
  function toggleHelp(force) {
    help.classList.toggle("show", force === undefined ? !help.classList.contains("show") : force);
  }

  // Traka i pokazivač: vidljivi dok se miš pomiče, skriveni nakon IDLE_MS mirovanja.
  let idleTimer = null;
  const wake = () => {
    document.documentElement.classList.remove("solari-idle");
    bar.classList.add("show");
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      if (bar.matches(":hover")) return wake();
      bar.classList.remove("show");
      if (opts.hideIdleCursor && fullscreen) document.documentElement.classList.add("solari-idle");
    }, IDLE_MS);
  };
  document.addEventListener("mousemove", wake, { passive: true });
  if (opts.hideIdleCursor && fullscreen) document.documentElement.classList.add("solari-idle");
  document.addEventListener("solari-mode", (e) => {
    fullscreen = Boolean(e.detail.fullscreen);
    if (!fullscreen) document.documentElement.classList.remove("solari-idle");
  });

  document.addEventListener("dblclick", () => call("toggle_fullscreen"));
  document.addEventListener("keydown", (e) => {
    if (e.altKey && e.key === "Enter" && !e.ctrlKey && !e.shiftKey) {  // Alt+Enter: cijeli zaslon uključi / isključi
      e.preventDefault();
      if (!e.repeat) call("toggle_fullscreen");
      return;
    }
    const handled = {
      F11: () => call("toggle_fullscreen"),
      Escape: () => (help.classList.contains("show") ? toggleHelp(false) : call("exit_fullscreen")),
      F2: () => call("open_settings"),
      F5: () => call("reload"),
      F1: () => toggleHelp(),
    }[e.key] || (e.ctrlKey && e.key === "," ? () => call("open_settings") : null);
    if (handled) { e.preventDefault(); handled(); }
  }, true);

  // Noćni način (Postavke → Prikaz): od-do (i preko ponoći) prikaz se zatamni na mali sat koji se pomiče
  // (zaštita od urezivanja slike) ili se zaslon ugasi. Pomak miša ili tipka probude prikaz na WAKE_MS.
  const night = opts.night || { mode: "off" };
  if (night.mode && night.mode !== "off") {
    const WAKE_MS = 5 * 60 * 1000, REPEAT_OFF_MS = 5 * 60 * 1000, CHECK_MS = 15 * 1000;
    const minutes = (hm) => { const [h, m] = String(hm || "0:0").split(":").map(Number); return (h || 0) * 60 + (m || 0); };
    const from = minutes(night.from), to = minutes(night.to);
    const isNight = (d = new Date()) => {
      const now = d.getHours() * 60 + d.getMinutes();
      return from === to ? false : from < to ? now >= from && now < to : now >= from || now < to;
    };
    const veil = document.createElement("div");
    veil.id = "solari-night";
    veil.innerHTML = '<span class="t"></span>';
    const nightCss = document.createElement("style");
    nightCss.textContent = `#solari-night { position: fixed; inset: 0; z-index: 1000001; background: #000; display: none; cursor: none; }
      #solari-night.show { display: block; }
      #solari-night .t { position: absolute; font: 600 64px 'Plus Jakarta Sans', 'Segoe UI', sans-serif; color: #2a3346;
        transition: left 2s, top 2s; }`;
    document.head.appendChild(nightCss);
    document.body.appendChild(veil);
    let wokenUntil = 0, offSentAt = 0, active = false;
    const clock = veil.querySelector(".t");
    const tick = () => {
      const on = isNight() && Date.now() >= wokenUntil;
      if (on !== active) {
        active = on;
        veil.classList.toggle("show", on);
        if (!on && night.mode === "screen_off" && offSentAt) { offSentAt = 0; const a = api(); if (a && a.set_display) a.set_display(true); }
      }
      if (!on) return;
      const d = new Date();
      clock.textContent = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
      clock.style.left = `${10 + (d.getMinutes() * 37) % 70}%`;
      clock.style.top = `${10 + (d.getMinutes() * 53) % 70}%`;
      if (night.mode === "screen_off" && Date.now() - offSentAt >= REPEAT_OFF_MS) {
        offSentAt = Date.now();
        const a = api();
        if (a && a.set_display) a.set_display(false);
      }
    };
    const nightWake = () => {
      if (!isNight()) return;
      const wasActive = active;
      wokenUntil = Date.now() + WAKE_MS;
      if (wasActive) tick();
    };
    ["mousemove", "keydown", "pointerdown"].forEach((ev) => document.addEventListener(ev, nightWake, { passive: true, capture: true }));
    setInterval(tick, CHECK_MS);
    tick();
  }
})();
