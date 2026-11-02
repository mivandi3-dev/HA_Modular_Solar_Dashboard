// Postavke i čarobnjak za prvo pokretanje. Svi podaci idu preko window.pywebview.api (desktop/settings_api.py,
// u C++ verziji src/bridge.cpp). Tekstovi se prevode s T() / translateDom() (i18n.js).
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const PANELS = ["welcome", "network", "plant", "display", "alerts", "reports", "server", "system"];
const WIZARD_PANELS = ["welcome", "network", "plant", "display", "system"];
const SERVER_WIZARD_PANELS = ["welcome", "network", "plant", "display", "server"];
const serverRole = () => state && state.role === "server";
const DECIMAL_FIELDS = ["peak_power_kwp", "co2_factor", "weather_lat", "weather_lon", "price_kwh", "feedin_price_kwh"];
let api = null;
let state = null;
let current = "network";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function setResult(el, res, busyText) {
  el.className = "result " + (busyText ? "busy" : res.ok ? "ok" : "fail");
  el.textContent = busyText || res.message;
}

async function busy(button, resultEl, busyText, fn) {
  button.disabled = true;
  setResult(resultEl, null, busyText);
  try {
    const res = await fn();
    if (res) setResult(resultEl, res);
    return res;
  } catch (e) {
    setResult(resultEl, { ok: false, message: String(e.message || e) });
    return null;
  } finally {
    button.disabled = false;
  }
}

// ------------------------------------------------------------ prikaz podataka
function ifaceCard(name, iface, selected, suggested) {
  let pill = `<span class="pill off">${T("nije spojena")}</span>`;
  if (iface.is_up && iface.link_local_only) pill = `<span class="pill warn">${T("nema mrežu")}</span>`;
  else if (iface.is_up && iface.ipv4) pill = `<span class="pill ok">${T("spojena")}</span>`;
  const addr = iface.ipv4 ? `${iface.ipv4}/${iface.prefix}` : T("bez IPv4 adrese");
  const speed = iface.speed_mbps ? ` · ${iface.speed_mbps >= 1000 ? iface.speed_mbps / 1000 + " Gb/s" : iface.speed_mbps + " Mb/s"}` : "";
  const hint = iface.name === suggested ? `<span class="hint">${T("preporučeno")}</span>` : "";
  return `<label class="iface"><input type="radio" name="${name}" value="${esc(iface.name)}" ${iface.name === selected ? "checked" : ""}>
    <span><b>${esc(iface.name)}${hint}</b><small>${esc(addr)}${speed}</small></span>${pill}</label>`;
}

function renderIfaces(selectedLogger, selectedInternet) {
  const list = state.interfaces;
  $("#logger-ifaces").innerHTML = list.map((i) => ifaceCard("logger_interface", i, selectedLogger, state.suggested.logger)).join("")
    || `<p class="muted">${T("Nije pronađena nijedna mrežna kartica.")}</p>`;
  $("#internet-ifaces").innerHTML =
    `<label class="iface"><input type="radio" name="internet_interface" value="" ${selectedInternet ? "" : "checked"}>
      <span><b>${T("Automatski")}</b><small>${T("Windows sam bira (zadani izlaz na internet)")}</small></span><span></span></label>`
    + list.map((i) => ifaceCard("internet_interface", i, selectedInternet, state.suggested.internet)).join("");
}

function renderScales(selected) {
  $("#scales").innerHTML = Object.entries(state.scales).map(([key, label]) => {
    const [title, res] = T(label).split(" – ");
    return `<label class="choice"><input type="radio" name="display_scale" value="${key}" ${key === selected ? "checked" : ""}>
      <span class="res">${esc(key === "auto" ? "Auto" : key.toUpperCase())}</span><b>${esc(title)}</b><small>${esc(res || "")}</small></label>`;
  }).join("");
}

function renderLanguages(selected) {
  const langs = (window.SOLARI_I18N && window.SOLARI_I18N.languages) || { hr: "Hrvatski" };
  $$(".language-select").forEach((sel) => {
    sel.innerHTML = Object.entries(langs).map(([code, name]) => `<option value="${code}">${esc(name)}</option>`).join("");
    sel.value = selected;
  });
}

function fill(s) {
  renderLanguages(s.language || "hr");
  $$("[data-field]").forEach((el) => {
    if (el.classList.contains("language-select")) return;
    const v = s[el.dataset.field];
    if (el.type === "checkbox") el.checked = Boolean(v);
    else if (DECIMAL_FIELDS.includes(el.dataset.field)) el.value = String(v).replace(".", (window.SOLARI_I18N.meta || {}).decimal || ",");
    else el.value = v ?? "";
  });
  $$('input[name="device_type"]').forEach((r) => { r.checked = r.value === (s.device_type || "logger"); });
  $$('input[name="night_mode"]').forEach((r) => { r.checked = r.value === (s.night_mode || "off"); });
  $$('input[name="forecast_days"]').forEach((r) => { r.checked = Number(r.value) === Number(s.forecast_days || 5); });
  renderCity(s);
  $$('input[name="data_source"]').forEach((r) => { r.checked = r.value === (s.data_source || "local"); });
  $("#network-panel").dataset.source = s.data_source || "local";
  renderCloudAccount(s);
  $("#smtp_password").value = "";
  $("#smtp_password").placeholder = s.smtp_password_set ? "••••••••" : "";
  $("#smtp-password-hint").textContent = s.smtp_password_set ? T("spremljena – ostavite prazno da ostane ista") : "";
  $$('input[name="mail_provider"]').forEach((r) => { r.checked = r.value === (s.mail_provider || "resend"); });
  $("#alerts-panel").dataset.provider = s.mail_provider || "resend";
  $("#resend_api_key").value = "";
  $("#resend_api_key").placeholder = s.resend_api_key_set ? "••••••••" : "re_…";
  $("#resend-key-hint").textContent = s.resend_api_key_set ? T("spremljen – ostavite prazno da ostane isti") : "";
  renderPalettes(s);
  renderIconThemes(s);
  showDeviceTypes(state.device_types);
  renderProfiles(s.device_profile);
  showDevice(s.device_type || "logger");
  document.documentElement.dataset.theme = s.theme;
  renderIfaces(s.logger_interface, s.internet_interface);
  renderScales(s.display_scale);
}

