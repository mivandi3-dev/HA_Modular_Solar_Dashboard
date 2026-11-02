// Widgeti – prijenos solar/widgets/{production,visitors,sky}.py. Svaki vraća jedan od oblika:
//   { html }                      obična kartica
//   { chart: { header, figure } } kartica s Plotly grafikonom
//   { flow: { base, overlay } }   tok energije (statični sloj + vrijednosti)
"use strict";

const Widgets = (() => {
  const { esc, fmt, energy, mass, delta, statusDot, tint } = UI;
  const CARD_HEADER_H = 100;
  const TREE_KG_CO2_PER_YEAR = 22, CAR_KG_CO2_PER_KM = 0.12;
  const HOUSEHOLD_KWH_PER_DAY = 3500 / 365, PHONE_CHARGE_KWH = 0.015, EV_KWH_PER_KM = 0.17, LED_KWH_PER_HOUR = 0.009;
  const PERIOD_LABELS = { today: "danas", month: "ovaj mjesec", year: "ove godine", total: "od puštanja u rad" };
  const PERFORMANCE_RATIO = 0.8, MJ_PER_KWH = 3.6;
  const FACT_SECONDS = 12;
  const FACTS = [
    "Sunce u jednom satu na Zemlju pošalje više energije nego što cijelo čovječanstvo potroši u godini dana.",
    "Svjetlost sa Sunca do nas putuje oko 8 minuta i 20 sekundi.",
    "Solarni paneli rade i po oblačnom danu – tada proizvode otprilike 10 do 25 % uobičajene snage.",
    "Paneli najbolje rade kad su hladni: po vrućini im se učinkovitost malo smanji.",
    "Solarni paneli nemaju pokretnih dijelova, pa traju 25 do 30 godina i više.",
    "Hrvatska ima oko 2.000 do 2.700 sunčanih sati godišnje – među najvišima u Europi.",
    "Prva solarna ćelija napravljena je 1883. godine; imala je učinkovitost oko 1 %.",
    "Današnji paneli pretvaraju u struju oko 20 do 23 % sunčeve svjetlosti koja na njih padne.",
    "Energija utrošena za izradu panela vrati se proizvodnjom za otprilike 1 do 3 godine.",
    "Svemirske letjelice i Međunarodna svemirska postaja napajaju se sunčevom energijom.",
    "Najviše struje elektrana proizvodi oko podneva, kad je sunce najviše na nebu.",
    "Svaki kWh sa sunca znači manje izgaranja fosilnih goriva i čišći zrak u gradu.",
  ];

  const thin = (values, n = 60) => values.filter((_, i) => i % Math.max(1, Math.floor(values.length / n)) === 0);
  const sum = (a) => a.reduce((x, y) => x + y, 0);
  const pctChange = (cur, prev) => (prev > 0 ? (cur / prev - 1) * 100 : null);
  const card = (h, inner, cls = "") => `<div class="card ${cls}" style="--h:${h}px">${inner}</div>`;
  const noData = (title, h, msg) =>  card(h, `<div class="card-title">${title}</div><div class="empty">${msg}</div>`);
  const dur = (sec) => { const m = Math.floor(sec / 60); return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`; };
  const forecastDays = (ctx) => ([2, 3, 5].includes(Number(ctx.settings.forecast_days)) ? Number(ctx.settings.forecast_days) : 5);
  const dayName = (i, d) => ([T("Danas"), T("Sutra")][i] || fmtDate("{weekday}", d).replace(/^./, (c) => c.toUpperCase()));
  const peakOf = (ctx) => ctx.curve.reduce((best, p) => (p.kw > (best ? best.kw : 0) ? p : best), null);

  // ---------------------------------------------------------------- pokazatelji
  function kpi(ctx, key, spark) {
    const s = ctx.settings, rt = ctx.rt, factor = s.co2_factor;
    const bars = ctx.lastDays(14).map((d) => d.kwh);
    let item;
    if (key === "power") {
      let value, sub;
      if (ctx.stale) {
        const u = rt.updated_at ? new Date(rt.updated_at * 1000) : null;
        const last = u ? T(" · zadnje {time}", { time: `${fmtDate("day_month", u)} ${UI.hhmm(u)}` }) : "";
        [value, sub] = ["—", `<span class="warn">${Icons.get("warning")} ${T("{device} nedostupan", { device: ctx.device })}${last}</span>`];
      } else {
        value = fmt(ctx.power, ctx.power < 100 ? 2 : 1);
        sub = statusDot(rt.running) + T("Uživo · {pct} % instalirane snage", { pct: fmt(ctx.loadPct, 0) });
      }
      item = { icon: UI.panelIcon(), tint: tint("blue"), label: T("Trenutna snaga"), value, unit: "kW", sub, spark: thin(ctx.curve.map((p) => p.kw)) };
    } else if (key === "today") {
      const [v, u] = energy(rt.day_kwh), peak = peakOf(ctx);
      item = { icon: Icons.get("sun_cloud"), tint: tint("amber"), label: T("Proizvodnja danas"), value: v, unit: u,
        sub: peak ? T("vrh {kw} kW u {time}", { kw: fmt(peak.kw, 1), time: UI.hhmm(peak.t) }) : T("danas još nema proizvodnje"), spark: thin(ctx.curve.map((p) => p.kw)) };
    } else if (key === "month") {
      const [v, u] = energy(rt.month_kwh);
      item = { icon: Icons.get("sun"), tint: tint("amber"), label: T("Proizvodnja ovaj mjesec"), value: v, unit: u, sub: delta(ctx.monthDelta) || T("od početka mjeseca"), spark: bars };
    } else if (key === "co2") {
      const [v, u] = mass(rt.month_kwh * factor);
      const monthStart = new Date(ctx.today.getFullYear(), ctx.today.getMonth(), 1);
      let acc = 0;
      const cum = ctx.daily.filter((d) => d.date >= monthStart).map((d) => (acc += d.kwh * factor));
      item = { icon: Icons.get("globe"), tint: tint("sky"), label: T("Manje CO₂ ovaj mjesec"), value: v, unit: u,
        sub: delta(ctx.monthDelta) || T("{factor} kg CO₂ po kWh", { factor: fmt(factor, 2) }), spark: cum };
    } else if (key === "year") {
      const [thisY, lastY] = ctx.year, [v, u] = energy(thisY);
      item = { icon: Icons.get("calendar_year"), tint: tint("green"), label: T("Proizvodnja {year}.", { year: ctx.today.getFullYear() }), value: v, unit: u,
        sub: delta(pctChange(thisY, lastY), T("u odnosu na isto razdoblje lani")) || T("od 1. siječnja"), spark: ctx.monthly.slice(-12).map((m) => m.kwh) };
    } else if (key === "total") {
      const [v, u] = energy(rt.total_kwh);
      let acc = 0;
      item = { icon: Icons.get("bolt"), tint: tint("green"), label: T("Ukupno proizvedeno"), value: v, unit: u, sub: T("od puštanja u rad {date}", { date: esc(s.commissioned) }),
        spark: bars.map((b) => (acc += b)) };
    } else if (key === "grid") {
      const load = rt.load_kw, loads = ctx.curve.map((p) => p.load).filter((v) => v != null);
      let value = "—", sub = meterMissing(s);
      if (load != null && !ctx.stale) {
        value = fmt(load, 2);
        sub = statusDot(true) + T("Uživo s mjerača") + (loads.length ? T(" · danas najviše {kw} kW", { kw: fmt(Math.max(...loads), 1) }) : "");
      }
      item = { icon: Icons.get("plug"), tint: tint("amber"), label: T("Potrošnja iz mreže"), value, unit: "kW", sub, spark: thin(loads) };
    } else {
      const load = rt.load_kw;
      let value = "—", sub = meterMissing(s);
      if (load != null && !ctx.stale) {
        // Mjerač daje potrošnju zgrade (neovisno o elektrani) – kao u toku energije (solar/energy.py).
        const share = load > 0 ? Math.min(ctx.power, load) / load * 100 : ctx.power > 0 ? 100 : 0;
        value = fmt(share, 0);
        sub = T("struje zgrade sada daje sunce · zgrada troši {kw} kW", { kw: fmt(load, 1) });
      }
      item = { icon: Icons.get("home"), tint: tint("green"), label: T("Udio sunca u potrošnji"), value, unit: value !== "—" ? "%" : "", sub, spark: null };
    }
    item.color = UI.theme().BRAND_GREEN;
    if (!spark) item.spark = null;
    return item;
  }
  const meterMissing = (s) => (s.meter_unit_id ? T("mjerač nedostupan") : T("potreban je mjerač potrošnje (Postavke → Mreža)"));
  const tile = (key) => (ctx, p, h) => ({ html: UI.kpiStrip([kpi(ctx, key, p.w >= 3)], h) });

  // ---------------------------------------------------------------- grafikoni i kartice proizvodnje
  function todayCurve(ctx, p, h) {
    const [v, u] = energy(ctx.rt.day_kwh);
    const header = UI.cardHeader(T("Proizvodnja danas"), v, u, "", T("Snaga, prosjek 5 min (kW)"));
    if (!ctx.curve.length) return { chart: { header: header + UI.empty(T("Za danas još nema podataka.")), figure: null } };
    return { chart: { header, figure: Charts.dailyCurve(ctx.curve, ctx.today, ctx.settings.peak_power_kwp, h - CARD_HEADER_H) } };
  }

  function bars(ctx, p, h) {
    const days = Number(p.options.days || 14), daily = ctx.lastDays(days);
    const title = T("Proizvodnja zadnjih {n} dana", { n: days });
    if (!daily.length) return { chart: { header: UI.cardHeader(title) + UI.empty(T("Nema podataka.")), figure: null } };
    const past = daily.filter((d) => d.date.getTime() !== ctx.today.getTime()).map((d) => d.kwh);
    const [v, u] = energy(sum(daily.map((d) => d.kwh)));
    const avg = past.length ? T("prosjek {kwh} kWh/dan", { kwh: fmt(sum(past) / past.length, 0) }) : "";
    return { chart: { header: UI.cardHeader(title, v, u, avg), figure: Charts.dailyBars(daily, ctx.today, h - CARD_HEADER_H) } };
  }

  function monthly(ctx, p, h) {
    const n = Number(p.options.months || 12), months = ctx.monthly.slice(-n);
    const title = T("Proizvodnja zadnjih {n} mjeseci", { n }), total = sum(months.map((m) => m.kwh));
    if (!(total > 0)) return { chart: { header: UI.cardHeader(title) + UI.empty(T("Nema podataka.")), figure: null } };
    const producing = months.filter((m) => m.kwh > 0).map((m) => m.kwh);
    const [v, u] = energy(total);
    return { chart: { header: UI.cardHeader(title, v, u, T("prosjek {mwh} MWh/mjesec", { mwh: fmt(sum(producing) / producing.length / 1000, 1) })),
      figure: Charts.monthlyBars(months, ctx.today, h - CARD_HEADER_H) } };
  }

  function speedo(ctx, p, h) {
    const peak = peakOf(ctx);
    const sub = ctx.stale ? T("{device} nedostupan", { device: ctx.device }) : T("{pct} % instalirane snage", { pct: fmt(ctx.loadPct, 0) });
    return { html: UI.speedometerCard(T("Trenutna proizvodnja"), ctx.stale ? null : ctx.power, ctx.settings.speedo_max_kw, sub,
      peak ? `${fmt(peak.kw, 1)} kW` : "—", T("uživo"), h) };
  }

  function todayGoal(ctx, p, h) {
    const th = UI.theme();
    const past = ctx.lastDays(15).filter((d) => d.date.getTime() !== ctx.today.getTime()).map((d) => d.kwh);
    const avg = past.length ? sum(past) / past.length : 0, today = ctx.rt.day_kwh, pct = avg > 0 ? today / avg * 100 : 0;
    const r = 52, stroke = 13, circ = 2 * Math.PI * r, arc = Math.min(pct, 100) / 100 * circ;
    const sunset = ctx.wx && ctx.wx.days[0] && ctx.wx.days[0].sunset ? new Date(ctx.wx.days[0].sunset) : null;
    const afterSunset = ctx.now.getHours() >= 17 || (sunset && ctx.now > sunset);
    const verdict = pct >= 100 ? T("Iznadprosječan dan! ☀️") : !afterSunset ? T("Dan još traje") : T("Oblačniji dan od prosjeka");
    return { html: card(h, `<div class="card-title">${T("Danas prema prosjeku")}<small>${T("zadnjih 14 dana")}</small></div><div class="goal-body">
      <svg viewBox="0 0 140 140" class="ring"><circle cx="70" cy="70" r="${r}" fill="none" stroke="${th.TRACK}" stroke-width="${stroke}"/>
      <circle cx="70" cy="70" r="${r}" fill="none" stroke="${th.BRAND_GREEN}" stroke-width="${stroke}" stroke-linecap="round"
        stroke-dasharray="${arc.toFixed(1)} ${circ.toFixed(1)}" transform="rotate(-90 70 70)"/>
      <text x="70" y="70" text-anchor="middle" dominant-baseline="central" font-size="27" font-weight="700" fill="${th.TEXT}">${fmt(pct, 0)}%</text></svg>
      <div class="goal-text"><div class="k">${T("Danas")}</div><div class="v">${fmt(today, 1)}<small>kWh</small></div>
      <div class="k">${T("Prosječan dan")}</div><div class="v">${fmt(avg, 0)}<small>kWh</small></div><div class="verdict">${verdict}</div></div></div>`, "goal") };
  }

  function flowNodes(ctx) {
    const rt = ctx.rt, stale = ctx.stale;
    const nodes = [{ pos: "tl", icon: UI.panelIcon(), label: T("Solarna proizvodnja"), value: stale ? "—" : `${fmt(ctx.power, 2)} kW` },
      { pos: "bl", icon: Icons.get("bolt"), label: T("Ukupna potrošnja el. energije"), value: stale || rt.load_kw == null ? "—" : `${fmt(rt.load_kw, 2)} kW` }];
    if (rt.load_kw != null && !stale) {
      // očitanje mjerača umanjeno za proizvodnju; negativna razlika = višak u mrežu
      const net = rt.load_kw - ctx.power;
      const [label, icon] = net >= 0 ? [T("Trenutna potrošnja električne energije"), Icons.get("building")] : [T("Predaja u mrežu"), Icons.get("tower")];
      nodes.push({ pos: "tr", icon, label, value: `${fmt(Math.abs(net), 2)} kW`, reverse: net < 0 });
    } else {
      const [v, u] = energy(rt.month_kwh);
      nodes.push({ pos: "tr", icon: Icons.get("chart"), label: T("Proizvedeno ovaj mjesec"), value: `${v} ${u}` });
    }
    const [cv, cu] = mass(rt.day_kwh * ctx.settings.co2_factor);
    nodes.push({ pos: "br", icon: Icons.get("sprout"), label: T("Manje CO₂ danas"), value: `${cv} ${cu}` });
    return nodes;
  }
  const flow = (ctx, p, h) => ({ flow: { nodes: flowNodes(ctx), live: Boolean(ctx.rt.running), height: h } });

  function records(ctx, p, h) {
    const rec = ctx.records || {}, items = [];
    if (rec.best_day) {
      const d = parseDate(rec.best_day[0]), [v, u] = energy(rec.best_day[1]);
      items.push({ icon: Icons.get("trophy"), tint: tint("amber"), label: T("Najbolji dan · {date}", { date: fmtDate("date_text", d) }), value: v, unit: u });
    }
    if (rec.best_month) {
      const m = parseDate(rec.best_month[0]), [v, u] = energy(rec.best_month[1]);
      items.push({ icon: Icons.get("calendar"), tint: tint("green"), label: T("Najbolji mjesec · {month}", { month: fmtDate("month_year", m) }), value: v, unit: u });
    }
    if (rec.peak_power) {
      const t = new Date(rec.peak_power[0] * 1000);
      items.push({ icon: Icons.get("bolt"), tint: tint("blue"), label: T("Najveća snaga · {date}", { date: `${fmtDate("date", t)} ${UI.hhmm(t)}` }), value: fmt(rec.peak_power[1], 1), unit: "kW" });
    }
    if (rec.producing_days && p.h >= 3) items.push({ icon: Icons.get("sun"), tint: tint("sky"), label: T("Dana s proizvodnjom"), value: fmt(rec.producing_days, 0), unit: T("dana") });
    if (!items.length) return { html: noData(T("Rekordi elektrane"), h, T("Još nema dovoljno podataka.")) };
    const first = rec.first_day ? parseDate(rec.first_day) : null;
    const right = first ? T("od {date}", { date: fmtDate("date", first) }) : "";
    return { html: UI.listCard(T("Rekordi elektrane"), items, right, h) };
  }

  // ---------------------------------------------------------------- za posjetitelje
  function environment(ctx, p, h) {
    const co2 = ctx.rt.total_kwh * ctx.settings.co2_factor, [mv, mu] = mass(co2);
    return { html: UI.listCard(T("Utjecaj na okoliš"), [
      { icon: Icons.get("tree"), tint: tint("green"), label: T("Posađena stabla"), value: fmt(co2 / TREE_KG_CO2_PER_YEAR, 0), unit: T("stabala") },
      { icon: Icons.get("globe"), tint: tint("sky"), label: T("Smanjena emisija CO₂"), value: mv, unit: mu },
      { icon: Icons.get("car"), tint: tint("amber"), label: T("Ušteda u kilometrima"), value: fmt(co2 / CAR_KG_CO2_PER_KM, 0), unit: "km" },
    ], T("od puštanja u rad {date}", { date: esc(ctx.settings.commissioned) }), h) };
  }

  const compact = (x) => (x >= 1e6 ? [fmt(x / 1e6, 1), T("mil.")] : x >= 1e4 ? [fmt(x / 1e3, 1), T("tis.")] : [fmt(x, 0), ""]);
  function equivalents(ctx, p, h) {
    const period = p.options.period || "month", kwh = ctx.periodKwh(period);
    const cells = [[Icons.get("home"), HOUSEHOLD_KWH_PER_DAY, T("dana opskrbe prosječnog kućanstva")], [Icons.get("phone"), PHONE_CHARGE_KWH, T("punjenja mobitela")],
      [Icons.get("ecar"), EV_KWH_PER_KM, T("km električnim automobilom")], [Icons.get("bulb"), LED_KWH_PER_HOUR, T("sati rada LED žarulje")]];
    const tiles = cells.map(([icon, per, label]) => { const [v, u] = compact(kwh / per);
      return `<div class="eq"><div class="i">${icon}</div><div><div class="v">${v}<small>${u}</small></div><div class="k">${esc(label)}</div></div></div>`; }).join("");
    const [ev, eu] = energy(kwh);
    return { html: card(h, `<div class="card-title">${T("Što smo proizveli")}<small>${ev} ${eu} · ${T(PERIOD_LABELS[period] || "")}</small></div><div class="eq-grid">${tiles}</div>`) };
  }

  function facts(ctx, p, h) {
    const n = FACTS.length, share = 100 / n;
    const keyframes = `@keyframes fact-cycle { 0% { opacity: 0; transform: translateY(6px); } ${(share * .08).toFixed(2)}% { opacity: 1; transform: none; } `
      + `${(share * .92).toFixed(2)}% { opacity: 1; transform: none; } ${share.toFixed(2)}% { opacity: 0; transform: translateY(-6px); } 100% { opacity: 0; } }`;
    const items = FACTS.map((f, i) => `<p class="fun-fact" style="animation: fact-cycle ${n * FACT_SECONDS}s linear ${i * FACT_SECONDS}s infinite">${esc(T(f))}</p>`).join("");
    return { html: card(h, `<style>${keyframes}</style><div class="card-title"><span>${Icons.get("bulb")} ${T("Znate li?")}</span><small>${T("zanimljivosti o sunčevoj energiji")}</small></div><div class="facts-body">${items}</div>`, "facts") };
  }

  const clock = (ctx, p, h) => ({ html: card(h, `<div class="time live-clock"></div><div class="date">${UI.dateHr(ctx.today)}</div>`, "clock-w") });
  const message = (ctx, p, h) => ({ html: card(h, `<div class="m-title">${esc(T(p.options.title))}</div><div class="m-text">${esc(T(p.options.text))}</div>`, "message") });

  // ---------------------------------------------------------------- vrijeme i sunce
  function sun(ctx, p, h) {
    const day = ctx.wx && ctx.wx.days[0];
    if (!day || !day.sunrise || !day.sunset) return { html: noData(T("Sunce danas"), h, T("Prognoza trenutno nije dostupna.")) };
    const th = UI.theme(), rise = new Date(day.sunrise), set = new Date(day.sunset), now = ctx.now;
    const f = (now - rise) / (set - rise), up = f >= 0 && f <= 1, ang = Math.PI * (1 - Math.min(Math.max(f, 0), 1));
    const x = 150 + 128 * Math.cos(ang), y = 128 - 104 * Math.sin(ang);
    const state = now < rise ? T("Izlazak za {time}", { time: dur((rise - now) / 1000) }) : now > set ? T("Sunce je zašlo – laku noć 🌙") : T("Do zalaska još {time}", { time: dur((set - now) / 1000) });
    const done = up ? `<path d="M22,128 A128,104 0 0 1 ${x.toFixed(1)},${y.toFixed(1)}" fill="none" stroke="${th.SUN}" stroke-width="3"/>` : "";
    const dot = up ? `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="13" fill="${th.SUN}" filter="url(#sun-glow)"/>` : "";
    return { html: card(h, `<div class="card-title">${T("Sunce danas")}<small>${esc(state)}</small></div><div class="sun-body">
      <svg viewBox="0 0 300 150" class="sun-arc"><defs><filter id="sun-glow" x="-1" y="-1" width="3" height="3"><feGaussianBlur stdDeviation="4" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
      <path d="M22,128 A128,104 0 0 1 278,128" fill="none" stroke="${th.MUTED}" stroke-opacity=".45" stroke-width="2" stroke-dasharray="4 6"/>${done}${dot}
      <line x1="6" y1="128" x2="294" y2="128" stroke="${th.MUTED}" stroke-opacity=".35"/>
      <text x="22" y="146" text-anchor="middle" font-size="12" fill="${th.MUTED}">${UI.hhmm(rise)}</text>
      <text x="278" y="146" text-anchor="middle" font-size="12" fill="${th.MUTED}">${UI.hhmm(set)}</text></svg>
      <div class="sun-facts"><div><span>${Icons.get("sunrise")} ${T("Izlazak")}</span><b>${UI.hhmm(rise)}</b></div><div><span>${Icons.get("sunset")} ${T("Zalazak")}</span><b>${UI.hhmm(set)}</b></div>
      <div><span>${T("Duljina dana")}</span><b>${dur((set - rise) / 1000)}</b></div><div><span>${T("Sunčanih sati")}</span><b>${fmt(day.sunshine_h || 0, 1)} h</b></div>
      <div><span>${T("UV indeks")}</span><b>${day.uv != null ? fmt(day.uv, 0) : "—"}</b></div></div></div>`, "sun-w") };
  }

  // Ušteda: vlastita potrošnja po cijeni iz mreže, višak po otkupnoj cijeni (izračun u src/data.cpp).
  function money(value, cur) {
    if (value >= 100000) return [fmt(value / 1000, 1), `${T("tis.")} ${cur}`];
    return [fmt(value, value < 1000 ? 2 : 0), cur];
  }
  function savings(ctx, p, h) {
    const sv = ctx.savings, s = ctx.settings, cur = s.currency || "€";
    if (!sv || sv.today == null) return { html: noData(T("Ušteda"), h, T("Još nema dovoljno podataka.")) };
    const rows = [[Icons.get("sun"), "amber", T("Danas"), sv.today], [Icons.get("calendar"), "green", T("Ovaj mjesec"), sv.month], [Icons.get("calendar_year"), "sky", T("Ove godine"), sv.year]];
    if (p.h >= 3) rows.push([Icons.get("money"), "blue", T("Ukupno od {date}", { date: fmtDate("date", parseDate(sv.first_day)) }), sv.total]);
    const items = rows.map(([icon, t, label, value]) => { const [v, u] = money(value, cur); return { icon, tint: tint(t), label, value: v, unit: u }; });
    const right = sv.metered && p.w >= 4
      ? T("{price} {cur}/kWh · višak {feed} {cur}/kWh", { price: fmt(s.price_kwh, 2), feed: fmt(s.feedin_price_kwh, 2), cur })
      : T("{price} {cur}/kWh", { price: fmt(s.price_kwh, 2), cur });
    return { html: UI.listCard(T("Ušteda"), items, esc(right), h) };
  }

  // Stvarno i prognoza: očekivana snaga po satima iz zračenja (sat koji završava u navedeno vrijeme).
  function expectedCurve(ctx) {
    const hourly = (ctx.wx && ctx.wx.hourly) || [], kwp = ctx.settings.peak_power_kwp, out = [];
    for (const [ts, rad] of hourly) {
      const mid = new Date(new Date(ts).getTime() - 1800e3);
      if (mid.toDateString() === ctx.today.toDateString()) out.push({ t: mid, kw: Math.max(rad || 0, 0) / 1000 * kwp * PERFORMANCE_RATIO });
    }
    return out;
  }
  function forecastCompare(ctx, p, h) {
    const title = T("Stvarno i prognoza"), curve = expectedCurve(ctx);
    if (!curve.length) return { html: noData(title, h, T("Prognoza trenutno nije dostupna.")) };
    const now = ctx.now.getTime();
    const expected = sum(curve.map((c) => c.kw * Math.min(Math.max((now - (c.t.getTime() - 1800e3)) / 3600e3, 0), 1)));
    const dayTotal = sum(curve.map((c) => c.kw)), actual = ctx.rt.day_kwh;
    let meta = "";
    if (expected >= 0.5) {
      const ratio = actual / expected * 100;
      meta = `<span class="${ratio >= 90 ? "up" : "down"}">${esc(T("{pct} % od očekivanog do sada", { pct: fmt(ratio, 0) }))}</span>`;
    }
    const [v, u] = energy(actual);
    const header = UI.cardHeader(title, v, u, meta, esc(T("očekivano danas ≈ {kwh} kWh", { kwh: fmt(dayTotal, 0) })));
    return { chart: { header, figure: Charts.forecastCompare(ctx.curve, curve, ctx.today, ctx.settings.peak_power_kwp, h - CARD_HEADER_H) } };
  }

  function forecastProduction(ctx, p, h) {
    if (!ctx.wx) return { html: noData(T("Očekivana proizvodnja"), h, T("Prognoza trenutno nije dostupna.")) };
    const days = ctx.wx.days.slice(0, 1 + forecastDays(ctx)), kwp = ctx.settings.peak_power_kwp;  // danas i sljedećih 2, 3 ili 5 dana
    const est = days.map((d) => (d.radiation_mj || 0) / MJ_PER_KWH * kwp * PERFORMANCE_RATIO), top = Math.max(1, ...est);
    const cols = days.map((d, i) => `<div class="fc-day"><div class="name">${i === 0 ? dayName(0, parseDate(d.date)) : fmtDate("{wd}", parseDate(d.date))}</div><div class="i">${Weather.describe(d.code).icon}</div>
      <div class="bar"><span style="height:${(est[i] / top * 100).toFixed(0)}%"></span></div><div class="v">${fmt(est[i], 0)}<small>kWh</small></div>
      <div class="so-far">${i === 0 ? T("dosad {kwh} kWh", { kwh: fmt(ctx.rt.day_kwh, 0) }) : "&nbsp;"}</div></div>`).join("");
    return { html: card(h, `<div class="card-title">${T("Očekivana proizvodnja")}<small>${T("procjena iz prognoze zračenja")}</small></div><div class="fc-grid" style="--n:${days.length}">${cols}</div>`) };
  }

  function weather(ctx, p, h) {
    const wx = ctx.wx;
    if (!wx) return { html: noData(T("Vremenska prognoza"), h, T("Prognoza trenutno nije dostupna.")) };
    const rows = wx.days.slice(0, p.h <= 1 ? Math.min(3, 1 + forecastDays(ctx)) : 1 + forecastDays(ctx)).map((d, i) => { const w = Weather.describe(d.code);
      return `<div class="wx-row"><span class="name">${dayName(i, parseDate(d.date))}</span><span class="i">${w.icon}</span><span class="label">${esc(w.label)}</span>`
        + `<b>${Math.round(d.tmax)}°</b><span class="muted">${Math.round(d.tmin)}°</span><span class="muted">${Icons.get("drop")} ${Math.round(d.rain_pct || 0)} %</span>`
        + `<span class="muted">UV ${fmt(d.uv || 0, 0)}</span></div>`; }).join("");
    const now = Weather.describe(wx.code, wx.is_day);
    return { html: card(h, `<div class="card-title">${T("Vremenska prognoza")}<small>${esc(T("sada {temp} °C · {label}", { temp: fmt(wx.temperature, 0), label: now.label.toLowerCase() }))}</small></div><div class="wx-list">${rows}</div>`) };
  }

  function status(ctx, p, h) {
    const rt = ctx.rt, ok = !ctx.stale, u = rt.updated_at ? new Date(rt.updated_at * 1000) : null;
    const age = u ? (ctx.now - u) / 1000 : null, pad = (n) => String(n).padStart(2, "0");
    const rows = [[ctx.device, `${statusDot(ok)}${ok ? T("povezan") : T("nedostupan")}`],
      [T("Zadnje očitanje"), u ? (age < 3600 ? T("{time} (prije {s} s)", { time: `${UI.hhmm(u)}:${pad(u.getSeconds())}`, s: Math.round(age) }) : `${fmtDate("day_month", u)} ${UI.hhmm(u)}`) : "—"],
      [T("Podaci danas"), rt.availability != null ? `${fmt(rt.availability, 0)} %` : "—"],
      [T("Faktor snage"), rt.pf != null ? fmt(rt.pf, 2) : "—"],
      [T("Mjerač potrošnje"), rt.load_kw != null ? `${fmt(rt.load_kw, 1)} kW` : ctx.settings.meter_unit_id ? T("nedostupan") : T("nije postavljen")]];
    return { html: card(h, `<div class="card-title">${T("Stanje sustava")}<small>${esc(ctx.settings.modbus_host)}</small></div><div class="status-list">`
      + rows.map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("") + "</div>") };
  }

  // ---------------------------------------------------------------- widgeti uređaja (rt.extra, poller)
  const extra = (ctx) => ctx.rt.extra || {};

  function battery(ctx, p, h) {
    const x = extra(ctx);
    if (x.battery_soc == null) return { html: noData(T("Baterija"), h, T("Uređaj trenutno ne javlja stanje baterije.")) };
    const th = UI.theme(), soc = Math.max(0, Math.min(100, x.battery_soc));
    const color = soc < 20 ? th.RED : soc < 50 ? th.AMBER : th.GREEN;
    const size = Math.max(90, Math.min(h - 60, 150)), r = size / 2 - 9, c = 2 * Math.PI * r;
    const ring = `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">`
      + `<circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${th.TRACK}" stroke-width="12"/>`
      + `<circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="12" stroke-linecap="round"`
      + ` stroke-dasharray="${(c * soc / 100).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 ${size / 2} ${size / 2})"/>`
      + (Icons.theme() !== "classic"  // neon/iconset: ugniježđeni SVG u sredini prstena; klasično: emoji kao tekst
        ? `<svg x="${size * 0.36}" y="${size * 0.36}" width="${size * 0.28}" height="${size * 0.28}" viewBox="0 0 24 24" class="nx-ico">${Icons.svgInner("battery")}</svg></svg>`
        : `<text x="50%" y="54%" text-anchor="middle" font-size="${size / 5}" fill="${th.TEXT}">🔋</text></svg>`);
    let state = "", cls = "";
    if (x.battery_kw != null) {
      const kw = x.battery_kw, abs = fmt(Math.abs(kw), 2);
      if (!x.battery_dir) state = T("snaga baterije {kw} kW", { kw: abs });
      else if (kw > 0.02) [state, cls] = [`▲ ${T("puni se {kw} kW", { kw: abs })}`, "charge"];
      else if (kw < -0.02) [state, cls] = [`▼ ${T("prazni se {kw} kW", { kw: abs })}`, "discharge"];
      else state = T("miruje");
    }
    return { html: card(h, `<div class="card-title">${T("Baterija")}<small>${T("uživo")}</small></div>`
      + `<div class="dev-battery">${ring}<div><div class="big">${fmt(soc, 0)}<small>%</small></div>`
      + `<div class="dev-state ${cls}">${esc(state)}</div>${batteryVolt(x)}</div></div>`) };
  }

  // napon baterije i nazivni napon sustava (12 / 24 / 48 V) – off-grid sustavi
  function batteryVolt(x) {
    if (x.battery_v == null) return "";
    const v = x.battery_v, nominal = v < 8 ? 0 : v < 17 ? 12 : v < 34 ? 24 : v < 68 ? 48 : 0;
    return `<div class="dev-volt">${fmt(v, 1)} V${nominal ? ` · ${T("sustav {v} V", { v: nominal })}` : ""}</div>`;
  }

  // Off-grid sustav: potrošnja na izlazu izmjenjivača, napon i frekvencija izlaza, opterećenje, baterija
  function offgrid(ctx, p, h) {
    const x = extra(ctx);
    if (x.ac_load_kw == null && x.battery_v == null) return { html: noData(T("Off-grid sustav"), h, T("Uređaj trenutno ne javlja podatke izmjenjivača.")) };
    const th = UI.theme(), pct = x.load_pct;
    const cell = (k, v, unit, d) => `<div><div class="k">${esc(k)}</div><div class="v">${v == null ? "—" : fmt(v, d)}<small>${unit}</small></div></div>`;
    const bar = pct == null ? "" : `<div class="dev-bar"><span style="width:${Math.max(2, Math.min(100, pct))}%;background:${pct > 85 ? th.RED : pct > 60 ? th.AMBER : th.GREEN}"></span></div>`;
    return { html: card(h, `<div class="card-title">${T("Off-grid sustav")}<small>${T("izlaz izmjenjivača")}</small></div>`
      + `<div class="dev-big">${x.ac_load_kw == null ? "—" : fmt(x.ac_load_kw, 2)}<small>kW</small></div>`
      + `<div class="dev-grid">${cell(T("Izlaz"), x.ac_out_v, "V", 0)}${cell(T("Frekvencija"), x.ac_out_hz, "Hz", 1)}`
      + `${cell(T("Opterećenje"), pct, "%", 0)}${cell(T("Baterija"), x.battery_v, "V", 1)}</div>${bar}`) };
  }

  function inverterTemp(ctx, p, h) {
    const t = extra(ctx).inverter_temp;
    if (t == null) return { html: noData(T("Temperatura invertera"), h, T("Uređaj trenutno ne javlja temperaturu.")) };
    const th = UI.theme(), [color, cls, label] = t < 50 ? [th.GREEN, "dev-ok", T("normalna")] : t < 65 ? [th.AMBER, "dev-warn", T("povišena")]
      : [th.RED, "dev-bad", T("visoka")];
    const pct = Math.max(4, Math.min(100, t / 80 * 100));
    return { html: card(h, `<div class="card-title">${T("Temperatura invertera")}<small class="${cls}">${esc(label)}</small></div>`
      + `<div class="dev-temp"><div class="big">${fmt(t, 1)}<small>°C</small></div>`
      + `<div class="bar"><i style="width:${pct.toFixed(0)}%;background:${color}"></i></div></div>`) };
  }

  function gridQuality(ctx, p, h) {
    const x = extra(ctx);
    if (x.grid_v == null && x.grid_hz == null) return { html: noData(T("Mreža"), h, T("Uređaj trenutno ne javlja napon i frekvenciju mreže.")) };
    // granice: 230 V ± 10 %, 50 Hz ± 0,2 Hz (uobičajeno u EU)
    const vOk = x.grid_v == null || (x.grid_v >= 207 && x.grid_v <= 253), fOk = x.grid_hz == null || Math.abs(x.grid_hz - 50) <= 0.2;
    const cell = (k, v, unit, ok, d) => `<div><div class="k">${esc(k)}</div><div class="v ${ok ? "" : "dev-warn"}">${v == null ? "—" : fmt(v, d)}<small>${unit}</small></div></div>`;
    return { html: card(h, `<div class="card-title">${T("Mreža")}<small class="${vOk && fOk ? "dev-ok" : "dev-warn"}">`
      + `${esc(vOk && fOk ? T("u granicama") : T("izvan uobičajenih granica"))}</small></div>`
      + `<div class="dev-grid">${cell(T("Napon"), x.grid_v, "V", vOk, 1)}${cell(T("Frekvencija"), x.grid_hz, "Hz", fOk, 2)}</div>`) };
  }

  const kpiStrip = (ctx, p, h) => ({ html: UI.kpiStrip(["power", "month", "co2", "total"].map((k) => kpi(ctx, k, p.w >= 10)), h) });

  return {
    kpi_strip: kpiStrip, tile_power: tile("power"), tile_today: tile("today"), tile_month: tile("month"), tile_year: tile("year"),
    tile_total: tile("total"), tile_co2: tile("co2"), tile_grid: tile("grid"), tile_selfuse: tile("selfuse"), today_curve: todayCurve, bars, monthly, speedo,
    today_goal: todayGoal, flow, records, environment, equivalents, facts, clock, message, sun, forecast_production: forecastProduction,
    weather, status, savings, forecast_compare: forecastCompare,
    battery, inverter_temp: inverterTemp, grid_quality: gridQuality, offgrid,
  };
})();
