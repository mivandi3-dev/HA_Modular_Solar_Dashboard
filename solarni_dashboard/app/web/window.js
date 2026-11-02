// Prozor bez okvira (3.1, samo Windows): tri kružića gore desno – minimiziraj, maksimiziraj, zatvori – i nevidljiva
// traka na vrhu za pomicanje prozora (dvoklik maksimizira). U cijelom zaslonu ništa od toga se ne prikazuje.
"use strict";

(() => {
  if (window.SOLARI_ANDROID || window.__solariWindow) return;
  window.__solariWindow = true;
  const api = () => window.pywebview && window.pywebview.api;
  const T = window.T || ((s) => s);

  const style = document.createElement("style");
  style.textContent = `
    #win-drag { position: fixed; top: 0; left: 0; right: 96px; height: 12px; z-index: 2147483000; }
    #win-ctrl { position: fixed; top: 10px; right: 12px; z-index: 2147483001; display: flex; gap: 8px; padding: 5px 7px;
                border-radius: 99px; background: rgba(15, 23, 42, .28); backdrop-filter: blur(6px); opacity: .7;
                transition: opacity .2s ease; }
    #win-ctrl:hover { opacity: 1; }
    #win-ctrl button { width: 14px; height: 14px; border-radius: 50%; border: 0; padding: 0; cursor: pointer; display: grid;
                       place-items: center; font: 700 10px/1 system-ui, sans-serif; color: transparent; }
    #win-ctrl:hover button { color: rgba(0, 0, 0, .55); }
    #win-ctrl .min { background: #F5BF4F; } #win-ctrl .max { background: #61C554; } #win-ctrl .close { background: #ED6A5E; }
    #win-ctrl button:focus-visible { outline: 2px solid #fff; outline-offset: 1px; }
    html.win-full #win-drag, html.win-full #win-ctrl { display: none; }
    html:not(.win-full) #se-side header { padding-top: 44px; }  /* izbornik Widgeti: „Sakrij” ispod kružića */`;
  document.head.appendChild(style);

  const drag = document.createElement("div");
  drag.id = "win-drag";
  const ctrl = document.createElement("div");
  ctrl.id = "win-ctrl";
  ctrl.innerHTML = `<button class="min" data-win="minimize">–</button><button class="max" data-win="maximize">+</button>`
    + `<button class="close" data-win="close">×</button>`;
  const titles = { minimize: T("Minimiziraj"), maximize: T("Maksimiziraj"), close: T("Zatvori") };
  ctrl.querySelectorAll("button").forEach((b) => { b.title = b.ariaLabel = titles[b.dataset.win]; });

  const setState = (st) => {
    if (!st) return;
    document.documentElement.classList.toggle("win-full", Boolean(st.fullscreen));
    const max = ctrl.querySelector(".max");
    max.textContent = st.maximized ? "−" : "+";
    max.title = max.ariaLabel = st.maximized ? T("Vrati veličinu") : T("Maksimiziraj");
  };

  ctrl.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-win]");
    if (!b || !api()) return;
    e.stopPropagation();
    setState(await api().window_control(b.dataset.win));
  });
  ctrl.addEventListener("dblclick", (e) => e.stopPropagation());  // dvoklik na dashboardu je cijeli zaslon
  drag.addEventListener("mousedown", (e) => {
    if (e.button === 0 && e.detail === 1 && api()) api().window_control("drag");
  });
  drag.addEventListener("dblclick", async (e) => {
    e.stopPropagation();
    if (api()) setState(await api().window_control("maximize"));
  });
  document.addEventListener("solari-mode", (e) => setState({ fullscreen: e.detail.fullscreen, maximized: false }));
  window.addEventListener("resize", () => { if (api()) api().window_state().then(setState); });

  const mount = () => {
    document.body.append(drag, ctrl);
    if (api()) api().window_state().then(setState);
  };
  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);
})();