function renderSystem() {
  $("#autostart").checked = state.autostart;
  $("#poller-status").innerHTML = state.poller_task
    ? T("Bilježenje podataka: <b>stalno</b> (zadatak sustava radi i kad je aplikacija zatvorena).")
    : T("Bilježenje podataka: <b>samo dok je aplikacija otvorena</b> (zadatak sustava nije instaliran).");
  $("#pin-state").textContent = state.settings.pin_set
    ? T("Postavke su zaključane PIN-om. Upišite novi PIN za promjenu.")
    : T("Postavke nisu zaključane. Za javni prikaz (predvorje) preporučuje se PIN.");
  $("#pin-clear-row").hidden = !state.settings.pin_set;
  renderDb(state.db);
  $("#paths").innerHTML = `${T("Postavke")}: <code>${esc(state.paths.config)}</code><br>${T("Podaci")}: <code>${esc(state.paths.data)}</code>`;
  $("#legacy-import").hidden = !state.legacy_db;
  $("#smartlogger-import").hidden = $("#smartlogger-help").hidden = !state.smartlogger_import;
  $("#legacy-path").textContent = state.legacy_db || "";
  const urls = state.remote_urls || [];
  $("#remote-urls").innerHTML = urls.length
    ? T("Adrese za preglednik: {urls}", { urls: urls.map((u) => `<code>${esc(u)}</code>`).join(" · ") })
    : T("Nema mrežne kartice s IPv4 adresom.");
  // 4.0 (SMA-08): pristupni ključ – preglednik ga traži pri prvom otvaranju
  const keyBox = $("#remote-key");
  if (keyBox) keyBox.innerHTML = state.remote_view_key
    ? `${T("Pristupni ključ (upišite ga u preglednik)")}: <code style="user-select:all">${esc(state.remote_view_key)}</code>
       <button type="button" class="btn ghost" data-action="remote-new-key">${T("Novi ključ")}</button>
       <br><small class="muted">${T("Pregled iz mreže je obični HTTP – koristite ga samo u pouzdanoj lokalnoj mreži.")}</small>`
    : "";
}

function renderServer() {
  const srv = state.server;
  if (!srv) return;
  $("#admin-who").innerHTML = srv.admin ? T("Prijavljeni ste kao {name} ({email}).", { name: `<b>${esc(srv.admin.name)}</b>`, email: esc(srv.admin.email) }) : "";
  $("#server-urls").innerHTML = T("Adrese API-ja: {urls}", { urls: srv.urls.map((u) => `<code>${esc(u)}</code>`).join(" · ") });
  $("#server-cert").innerHTML = srv.certificate
    ? T("Kod za uparivanje klijenata: {code}", { code: `<b style="font-size:1.4em;letter-spacing:.08em;user-select:all">${esc(srv.certificate.pairing_code)}</b>` })
      + "<br>" + T("HTTPS certifikat (otisak SHA-256): {fp} – vrijedi do {date}.",
        { fp: `<code>${esc(srv.certificate.fingerprint)}</code>`, date: esc(srv.certificate.not_after) })
    : T("HTTPS certifikat bit će izrađen kad uključite pristup iz lokalne mreže.");
  $("#server-status").innerHTML = srv.task
    ? T("Bilježenje i API: <b>stalno</b> (zadatak sustava radi i kad je ovaj prozor zatvoren).")
    : srv.in_app ? T("Bilježenje i API rade <b>dok je ovaj prozor otvoren</b> (zadatak sustava nije instaliran).")
      : T("API vodi drugi proces poslužitelja.");
  const port = $('[data-field="server_port"]').value || "8700";
  $("#cf-quick").textContent = `cloudflared tunnel --url http://localhost:${port}`;
  if (!users) loadUsers();
}

// ------------------------------------------------------------ lokacija prognoze: grad umjesto koordinata (3.1)
function renderCity(s) {
  const lat = Number(String(s.weather_lat).replace(",", ".")), lon = Number(String(s.weather_lon).replace(",", "."));
  $("#city-now").innerHTML = T("Prognoza za: {city}", { city: `<b>${esc(s.weather_city || "—")}</b>` })
    + ` <span class="muted small">(${lat.toFixed(3)} / ${lon.toFixed(3)})</span>`;
}

function pickPlace(p) {
  $('[data-field="weather_city"]').value = p.label;
  $('[data-field="weather_lat"]').value = String(p.lat);
  $('[data-field="weather_lon"]').value = String(p.lon);
  $("#places").innerHTML = "";
  renderCity({ weather_city: p.label, weather_lat: p.lat, weather_lon: p.lon });
  setResult($("#city-result"), { ok: true, message: T("Odabrano – spremite postavke.") });
}

// ------------------------------------------------------------ dvofaktorska prijava (3.1): QR kod, kod, kodovi za oporavak
function showTotp(box, info, out) {
  box.hidden = !info;
  if (!info) return;
  if (out && !info.invalid) out.className = "result";  // uputa, a ne greška
  const setup = info.step === "setup" && info.uri;
  $(".totp-setup", box).hidden = !setup;
  if (setup) {
    const qr = window.qrcode(0, "M");
    qr.addData(info.uri);
    qr.make();
    $(".qr", box).innerHTML = qr.createSvgTag({ cellSize: 4, margin: 3, scalable: true });
    $(".secret", box).textContent = info.secret.replace(/(.{4})/g, "$1 ").trim();
  }
  $(".totp-code", box).value = "";
  $(".totp-code", box).focus();
}

// aktivacija računa (jednokratni kod): polja za vlastitu lozinku; vraća novu lozinku, "" (blok skriven) ili null (ne podudaraju se)
function newPassword(box, out) {
  if (box.hidden) return "";
  const a = $(".np1", box).value, b = $(".np2", box).value;
  if (!a || a !== b) { setResult(out, { ok: false, message: a ? T("Lozinke se ne podudaraju.") : T("Upišite novu lozinku.") }); return null; }
  return a;
}
function showNewPassword(box, on) {
  box.hidden = !on;
  if (!on) { $$("input", box).forEach((i) => { i.value = ""; }); return; }
  $(".np1", box).focus();
}

