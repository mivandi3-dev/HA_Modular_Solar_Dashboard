// Formatiranje i vizualne komponente – prijenos solar/ui.py u JS (isti HTML i SVG, isti CSS razredi).
"use strict";

const UI = (() => {
  let pal = window.SOLARI_THEMES.dark; // paleta teme (T() je prijevod iz i18n.js)
  let themeName = "dark";

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // SMA-18: adresa slike s poslužitelja smije biti samo slika aplikacije – inače se ne prikazuje (nema ubacivanja atributa/CSS-a)
  const IMAGE_PREFIXES = ["https://app.solari/", "https://data.solari/", "/api/v1/images/", "/api/image/", "blob:", "data:image/"];
  const safeImageUrl = (u) => {
    if (typeof u !== "string" || !IMAGE_PREFIXES.some((p) => u.startsWith(p))) return "";
    return /["'()<>\\\s]/.test(u) ? "" : u;  // navodnici, zagrade, <>, \ i razmaci nisu dopušteni
  };
  const weekdayIndex = (d) => (d.getDay() + 6) % 7; // ponedjeljak = 0

  // ---------------------------------------------------------------- formatiranje prema jeziku (i18n.js)
  const fmt = (x, decimals = 1) => fmtNum(x, decimals);
  const energy = (kwh) => (kwh >= 1000 ? [fmt(kwh / 1000, 2), "MWh"] : [fmt(kwh, 1), "kWh"]);
  const mass = (kg) => (kg >= 1000 ? [fmt(kg / 1000, 2), "t"] : [fmt(kg, 0), "kg"]);
  const dateHr = (d) => fmtDate("date_long", d);
  const statusDot = (running) => `<span class="status-dot ${running ? "on" : "off"}"></span>`;
  function delta(pct, suffix) {
    if (pct == null || !isFinite(pct)) return "";
    const [cls, sign] = pct >= 0 ? ["up", "+"] : ["down", "−"];
    return `<span class="${cls}">${sign}${fmt(Math.abs(pct), 1)} %</span> ${suffix == null ? T("u odnosu na prošli mjesec") : suffix}`;
  }
  const pad = (n) => String(n).padStart(2, "0");
  const hhmm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const tint = (name) => pal[`TINT_${name.toUpperCase()}`];
  const rgba = (hex, a) => `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)},${a})`;

  // Tema i korisničke boje (colors.js); bez colors.js samo tema
  function setTheme(name, colors) {
    themeName = window.SOLARI_THEMES[name] ? name : "dark";
    const base = window.SOLARI_THEMES[themeName];
    pal = window.SolariColors ? window.SolariColors.palette(base, colors) : base;
  }

  // ---------------------------------------------------------------- SVG primitivi
  function sparkline(values, color, width = 120, height = 40) {
    const vals = (values || []).filter((v) => v === v && v != null);
    if (vals.length < 2) return `<svg width="${width}" height="${height}"></svg>`;
    // 5.2: rub od 4 px – crta, njezin zaobljeni kraj i točka zadnje vrijednosti ne odsijecaju se na rubu kartice
    const pad = 4, lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1, step = (width - 2 * pad) / (vals.length - 1);
    const pts = vals.map((v, i) => [pad + i * step, height - 4 - (v - lo) / span * (height - 8)]);
    let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
    for (let i = 0; i < pts.length - 1; i++) { // Catmull-Rom → Bezier
      const p0 = pts[Math.max(i - 1, 0)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(i + 2, pts.length - 1)];
      const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6], c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
      d += ` C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
    }
    const last = pts[pts.length - 1];
    let h = 0;
    for (const ch of color + vals.join(",")) h = (h * 31 + ch.charCodeAt(0)) | 0;
    const gid = `g${Math.abs(h)}`;
    return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">`
      + `<stop offset="0" stop-color="${color}" stop-opacity=".28"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>`
      + `<path d="${d} L${(width - pad).toFixed(1)},${height} L${pad},${height} Z" fill="url(#${gid})"/>`
      + `<path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round"/>`
      + `<circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.6" fill="${color}"/></svg>`;
  }

  function speedometer(value, maxValue, sub = "", peak = "", step = 10) {
    const cx = 160, cy = 108, r = 96, sweep = 240, start = 210;
    const clampV = (v) => Math.max(0, Math.min(v, maxValue));
    const point = (v, radius) => { const a = (start - sweep * clampV(v) / maxValue) * Math.PI / 180; return [cx + radius * Math.cos(a), cy - radius * Math.sin(a)]; };
    const arc = (v) => {
      const [x0, y0] = point(0, r), [x1, y1] = point(v, r);
      const large = sweep * Math.min(v, maxValue) / maxValue > 180 ? 1 : 0;
      return `M${x0.toFixed(1)},${y0.toFixed(1)} A${r},${r} 0 ${large} 1 ${x1.toFixed(1)},${y1.toFixed(1)}`;
    };
    let ticks = "";
    const tickStep = Math.max(2, Math.ceil(maxValue / 400) * 2);  // najviše ~200 crtica i za velike vrijednosti (audit W-03)
    for (let i = 0; i <= maxValue; i += tickStep) {
      const major = i % step === 0;
      const [x0, y0] = point(i, r - 13), [x1, y1] = point(i, r - (major ? 24 : 18));
      ticks += `<line x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}" stroke="${major ? pal.TEXT : pal.MUTED}" `
        + `stroke-opacity="${major ? .75 : .4}" stroke-width="${major ? 2 : 1.2}" stroke-linecap="round"/>`;
      if (major) {
        const [lx, ly] = point(i, r - 37);
        ticks += `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle" dominant-baseline="central" font-size="11.5" font-weight="600" fill="${pal.MUTED}">${i}</text>`;
      }
    }
    const v = value == null ? 0 : value;
    const tip = point(v, r - 16), tail = point(v, -14);
    const a = (start - sweep * clampV(v) / maxValue) * Math.PI / 180;
    const nx = 5 * Math.sin(a), ny = 5 * Math.cos(a);
    const needle = `${tip[0].toFixed(1)},${tip[1].toFixed(1)} ${(cx + nx).toFixed(1)},${(cy + ny).toFixed(1)} ${tail[0].toFixed(1)},${tail[1].toFixed(1)} ${(cx - nx).toFixed(1)},${(cy - ny).toFixed(1)}`;
    const valueArc = value != null && v > maxValue * .004
      ? `<path d="${arc(v)}" fill="none" stroke="${pal.BRAND_GREEN}" stroke-width="14" stroke-linecap="round" filter="url(#speedo-glow)"/>` : "";
    const text = value == null ? "—" : fmt(v, 1);
    const peakHtml = peak ? `<tspan dx="8">·</tspan><tspan dx="8">${esc(T("max. danas"))} </tspan><tspan font-weight="700" fill="${pal.TEXT}">${esc(peak)}</tspan>` : "";
    return `<svg viewBox="0 0 320 192" xmlns="http://www.w3.org/2000/svg"><defs>`
      + `<filter id="speedo-glow" filterUnits="userSpaceOnUse" x="0" y="0" width="320" height="192"><feGaussianBlur stdDeviation="3" result="b"/>`
      + `<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>`
      + `<path d="${arc(maxValue)}" fill="none" stroke="${pal.TRACK}" stroke-width="14" stroke-linecap="round"/>${valueArc}${ticks}`
      + `<polygon points="${needle}" fill="${pal.TEXT}" opacity="${value == null ? .35 : .92}"/>`
      + `<circle cx="${cx}" cy="${cy}" r="8" fill="${pal.CARD_SOLID}" stroke="${pal.TEXT}" stroke-opacity=".9" stroke-width="3"/>`
      + `<text x="${cx}" y="166" text-anchor="middle" font-size="28" font-weight="700" fill="${pal.TEXT}" letter-spacing="-.5">${esc(text)}<tspan font-size="14" font-weight="600" fill="${pal.MUTED}" dx="5">kW</tspan></text>`
      + `<text x="${cx}" y="187" text-anchor="middle" font-size="12" fill="${pal.MUTED}">${esc(sub)}${peakHtml}</text></svg>`;
  }

  const SOLAR_PANEL_ICON = `<svg width="36" height="36" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
    <path d="M8 4h19l-3 17H5z" fill="#2F6BEA" stroke="#CBD5E1" stroke-width="1.4" stroke-linejoin="round"/>
    <path d="M14.3 4l-2.1 17M20.7 4l-2.6 17M7 9.7h19M6 15.3h19" stroke="#CBD5E1" stroke-width="1"/>
    <path d="M14.5 21v5M10 27h9" stroke="#94A3B8" stroke-width="2" stroke-linecap="round"/></svg>`;
  // ikona solarnog panela: klasična (izvorna) ili neon (icons.js)
  const panelIcon = () => (Icons.theme() !== "classic" ? Icons.get("panel") : SOLAR_PANEL_ICON);
  const tile = (icon, tintColor) => `<div class="tile" style="background:${tintColor}">${icon}</div>`;

  // ---------------------------------------------------------------- sekcije
  function heroBackground(photoUrl) {
    photoUrl = safeImageUrl(photoUrl);
    const fade = pal.FADE;
    const layers = [`linear-gradient(90deg, rgba(${fade},.97) 0%, rgba(${fade},.86) 24%, rgba(${fade},0) 52%)`,
      `linear-gradient(180deg, rgba(${fade},0) 70%, rgba(${fade},.55) 100%)`];
    if (themeName === "dark") layers.push(`linear-gradient(rgba(${fade},.28), rgba(${fade},.28))`);
    layers.push(photoUrl ? `url('${photoUrl}')` : `linear-gradient(135deg, rgba(${fade},.6), rgba(${fade},1))`);
    return `<div class="hero-bg" style="background-image:${layers.join(", ")}"></div>`;
  }

  function heroContent(greeting, headlineHtml, siteHtml, weatherHtml) {
    return `<div class="hero"><div class="hero-left"><div><div class="greet">${esc(greeting)} ${Icons.get("greet")}  ·  <span class="live-clock"></span></div>`
      + `<h1>${headlineHtml}</h1></div>${siteHtml}</div>${weatherHtml}</div>`;
  }

  function siteCard(logoUrl, name, location, state, stateCls) {
    const logo = safeImageUrl(logoUrl);
    return `<div class="glass site-card"><div class="name">${esc(location)}</div>${logo ? `<img class="logo" src="${esc(logo)}" alt="${esc(name)}">` : ""}`
      + `<div class="facts"><div class="fact ${stateCls}"><div class="k">${T("Status")}</div><div class="v">${esc(state)}</div></div></div></div>`;
  }

  function weatherCard(today, w, days = 5) {
    if (!w) {
      return `<div class="glass weather"><div class="date">${dateHr(today)}</div>`
        + `<div class="cond" style="text-align:center">${T("Prognoza trenutno nije dostupna")}</div><div></div></div>`;
    }
    const now = Weather.describe(w.code, w.is_day);
    const next = w.days.slice(1, 1 + days).map((d) => {  // sljedećih 2, 3 ili 5 dana (Postavke → Prikaz)
      const date = parseDate(d.date);
      return `<div class="day">${fmtDate("{wd}", date)}<div class="i">${Weather.describe(d.code).icon}</div>`
        + `<b>${Math.round(d.tmax)}°</b> / ${Math.round(d.tmin)}°</div>`;
    }).join("");
    return `<div class="glass weather"><div class="date">${dateHr(today)}</div>`
      + `<div class="now"><div class="icon">${now.icon}</div><div><div class="temp">${fmt(w.temperature, 0)}°C</div><div class="cond">${esc(now.label)}</div></div></div>`
      + `<div class="row"><span>${T("Sunčevo zračenje")}</span><b>${fmt(w.radiation_wm2, 0)} W/m²</b></div>`
      + `<div class="row"><span>${T("Vjetar")}</span><b>${fmt(w.wind_kmh, 0)} km/h</b></div><div class="days">${next}</div></div>`;
  }

  function kpiStrip(items, height) {
    const cells = items.map((i) => `<div class="kpi">${tile(i.icon, i.tint)}<div><div class="label">${esc(i.label)}</div>`
      + `<div class="value">${i.value}<small>${esc(i.unit)}</small></div></div>`
      + `${i.spark != null ? sparkline(i.spark, i.color) : "<span></span>"}<div class="sub">${i.sub}</div></div>`).join("");
    return `<div class="glass kpis${items.length === 1 ? " single" : ""}" style="--h:${height}px">${cells}</div>`;
  }

  const cardHeader = (title, big = "", unit = "", meta = "", right = "") =>
    `<div class="card-title">${esc(title)}<small>${right}</small></div>`
    + (big ? `<div class="headline"><div class="big">${big}<small>${esc(unit)}</small></div><div class="meta">${meta}</div></div>` : "");

  const empty = (message) => `<div class="empty">${esc(message)}</div>`;

  function listCard(title, items, right, height) {
    const rows = items.map((i) => `<div class="item">${tile(i.icon, i.tint)}<div><div class="k">${esc(i.label)}</div>`
      + `<div class="v">${i.value}<small>${esc(i.unit)}</small></div></div></div>`).join("");
    return `<div class="card" style="--h:${height}px"><div class="card-title">${esc(title)}<small>${right}</small></div><div class="list">${rows}</div></div>`;
  }

  function speedometerCard(title, value, maxValue, sub, peak, right, height) {
    const svg = speedometer(value, maxValue, sub, peak);
    return `<div class="card" style="--h:${height}px"><div class="card-title">${esc(title)}<small>${right}</small></div><div class="speedo">${svg}</div></div>`;
  }

  // Tok energije: statični sloj (crtež, linije, strelice) i sloj s vrijednostima.
  function bezier([[x0, y0], [x1, y1], [x2, y2], [x3, y3]], t) {
    const u = 1 - t;
    return [[u ** 3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x3, u ** 3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y3],
      [3 * u * u * (x1 - x0) + 6 * u * t * (x2 - x1) + 3 * t * t * (x3 - x2), 3 * u * u * (y1 - y0) + 6 * u * t * (y2 - y1) + 3 * t * t * (y3 - y2)]];
  }
  function flowLayers(drawingUri, nodes, live, height) {
    const anchors = { tl: [17, 22], bl: [17, 78], tr: [83, 22], br: [83, 78] };
    const curves = {};
    for (const [pos, [x, y]] of Object.entries(anchors)) {
      if (nodes.some((n) => n.pos === pos)) curves[pos] = [[x, y], [(x + 50) / 2, y], [(x + 50) / 2, 50], [50 + (x - 50) * .22, 50]];
    }
    // Čvor s reverse (višak proizvodnje ide u mrežu): crtice i strelice teku od zgrade prema čvoru.
    const reverse = new Set(nodes.filter((n) => n.reverse).map((n) => n.pos));
    const paths = Object.entries(curves).map(([pos, [p0, p1, p2, p3]]) => `<path class="${live ? "live" : ""}${reverse.has(pos) ? " rev" : ""}" d="M${p0[0]},${p0[1]} C${p1[0]},${p1[1]} ${p2[0]},${p2[1]} ${p3[0]},${p3[1]}" `
      + `fill="none" stroke="${pal.FLOW_LINE}" stroke-width="1.6" vector-effect="non-scaling-stroke"/>`).join("");
    let arrows = "";
    if (live) {
      const steps = 20, duration = 2.4, tEnd = .55;
      const keyframes = Object.entries(curves).map(([pos, curve]) => `@keyframes flow-${pos} {` + Array.from({ length: steps + 1 }, (_, i) => {
        const rev = reverse.has(pos), sign = rev ? -1 : 1;
        const [[x, y], [dx, dy]] = bezier(curve, (rev ? steps - i : i) / steps * tEnd);
        return `${(i * 100 / steps).toFixed(0)}% { left: ${x.toFixed(2)}%; top: ${y.toFixed(2)}%; --dx: ${(dx * sign).toFixed(3)}; --dy: ${(dy * sign).toFixed(3)}; opacity: ${i === 0 || i === steps ? 0 : 1}; }`;
      }).join(" ") + "}").join("");
      arrows = `<style>${keyframes}</style>` + Object.keys(curves).flatMap((pos) => [0, 1, 2].map((k) =>
        `<i class="arrow" style="animation: flow-${pos} ${duration}s linear ${(-k * duration / 3).toFixed(1)}s infinite"></i>`)).join("");
    }
    const img = drawingUri ? `<img class="building" src="${drawingUri}" alt="Naša zgrada">` : "";
    const boxes = nodes.map((n) => `<div class="node ${n.pos}"><div class="i">${n.icon}</div><div><div class="k">${esc(n.label)}</div><div class="v">${n.value}</div></div></div>`).join("");
    return {
      base: `<div class="card" style="--h:${height}px"><div class="flow"><svg class="lines" viewBox="0 0 100 100" preserveAspectRatio="none">${paths}</svg>${arrows}${img}</div></div>`,
      overlay: `<div class="card overlay" style="--h:${height}px"><div class="flow">${boxes}</div></div>`,
    };
  }

  return {
    SOLAR_PANEL_ICON, panelIcon, esc, safeImageUrl, fmt, energy, mass, dateHr, statusDot, delta,
    hhmm, tint, rgba, setTheme, theme: () => pal, themeName: () => themeName, weekdayIndex, sparkline, speedometer, tile,
    heroBackground, heroContent, siteCard, weatherCard, kpiStrip, cardHeader, empty, listCard, speedometerCard, flowLayers,
  };
})();

// "2026-10-29" → lokalni datum (ponoć)
function parseDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

// ---------------------------------------------------------------- WMO šifre vremena (solar/weather.py)
const Weather = (() => {
  const WMO = {
    0: ["Vedro", "sun", "moon"], 1: ["Pretežno vedro", "sun_cloud", "moon"], 2: ["Djelomično oblačno", "partly", "cloud"], 3: ["Oblačno", "cloud", "cloud"],
    45: ["Magla", "fog", "fog"], 48: ["Magla s injem", "fog", "fog"], 51: ["Slaba rosulja", "showers", "rain"], 53: ["Rosulja", "showers", "rain"],
    55: ["Jaka rosulja", "rain", "rain"], 56: ["Ledena rosulja", "rain", "rain"], 57: ["Ledena rosulja", "rain", "rain"],
    61: ["Slaba kiša", "showers", "rain"], 63: ["Kiša", "rain", "rain"], 65: ["Jaka kiša", "rain", "rain"], 66: ["Ledena kiša", "rain", "rain"],
    67: ["Ledena kiša", "rain", "rain"], 71: ["Slab snijeg", "snow", "snow"], 73: ["Snijeg", "snow", "snow"], 75: ["Jak snijeg", "snowflake", "snowflake"],
    77: ["Zrnati snijeg", "snow", "snow"], 80: ["Pljuskovi", "showers", "rain"], 81: ["Pljuskovi", "rain", "rain"], 82: ["Jaki pljuskovi", "thunder", "thunder"],
    85: ["Snježni pljuskovi", "snow", "snow"], 86: ["Snježni pljuskovi", "snow", "snow"], 95: ["Grmljavina", "thunder", "thunder"],
    96: ["Grmljavina s tučom", "thunder", "thunder"], 99: ["Grmljavina s tučom", "thunder", "thunder"],
  };
  function describe(code, isDay = 1) {
    const [label, day, night] = WMO[code] || ["—", "thermometer", "thermometer"];
    return { label: T(label), icon: Icons.get(isDay ? day : night) };  // tema ikona: icons.js
  }
  return { describe };
})();

// ---------------------------------------------------------------- uklanjanje pozadine crteža (solar/ui.py _cutout_b64)
const Cutout = (() => {
  const cache = new Map();
  function boxStd(gray, w, h, r) {
    const k = 2 * r + 1, W = w + 2 * (r + 1), H = h + 2 * (r + 1);
    const sum = new Float64Array((W + 1) * (H + 1)), sq = new Float64Array((W + 1) * (H + 1));
    const at = (x, y) => gray[Math.min(h - 1, Math.max(0, y - r - 1)) * w + Math.min(w - 1, Math.max(0, x - r - 1))];
    for (let y = 0; y < H; y++) {
      let rs = 0, rq = 0;
      for (let x = 0; x < W; x++) {
        const v = at(x, y);
        rs += v; rq += v * v;
        sum[(y + 1) * (W + 1) + x + 1] = sum[y * (W + 1) + x + 1] + rs;
        sq[(y + 1) * (W + 1) + x + 1] = sq[y * (W + 1) + x + 1] + rq;
      }
    }
    const out = new Float32Array(w * h);
    const box = (arr, x, y) => arr[(y + k) * (W + 1) + x + k] - arr[y * (W + 1) + x + k] - arr[(y + k) * (W + 1) + x] + arr[y * (W + 1) + x];
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const m = box(sum, x + 1, y + 1) / (k * k), q = box(sq, x + 1, y + 1) / (k * k);
      out[y * w + x] = Math.sqrt(Math.max(0, q - m * m));
    }
    return out;
  }

  async function process(url, maxWidth) {
    const img = new Image();
    img.src = url;
    await img.decode();
    const scale = Math.min(1, maxWidth / img.naturalWidth);
    const w = Math.round(img.naturalWidth * scale), h = Math.round(img.naturalHeight * scale);
    const canvas = document.createElement("canvas");
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(img, 0, 0, w, h);
    const data = ctx.getImageData(0, 0, w, h), px = data.data;
    // PNG s prozirnom pozadinom koristi se kakav jest
    for (let i = 3; i < px.length; i += 4 * 97) if (px[i] < 250) return canvas.toDataURL("image/png");

    const k = Math.max(4, Math.floor(Math.min(h, w) * .04));
    const corner = (x0, y0) => {
      const s = [0, 0, 0];
      for (let y = y0; y < y0 + k; y++) for (let x = x0; x < x0 + k; x++) for (let c = 0; c < 3; c++) s[c] += px[(y * w + x) * 4 + c];
      return s.map((v) => v / (k * k));
    };
    const tl = corner(0, 0), tr = corner(w - k, 0), bl = corner(0, h - k), br = corner(w - k, h - k);
    const n = w * h, bg = new Float32Array(n * 3), diff = new Float32Array(n), gray = new Float32Array(n), shadowLike = new Uint8Array(n);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const fx = x / (w - 1), fy = y / (h - 1), i = y * w + x;
      let d = 0;
      for (let c = 0; c < 3; c++) {
        const b = (tl[c] * (1 - fx) + tr[c] * fx) * (1 - fy) + (bl[c] * (1 - fx) + br[c] * fx) * fy;
        bg[i * 3 + c] = b;
        d = Math.max(d, Math.abs(px[i * 4 + c] - b));
      }
      diff[i] = d;
      gray[i] = (px[i * 4] + px[i * 4 + 1] + px[i * 4 + 2]) / 3;
    }
    const std = boxStd(gray, w, h, 3);
    for (let i = 0; i < n; i++) {
      const r = px[i * 4], g = px[i * 4 + 1], b = px[i * 4 + 2];
      shadowLike[i] = std[i] < 14 && b - r > 25 && b >= g && g >= r && b > 150 ? 1 : 0;
    }
    // područje slično pozadini povezano s rubom (mreža 1/2 zbog brzine), poplava iz rubova
    const lw = Math.ceil(w / 2), lh = Math.ceil(h / 2), low = new Uint8Array(lw * lh), reach = new Uint8Array(lw * lh);
    for (let y = 0; y < lh; y++) for (let x = 0; x < lw; x++) { const i = y * 2 * w + x * 2; low[y * lw + x] = diff[i] < 34 || shadowLike[i] ? 1 : 0; }
    const stack = [];
    const push = (x, y) => { const i = y * lw + x; if (low[i] && !reach[i]) { reach[i] = 1; stack.push(i); } };
    for (let x = 0; x < lw; x++) { push(x, 0); push(x, lh - 1); }
    for (let y = 0; y < lh; y++) { push(0, y); push(lw - 1, y); }
    while (stack.length) {
      const i = stack.pop(), x = i % lw, y = (i - x) / lw;
      if (x > 0) push(x - 1, y); if (x < lw - 1) push(x + 1, y); if (y > 0) push(x, y - 1); if (y < lh - 1) push(x, y + 1);
    }
    // razmazana maska u punoj razlučivosti
    const mask = document.createElement("canvas");
    mask.width = lw; mask.height = lh;
    const mctx = mask.getContext("2d", { willReadFrequently: true });
    const mdata = mctx.createImageData(lw, lh);
    for (let i = 0; i < lw * lh; i++) { mdata.data[i * 4 + 3] = reach[i] * 255; }
    mctx.putImageData(mdata, 0, 0);
    const big = document.createElement("canvas");
    big.width = w; big.height = h;
    const bctx = big.getContext("2d", { willReadFrequently: true });
    bctx.filter = "blur(1.2px)";
    bctx.drawImage(mask, 0, 0, w, h);
    const region = bctx.getImageData(0, 0, w, h).data;

    for (let i = 0; i < n; i++) {
      const reg = region[i * 4 + 3] / 255;
      const bgMean = (bg[i * 3] + bg[i * 3 + 1] + bg[i * 3 + 2]) / 3;
      const shadowAlpha = Math.min(.5, Math.max(0, (bgMean - gray[i]) / 140));
      const edgeAlpha = shadowLike[i] ? 0 : Math.min(1, Math.max(0, (diff[i] - 10) / 40));
      const alpha = reg * Math.max(shadowAlpha, edgeAlpha) + (1 - reg);
      const al = Math.min(1, Math.max(1e-3, alpha));
      const isShadow = reg > .5 && shadowAlpha >= edgeAlpha;
      for (let c = 0; c < 3; c++) {
        px[i * 4 + c] = isShadow ? [8, 16, 38][c] : Math.min(255, Math.max(0, (px[i * 4 + c] - (1 - al) * bg[i * 3 + c]) / al));
      }
      px[i * 4 + 3] = Math.round(alpha * 255);
    }
    ctx.putImageData(data, 0, 0);
    return canvas.toDataURL("image/webp", .85);
  }

  return {
    get(url, maxWidth = 2200) {
      if (!cache.has(url)) cache.set(url, process(url, maxWidth).catch(() => url));
      return cache.get(url);
    },
  };
})();
