// Most JS ↔ C++ (src/bridge.cpp) preko WebView2 poruka. Izlaže isto sučelje kao pywebview u Python
// verziji – window.pywebview.api.<metoda>(...) vraća Promise – pa settings.js, editor.js i overlay.js
// rade bez izmjena. Događaji iz aplikacije: "mode" (cijeli zaslon) i "reload" (nove postavke/slike).
(() => {
  "use strict";
  const webview = window.chrome && window.chrome.webview;
  const pending = new Map();
  let nextId = 1;

  // Pregled iz mreže (src/remote.cpp, 4.0): obični preglednik nema WebView2 – podaci s /api/dashboard i slike
  // s /api/image/<vrsta> samo uz pristupni ključ u zaglavlju X-Solari-View-Key (nikad u adresi – SMA-08).
  if (!webview) {
    const KEY = "solari-view-key";
    const store = { get: () => { try { return sessionStorage.getItem(KEY) || localStorage.getItem(KEY) || ""; } catch { return ""; } },
      set: (k, remember) => { try { sessionStorage.setItem(KEY, k); if (remember) localStorage.setItem(KEY, k); } catch { /* bez pohrane */ } },
      clear: () => { try { sessionStorage.removeItem(KEY); localStorage.removeItem(KEY); } catch { /* bez pohrane */ } } };
    // obrazac za ključ (bez innerHTML s korisničkim podacima)
    const askKey = (message) => new Promise((resolve) => {
      const box = document.createElement("form");
      box.style.cssText = "position:fixed;inset:0;display:grid;place-content:center;gap:10px;background:#0b1220;color:#fff;z-index:99;font:16px sans-serif";
      const title = document.createElement("p");
      title.textContent = message || "Pristupni ključ pregleda iz mreže (Postavke → Sustav na računalu sa Solarnim monitorom):";
      const input = Object.assign(document.createElement("input"), { type: "password", autocomplete: "off", required: true });
      const remember = Object.assign(document.createElement("input"), { type: "checkbox" });
      const label = document.createElement("label");
      label.append(remember, " Zapamti na ovom uređaju");
      const ok = Object.assign(document.createElement("button"), { type: "submit", textContent: "U redu" });
      box.append(title, input, label, ok);
      box.addEventListener("submit", (e) => { e.preventDefault(); store.set(input.value.trim(), remember.checked); box.remove(); resolve(); });
      document.body.appendChild(box);
      input.focus();
    });
    const blobs = new Map();  // adresa slike (s oznakom verzije) → blob: URL
    const authFetch = async (path) => {
      for (let attempt = 0; attempt < 5; ++attempt) {
        if (!store.get()) await askKey();
        const res = await fetch(path, { cache: "no-store", headers: { "X-Solari-View-Key": store.get() } });
        if (res.status === 401) { store.clear(); await askKey("Ključ nije ispravan – upišite ga ponovno:"); continue; }
        if (res.status === 429) throw new Error("Previše pogrešnih ključeva – pokušajte za 10 minuta.");
        return res;
      }
      throw new Error("Pristupni ključ nije ispravan.");
    };
    const image = async (kind, url) => {
      if (!url) return "";
      if (!blobs.has(url)) {
        const res = await authFetch(`/api/image/${kind}`);
        blobs.set(url, res.ok ? URL.createObjectURL(await res.blob()) : "");
      }
      return blobs.get(url);
    };
    const remoteApi = {
      get_dashboard: async () => {
        const res = await authFetch("/api/dashboard");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const d = await res.json();
        const images = d.images || {};
        for (const kind of ["hero", "drawing", "logo"]) images[kind] = await image(kind, images[kind]);
        d.images = images;
        return d;
      },
    };
    window.pywebview = { api: new Proxy(remoteApi, { get: (o, m) => o[m] || (async () => null) }) };
    document.addEventListener("DOMContentLoaded", () => window.dispatchEvent(new Event("pywebviewready")));
    return;
  }

  webview.addEventListener("message", (e) => {
    const msg = e.data;
    if (msg && msg.id != null && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.ok) resolve(msg.result); else reject(new Error(msg.error || "Greška"));
      return;
    }
    if (msg && msg.event === "mode") {
      document.dispatchEvent(new CustomEvent("solari-mode", { detail: { fullscreen: Boolean(msg.fullscreen) } }));
    } else if (msg && msg.event === "reload") {
      if (window.solariReload) window.solariReload(); else location.reload();
    }
  });

  const api = new Proxy({}, {
    get: (_, method) => (...args) => new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      webview.postMessage(JSON.stringify({ id, method: String(method), args }));
    }),
  });
  window.pywebview = { api };
  // isti događaj kao pywebview – tek kad se izvrše sve skripte stranice (DOMContentLoaded),
  // jer se datoteke s virtualnog hosta učitavaju asinkrono
  const ready = () => window.dispatchEvent(new Event("pywebviewready"));
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ready);
  else setTimeout(ready, 0);
})();
