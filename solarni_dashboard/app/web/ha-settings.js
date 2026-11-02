// Postavke u Home Assistantu: učitava se iza settings.js i mijenja samo ono što u pregledniku radi drukčije nego u
// Windows aplikaciji – datoteke se biraju i šalju iz preglednika (umjesto Windows dijaloga), CSV se preuzima,
// mrežna kartica prema uređaju smije biti „automatski”, a u odjeljku Sustav je stanje Solarnog poslužitelja.
"use strict";

(() => {
  const unlock = () => (window.SolariHa ? window.SolariHa.unlockToken() : "");

  // ---------------------------------------------------------------- odabir i slanje datoteke
  function pickFile(accept) {
    return new Promise((resolve) => {
      const input = Object.assign(document.createElement("input"), { type: "file", accept, hidden: true });
      input.addEventListener("change", () => { resolve(input.files[0] || null); input.remove(); }, { once: true });
      window.addEventListener("focus", () => setTimeout(() => { if (!input.files.length) { resolve(null); input.remove(); } }, 800), { once: true });
      document.body.appendChild(input);
      input.click();
    });
  }

  async function upload(what, file, kind) {
    const res = await fetch(`api/upload/${what}${kind ? `?kind=${encodeURIComponent(kind)}` : ""}`, {
      method: "POST", credentials: "same-origin", body: file,
      headers: { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(file.name), "X-Solari-Unlock": unlock() },
    });
    if (!res.ok) return { ok: false, message: `HTTP ${res.status}` };
    return res.json();
  }

  const cancelled = { ok: true, message: "" };

  actions.import = (btn) => busy(btn, $("#import-result"), T("Uvozim povijest…"), async () => {
    const file = await pickFile(".db");
    if (!file) return cancelled;
    const res = await upload("history", file);
    if (res.db) renderDb(res.db);
    return res;
  });
  actions["import-smartlogger"] = (btn) => busy(btn, $("#smartlogger-result"), T("Uvozim povijest…"), async () => {
    const file = await pickFile(".zip,.emap");
    if (!file) return cancelled;
    const res = await upload("smartlogger", file);
    if (res.db) renderDb(res.db);
    return res;
  });
  actions["choose-image"] = (btn) => busy(btn, $("#image-result"), T("Obrađujem sliku…"), async () => {
    const file = await pickFile(".jpg,.jpeg,.png,.webp");
    if (!file) return cancelled;
    const res = await upload("image", file, btn.dataset.kind);
    if (res.image) { state.images[res.image.kind] = res.image; renderImages(); }
    return res;
  });
  actions["report-csv"] = () => {
    const a = document.createElement("a");
    a.href = `api/report.csv?year=${report.year}&month=${report.month}&unlock=${encodeURIComponent(unlock())}`;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  };
  actions["open-data"] = actions["open-logs"] = () => {};

  // ---------------------------------------------------------------- mrežne kartice: „automatski” i za uređaj
  const baseRenderIfaces = renderIfaces;
  renderIfaces = function (selectedLogger, selectedInternet) {  // eslint-disable-line no-global-assign
    baseRenderIfaces(selectedLogger, selectedInternet);
    const auto = (name, selected) => `<label class="iface"><input type="radio" name="${name}" value="" ${selected ? "" : "checked"}>
      <span><b>${T("Automatski")}</b><small>${T("Sustav sam bira karticu (zadana ruta)")}</small></span><span></span></label>`;
    $("#logger-ifaces").insertAdjacentHTML("afterbegin", auto("logger_interface", selectedLogger));
    $$("#internet-ifaces .iface small").forEach((el) => {
      if (el.textContent === T("Windows sam bira (zadani izlaz na internet)")) el.textContent = T("Sustav sam bira karticu (zadana ruta)");
    });
  };

  const baseStepValid = stepValid;
  stepValid = function () {  // eslint-disable-line no-global-assign
    if (current !== "network") return true;
    if (!$('input[name="logger_interface"]:checked')) $('input[name="logger_interface"][value=""]')?.click();
    return baseStepValid();
  };

  // ---------------------------------------------------------------- Sustav: stanje poslužitelja umjesto Windows zadatka
  const fmtTime = (ts) => (ts ? new Date(ts * 1000).toLocaleString((window.SOLARI_I18N.meta || {}).locale || "hr-HR") : "—");
  const baseRenderSystem = renderSystem;
  renderSystem = function () {  // eslint-disable-line no-global-assign
    baseRenderSystem();
    const ha = state.ha || {}, p = ha.poller || {};
    let text = `${T("Solarni poslužitelj")}: <code>${esc(ha.server_url || "")}</code> · ${T("zadnje očitanje")}: <b>${esc(fmtTime(p.last_ok))}</b>`;
    if (p.last_error) text += `<br><span class="err">${esc(p.last_error)}</span>`;
    $("#poller-status").innerHTML = text;
    $("#paths").innerHTML = `${T("Podaci")}: <code>${esc((state.paths || {}).data || "")}</code> · ${T("Zapisi: Home Assistant → Postavke → Dodaci → Solarni poslužitelj → Zapisnik")}`;
    if (!ha.view_port) {
      const rv = $('[data-field="remote_view"]');
      if (rv) rv.closest("fieldset").querySelector("#remote-urls").textContent =
        T("Pregled iz mreže radi kad je u postavkama add-ona Solarni monitor otvoren port 8600.");
    }
  };
})();