// kodovi za oporavak (samo jednom, odmah nakon postavljanja); vraća Promise koji se ispuni na „nastavi”
function showRecovery(box, codes) {
  return new Promise((resolve) => {
    if (!codes || !codes.length) return resolve();
    $(".codes", box).textContent = codes.join("\n");
    box.hidden = false;
    $('[data-action="recovery-done"]', box).onclick = () => { $(".codes", box).textContent = ""; box.hidden = true; resolve(); };
  });
}

// ------------------------------------------------------------ prijava klijenta na Solarni poslužitelj (3.0)
function renderCloudAccount(s) {
  const acc = s.cloud_account;
  $("#cloud-account").innerHTML = acc
    ? T("Prijavljeni ste kao {name} ({email}).", { name: `<b>${esc(acc.name)}</b>`, email: esc(acc.email) })
    : "";
  $$(".cloud-login").forEach((el) => { el.hidden = Boolean(acc); });
  $$(".cloud-logout").forEach((el) => { el.hidden = !acc; });
  if (acc) $("#cloud_email").value = acc.email;
}

// ------------------------------------------------------------ korisnici poslužitelja (3.0)
let users = null;
let editing = null;  // korisnik u dijalogu (null = novi)

async function loadUsers() {
  const res = await api.users_list();
  if (res.ok) { users = res.users; renderUsers(); } else setResult($("#users-result"), res);
}

function fmtWhen(ts) {
  if (!ts) return T("nikad");
  const d = new Date(ts * 1000), p = (n) => String(n).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}. ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function renderUsers() {
  $("#users").innerHTML = users.map((u) => {
    const pills = [u.role === "admin" ? `<span class="pill">${T("administrator")}</span>` : `<span class="pill off">${T("korisnik")}</span>`];
    if (u.disabled) pills.push(`<span class="pill bad">${T("blokiran")}</span>`);
    else if (u.locked) pills.push(`<span class="pill bad">${T("zaključan 15 min")}</span>`);
    if (u.activation_expired) pills.push(`<span class="pill bad">${T("aktivacijski kod istekao")}</span>`);
    else if (u.activation_pending) pills.push(`<span class="pill warn">${T("čeka aktivaciju")}</span>`);
    if (u.totp_enabled) pills.push(`<span class="pill ok">${T("2FA")}</span>`);
    else if (u.totp_required) pills.push(`<span class="pill warn">${T("2FA čeka postavljanje")}</span>`);
    if (u.me) pills.push(`<span class="pill ok">${T("vi")}</span>`);
    return `<div class="user-row" role="row" data-id="${u.id}">
      <div class="who"><b>${esc(u.first_name)} ${esc(u.last_name)}</b><small>${esc(u.email)}</small></div>
      <div class="tags">${pills.join("")}</div>
      <div class="meta muted small">${T("zadnja prijava: {when}", { when: fmtWhen(u.last_login) })}<br>${T("prijavljen na {n} uređaja", { n: u.sessions })}</div>
      <div class="acts">
        <button class="btn" data-action="user-edit" data-id="${u.id}">${T("Uredi")}</button>
        ${u.me ? "" : `<button class="btn ghost" data-action="user-toggle" data-id="${u.id}">${u.disabled ? T("Odblokiraj") : T("Blokiraj")}</button>
        <button class="btn ghost danger" data-action="user-delete" data-id="${u.id}">${T("Obriši")}</button>`}
      </div></div>`;
  }).join("") || `<p class="muted">${T("Nema korisnika.")}</p>`;
}

function userForm(root) {
  const v = (k) => { const el = $(`[data-user="${k}"]`, root); return el ? el.value : ""; };
  const totp = $('[data-user="totp_required"]', root);
  return { first_name: v("first_name").trim(), last_name: v("last_name").trim(), email: v("email").trim(), password: v("password"),
           password2: v("password2"), role: v("role") || "admin", totp_required: Boolean(totp && totp.checked) };
}

function showUserErrors(root, errors) {
  $$("[data-user-error]", root).forEach((el) => { el.textContent = (errors && errors[el.dataset.userError]) || ""; });
}

// lozinka i ponovljena lozinka moraju biti iste (prije slanja); vraća greške ili null
function passwordMismatch(f, required) {
  if (!required && !f.password && !f.password2) return null;
  return f.password !== f.password2 ? { password2: T("Lozinke se ne podudaraju.") } : null;
}

// 5.2: administrator uvijek ima dvofaktorsku prijavu – kvačica je uključena i zaključana (poslužitelj to i sam provodi)
function syncAdminTotp(root) {
  const role = $('[data-user="role"]', root), box = $('[data-user="totp_required"]', root);
  if (!role || !box) return;
  const admin = role.value === "admin";
  if (admin) box.checked = true;
  box.disabled = admin;
  const note = $(".totp-admin-note", root);
  if (note) note.hidden = !admin;
}

function openUserDialog(u) {
  editing = u || null;
  const root = $("#user-dialog");
  $("#user-dialog-title").textContent = u ? T("Uredi korisnika") : T("Novi korisnik");
  for (const k of ["first_name", "last_name", "email"]) $(`[data-user="${k}"]`, root).value = u ? u[k] : "";
  $('[data-user="role"]', root).value = u ? u.role : "user";
  $('[data-user="role"]', root).disabled = Boolean(u && u.me);
  $('[data-user="password"]', root).value = $('[data-user="password2"]', root).value = "";
  $("#user-password-hint").textContent = u ? T("prazno = lozinka ostaje ista")
    : T("prazno = jednokratni kod (vrijedi 72 sata) šalje se korisniku e-poštom; njime se registrira i postavlja svoju lozinku");
  $("#user-pw-admin").hidden = !(u && !u.me);
  $('[data-user="totp_required"]', root).checked = Boolean(u && u.totp_required);
  syncAdminTotp(root);
  $("#user-totp-admin").hidden = !(u && u.totp_enabled);
  if (u && u.totp_enabled) {
    $("#user-totp-state").textContent = T("Dvofaktorska prijava je postavljena; preostalo kodova za oporavak: {n}.", { n: u.recovery_left });
  }
  showUserErrors(root, null);
  $("#user-result").textContent = "";
  root.showModal();
  $('[data-user="first_name"]', root).focus();
}

