// Mjesečni izvještaj (prozor postavki na Windowsima i Android aplikacija): odabir mjeseca, grafikon i tablica.
// Koristi $, esc (stranica), T, fmtNum, fmtDate (i18n.js); podatke daje solar/report.py ili src/report.cpp.
"use strict";

const day = (iso) => new Date(`${iso}T00:00`); // "2026-10-05" kao lokalni dan, ne UTC

function renderMonths() {
  const sel = $("#report-month");
  const now = new Date(), prev = sel.value;
  const months = Array.from({ length: 24 }, (_, i) => new Date(now.getFullYear(), now.getMonth() - i, 1));
  sel.innerHTML = months.map((d, i) => `<option value="${d.getFullYear()}-${d.getMonth() + 1}">${
    esc(fmtDate("month_year", d))}${i === 0 ? " " + esc(T("(do danas)")) : ""}</option>`).join("");
  sel.value = prev || `${months[1].getFullYear()}-${months[1].getMonth() + 1}`;
}

function reportChart(r) {
  const W = 760, H = 210, padL = 44, padB = 24, n = r.days.length || 1;
  const top = Math.max(1, ...r.days.map((d) => Math.max(d.kwh || 0, d.load || 0))) * 1.1;
  const bw = (W - padL) / n, y = (v) => H - padB - (v / top) * (H - padB - 8);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top);
  const grid = ticks.map((v) => `<line x1="${padL}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="#E2E8F0"/>
    <text x="${padL - 6}" y="${y(v) + 4}" text-anchor="end" font-size="10" fill="#64748B">${fmtNum(v, 0)}</text>`).join("");
  const bars = r.days.map((d, i) => {
    const x = padL + i * bw, w = r.metered ? bw * 0.38 : bw * 0.7;
    const prod = `<rect x="${x + bw * 0.12}" y="${y(d.kwh || 0)}" width="${w}" height="${H - padB - y(d.kwh || 0)}" rx="2" fill="#71BF43"/>`;
    const load = r.metered && d.load != null ? `<rect x="${x + bw * 0.12 + w + 1}" y="${y(d.load)}" width="${w}" height="${H - padB - y(d.load)}" rx="2" fill="#F59E0B"/>` : "";
    const label = n <= 16 || i % 2 === 0 ? `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle" font-size="9.5" fill="#64748B">${day(d.date).getDate()}</text>` : "";
    return prod + load + label;
  }).join("");
  const legend = `<g font-size="10.5" fill="#334155"><rect x="${padL}" y="0" width="10" height="10" rx="2" fill="#71BF43"/>
    <text x="${padL + 14}" y="9">${esc(T("Proizvodnja"))} (kWh)</text>${r.metered ? `<rect x="${padL + 130}" y="0" width="10" height="10" rx="2" fill="#F59E0B"/>
    <text x="${padL + 144}" y="9">${esc(T("Potrošnja"))} (kWh)</text>` : ""}</g>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(T("Proizvodnja po danima"))}">${grid}${bars}${legend}</svg>`;
}

