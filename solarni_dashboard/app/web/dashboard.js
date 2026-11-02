// Dashboard: dohvaća podatke iz C++ (get_dashboard), iscrtava zaglavlje i mrežu widgeta.
// Iscrtava se samo ono što se promijenilo, pa animacije (tok energije, zanimljivosti) teku bez prekida.
"use strict";

(() => {
  const api = () => window.pywebview.api;
  const container = document.querySelector(".block-container");
  const heroWrap = document.querySelector(".hero-wrap");
  const pagesHost = document.querySelector(".st-key-pages");
  const pageGrids = []; // .st-key-grid-pN – stranice rasporeda jedna preko druge (pages.js bira vidljivu)
  // pregled iz mreže u običnom pregledniku (Android aplikacija ima svoj most – android-bridge.js)
  const remote = !(window.chrome && window.chrome.webview) && !window.SOLARI_ANDROID && !window.SOLARI_HA;  // HA: ha-bridge.js
  const GRID_ROW = 130, GRID_GAP = 14; // ui.GRID_ROW, ui.GRID_GAP
  const widgets = new Map(); // id → { type, wrap, last }
  const drawings = new Map(); // URL crteža → podatkovni URI bez pozadine
  let data = null, theme = null, timer = null, booted = false, last = { heroBg: "", hero: "" };

  // Tekst naslova iz postavki: HTML se escapira, *dio teksta* istakne se bojom (isto kao ui.highlight).
  const highlight = (text) => UI.esc(text).replace(/\*([^*]+)\*/g, "<span class='hl'>$1</span>");
  const heightPx = (rows) => rows * GRID_ROW + (rows - 1) * GRID_GAP;
  const greeting = (h) => (h >= 5 && h < 12 ? T("Dobro jutro") : h >= 12 && h < 18 ? T("Dobar dan") : T("Dobra večer"));  // ikona pozdrava dolazi iz teme ikona (heroContent)

  // ---------------------------------------------------------------- kontekst za widgete (solar/widgets/context.py)
  function makeCtx(d) {
    const rt = d.realtime, settings = d.settings;
    // [datum, proizvodnja, potrošnja, iz mreže, predaja] – zadnja tri samo uz mjerač
    const daily = d.daily.map(([iso, kwh, load, imp, exp]) => ({ date: parseDate(iso), kwh, load, import: imp, export: exp }));
    const today = parseDate(d.today), now = new Date(d.now * 1000);
    const stale = rt.stale, power = rt.power_kw;
    const prevMonthStart = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    let monthDelta = null;
    if (today.getDate() > 1) {
      const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
      const prevEnd = new Date(prevMonthStart.getFullYear(), prevMonthStart.getMonth(), today.getDate() - 1);
      const sumRange = (a, b) => daily.filter((x) => x.date >= a && x.date <= b).reduce((s, x) => s + x.kwh, 0);
      const cur = sumRange(monthStart, new Date(today.getTime() - 864e5)), prev = sumRange(prevMonthStart, prevEnd);
      monthDelta = prev > 0 ? (cur / prev - 1) * 100 : null;
    }
    return {
      settings, rt, now, today, stale, power, daily, monthDelta,
      device: settings.device_type === "logger" ? T("Logger") : T("Inverter"),
      wx: d.weather, records: d.records, year: d.year, savings: d.savings,
      loadPct: settings.peak_power_kwp && !stale ? power / settings.peak_power_kwp * 100 : 0,
      curve: d.curve.map(([t, kw, load]) => ({ t: new Date(t * 1000), kw, load })), // load = mjerač (iz mreže)
      monthly: d.monthly.map(([iso, kwh]) => ({ month: parseDate(iso), kwh })),
      lastDays: (n) => daily.filter((x) => (today - x.date) / 864e5 < n),
      periodKwh: (p) => (p === "today" ? rt.day_kwh : p === "month" ? rt.month_kwh : p === "year" ? d.year[0] : rt.total_kwh),
    };
  }

  // ---------------------------------------------------------------- iscrtavanje
  // 5.1: izgled nadzorne ploče (Postavke → Prikaz): classic | aurora | control | daylight (svijetli – uvijek svijetla tema);
  // heroPhoto=false: zaglavlje bez fotografije elektrane (izbor u izgledu „kontrolna soba”)
  const DESIGNS = ["classic", "aurora", "control", "daylight"];
  function setTheme(name, palette, iconTheme, design, heroPhoto) {
    const d = DESIGNS.includes(design) ? design : "classic";
    if (d === "daylight") { name = "light"; palette = ""; }
    const SC = window.SolariColors;
    const colors = SC ? SC.colorsOf(SC.paletteKey(name, palette)) : {};
    const key = `${name} ${palette || ""} ${iconTheme || ""} ${d} ${heroPhoto !== false}`;  // tema, paleta, ikone, izgled
    if (key === theme) return;
    theme = key;
    const root = document.documentElement;
    root.dataset.design = d;
    root.dataset.heroPhoto = heroPhoto === false ? "0" : "1";
    const dl = document.getElementById("design-css");
    if (dl) {
      if (d === "classic") dl.removeAttribute("href");
      else dl.href = `design-${d}.css`;
    }
    UI.setTheme(name, colors);
    Icons.setTheme(iconTheme, UI.themeName());
    document.getElementById("theme-css").href = `dashboard-${UI.themeName()}.css`;
    if (window.SolariColors) window.SolariColors.apply(UI.theme(), colors);
    last = { heroBg: "", hero: "" };
    for (const w of widgets.values()) w.last = {};
  }

  function renderHero(ctx) {
    const rt = ctx.rt;
    let headline, state, cls;
    if (ctx.stale) [headline, state, cls] = [`${T("Podaci s elektrane")}<br><span class='hl'>${T("trenutno nisu dostupni")}</span>`, T("Nedostupna"), "err"];
    else if (rt.running) [headline, state, cls] = [`${highlight(T(ctx.settings.headline))}<br>${highlight(T(ctx.settings.headline_running))}`, T("Aktivna"), "ok"];
    else [headline, state, cls] = [`${highlight(T(ctx.settings.headline))}<br>${highlight(T(ctx.settings.headline_idle))}`, T("Miruje"), "off"];
    const bg = UI.heroBackground(data.images.hero);
    const content = UI.heroContent(greeting(ctx.now.getHours()), headline,
      UI.siteCard(data.images.logo, ctx.settings.plant_name, ctx.settings.location, state, cls), UI.weatherCard(ctx.today, ctx.wx, Number(ctx.settings.forecast_days) || 5));
    if (bg !== last.heroBg) {
      heroWrap.querySelector(".hero-bg-layer").innerHTML = bg;
      last.heroBg = bg;
    }
    if (content !== last.hero) {
      heroWrap.querySelector(".hero-layer").innerHTML = content;
      last.hero = content;
      tickClock();
    }
  }

  function setHtml(el, html, key, w) {
    if (w.last[key] === html) return;
    el.innerHTML = html;
    w.last[key] = html;
  }

  function renderChart(w, p, h, out) {
    if (w.last.mode !== "chart") {
      w.wrap.innerHTML = `<div class="st-key-card-${p.id}"><div class="hdr"></div><div class="plot"></div></div>`;
      w.last = { mode: "chart" };
    }
    const cardEl = w.wrap.firstElementChild;
    cardEl.style.height = `${h}px`;
    setHtml(cardEl.querySelector(".hdr"), out.chart.header, "hdr", w);
    const plot = cardEl.querySelector(".plot");
    if (out.chart.figure) {
      const f = out.chart.figure;
      plot.style.display = "";
      Plotly.react(plot, f.data, f.layout, f.config);
    } else {
      Plotly.purge(plot);
      plot.style.display = "none";
    }
  }

  function renderFlow(w, p, out) {
    const f = out.flow, url = UI.safeImageUrl(data.images.drawing);
    if (!drawings.has(url)) {
      drawings.set(url, null);
      Cutout.get(url).then((uri) => { drawings.set(url, uri); render(); });
    }
    const layers = UI.flowLayers(drawings.get(url), f.nodes, f.live, f.height);
    if (w.last.mode !== "flow") {
      w.wrap.innerHTML = `<div class="st-key-flow-${p.id}"><div class="base"></div><div class="over"></div></div>`;
      w.last = { mode: "flow" };
    }
    const host = w.wrap.firstElementChild;
    if (w.last.base !== layers.base) { host.children[0].outerHTML = `<div class="base">${layers.base}</div>`; w.last.base = layers.base; }
    if (w.last.over !== layers.overlay) { host.children[1].innerHTML = layers.overlay; w.last.over = layers.overlay; }
  }

  function pageGrid(n) {
    while (pageGrids.length <= n) {
      const g = document.createElement("section");
      g.className = `st-key-grid-p${pageGrids.length}`;
      g.setAttribute("aria-label", "Widgeti");
      pagesHost.appendChild(g);
      pageGrids.push(g);
    }
    return pageGrids[n];
  }

  function renderGrid(ctx) {
    const seen = new Set();
    const pages = data.pages || [[]];
    let meta = pagesHost.querySelector(".solari-pages");
    if (!meta) { meta = document.createElement("span"); meta.className = "solari-pages"; meta.hidden = true; pagesHost.prepend(meta); }
    meta.dataset.count = String(pages.length);
    meta.dataset.rotate = String(data.rotateS || 0);
    pageGrids.splice(pages.length).forEach((g) => g.remove());
    pages.forEach((items, n) => { const grid = pageGrid(n); for (const p of items) {
      seen.add(p.id);
      let w = widgets.get(p.id);
      if (!w || w.type !== p.type || w.wrap.parentElement !== grid) {
        if (w) w.wrap.remove();
        const wrap = document.createElement("div");
        wrap.className = `st-key-w-${p.id}`;
        grid.appendChild(wrap);
        w = { type: p.type, wrap, last: {} };
        widgets.set(p.id, w);
      }
      w.wrap.style.gridColumn = `${p.x + 1} / span ${p.w}`;
      w.wrap.style.order = String(p.y * 100 + p.x);  // redoslijed kad su widgeti jedan ispod drugog (uspravni Android)
      w.wrap.style.gridRow = `${p.y + 1} / span ${p.h}`;
      const h = heightPx(p.h);
      try {
        const out = Widgets[p.type](ctx, p, h);
        if (out.chart) renderChart(w, p, h, out);
        else if (out.flow) renderFlow(w, p, out);
        else {
          if (w.last.mode !== "html") { w.last = { mode: "html" }; }
          setHtml(w.wrap, out.html, "html", w);
        }
      } catch (e) {
        console.error(p.type, e);
        w.last = {};
        w.wrap.innerHTML = `<div class="card widget-error" style="--h:${h}px">${UI.esc(p.type)}<br>${T("trenutno nije dostupan")}</div>`;
      }
    } });
    for (const [id, w] of widgets) {
      if (!seen.has(id)) { w.wrap.remove(); widgets.delete(id); }
    }
  }

  function render() {
    if (!data) return;
    setTheme(data.settings.theme, data.settings.palette, data.settings.icon_theme, data.settings.design, data.settings.hero_photo);
    const ctx = makeCtx(data);
    renderHero(ctx);
    renderGrid(ctx);
    tickClock();
  }

  // ---------------------------------------------------------------- sat (sekunde teku u pregledniku)
  const clockFmt = new Intl.DateTimeFormat("hr-HR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  function tickClock() {
    const now = clockFmt.format(new Date());
    document.querySelectorAll(".live-clock").forEach((el) => { if (el.textContent !== now) el.textContent = now; });
  }
  setInterval(tickClock, 250);

  // ---------------------------------------------------------------- osvježavanje
  async function refresh() {
    clearTimeout(timer);
    try {
      // 5.2: Android – jezik je lokalna postavka; učitava se prije podataka, da i poruka bez veze bude na jeziku korisnika
      if (window.SOLARI_ANDROID && !window.SOLARI_I18N && window.SolariAndroid) {
        try { await loadLanguage(JSON.parse(window.SolariAndroid.getSettings()).language); } catch (e) { /* zadano hr */ }
      }
      data = await api().get_dashboard();
      await loadLanguage(data.settings.language);
      render();
      if (!booted) boot();
    } catch (e) {
      console.error(e); // zadnji podaci ostaju na ekranu
      // prije prvih podataka: razlog umjesto "Pokrećem dashboard…" (pokušava se ponovno)
      const loading = !booted && document.querySelector(".loading");
      if (loading) {
        loading.textContent = `${T("Poslužitelj ne odgovara.")} ${e && e.message ? e.message : e}`;
        // 5.2: Android nema tipku F2 – uz poruku (npr. „prijavite se ponovno”) uvijek gumb za postavke i prijavu
        if (window.SOLARI_ANDROID) {
          const go = document.createElement("button");
          go.type = "button";
          go.className = "loading-settings";
          go.textContent = `⚙ ${T("Postavke i prijava")}`;
          go.addEventListener("click", () => api().open_settings());
          loading.append(document.createElement("br"), go);
        }
      }
      // 5.0.1: i bez podataka prečaci moraju raditi (F2 postavke / prijava, F11 i Alt+Enter, Esc) – inače korisnik ostaje
      // zarobljen na poruci preko cijelog zaslona. 5.2: na Androidu i izbornik ☰ (postavke) – ne ovisi o podacima.
      if (!booted && !remote) loadScripts(window.SOLARI_ANDROID ? ["overlay.js", "android-menu.js"] : ["overlay.js"]);
    }
    const seconds = Math.min(60, Math.max(5, (data && data.settings.poll_interval_s) || 10));
    timer = setTimeout(refresh, seconds * 1000);
  }

  // Rječnik i18n/<jezik>.json (isti kao u Python verziji); pri promjeni jezika stranica se učita iznova.
  async function loadLanguage(code) {
    const lang = code || "hr";
    if (window.SOLARI_I18N && window.SOLARI_I18N.lang === lang) return;
    if (window.SOLARI_I18N) { location.reload(); return; }
    const res = await fetch(`i18n/${lang}.json`);
    const bundle = await res.json();
    window.SOLARI_I18N = { lang, meta: bundle.meta, strings: bundle.strings || {} };
    document.documentElement.lang = lang;
    document.querySelector(".loading").textContent = T("Pokrećem dashboard…");
  }

  // Svaka skripta samo jednom (overlay.js se može učitati već uz poruku o grešci – dvostruki prečaci bi se poništavali)
  const loadedScripts = new Set();
  function loadScripts(list) {
    for (const src of list) {
      if (loadedScripts.has(src)) continue;
      loadedScripts.add(src);
      const el = document.createElement("script");
      el.src = src;
      document.body.appendChild(el);
    }
  }

  // Prečaci (overlay.js) i editor widgeta (editor.js) učitavaju se nakon prvih podataka.
  function boot() {
    // overlay.js je već učitan uz poruku o grešci (bez opcija): jedno ponovno učitavanje postavlja noćni način,
    // skrivanje pokazivača i verziju (audit W-11)
    if (loadedScripts.has("overlay.js")) { location.reload(); return; }
    booted = true;
    document.querySelector(".loading").remove();
    if (remote) return; // u pregledniku nema prečaca, editora ni noćnog načina
    const s = data.settings;
    window.SOLARI_OPTIONS = { hideIdleCursor: s.hide_idle_cursor, version: data.version, fullscreen: data.fullscreen,
      night: { mode: s.night_mode, from: s.night_from, to: s.night_to } };
    // Android: umjesto editora rasporeda (mreža 12 × 5) ima svoj izbornik i popis widgeta (android-menu.js)
    loadScripts(window.SOLARI_ANDROID ? ["overlay.js", "android-menu.js"] : ["overlay.js", "editor.js", "window.js"]);
  }

  window.solariRender = refresh;               // editor: odmah iscrtaj novi raspored
  window.solariReload = () => location.reload(); // nove postavke ili slike
  container.style.visibility = "visible";
  refresh();
})();