function wipeUserForm(root) { $$('input[type="password"]', root).forEach((el) => { el.value = ""; }); }

// ------------------------------------------------------------ izvještaj (PDF preko ispisa, CSV za Excel)
let report = null;

function selectedMonth() {
  const [year, month] = $("#report-month").value.split("-").map(Number);
  return { year, month };
}

function renderImages() {
  $("#images").innerHTML = ["hero", "drawing", "logo"].map((k) => state.images[k]).filter(Boolean).map((img) => `
    <div class="image-card ${esc(img.kind)}">
      <div class="thumb" style="background-image:url('${img.thumb}')"></div>
      <h3>${esc(T(img.title))}<span class="ratio">${esc(T("omjer {ratio}", { ratio: T(img.ratio) }))}</span></h3>
      <p>${img.width ? `${img.custom ? T("Vlastita slika") : T("Izvorna slika")} · ${img.width} × ${img.height} px` : T("Slika nije pronađena")}</p>
      <p>${esc(T(img.hint))}</p>
      <div class="row-start">
        <button class="btn" data-action="choose-image" data-kind="${esc(img.kind)}">${T("Promijeni…")}</button>
        ${img.custom ? `<button class="btn ghost" data-action="reset-image" data-kind="${esc(img.kind)}">${T("Vrati izvornu")}</button>` : ""}
      </div>
    </div>`).join("");
}

function renderHeadline() {
  const hl = (t) => esc(T(t)).replace(/\*([^*]+)\*/g, '<span class="hl">$1</span>');
  const f = (k) => $(`[data-field="${k}"]`).value;
  $("#headline-preview").innerHTML = `${hl(f("headline"))}<br>${hl(f("headline_running"))}`;
}

function renderDb(db) {
  const locale = (window.SOLARI_I18N.meta || {}).locale || "hr-HR";
  const when = (ts) => (ts ? new Date(ts.replace(" ", "T") + "Z").toLocaleString(locale) : "—");
  $("#db-status").innerHTML = db.readings
    ? T("Baza: <b>{n}</b> očitanja · od {first} · zadnje {last}", { n: fmtNum(db.readings, 0), first: when(db.first), last: when(db.last) })
    : T("Baza je prazna – povijest se gradi od prvog očitanja (ili je uvezite niže).");
}

function renderScreens() {
  $("#monitor").innerHTML = state.screens.map((s) => `<option value="${s.index}">${esc(
    T("Zaslon {n} – {w} × {h}", { n: s.index + 1, w: s.width, h: s.height }) + (s.primary ? " " + T("(glavni)") : ""))}</option>`).join("");
}

// Sve što ovisi o jeziku – pri pokretanju i nakon promjene jezika
function renderAll(s) {
  translateDom(document.body);
  $("#version").textContent = T("Verzija {v}", { v: state.version });
  $("#mode-label").textContent = state.wizard ? T("Prvo postavljanje") : T("Postavke");
  $(".brand b").textContent = serverRole() ? T("Solarni poslužitelj") : "Solarni monitor";
  document.title = serverRole() ? T("Solarni poslužitelj – postavke") : T("Solarni monitor – postavke");
  renderScreens();
  fill(s);
  renderSystem();
  renderImages();
  renderHeadline();
  renderMonths();
  renderServer();
  if (report) renderReport(report);
}

// ------------------------------------------------------------ obrazac
function collect() {
  const form = {};
  $$("[data-field]").forEach((el) => { form[el.dataset.field] = el.type === "checkbox" ? el.checked : el.value; });
  ["logger_interface", "internet_interface", "display_scale", "device_type", "night_mode", "data_source", "icon_theme", "design", "mail_provider"].forEach((name) => {
    const r = $(`input[name="${name}"]:checked`);
    form[name] = r ? r.value : "";
  });
  form.autostart = $("#autostart").checked;
  form.forecast_days = Number(($('input[name="forecast_days"]:checked') || {}).value || 5);
  form.pin_new = $("#pin_new").value;
  form.pin_clear = $("#pin_clear").checked;
  form.smtp_password = $("#smtp_password").value;
  form.resend_api_key = $("#resend_api_key").value.trim();
  // tema je osnova odabrane palete (Tamna/Svijetla su boje same teme)
  form.palette = selectedPalette();
  form.theme = window.SolariColors ? window.SolariColors.themeOf(form.palette) : form.palette;
  if (!form.data_source) form.data_source = "local";
  return form;
}

function showErrors(errors) {
  $$("[data-error]").forEach((el) => { el.textContent = errors[el.dataset.error] || ""; });
  $$("[data-field], #pin_new, #smtp_password, #resend_api_key").forEach((el) => el.classList.toggle("invalid", Boolean(errors[el.dataset.field || el.id])));
  const first = Object.keys(errors)[0];
  if (!first) return;
  const panel = $(`[data-error="${first}"]`)?.closest(".panel");
  if (panel) show(panel.dataset.panel);
}

// ------------------------------------------------------------ navigacija
function steps() {
  if (state.wizard) return serverRole() ? SERVER_WIZARD_PANELS : WIZARD_PANELS;
  return PANELS.filter((p) => p !== "welcome" && (serverRole() ? p !== "system" : p !== "server"));
}

function show(name) {
  current = name;
  $$(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === name));
  const order = steps();
  $$("#nav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.panel === name);
    b.classList.toggle("done", state.wizard && order.indexOf(b.dataset.panel) < order.indexOf(name));
  });
  document.body.classList.toggle("last", order.indexOf(name) === order.length - 1);
  $("#btn-back").hidden = order.indexOf(name) === 0;
  $(".content").scrollTop = 0;
}

