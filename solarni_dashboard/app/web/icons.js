// Teme ikona dashboarda (Postavke → Prikaz → Ikone): "classic" = emoji (kao do sada), "neon" = hi-tech SVG ikone u
// stilu ikone aplikacije (neonsko plavi obrub s prijelazom cijan → plava, narančasto sunce, blagi sjaj).
// "iconset" = rasterske ikone iz kompleta (web/icons/iconset/<ključ>.png); ključ kojeg nema u kompletu → neon SVG.
// Upotreba: Icons.setTheme(settings.icon_theme, uiTheme); Icons.get("sun") → HTML (emoji ili <svg>).
// Ikone su statični nizovi iz ove datoteke (bez korisničkog unosa) – sigurno ih je umetati kao HTML.
(function () {
  "use strict";

  // ključ → emoji (klasična tema; isti znakovi kao prije 4.0)
  const EMOJI = {
    panel: "", sun: "☀️", sun_cloud: "🌤️", partly: "⛅", cloud: "☁️", rain: "🌧️", showers: "🌦️", snow: "🌨️",
    snowflake: "❄️", fog: "🌫️", thunder: "⛈️", moon: "🌙", sunrise: "🌅", sunset: "🌇", thermometer: "🌡️",
    globe: "🌍", calendar: "📅", calendar_year: "🗓️", bolt: "⚡", plug: "🔌", home: "🏠", building: "🏢", tower: "🗼",
    chart: "📈", sprout: "🌱", tree: "🌳", trophy: "🏆", car: "🚗", ecar: "🚘", bulb: "💡", drop: "💧", money: "💶",
    phone: "📱", battery: "🔋", warning: "⚠", greet: "👋",
  };

  // Atributi crteža: B = plavi neonski obrub, S = sunce (ispuna), O = narančasti obrub
  const B = 'fill="none" stroke="url(#nx-b)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"';
  const S = 'fill="url(#nx-s)" stroke="none"';
  const O = 'fill="none" stroke="url(#nx-s)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"';
  const rays = (cx, cy, r1, r2, n = 8) => {
    let d = "";
    for (let i = 0; i < n; i++) {
      const a = (Math.PI * 2 * i) / n;
      d += `M${(cx + r1 * Math.cos(a)).toFixed(2)} ${(cy + r1 * Math.sin(a)).toFixed(2)}L${(cx + r2 * Math.cos(a)).toFixed(2)} ${(cy + r2 * Math.sin(a)).toFixed(2)}`;
    }
    return `<path ${O} d="${d}"/>`;
  };
  const CLOUD = (dx = 0, dy = 0) => `<path ${B} transform="translate(${dx} ${dy})" d="M7 18h10a4 4 0 0 0 .6-7.95A5.5 5.5 0 0 0 7.1 9.6 4.2 4.2 0 0 0 7 18Z"/>`;
  const SMALL_SUN = (cx, cy) => `<circle cx="${cx}" cy="${cy}" r="2.6" ${S}/>${rays(cx, cy, 3.8, 5.2)}`;

  const NEON = {
    panel: `<path ${B} d="M3.5 16.5 7.5 6.5h13l-4 10Z"/><path ${B} d="M5.5 11.5h13M11.8 6.5l-4 10M16.2 6.5l-4 10"/><path ${B} d="M12 16.5V20M9 20.5h6"/><circle cx="4.5" cy="4.5" r="2" ${S}/>`,
    sun: `<circle cx="12" cy="12" r="4.6" ${S}/>${rays(12, 12, 6.8, 9.8)}`,
    sun_cloud: `${SMALL_SUN(15.5, 7.5)}${CLOUD(-1.5, 2)}`,
    partly: `${SMALL_SUN(9, 8)}${CLOUD(1, 2)}`,
    cloud: CLOUD(0, 0),
    rain: `${CLOUD(0, -2)}<path ${B} d="M8.5 19.5l-1 2M12.5 19.5l-1 2M16.5 19.5l-1 2"/>`,
    showers: `${SMALL_SUN(16, 6.5)}${CLOUD(-1.5, -1)}<path ${B} d="M8 19.5l-1 2M12 19.5l-1 2"/>`,
    snow: `${CLOUD(0, -2)}<path ${B} d="M8 20.5h.01M12 21.5h.01M16 20.5h.01M10 22.5h.01M14 22.5h.01" stroke-width="2.4"/>`,
    snowflake: `<path ${B} d="M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9"/><path ${B} d="M9.5 4.5 12 7l2.5-2.5M9.5 19.5 12 17l2.5 2.5"/>`,
    fog: `${CLOUD(0, -3)}<path ${B} d="M4 18.5h16M6 21.5h12"/>`,
    thunder: `${CLOUD(0, -2.5)}<path ${S} d="M12.5 13.5 9.5 18.5h2.6l-1.3 4 4.2-5.6h-2.6l1.6-3.4Z"/>`,
    moon: `<path fill="url(#nx-b)" opacity=".9" d="M15.5 3.5a8.5 8.5 0 1 0 5 13.7A7 7 0 0 1 15.5 3.5Z"/>`,
    sunrise: `<path ${S} d="M7 16a5 5 0 0 1 10 0Z"/>${rays(12, 16, 6.6, 8.8, 7)}<path ${B} d="M3 19h18M12 3v4M9.5 5.5 12 3l2.5 2.5"/>`,
    sunset: `<path ${S} d="M7 16a5 5 0 0 1 10 0Z"/>${rays(12, 16, 6.6, 8.8, 7)}<path ${B} d="M3 19h18M12 3v4M9.5 4.5 12 7l2.5-2.5"/>`,
    thermometer: `<path ${B} d="M10 14.5V5a2 2 0 0 1 4 0v9.5a4 4 0 1 1-4 0Z"/><circle cx="12" cy="17.6" r="1.9" ${S}/><path ${O} d="M12 15.5V8.5"/>`,
    globe: `<circle cx="12" cy="12" r="8.5" ${B}/><path ${B} d="M3.5 12h17M12 3.5c3 3.2 3 13.8 0 17M12 3.5c-3 3.2-3 13.8 0 17"/>`,
    calendar: `<rect x="3.5" y="5" width="17" height="15.5" rx="2.5" ${B}/><path ${B} d="M3.5 9.5h17M8 3v4M16 3v4"/><circle cx="8.5" cy="13.5" r="1.2" ${S}/><path ${B} d="M12 13.5h.01M15.5 13.5h.01M8.5 17h.01M12 17h.01" stroke-width="2.4"/>`,
    calendar_year: `<rect x="3.5" y="5" width="17" height="15.5" rx="2.5" ${B}/><path ${B} d="M3.5 9.5h17M8 3v4M16 3v4"/><path ${O} d="M7.5 16.5l2.5-3 2.5 2 4-4"/>`,
    bolt: `<path ${S} d="M13.5 2.5 5 13.5h6l-1.5 8 9-11.5h-6l1-7.5Z"/>`,
    plug: `<path ${B} d="M9 3v4M15 3v4M6.5 7h11v3.5a5.5 5.5 0 0 1-11 0Z"/><path ${O} d="M12 16v5"/>`,
    home: `<path ${B} d="M3.5 11.5 12 4l8.5 7.5"/><path ${B} d="M5.5 10v10h13V10"/><path fill="url(#nx-b)" opacity=".85" d="M13.2 6.2l4.6 4.1h-6.4Z"/><rect x="10" y="14" width="4" height="6" ${O}/>`,
    building: `<rect x="5" y="3.5" width="14" height="17" rx="1.5" ${B}/><path ${B} d="M9 8h.01M12 8h.01M15 8h.01M9 11.5h.01M12 11.5h.01M15 11.5h.01" stroke-width="2.4"/><path ${O} d="M10.5 20.5V16h3v4.5"/>`,
    tower: `<path ${B} d="M12 2.5 7 21.5M12 2.5l5 19M8.5 15.5h7M9.6 11h4.8M5 7.5h14M7 21.5h10"/><path ${O} d="M5 7.5v2M19 7.5v2"/>`,
    chart: `<path ${B} d="M4.5 20.5v-4M9 20.5v-6.5M13.5 20.5V12M18 20.5V8.5"/><path ${O} d="M3.5 13 8.5 9.5l4 2.5 7-6.5"/><circle cx="19.5" cy="5.5" r="1.4" ${S}/>`,
    sprout: `<path ${B} d="M12 21v-9"/><path fill="url(#nx-b)" opacity=".85" d="M12 12.5C12 8 9 5.5 4.5 5.5 4.5 10 7.5 12.5 12 12.5Z"/><path ${S} d="M12 10c0-3.6 2.5-6 6.5-6 0 3.9-2.6 6-6.5 6Z"/>`,
    tree: `<path ${B} d="M12 21.5v-6M9 18.5l3-2 3 2"/><path ${B} d="M12 3a6 6 0 0 0-5.6 8.2A4.5 4.5 0 0 0 9.5 16h5a4.5 4.5 0 0 0 3.1-4.8A6 6 0 0 0 12 3Z"/>`,
    trophy: `<path ${S} d="M7.5 3.5h9v4.5a4.5 4.5 0 0 1-9 0Z"/><path ${B} d="M7.5 5.5h-3a3 3 0 0 0 3.6 3.9M16.5 5.5h3a3 3 0 0 1-3.6 3.9M12 12.5v4M8.5 20.5h7M9.5 20.5l.8-4h3.4l.8 4"/>`,
    car: `<path ${B} d="M4 15.5v-3l2-4.5h12l2 4.5v3M3.5 15.5h17v2.5h-17Z"/><circle cx="7.5" cy="18" r="1.7" ${S}/><circle cx="16.5" cy="18" r="1.7" ${S}/>`,
    ecar: `<path ${B} d="M4 15.5v-3l2-4.5h12l2 4.5v3M3.5 15.5h17v2.5h-17Z"/><circle cx="7.5" cy="18" r="1.7" ${S}/><circle cx="16.5" cy="18" r="1.7" ${S}/><path ${S} d="M12.6 8.8 10.4 12.6h1.7l-.8 2.6 2.8-3.9h-1.7l.9-2.5Z"/>`,
    bulb: `<path ${B} d="M9 17.5h6M9.8 20.5h4.4M8.5 14.5a6 6 0 1 1 7 0c-.6.5-1 1.2-1 2v1h-5v-1c0-.8-.4-1.5-1-2Z"/><path ${O} d="M12 6.5v3l1.5 1.5"/>`,
    drop: `<path ${B} d="M12 3s6 6.4 6 11a6 6 0 0 1-12 0c0-4.6 6-11 6-11Z"/><path ${O} d="M9.5 15a2.6 2.6 0 0 0 2.5 2.5"/>`,
    money: `<circle cx="12" cy="12" r="8.5" ${B}/><path ${O} d="M15.5 8.5a4.2 4.2 0 1 0 0 7M7.5 11h6M7.5 13.5h6"/>`,
    phone: `<rect x="6.5" y="2.5" width="11" height="19" rx="2.5" ${B}/><path ${O} d="M10.5 18.5h3"/><path ${S} d="M12.8 6.5 10.6 10.4h1.7l-.8 2.6 2.8-3.9h-1.7l.9-2.6Z"/>`,
    battery: `<rect x="3" y="7" width="16" height="10" rx="2" ${B}/><path ${B} d="M21 10.5v3"/><rect x="5.2" y="9.2" width="8.5" height="5.6" rx="1" ${S}/>`,
    warning: `<path ${O} d="M12 3.5 21.5 20h-19Z"/><path ${O} d="M12 9.5v5M12 17.5h.01" stroke-width="2.2"/>`,
    greet: `<circle cx="12" cy="12" r="3.6" ${S}/>${rays(12, 12, 5.6, 8.2)}`,
  };

  // ključevi s PNG ikonom u web/icons/iconset (izrezano iz iconset.png)
  const ICONSET = ["battery", "bolt", "building", "bulb", "calendar", "calendar_year", "chart", "drop", "ecar", "globe", "greet", "home", "money", "panel", "partly", "plug", "rain", "showers", "sprout", "sun", "sun_cloud", "thermometer", "tower", "tree", "trophy", "warning"];
  const ICONSET_DIR = "icons/iconset/";

  const ALL = Object.keys(EMOJI);
  let current = "classic";

  function ensureDefs() {  // jedan skup prijelaza za sve ikone (id-ovi nx-b, nx-s)
    if (document.getElementById("nx-defs")) return;
    const holder = document.createElement("div");
    holder.innerHTML = '<svg id="nx-defs" width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>'
      + '<linearGradient id="nx-b" x1="0" y1="0" x2="1" y2="1"><stop offset="0" style="stop-color:var(--nx-b1,#7DF9FF)"/><stop offset="1" style="stop-color:var(--nx-b2,#2F7BFF)"/></linearGradient>'
      + '<linearGradient id="nx-s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFE066"/><stop offset="1" stop-color="#FF7A00"/></linearGradient>'
      + "</defs></svg>";
    document.body.appendChild(holder.firstChild);
    const style = document.createElement("style");
    style.id = "nx-style";
    style.textContent = ".nx-ico{width:1.2em;height:1.2em;vertical-align:-.2em;overflow:visible;"
      + "filter:drop-shadow(0 0 1.5px var(--nx-glow,rgba(56,189,248,.9))) drop-shadow(0 0 5px var(--nx-glow2,rgba(47,123,255,.45)))}"
      + ".tile .nx-ico,.i .nx-ico,.icon .nx-ico{width:1.35em;height:1.35em}"
      + ".ix-ico{width:1.45em;height:1.45em;vertical-align:-.32em;object-fit:contain}"
      + ".tile .ix-ico,.i .ix-ico,.icon .ix-ico{width:1.6em;height:1.6em}";
    document.head.appendChild(style);
  }

  // Tema ikona; uiTheme "light" → tamniji plavi i slabiji sjaj (čitljivost na svijetloj pozadini)
  function setTheme(name, uiTheme) {
    current = name === "neon" || name === "iconset" ? name : "classic";
    if (current === "classic" || typeof document === "undefined") return;  // iconset: neon je zamjena za ključeve bez PNG-a
    ensureDefs();
    const light = uiTheme === "light";
    const root = document.documentElement.style;
    root.setProperty("--nx-b1", light ? "#0EA5E9" : "#7DF9FF");
    root.setProperty("--nx-b2", light ? "#1D4ED8" : "#2F7BFF");
    root.setProperty("--nx-glow", light ? "rgba(14,165,233,.35)" : "rgba(56,189,248,.9)");
    root.setProperty("--nx-glow2", light ? "rgba(29,78,216,.15)" : "rgba(47,123,255,.45)");
  }

  function get(key) {
    if (current === "iconset" && ICONSET.includes(key)) return `<img class="ix-ico" src="${ICONSET_DIR}${key}.png" alt="" aria-hidden="true" draggable="false">`;
    if (current !== "classic" && NEON[key]) return `<svg class="nx-ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${NEON[key]}</svg>`;
    return EMOJI[key] !== undefined ? EMOJI[key] : "";
  }

  // za ugnježđivanje u postojeći <svg> (npr. prsten baterije): iconset → <image>, inače neon crtež
  const svgInner = (key) => (current === "iconset" && ICONSET.includes(key)
    ? `<image href="${ICONSET_DIR}${key}.png" x="0" y="0" width="24" height="24"/>` : NEON[key] || "");
  const api = { get, svgInner, setTheme, theme: () => current, keys: () => ALL.slice(), THEMES: ["classic", "neon", "iconset"], _neon: NEON, _emoji: EMOJI, _iconset: ICONSET };
  if (typeof window !== "undefined") window.Icons = api;
  if (typeof module !== "undefined") module.exports = api;
})();
