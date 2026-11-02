// Prijevodi za sva sučelja (postavke, editor, prečaci, C++ dashboard). Rječnik dolazi iz i18n/<jezik>.json
// (window.SOLARI_I18N = {lang, meta, strings, languages}); ključ je hrvatski tekst, pa nepoznat tekst
// ostaje kakav jest. translateDom() prevodi statični HTML i pamti izvornik, pa se jezik može mijenjati u hodu.
"use strict";

(() => {
  const bundle = () => window.SOLARI_I18N || { lang: "hr", meta: null, strings: {} };

  // T("vrh {kw} kW u {time}", {kw: "31,7", time: "09:10"})
  window.T = (text, vars) => {
    let s = (bundle().strings || {})[text] || text;
    if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
    return s;
  };

  const normalize = (html) => html.replace(/\s+/g, " ").trim();
  const ATTRS = ["placeholder", "title", "aria-label"];
  const originals = new WeakMap(); // tekstni čvor → izvorni tekst

  window.translateDom = (root = document.body) => {
    document.documentElement.lang = bundle().lang || "hr";
    root.querySelectorAll("[data-i18n]").forEach((el) => {
      if (!el.dataset.i18nKey) el.dataset.i18nKey = normalize(el.innerHTML);
      el.innerHTML = T(el.dataset.i18nKey);
    });
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.parentElement && n.parentElement.closest("script, style, [data-i18n], [data-no-i18n]")
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
    });
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!originals.has(n)) originals.set(n, n.nodeValue);
      const orig = originals.get(n), key = orig.trim().replace(/\s+/g, " ");
      if (!key || !/\p{L}/u.test(key)) continue;
      const lead = orig.match(/^\s*/)[0], trail = orig.match(/\s*$/)[0];
      n.nodeValue = lead + T(key) + trail;
    }
    root.querySelectorAll(ATTRS.map((a) => `[${a}]`).join(",")).forEach((el) => {
      for (const a of ATTRS) {
        if (!el.hasAttribute(a)) continue;
        const store = `i18n${a.replace(/(^|-)(\w)/g, (m, d, c) => c.toUpperCase())}`;
        if (!(store in el.dataset)) el.dataset[store] = el.getAttribute(a);
        el.setAttribute(a, T(el.dataset[store]));
      }
    });
  };

  // Brojevi i datumi prema jeziku (isto kao solar/i18n.py)
  const meta = () => bundle().meta || { decimal: ",", group: "." };
  window.fmtNum = (x, decimals = 1) => {
    const v = Number(x) || 0, fixed = Math.abs(v).toFixed(decimals);
    const [int, frac] = fixed.split(".");
    const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, meta().group);
    return (v < 0 && Number(fixed) !== 0 ? "-" : "") + grouped + (frac ? meta().decimal + frac : "");
  };
  // fmtDate("date_long", d) – uzorak iz meta, ili doslovni uzorak npr. fmtDate("{wd}", d)
  window.fmtDate = (pattern, d) => {
    const m = meta(), wd = (d.getDay() + 6) % 7;
    const parts = { d: d.getDate(), m: d.getMonth() + 1, y: d.getFullYear(), yy: d.getFullYear() % 100,
      month: m.months[d.getMonth()], month_gen: m.months_gen[d.getMonth()], mon: m.months_short[d.getMonth()],
      weekday: m.weekdays[wd], wd: m.weekdays_short[wd] };
    return (m[pattern] || pattern).replace(/\{(\w+)(?::02)?\}/g, (all, k) => {
      const v = parts[k];
      return all.includes(":02") ? String(v).padStart(2, "0") : String(v);
    });
  };
})();