function stepValid() {
  if (current !== "network") return true;
  const errors = {};
  if ($('input[name="data_source"]:checked')?.value === "cloud" && !serverRole()) {
    if (!$('[data-field="cloud_url"]').value.trim()) errors.cloud_url = T("Upišite adresu poslužitelja, npr. https://solar.tvrtka.hr");
    if (!state.settings.cloud_account) errors.cloud_login = T("Prijavite se na poslužitelj (e-pošta i lozinka).");
    showErrors(errors);
    return !Object.keys(errors).length;
  }
  if (!$('input[name="logger_interface"]:checked')) errors.logger_interface = T("Izaberite mrežnu karticu koja vodi do loggera.");
  if (!$('[data-field="modbus_host"]').value.trim()) errors.modbus_host = T("Upišite IP adresu uređaja.");
  showErrors(errors);
  return !Object.keys(errors).length;
}

function move(delta) {
  const order = steps();
  if (delta > 0 && !stepValid()) return;
  show(order[Math.max(0, Math.min(order.length - 1, order.indexOf(current) + delta))]);
}

// Promjena jezika: učitaj rječnik i odmah prevedi prozor (sprema se tek gumbom Spremi).
async function changeLanguage(code) {
  const form = collect();
  window.SOLARI_I18N = await api.get_i18n(code);
  renderAll({ ...state.settings, ...form, language: code });
}