function renderReport(r) {
  const cur = r.currency, t = r.totals, month = new Date(r.year, r.month - 1, 1);
  const num = (v, d = 0) => (v == null ? "—" : fmtNum(v, d));
  const delta = (now, before) => {
    if (!before) return "";
    const p = (now / before - 1) * 100;
    return `<small class="${p >= 0 ? "up" : "down"}">${p >= 0 ? "+" : "−"}${fmtNum(Math.abs(p), 1)} %</small>`;
  };
  const kpi = (label, value, unit, sub = "") => `<div class="kpi"><span>${esc(label)}</span><b>${value} <small>${esc(unit)}</small></b>${sub}</div>`;
  const kpis = [
    kpi(T("Proizvodnja"), num(t.kwh), "kWh"),
    kpi(T("Ušteda"), num(t.savings, 2), cur),
    kpi(T("Manje CO₂"), num(t.co2_kg), "kg"),
    kpi(T("Najveća snaga"), r.peak ? num(r.peak.kw, 1) : "—", "kW", r.peak ? `<small>${esc(fmtDate("date", new Date(r.peak.ts)))} ${esc(String(r.peak.ts).slice(11, 16))}</small>` : ""),
    kpi(T("Prošli mjesec"), num(r.compare.prev_month), "kWh", delta(t.kwh, r.compare.prev_month)),
    kpi(T("Isti mjesec lani"), r.compare.last_year ? num(r.compare.last_year) : "—", "kWh", delta(t.kwh, r.compare.last_year)),
  ];
  if (r.metered) {
    kpis.push(kpi(T("Potrošnja zgrade"), num(t.load), "kWh", `<small>${esc(T("iz mreže {kwh} kWh", { kwh: num(t.import) }))}</small>`));
    kpis.push(kpi(T("Sunce pokriva potrošnju"), num(t.autarky, 0), "%", `<small>${esc(T("predano u mrežu {kwh} kWh", { kwh: num(t.export) }))}</small>`));
  } else {
    kpis.push(kpi(T("Najbolji dan"), r.best_day ? num(r.best_day.kwh) : "—", "kWh", r.best_day ? `<small>${esc(fmtDate("date", day(r.best_day.date)))}</small>` : ""));
    kpis.push(kpi(T("Instalirana snaga"), num(r.kwp, 1), "kWp"));
  }
  const cols = r.metered ? ["kwh", "load", "import", "export", "savings"] : ["kwh", "savings"];
  const heads = { kwh: T("Proizvodnja"), load: T("Potrošnja"), import: T("Iz mreže"), export: T("Predaja u mrežu"), savings: T("Ušteda") };
  const unit = (c) => (c === "savings" ? cur : "kWh");
  const rows = r.days.map((d) => `<tr><td>${esc(fmtDate("date", day(d.date)))}</td>${
    cols.map((c) => `<td>${num(d[c], c === "savings" ? 2 : 1)}</td>`).join("")}</tr>`).join("");
  const total = { kwh: t.kwh, load: t.load, import: t.import, export: t.export, savings: t.savings };
  $("#report").innerHTML = `
    <header><div><h2>${esc(r.plant)}</h2><p>${esc(r.location)} · ${num(r.kwp, 1)} kWp</p></div>
      <div class="period">${esc(T("Mjesečni izvještaj"))}<br>${esc(fmtDate("month_year", month))}${
        r.complete ? "" : `<br><small>${esc(T("do {date}", { date: fmtDate("date", day(r.until)) }))}</small>`}</div></header>
    <section class="kpis">${kpis.join("")}</section>
    <h3>${esc(T("Proizvodnja po danima"))}</h3>${reportChart(r)}
    <h3>${esc(T("Dnevni podaci"))}</h3>
    <table><thead><tr><th>${esc(T("Datum"))}</th>${cols.map((c) => `<th>${esc(heads[c])} (${esc(unit(c))})</th>`).join("")}</tr></thead>
      <tbody>${rows}</tbody><tfoot><tr><td>${esc(T("Ukupno"))}</td>${cols.map((c) => `<td>${num(total[c], c === "savings" ? 2 : 0)}</td>`).join("")}</tr></tfoot></table>
    <p class="note">${esc(T("Ušteda: {price} {cur}/kWh za struju potrošenu sa sunca, {feed} {cur}/kWh za višak predan u mrežu. CO₂: {factor} kg/kWh. Izrađeno {date}.",
      { price: fmtNum(r.price, 2), feed: fmtNum(r.feedin, 2), cur, factor: fmtNum(r.co2_factor, 2), date: `${fmtDate("date", new Date(r.generated))} ${r.generated.slice(11, 16)}` }))}</p>`;
  $("#report").hidden = false;
}
