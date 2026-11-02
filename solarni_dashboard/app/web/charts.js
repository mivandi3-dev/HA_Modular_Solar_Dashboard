// Plotly grafikoni – prijenos solar/charts.py (iste postavke, boje prate temu).
"use strict";

const Charts = (() => {
  const FONT = "'Plus Jakarta Sans', 'Segoe UI', sans-serif";
  const CONFIG = { staticPlot: true, displayModeBar: false, responsive: true };
  const pad = (n) => String(n).padStart(2, "0");
  const local = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;

  function layout(height) {
    const th = UI.theme();
    return {
      height, autosize: true,
      margin: { l: 4, r: 8, t: 8, b: 4 },
      font: { size: 13, family: FONT, color: th.MUTED },
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      separators: ((window.SOLARI_I18N || {}).meta || {}).decimal + ((window.SOLARI_I18N || {}).meta || {}).group,
      showlegend: false,
    };
  }
  const grid = () => ({ gridcolor: UI.theme().GRID, zeroline: false, linecolor: "rgba(0,0,0,0)", ticks: "", automargin: true });

  // Krivulja snage danas: os od punog sata prve do punog sata zadnje proizvodnje, oznaka vrha.
  function dailyCurve(points, day, peakKwp, height) {
    const th = UI.theme(), green = th.BRAND_GREEN;
    const x = points.map((p) => local(p.t)), y = points.map((p) => p.kw);
    const traces = [{
      x, y, type: "scatter", mode: "lines", name: T("Proizvodnja"),
      line: { color: green, width: 2.5, shape: "spline", smoothing: 0.8 }, fill: "tozeroy",
      fillgradient: { type: "vertical", colorscale: [[0, UI.rgba(green, 0)], [1, UI.rgba(green, th.AREA_ALPHA)]] },
    }];
    // Potrošnja s mjerača (iz mreže) – isprekidana jantarna linija, kao u Python verziji
    const loads = points.map((p) => (p.load == null ? null : p.load));
    const withLoad = loads.some((v) => v != null);
    if (withLoad) {
      traces.push({ x, y: loads, type: "scatter", mode: "lines", name: T("Potrošnja"), connectgaps: false,
        line: { color: th.LOAD, width: 2, shape: "spline", smoothing: 0.8, dash: "dot" } });
    }
    const annotations = [];
    const maxKw = y.length ? Math.max(...y) : 0;
    const top = Math.max(maxKw, ...loads.filter((v) => v != null));
    if (maxKw > 0) {
      const peak = points[y.indexOf(maxKw)];
      traces.push({ x: [local(peak.t)], y: [maxKw], type: "scatter", mode: "markers", showlegend: false, name: "vrh",
        marker: { size: 11, color: th.CARD_SOLID, line: { color: green, width: 3 } } });
      annotations.push({ x: local(peak.t), y: maxKw, yshift: 30, showarrow: false, align: "center",
        text: `<b>${UI.fmt(maxKw, 1)} kW</b><br><span style='font-size:11px;color:${th.MUTED}'>${UI.hhmm(peak.t)}</span>`,
        bgcolor: th.CARD_SOLID, bordercolor: th.GRID, borderpad: 6, font: { size: 13, color: th.TEXT } });
    }
    const producing = points.filter((p) => p.kw > 0).map((p) => p.t);
    let start, end;
    if (producing.length) {
      start = new Date(producing[0]); start.setMinutes(0, 0, 0);
      end = new Date(producing[producing.length - 1]);
      if (end.getMinutes() || end.getSeconds()) { end.setHours(end.getHours() + 1); end.setMinutes(0, 0, 0); }
      if (end - start < 3600e3) end = new Date(start.getTime() + 3600e3);
    } else {
      start = new Date(day); end = new Date(day.getTime() + 24 * 3600e3);
    }
    const spanH = (end - start) / 3600e3;
    const tickHours = spanH <= 6 ? 1 : spanH <= 14 ? 2 : 3;
    return {
      data: traces,
      layout: { ...layout(height), annotations, showlegend: withLoad,
        legend: { orientation: "h", yanchor: "bottom", y: 1.0, xanchor: "right", x: 1, bgcolor: "rgba(0,0,0,0)", font: { size: 12 } },
        xaxis: { ...grid(), showgrid: false, type: "date", range: [local(start), local(end)], tickformat: "%H:%M",
          tick0: local(day), dtick: tickHours * 3600 * 1000, ticklabelstandoff: 8 },
        yaxis: { ...grid(), rangemode: "tozero", range: [0, Math.max(peakKwp * 0.25, top * 1.45, 1)], nticks: 5, ticksuffix: " kW" } },
      config: CONFIG,
    };
  }

  // Uski ekran (Android mobitel): oznake vodoravno i svaka druga kad ih je puno – inače se zakreću i preklapaju
  const narrowAxis = (count) => (window.innerWidth < 700 ? { tickangle: 0, dtick: count > 8 ? 2 : 1, automargin: true } : {});

  // Stupci po danima; današnji (nepotpuni) dan blijeđe. Uz mjerač i potrošnja (jantarno), inače prosjek isprekidano.
  function dailyBars(days, today, height) {
    const th = UI.theme();
    const labels = days.map((d) => fmtDate("chart_day", d.date));
    const isToday = (d) => d.date.getTime() === today.getTime();
    const opacity = days.map((d) => (isToday(d) ? 0.4 : 1));
    const withLoad = days.some((d) => d.load != null);
    const past = days.filter((d) => !isToday(d)).map((d) => d.kwh);
    const avg = past.length ? past.reduce((a, b) => a + b, 0) / past.length : 0;
    const maxKwh = Math.max(0, ...days.map((d) => Math.max(d.kwh, d.load || 0)));
    const data = [{ x: labels, y: days.map((d) => d.kwh), type: "bar", name: T("Proizvodnja"),
      marker: { color: th.BRAND_GREEN, opacity, cornerradius: 5, line: { width: 0 } } }];
    if (withLoad) {
      data.push({ x: labels, y: days.map((d) => d.load), type: "bar", name: T("Potrošnja"),
        marker: { color: th.LOAD, opacity, cornerradius: 5, line: { width: 0 } } });
    }
    return {
      data,
      layout: { ...layout(height), bargap: 0.32, bargroupgap: 0.1, barmode: "group", showlegend: withLoad,
        legend: { orientation: "h", yanchor: "bottom", y: 1.0, xanchor: "right", x: 1, bgcolor: "rgba(0,0,0,0)", font: { size: 12 } },
        shapes: avg > 0 && !withLoad ? [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: avg, y1: avg, line: { color: UI.rgba(th.MUTED, ".7"), width: 1, dash: "dot" } }] : [],
        xaxis: { ...grid(), showgrid: false, type: "category", tickfont: { size: 11 }, ...narrowAxis(days.length) },
        yaxis: { ...grid(), nticks: 5, ticksuffix: " kWh", rangemode: "tozero", ...(maxKwh > 0 ? {} : { range: [0, 1] }) } },
      config: CONFIG,
    };
  }

  // Stvarna snaga danas i očekivana po satima iz prognoze zračenja (isto kao charts.forecast_compare).
  function forecastCompare(points, expected, day, peakKwp, height) {
    const th = UI.theme(), green = th.BRAND_GREEN;
    const exX = expected.map((e) => local(e.t)), exY = expected.map((e) => e.kw);
    const data = [
      { x: exX, y: exY, type: "scatter", mode: "lines", name: T("Prognoza"),
        line: { color: th.SUN, width: 2, shape: "spline", smoothing: 0.8, dash: "dash" } },
      { x: points.map((p) => local(p.t)), y: points.map((p) => p.kw), type: "scatter", mode: "lines", name: T("Proizvodnja"),
        line: { color: green, width: 2.5, shape: "spline", smoothing: 0.8 }, fill: "tozeroy",
        fillgradient: { type: "vertical", colorscale: [[0, UI.rgba(green, 0)], [1, UI.rgba(green, th.AREA_ALPHA)]] } },
    ];
    const lit = expected.filter((e) => e.kw > 0.01 * Math.max(peakKwp, 1)).map((e) => e.t);
    let start = new Date(day), end = new Date(day.getTime() + 24 * 3600e3);
    if (lit.length) {
      start = new Date(lit[0].getTime() - 1800e3); start.setMinutes(0, 0, 0);
      end = new Date(lit[lit.length - 1].getTime() + 1800e3);
      if (end.getMinutes()) { end.setHours(end.getHours() + 1); end.setMinutes(0, 0, 0); }
    }
    const top = Math.max(0.1, ...exY, ...points.map((p) => p.kw));
    return {
      data,
      layout: { ...layout(height), showlegend: true,
        legend: { orientation: "h", yanchor: "bottom", y: 1.0, xanchor: "right", x: 1, bgcolor: "rgba(0,0,0,0)", font: { size: 12 } },
        xaxis: { ...grid(), showgrid: false, type: "date", range: [local(start), local(end)], tickformat: "%H:%M",
          tick0: local(day), dtick: 2 * 3600 * 1000, ticklabelstandoff: 8 },
        yaxis: { ...grid(), rangemode: "tozero", range: [0, Math.max(peakKwp * 0.25, top * 1.25)], nticks: 5, ticksuffix: " kW" } },
      config: CONFIG,
    };
  }

  // Stupci po mjesecima (MWh) s iznosom iznad stupca; tekući mjesec blijeđe.
  function monthlyBars(months, today, height) {
    const th = UI.theme();
    const current = new Date(today.getFullYear(), today.getMonth(), 1).getTime();
    const top = Math.max(0, ...months.map((m) => m.kwh)) / 1000;
    return {
      data: [{ x: months.map((m) => fmtDate("chart_month", m.month)), y: months.map((m) => m.kwh / 1000),
        type: "bar", text: months.map((m) => (m.kwh > 0 ? UI.fmt(m.kwh / 1000, 1) : "")), textposition: "outside", cliponaxis: false,
        textfont: { size: 11, color: th.MUTED },
        marker: { color: th.BRAND_GREEN, opacity: months.map((m) => (m.month.getTime() === current ? 0.4 : 1)), cornerradius: 5, line: { width: 0 } } }],
      layout: { ...layout(height), bargap: 0.28,
        xaxis: { ...grid(), showgrid: false, type: "category", tickfont: { size: 11 }, ...narrowAxis(months.length) },
        yaxis: { ...grid(), nticks: 4, ticksuffix: " MWh", rangemode: "tozero", range: [0, Math.max(top * 1.22, 0.1)] } },
      config: CONFIG,
    };
  }

  return { dailyCurve, dailyBars, monthlyBars, forecastCompare };
})();