// ------------------------------------------------------------ akcije
const actions = {
  "refresh-ifaces": async () => {
    const form = collect();
    state.interfaces = await api.interfaces();
    renderIfaces(form.logger_interface, form.internet_interface);
  },
  "test-logger": (btn) => busy(btn, $("#logger-result"), T("Spajam se na uređaj…"), () => api.test_logger(collect())),
  "test-internet": (btn) => busy(btn, $("#internet-result"), T("Dohvaćam prognozu…"), () => api.test_internet(collect())),
  import: (btn) => busy(btn, $("#import-result"), T("Uvozim povijest…"), async () => {
    const res = await api.import_history(null);
    if (res.db) renderDb(res.db);
    return res.cancelled ? { ok: true, message: "" } : res;
  }),
  "import-smartlogger": (btn) => busy(btn, $("#smartlogger-result"), T("Uvozim povijest…"), async () => {
    const res = await api.import_smartlogger(null);
    if (res.db) renderDb(res.db);
    return res.cancelled ? { ok: true, message: "" } : res;
  }),
  "import-legacy": (btn) => busy(btn, $("#import-result"), T("Uvozim povijest…"), async () => {
    const res = await api.import_history(state.legacy_db);
    if (res.db) renderDb(res.db);
    if (res.ok) $("#legacy-import").hidden = true;
    return res;
  }),
  "choose-image": (btn) => busy(btn, $("#image-result"), T("Obrađujem sliku…"), async () => {
    const res = await api.choose_image(btn.dataset.kind);
    if (res.image) { state.images[res.image.kind] = res.image; renderImages(); }
    return res.cancelled ? { ok: true, message: "" } : res;
  }),
  "reset-image": (btn) => busy(btn, $("#image-result"), T("Vraćam izvornu sliku…"), async () => {
    const res = await api.reset_image(btn.dataset.kind);
    if (res.image) { state.images[res.image.kind] = res.image; renderImages(); }
    return res;
  }),
  "cloud-login": (btn) => busy(btn, $("#cloud-result"), T("Prijavljujem se…"), async () => {
    const npw = newPassword($("#cloud-newpw"), $("#cloud-result"));
    if (npw === null) return null;
    const res = await api.cloud_login({ cloud_url: $('[data-field="cloud_url"]').value, email: $("#cloud_email").value.trim(),
                                        password: $("#cloud_password").value, totp: $("#cloud-totp .totp-code").value, new_password: npw,
                                        pairing_code: $("#cloud_pairing").value.trim() });
    if (res.pairing) { $("#cloud_pairing").focus(); return res; }  // SMA-04: kod za uparivanje je obavezan
    if (res.password_change) { showNewPassword($("#cloud-newpw"), true); return res; }  // aktivacijski kod – treba vlastita lozinka
    if (npw) { $("#cloud_password").value = npw; showNewPassword($("#cloud-newpw"), false); }  // promijenjena – dalje s novom
    if (res.totp) { setResult($("#cloud-result"), res); showTotp($("#cloud-totp"), res.totp, $("#cloud-result")); return null; }  // lozinka ostaje do unosa koda
    $("#cloud_password").value = "";  // lozinka ne ostaje ni u obrascu
    showTotp($("#cloud-totp"), null);
    if (res.ok) {
      await showRecovery($("#cloud-totp-recovery"), res.recovery_codes);
      state.settings.cloud_account = res.account;
      state.settings.cloud_cert_pin = res.pin;
      state.settings.cloud_url = res.cloud_url;
      $('[data-field="cloud_url"]').value = res.cloud_url;
      renderCloudAccount(state.settings);
      showErrors({});
    }
    return res;
  }),
  // zaboravljena lozinka: kod e-poštom, zatim nova lozinka (prozor poslužitelja ili prijava klijenta na poslužitelj)
  "forgot-send": (btn) => {
    const box = btn.closest("[data-forgot]"), out = $(".fp-result", box);
    if (box.dataset.forgot === "admin") {
      return busy(btn, out, T("Šaljem…"), () => api.admin_forgot_password($("#login-email").value.trim()));
    }
    return busy(btn, out, T("Šaljem…"), async () => {
      const res = await api.cloud_forgot_password(forgotForm());
      if (res.pairing) $("#cloud_pairing").focus();
      return res;
    });
  },
  "forgot-reset": (btn) => {
    const box = btn.closest("[data-forgot]"), out = $(".fp-result", box);
    const code = $(".fp-code", box).value.trim(), np1 = $(".fp-np1", box).value, np2 = $(".fp-np2", box).value;
    if (!code) { setResult(out, { ok: false, message: T("Upišite kod iz e-pošte.") }); return null; }
    if (!np1 || np1 !== np2) { setResult(out, { ok: false, message: T("Nove lozinke se ne podudaraju.") }); return null; }
    return busy(btn, out, T("Spremam (sigurno spremanje lozinke traje sekundu)…"), async () => {
      const res = box.dataset.forgot === "admin"
        ? await api.admin_reset_password($("#login-email").value.trim(), code, np1)
        : await api.cloud_reset_password({ ...forgotForm(), code, new_password: np1 });
      if (res.ok) {
        $$(".fp-code, .fp-np1, .fp-np2", box).forEach((el) => { el.value = ""; });
        box.open = false;
        $(box.dataset.forgot === "admin" ? "#login-password" : "#cloud_password").focus();
      }
      return res;
    });
  },
  "cloud-logout": (btn) => busy(btn, $("#cloud-result"), T("Odjavljujem…"), async () => {
    const res = await api.cloud_logout();
    if (res.ok) { state.settings.cloud_account = null; renderCloudAccount(state.settings); }
    return res;
  }),
  "admin-logout": () => api.admin_logout(),
  "user-add": () => openUserDialog(null),
  "user-edit": (btn) => openUserDialog(users.find((u) => String(u.id) === btn.dataset.id)),
  "city-search": (btn) => busy(btn, $("#city-result"), T("Tražim…"), async () => {
    const iface = ($('input[name="internet_interface"]:checked') || {}).value || "";
    const res = await api.geocode($("#city-query").value, iface, state.settings.language || "hr");
    if (!res.ok) return res;
    if (res.places.length === 1) { pickPlace(res.places[0]); return { ok: true, message: T("Odabrano – spremite postavke.") }; }
    $("#places").innerHTML = res.places.map((p, i) => `<button type="button" class="place" data-i="${i}">${esc(p.label)}`
      + ` <small class="muted">${p.lat.toFixed(2)} / ${p.lon.toFixed(2)}</small></button>`).join("");
    $$("#places .place").forEach((b) => b.addEventListener("click", () => pickPlace(res.places[Number(b.dataset.i)])));
    return { ok: true, message: T("Izaberite mjesto s popisa.") };
  }),
  "user-reset-password": (btn) => busy(btn, $("#user-result"), T("Spremam…"), async () => {
    const res = await api.user_reset_password(editing.id);
    if (res.users) { users = res.users; renderUsers(); editing = users.find((x) => x.id === editing.id); }
    return res;  // kod ide samo e-poštom korisniku – administrator ga ne vidi
  }),
  "remote-new-key": (btn) => busy(btn, $("#remote-urls"), T("Spremam…"), async () => {
    const res = await api.remote_view_new_key();
    if (res.ok) { state.remote_view_key = res.remote_view_key; renderSystem(); }
    return res;
  }),
  "user-logout-all": (btn) => busy(btn, $("#user-result"), T("Spremam…"), async () => {
    const res = await api.user_logout_all(editing.id);
    if (res.users) { users = res.users; renderUsers(); editing = users.find((x) => x.id === editing.id); }
    return res;
  }),
  "user-reset-totp": (btn) => busy(btn, $("#user-result"), T("Spremam…"), async () => {
    const res = await api.user_reset_totp(editing.id);
    if (res.users) { users = res.users; renderUsers(); editing = users.find((x) => x.id === editing.id); $("#user-totp-admin").hidden = true; }
    return res;
  }),
  "user-cancel": () => { wipeUserForm($("#user-dialog")); $("#user-dialog").close(); },
  "user-toggle": (btn) => {
    const u = users.find((x) => String(x.id) === btn.dataset.id);
    return busy(btn, $("#users-result"), T("Spremam…"), async () => {
      const res = await api.user_set_disabled(u.id, !u.disabled);
      if (res.users) { users = res.users; renderUsers(); }
      return res;
    });
  },
  "user-delete": (btn) => {
    if (!btn.dataset.confirm) {  // drugi klik potvrđuje
      btn.dataset.confirm = "1";
      btn.textContent = T("Potvrdi brisanje");
      return;
    }
    return busy(btn, $("#users-result"), T("Brišem…"), async () => {
      const res = await api.user_delete(Number(btn.dataset.id));
      if (res.users) { users = res.users; renderUsers(); }
      return res;
    });
  },
  "test-email": (btn) => busy(btn, $("#email-result"), T("Šaljem probnu poruku…"), () => api.test_email(collect())),
  "report-show": (btn) => busy(btn, $("#report-result"), T("Izrađujem izvještaj…"), async () => {
    const { year, month } = selectedMonth();
    const res = await api.get_report(year, month);
    if (!res.ok) return res;
    report = res.report;
    renderReport(report);
    $("#report-print").disabled = $("#report-csv").disabled = false;
    return { ok: true, message: "" };
  }),
  "report-print": () => window.print(),
  "report-csv": (btn) => busy(btn, $("#report-result"), T("Spremam…"), async () => {
    const res = await api.save_report_csv(report.year, report.month);
    return res.cancelled ? { ok: true, message: "" } : res;
  }),
  "goto-images": () => { show("display"); $("#images-card").scrollIntoView({ block: "start" }); },
  "open-data": () => api.open_folder("data"),
  "open-logs": () => api.open_folder("logs"),
  back: () => move(-1),
  next: () => move(1),
  close: () => api.close(),
  save: (btn) => busy(btn, $("#save-result"), T("Spremam…"), async () => {
    const res = await api.save(collect());
    showErrors(res.errors || {});
    if (res.ok) setTimeout(() => api.close(), state.wizard ? 150 : 700);
    return res;
  }),
};

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action]");
  if (btn && actions[btn.dataset.action]) { e.preventDefault(); actions[btn.dataset.action](btn); }
  const nav = e.target.closest("#nav button");
  if (nav && (!state.wizard || steps().indexOf(nav.dataset.panel) <= steps().indexOf(current) || stepValid())) show(nav.dataset.panel);
});
// ---------------------------------------------------------------- tema: palete boja (colors.js, zajedničko s Androidom)
function selectedPalette() {
  return ($('input[name="palette"]:checked') || {}).value || "dark";
}

