// Stranice rasporeda widgeta: sve su iscrtane jedna preko druge, vidljiva je html[data-page="N"].
// Broj stranica i izmjena dolaze iz <span class="solari-pages" data-count data-rotate> u mreži
// (Python: solar/widgets/render.py, C++: web/dashboard.js). Editor (editor.js) prikazuje stranicu koju
// uređuje i za to vrijeme zaustavlja izmjenu. U pregledniku na drugom računalu (pregled iz mreže)
// prikaz se još i umanji ili uveća da stane u prozor.
(() => {
  if (window.SolariPages) return;
  const root = document.documentElement;
  const TICK_MS = 500;
  let page = 0, editing = null, shownAt = Date.now();

  function meta() {
    const el = document.querySelector(".solari-pages");
    const count = el ? Math.max(1, Number(el.dataset.count) || 1) : 1;
    return { count, rotate: el ? Number(el.dataset.rotate) || 0 : 0 };
  }

  function show(n) {
    const { count } = meta();
    const next = ((n % count) + count) % count;
    if (String(next) !== root.dataset.page) {
      root.dataset.page = String(next);
      window.dispatchEvent(new Event("resize")); // grafikoni na skrivenoj stranici dobivaju pravu širinu
    }
    page = next;
    shownAt = Date.now();
  }

  setInterval(() => {
    const m = meta();
    if (editing !== null) {
      if (page !== editing) show(editing);
      return;
    }
    if (page >= m.count) show(0);
    else if (m.rotate > 0 && m.count > 1 && Date.now() - shownAt >= m.rotate * 1000) show(page + 1);
  }, TICK_MS);

  // Pregled iz mreže: dashboard je složen za 1920 × 1080 CSS px kao i u aplikaciji (WebView2 ZoomFactor).
  // Android aplikacija skalira sama (viewport širine 1920 CSS px), kao WebView2 ZoomFactor na Windowsima.
  const inApp = Boolean((window.chrome && window.chrome.webview) || window.SOLARI_ANDROID);
  if (!inApp) {
    const fit = () => { root.style.zoom = String(Math.min(window.innerWidth / 1920, window.innerHeight / 1080)); };
    window.addEventListener("resize", fit);
    fit();
  }

  window.SolariPages = {
    get page() { return page; },
    get count() { return meta().count; },
    edit(n) { editing = n; show(n); },
    stopEdit() { if (editing !== null) { editing = null; shownAt = Date.now(); } },
  };
  show(0);
})();
