// Most za Home Assistant (umjesto bridge.js / WebView2): isto sučelje window.pywebview.api.<metoda>(...) → Promise,
// pa dashboard, editor rasporeda, prečaci, noćni način i postavke rade bez izmjena. Pozivi idu na dashboard add-on
// (POST api/bridge/<metoda>, relativno – radi iza Ingress putanje); radnje prozora (cijeli zaslon, postavke, zatvaranje)
// izvodi preglednik. Prijavu vodi Home Assistant; PIN postavki (ako je postavljen) daje oznaku otključavanja za ovu karticu.
"use strict";

(() => {
  window.SOLARI_HA = true;
  window.__solariWindow = true;  // nema okvira prozora (window.js) – Home Assistant ima svoj
  const UNLOCK = "solari-unlock", PANEL = "solari-panel";
  const session = {
    get: (k) => { try { return sessionStorage.getItem(k) || ""; } catch { return ""; } },
    set: (k, v) => { try { if (v) sessionStorage.setItem(k, v); else sessionStorage.removeItem(k); } catch { /* bez pohrane */ } },
  };

  async function call(method, args) {
    const res = await fetch(`api/bridge/${encodeURIComponent(method)}`, {
      method: "POST", cache: "no-store", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Solari-Unlock": session.get(UNLOCK) },
      body: JSON.stringify({ args }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const msg = await res.json();
    if (!msg.ok) throw new Error(msg.error || "Greška");
    return msg.result;
  }

  // slike s poslužitelja → blob: URL (components.js dopušta samo poznate prefikse; Ingress kolačić ide sa zahtjevom)
  const blobs = new Map();
  async function image(url) {
    if (!url) return "";
    if (!blobs.has(url)) {
      try {
        const res = await fetch(url, { credentials: "same-origin" });
        blobs.set(url, res.ok ? URL.createObjectURL(await res.blob()) : "");
      } catch { blobs.set(url, ""); }
    }
    return blobs.get(url);
  }

  const isFullscreen = () => Boolean(document.fullscreenElement);
  const mode = () => document.dispatchEvent(new CustomEvent("solari-mode", { detail: { fullscreen: isFullscreen() } }));
  document.addEventListener("fullscreenchange", mode);
  async function toggleFullscreen() {
    try {
      if (isFullscreen()) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen({ navigationUI: "hide" });
    } catch (e) { console.warn("Cijeli zaslon:", e); }
    return isFullscreen();
  }

  const local = {
    async get_dashboard() {
      const d = await call("get_dashboard", []);
      const images = d.images || {};
      for (const kind of ["hero", "drawing", "logo"]) images[kind] = await image(images[kind]);
      d.images = images;
      d.fullscreen = isFullscreen();
      return d;
    },
    async get_state() {
      const st = await call("get_state", []);
      const panel = session.get(PANEL);
      if (panel) { st.panel = panel; session.set(PANEL, ""); }
      return st;
    },
    async unlock(pin) { const r = await call("unlock", [pin]); if (r && r.ok) session.set(UNLOCK, r.unlock_token || ""); return r; },
    async unlock_layout(pin) {
      const r = await call("unlock_layout", [pin]);
      if (r && r.ok && !session.get(UNLOCK)) session.set(UNLOCK, r.unlock_token || "");
      return r;
    },
    toggle_fullscreen: toggleFullscreen,
    async exit_fullscreen() { if (isFullscreen()) await toggleFullscreen(); return false; },
    async open_settings(panel) { session.set(PANEL, panel || ""); location.href = "settings.html"; },
    async close() { location.href = "index.html"; },
    async admin_logout() { location.href = "index.html"; },
    async reload() { location.reload(); },
    async quit() { /* u pregledniku nema izlaza iz aplikacije */ },
    async set_display() { /* zaslon gasi uređaj (TV/tablet); noćni način zatamni prikaz */ },
    async set_sidebar() { /* bez okvira prozora */ },
    async window_state() { return { fullscreen: isFullscreen(), maximized: false }; },
    async window_control() { return { fullscreen: isFullscreen(), maximized: false }; },
    async open_folder() { return null; },
  };

  window.SolariHa = { call, unlockToken: () => session.get(UNLOCK) };
  const api = new Proxy(local, { get: (o, m) => o[m] || ((...args) => call(String(m), args)) });
  window.pywebview = { api };
  const ready = () => window.dispatchEvent(new Event("pywebviewready"));
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ready);
  else setTimeout(ready, 0);
})();