// ---------------------------------------------------------------- tema ikona (icons.js): odabir s primjerima
const ICON_SAMPLE = ["sun", "sun_cloud", "rain", "bolt", "battery", "home", "chart", "globe"];
function renderDesigns(s) {  // 5.1: izgled nadzorne ploče
  const want = ["aurora", "control", "daylight"].includes(s.design) ? s.design : "classic";
  $$('input[name="design"]').forEach((r) => { r.checked = r.value === want; });
  const photo = $(".design-photo");
  const sync = () => { if (photo) photo.classList.toggle("dim", (($('input[name="design"]:checked') || {}).value) !== "control"); };
  $$('input[name="design"]').forEach((r) => r.addEventListener("change", sync));
  sync();
}

function renderIconThemes(s) {
  renderDesigns(s);
  const want = ["neon", "iconset"].includes(s.icon_theme) ? s.icon_theme : "classic";
  $$('input[name="icon_theme"]').forEach((r) => { r.checked = r.value === want; });
  const I = window.Icons;
  if (!I) return;
  const ui = document.documentElement.dataset.theme === "light" ? "light" : "dark";
  $$(".icon-preview").forEach((el) => {
    I.setTheme(el.dataset.iconTheme, ui);
    el.innerHTML = ICON_SAMPLE.map((k) => `<span>${I.get(k)}</span>`).join("");  // statične ikone iz icons.js
  });
  I.setTheme("classic", ui);
}

function renderPalettes(s) {
  const SC = window.SolariColors, box = $(".palettes");
  if (!box) return;
  if (!SC) {  // bez colors.js (Python verzija) samo Tamna i Svijetla
    box.querySelectorAll("[data-palette]").forEach((l) => { l.hidden = !["dark", "light"].includes(l.dataset.palette); });
    $$('input[name="palette"]').forEach((r) => { r.checked = r.value === (s.theme || "dark"); });
    return;
  }
  SC.renderChoices(box, SC.paletteKey(s.theme, s.palette));
}

// Ostali proizvođači: popis modela iz C++-a (vendors.cpp) i upute za odabrani model
function renderProfiles(selected) {
  const sel = $("#device-profile");
  const profiles = state.device_profiles || [];
  sel.innerHTML = profiles.map((p) => `<option value="${esc(p.key)}">${esc(p.name)}</option>`).join("");
  if (selected) sel.value = selected;
  renderProfileHelp();
}

function profile() {
  return (state.device_profiles || []).find((p) => p.key === $("#device-profile").value);
}

function renderProfileHelp() {
  const p = profile();
  if (!p) return;
  const parts = [T("Uobičajeno: port {port}, Modbus adresa {unit}.", { port: p.port, unit: p.unit })];
  if (p.link === "solarman") parts.push(T("Port 8899 = Wi-Fi logger (Solarman) – upišite serijski broj loggera; port 502 = Modbus TCP pristupnik."));
  if (p.link === "goodwe") parts.push(T("Port 8899 = GoodWe Wi-Fi/LAN modul (UDP); port 502 = Modbus TCP."));
  if (p.link === "tcp") parts.push(T("Modbus TCP – na uređaju ili preko RS485 → Modbus TCP pristupnika."));
  if (p.link === "serial") {
    parts.length = 0;
    parts.push(T("Modbus RTU na serijskom portu (USB, RS232 ili RS485 pretvarač), brzina {baud}, Modbus adresa {unit}.", { baud: p.port, unit: p.unit }));
    parts.push(T("Adrese registara su iz dokumentacije proizvođača i nisu isprobane na svakom modelu."));
  }
  if (!p.energy) parts.push(T("Uređaj ne daje proizvedenu energiju – Solarni monitor je računa iz snage."));
  if (!p.meter) parts.push(T("Mjerač se za ovaj uređaj ne čita."));
  $("#vendor-help").textContent = parts.join(" ");
  $("#logger-serial-field").hidden = $("#device-card").dataset.device !== "vendor" || p.link !== "solarman";
}

// Polja kartice uređaja: data-show="inverter sunspec" – vidljivo za navedene vrste uređaja
function showDevice(type) {
  $("#device-card").dataset.device = type;
  $$("#device-card [data-show]").forEach((el) => { el.hidden = !el.dataset.show.split(" ").includes(type); });
  if (type === "vendor") renderProfileHelp();
  // off-grid uređaji na COM/USB: umjesto IP adrese i porta serijski port i brzina
  const serial = type === "voltronic" || type === "vedirect" || (type === "vendor" && profile() && profile().link === "serial");
  $("#device-card").dataset.serial = serial ? "1" : "";
  const ports = state.serial_ports || [];
  $("#serial-ports").textContent = (ports.length ? T("Pronađeni portovi: {ports}", { ports: ports.join(", ") }) : T("Nijedan COM port nije pronađen – provjerite kabel i upravljački program."))
    + (type === "voltronic" ? " · " + T("USB = izmjenjivač spojen USB kabelom") : "");
}

// Vrste uređaja koje aplikacija podržava (C++: i SunSpec i Fronius); bez popisa samo Huawei
function showDeviceTypes(types) {
  $$("[data-device-type]").forEach((el) => { el.hidden = !(types || []).includes(el.dataset.deviceType); });
}

