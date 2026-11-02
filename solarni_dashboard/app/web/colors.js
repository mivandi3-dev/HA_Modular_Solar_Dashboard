// Palete boja (Postavke → Prikaz → Tema): boje palete preko boja teme (themes.js).
// Dijele ih dashboard, grafikoni i Android. Paleta teme i CSS dashboarda izvoze se iz Python verzije, pa se boje
// ne upisuju u njih – palette() vraća izmijenjenu kopiju palete, a apply() dodaje CSS koji nadjačava teme.
"use strict";

window.SolariColors = (() => {
  const KEYS = ["page", "card", "text", "accent", "production", "consumption", "export"];
  const HEX = /^#[0-9a-f]{6}$/i;
  // Palete (Postavke → Prikaz → Tema): osnovna tema (svijetla/tamna) i boje; Tamna i Svijetla su boje same teme
  const PALETTES = {
    dark: { theme: "dark", colors: {} },
    light: { theme: "light", colors: {} },
    ocean: { theme: "dark", colors: { page: "#061C26", card: "#0B2E3D", text: "#E0F2F1", accent: "#2DD4BF",
      production: "#38BDF8", consumption: "#F59E0B", export: "#34D399" } },
    forest: { theme: "dark", colors: { page: "#0A1710", card: "#12281B", text: "#E8F5EC", accent: "#A3E635",
      production: "#22C55E", consumption: "#F97316", export: "#84CC16" } },
    sunset: { theme: "dark", colors: { page: "#1A0F1E", card: "#2A1630", text: "#FCE7F3", accent: "#FB7185",
      production: "#FBBF24", consumption: "#A78BFA", export: "#34D399" } },
    midnight: { theme: "dark", colors: { page: "#0B0B1E", card: "#17173A", text: "#E8E8FF", accent: "#A78BFA",
      production: "#60A5FA", consumption: "#F472B6", export: "#34D399" } },
    graphite: { theme: "dark", colors: { page: "#111315", card: "#1C1F23", text: "#E5E7EB", accent: "#F59E0B",
      production: "#FACC15", consumption: "#60A5FA", export: "#4ADE80" } },
    contrast: { theme: "dark", colors: { page: "#000000", card: "#141414", text: "#FFFFFF", accent: "#FFD400",
      production: "#00B7FF", consumption: "#FF8A00", export: "#00E676" } },
    paper: { theme: "light", colors: { page: "#F3EFE6", card: "#FFFDF8", text: "#1F2937", accent: "#B45309",
      production: "#2563EB", consumption: "#D97706", export: "#059669" } },
    sky: { theme: "light", colors: { page: "#EAF4FF", card: "#FFFFFF", text: "#0F2A44", accent: "#0284C7",
      production: "#0EA5E9", consumption: "#F97316", export: "#16A34A" } },
    sand: { theme: "light", colors: { page: "#F5EFE3", card: "#FFFBF2", text: "#3B2F2F", accent: "#C2410C",
      production: "#D97706", consumption: "#7C3AED", export: "#15803D" } },
  };
  const PAGE = { dark: "#0B1120", light: "#EEF2F8" };  // osnovna boja pozadine tema (PAGE je gradijent)

  const clean = (colors) => Object.fromEntries(Object.entries(colors || {}).filter(([k, v]) => KEYS.includes(k) && HEX.test(v)));
  const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const rgba = (hex, a) => `rgba(${rgb(hex).join(",")},${a})`;
  const toHex = (c) => "#" + c.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");
  const mix = (a, b, t) => toHex(rgb(a).map((v, i) => v + (rgb(b)[i] - v) * t));
  const light = (hex) => { const [r, g, b] = rgb(hex); return 0.299 * r + 0.587 * g + 0.114 * b > 150; };

  // Boje teme kao početne vrijednosti u postavkama
  function defaults(themeName) {
    const t = window.SOLARI_THEMES[themeName] || window.SOLARI_THEMES.dark;
    return { page: PAGE[themeName] || PAGE.dark, card: t.CARD_SOLID, text: t.TEXT, accent: t.ACCENT,
      production: t.BRAND_GREEN, consumption: t.LOAD, export: t.GREEN };
  }

  // Paleta teme s korisničkim bojama (ključevi kao u themes.js)
  function palette(base, colors) {
    const c = clean(colors), p = { ...base };
    if (c.page) {
      const glow = mix(c.page, c.accent || c.text || (light(c.page) ? "#FFFFFF" : "#3B82F6"), 0.14);
      p.PAGE = `radial-gradient(1200px 600px at 85% 0%, ${glow} 0%, transparent 60%), `
        + `linear-gradient(180deg, ${c.page} 0%, ${mix(c.page, light(c.page) ? "#000000" : "#FFFFFF", 0.04)} 100%)`;
      p.FADE = rgb(c.page).join(",");
    }
    if (c.card) {
      p.CARD = rgba(c.card, 0.78);
      p.CARD_SOLID = c.card;
    }
    if (c.text) {
      const under = c.card || base.CARD_SOLID;
      p.TEXT = c.text;
      p.MUTED = mix(c.text, under, 0.38);
      p.GREET = mix(c.text, under, 0.15);
      p.LINE = rgba(c.text, 0.09);
      p.GRID = rgba(c.text, 0.07);
      p.TRACK = rgba(c.text, 0.1);
    }
    if (c.accent) p.ACCENT = c.accent;
    if (c.production) {
      p.BRAND_GREEN = c.production;
      p.FLOW_LINE = c.production;
    }
    if (c.consumption) {
      p.LOAD = c.consumption;
      p.TINT_AMBER = rgba(c.consumption, 0.16);
    }
    if (c.export) {
      p.GREEN = c.export;
      p.TINT_GREEN = rgba(c.export, 0.16);
    }
    return p;
  }

  // CSS koji nadjačava teme (varijable, pozadina i dva mjesta s upisanom bojom proizvodnje)
  function css(p, colors) {
    const c = clean(colors);
    if (!Object.keys(c).length) return "";
    const vars = [];
    if (c.card) vars.push(`--card: ${p.CARD}`, `--card-solid: ${p.CARD_SOLID}`, `--border: ${rgba(c.text || p.TEXT, 0.08)}`);
    if (c.text) vars.push(`--text: ${p.TEXT}`, `--muted: ${p.MUTED}`, `--greet: ${p.GREET}`, `--line: ${p.LINE}`);
    if (c.accent) vars.push(`--accent: ${c.accent}`);
    if (c.export) vars.push(`--green: ${c.export}`);
    if (c.consumption) vars.push(`--amber: ${c.consumption}`);
    let out = vars.length ? `:root { ${vars.join("; ")}; }\n` : "";
    if (c.page) out += `.stApp, body { background: ${p.PAGE} !important; }\n`;
    if (c.production) out += `.flow .arrow, .fc-day .bar span { background: ${c.production} !important; }\n`;
    return out;
  }

  function apply(p, colors) {
    let el = document.getElementById("solari-colors");
    if (!el) {
      el = document.createElement("style");
      el.id = "solari-colors";
      document.head.appendChild(el);
    }
    el.textContent = css(p, colors);
  }

  // Paleta prema spremljenim postavkama ("" = boje teme)
  const paletteKey = (theme, palette) => (PALETTES[palette] ? palette : theme === "light" ? "light" : "dark");
  const colorsOf = (key) => (PALETTES[key] || PALETTES.dark).colors;
  const themeOf = (key) => (PALETTES[key] || PALETTES.dark).theme;

  // Kartice paleta u postavkama (Windows i Android): input name="palette", sličica s bojama palete
  function renderChoices(box, selected) {
    box.querySelectorAll("[data-palette]").forEach((label) => {
      const key = label.dataset.palette, c = { ...defaults(themeOf(key)), ...colorsOf(key) };
      const sw = label.querySelector(".swatch");
      // minijatura dashboarda: pozadina, kartica s naslovom, krivulja proizvodnje, isprekidana potrošnja, naglasak
      sw.style.background = c.page;
      sw.innerHTML = `<svg viewBox="0 0 120 60" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
        <rect x="6" y="6" width="108" height="48" rx="8" fill="${c.card}"/>
        <rect x="13" y="13" width="36" height="4.5" rx="2.2" fill="${c.text}" opacity=".9"/>
        <rect x="13" y="21" width="22" height="3.5" rx="1.7" fill="${c.text}" opacity=".45"/>
        <rect x="88" y="12" width="19" height="7" rx="3.5" fill="${c.accent}"/>
        <path d="M13 48 C26 48 32 30 47 29 S70 35 80 31 S99 30 107 48 Z" fill="${c.production}" opacity=".3"/>
        <path d="M13 48 C26 48 32 30 47 29 S70 35 80 31 S99 30 107 48" fill="none" stroke="${c.production}" stroke-width="2.2" stroke-linecap="round"/>
        <path d="M13 40 C40 42 72 37 107 41" fill="none" stroke="${c.consumption}" stroke-width="1.7" stroke-dasharray="3.5 2.5" stroke-linecap="round"/>
      </svg>`;
      label.querySelector("input").checked = key === selected;
    });
  }

  return { KEYS, PALETTES, clean, defaults, palette, css, apply, mix, paletteKey, colorsOf, themeOf, renderChoices };
})();