document.addEventListener("input", (e) => {
  if (e.target.dataset && e.target.dataset.field && e.target.dataset.field.startsWith("headline")) renderHeadline();
});
document.addEventListener("change", (e) => {
  if (e.target.name === "palette") {
    document.documentElement.dataset.theme = window.SolariColors ? window.SolariColors.themeOf(e.target.value) : e.target.value;
  }
  if (e.target.name === "device_type") {
    // zadani port nove vrste uređaja, ako je upisan zadani port druge vrste
    const port = $('[data-field="modbus_port"]');
    if (["80", "502", "1502", "6607", "8899"].includes(port.value.trim())) {
      port.value = e.target.value === "fronius" ? "80" : e.target.value === "vendor" && profile() ? String(profile().port) : "502";
    }
    showDevice(e.target.value);
  }
  if (e.target.id === "device-profile") {
    // uobičajeni port i adresa odabranog modela, ako su upisane uobičajene vrijednosti
    const p = profile(), port = $('[data-field="modbus_port"]'), units = $('[data-field="inverter_units"]');
    if (p && ["80", "502", "1502", "6607", "8899"].includes(port.value.trim())) port.value = String(p.port);
    if (p && ["", "0", "1", "100", "126", "247", "71"].includes(units.value.trim())) units.value = String(p.unit);
    renderProfileHelp();
    showDevice("vendor");
  }
  if (e.target.dataset && e.target.dataset.field === "modbus_port") renderProfileHelp();
  if (e.target.name === "data_source") $("#network-panel").dataset.source = e.target.value;
  if (e.target.name === "mail_provider") $("#alerts-panel").dataset.provider = e.target.value;
  if (e.target.dataset && e.target.dataset.field === "server_port") renderServer();
  if (e.target.classList.contains("language-select")) changeLanguage(e.target.value);
  if (e.target.id === "report-month") { report = null; $("#report").hidden = true; $("#report-print").disabled = $("#report-csv").disabled = true; }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && state && !state.wizard) api.close();
});

// ------------------------------------------------------------ pokretanje
async function start() {
  api = window.pywebview.api;
  state = await api.get_state();
  if (state.i18n) window.SOLARI_I18N = state.i18n;
  translateDom(document.body);
  if (state.locked && state.auth && state.auth.server) return startServerAuth();
  if (state.locked) {
    $("#lock").hidden = false;
    $("#lock-form").hidden = false;
    $("#pin").focus();
    $("#lock-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const res = await api.unlock($("#pin").value);
      setResult($("#lock-result"), res);
      if (res.ok) { $("#lock").hidden = true; await start(); } else { $("#pin").select(); }
    }, { once: false });
    return;
  }
  document.body.classList.toggle("wizard", state.wizard);
  document.body.classList.toggle("server-role", serverRole());
  document.body.classList.toggle("has-cloud", Boolean(state.features && state.features.cloud) && !serverRole());
  $("#legacy-note").hidden = !(state.wizard && state.legacy_db);
  renderAll(state.settings);
  $("#app").hidden = false;
  show(state.wizard ? "welcome" : steps().includes(state.panel) ? state.panel : "network");
  if (state.panel === "display") $("#images-card").scrollIntoView({ block: "start" });
}

function forgotForm() {
  return { cloud_url: $('[data-field="cloud_url"]').value, email: $("#cloud_email").value.trim(), pairing_code: $("#cloud_pairing").value.trim() };
}

// Solarni poslužitelj: prozor se otvara tek nakon prijave administratora (ili izrade prvoga)
function startServerAuth() {
  const a = state.auth;
  $("#lock").hidden = false;
  $("#lock-form").hidden = true;
  if (a.error) {
    $("#admin-login").hidden = false;
    setResult($("#login-result"), { ok: false, message: a.error });
    $("#login-submit").disabled = true;
    return;
  }
  const form = a.setup ? $("#admin-setup") : $("#admin-login");
  form.hidden = false;
  $("input", form).focus();
  form.onsubmit = async (e) => {
    e.preventDefault();
    const btn = a.setup ? $("#setup-submit") : $("#login-submit"), out = a.setup ? $("#setup-result") : $("#login-result");
    let res;
    if (a.setup) {
      const f = userForm(form), mismatch = passwordMismatch(f, true);
      showUserErrors(form, mismatch);
      if (mismatch) return;
      res = await busy(btn, out, T("Izrađujem račun (sigurno spremanje lozinke traje sekundu)…"), () => api.setup_admin(f));
      if (res) showUserErrors(form, res.errors);
      if (res && res.totp) {  // 5.2: račun je izrađen – odmah QR kod i potvrda kodom iz autentifikatora
        $("#login-email").value = f.email;
        $("#login-password").value = f.password;
        wipeUserForm(form);
        form.hidden = true;
        a.setup = false;
        startServerAuth();
        setResult($("#login-result"), res);
        showTotp($("#login-totp"), res.totp, $("#login-result"));  // uputa (ne greška), polje za kod dobiva fokus
        return;
      }
    } else {
      const npw = newPassword($("#login-newpw"), out);
      if (npw === null) return;
      res = await busy(btn, out, T("Provjeravam…"), () => api.admin_login($("#login-email").value.trim(), $("#login-password").value,
                                                                           $("#login-totp .totp-code").value, npw));
      if (res && res.password_change) { showNewPassword($("#login-newpw"), true); return; }
      if (res && npw && (res.ok || res.totp)) { $("#login-password").value = npw; showNewPassword($("#login-newpw"), false); }
      if (res && res.totp) { showTotp($("#login-totp"), res.totp, out); return; }  // lozinka ostaje do unosa koda
      $("#login-password").value = "";
      showTotp($("#login-totp"), null);
      if (res && !res.ok) $("#login-password").focus();
      if (res && res.ok) await showRecovery($("#login-totp-recovery"), res.recovery_codes);
    }
    if (res && res.ok) {
      wipeUserForm(form);
      form.hidden = true;
      $("#lock").hidden = true;
      await start();
    }
  };
}

$('#user-dialog [data-user="role"]').addEventListener("change", () => syncAdminTotp($("#user-dialog")));

$("#user-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const root = $("#user-dialog"), f = userForm(root), mismatch = passwordMismatch(f, false);  // novi bez lozinke = aktivacijski kod
  showUserErrors(root, mismatch);
  if (mismatch) return;
  if (editing) f.id = editing.id;
  const res = await busy($("#user-submit"), $("#user-result"), T("Spremam (sigurno spremanje lozinke traje sekundu)…"), () => api.user_save(f));
  if (!res) return;
  showUserErrors(root, res.errors);
  if (res.ok) {
    users = res.users;
    renderUsers();
    wipeUserForm(root);
    root.close();
    setResult($("#users-result"), res);
  }
});



window.addEventListener("pywebviewready", start);
