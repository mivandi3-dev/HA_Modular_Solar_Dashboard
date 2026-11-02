"""Slanje e-pošte (mailer.cpp, alerts.cpp send_mail): servis Resend (HTML predložak na jeziku postavki, svaki primatelj
zasebno) ili vlastiti SMTP (STARTTLS / SSL / bez zaštite). U HA verziji nema korisnika, pa ni aktivacijskih kodova."""
from __future__ import annotations

import html
import json
import smtplib
import ssl
import time
import uuid
from email.message import EmailMessage
from email.utils import formatdate
from typing import Any

from .config import parse_recipients, valid_host_name, valid_resend_key
from .i18n import language, tr
from .netinfo import http_request, source_ip
from .util import log

RESEND_BATCH_URL = "https://api.resend.com/emails/batch"
MAIL_FROM_ALERTS = "Solar Dashboard <modular@solardashboard.bid>"
RESEND_BATCH_MAX = 100
TIMEOUT_S = 30


class MailError(RuntimeError):
    pass


def _frame(lang: str, preheader: str, inner: str, foot: str) -> str:
    e = html.escape
    return (f'<!DOCTYPE html><html lang="{e(lang)}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark">'
            "<title>Solar Dashboard</title></head>"
            '<body style="margin:0;padding:0;background:#0b1020;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#0f172a">'
            f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{e(preheader)}</div>'
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b1020;padding:32px 12px"><tr><td align="center">'
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border-radius:18px;overflow:hidden">'
            '<tr><td style="background:linear-gradient(135deg,#0ea5e9,#1d4ed8);background-color:#1d4ed8;padding:22px 28px;color:#ffffff;'
            'font-size:20px;font-weight:700;letter-spacing:.3px">&#9728;&#65039; Solar Dashboard</td></tr>'
            f'<tr><td style="padding:28px 28px 8px 28px;font-size:15px;line-height:1.6">{inner}</td></tr>'
            f'<tr><td style="padding:8px 28px 26px 28px;font-size:12px;line-height:1.5;color:#64748b">{foot}</td></tr>'
            "</table></td></tr></table></body></html>")


def _paragraphs(text: str) -> str:
    parts = [p for p in text.split("\n\n") if p.strip()]
    return "".join('<p style="margin:0 0 14px 0">' + html.escape(p.strip("\n")).replace("\n", "<br>") + "</p>" for p in parts)


def alert_mail(subj: str, body: str, plant: str) -> dict[str, str]:
    note = tr("Ovo je automatska poruka Solarnog monitora ({plant}). Primatelje obavijesti mijenjate u Postavke → Obavijesti.",
              {"plant": plant})
    inner = f'<h1 style="margin:0 0 16px 0;font-size:19px;line-height:1.35;color:#0f172a">{html.escape(subj)}</h1>' + _paragraphs(body)
    return {"subject": subj, "html": _frame(language(), subj, inner, html.escape(note) + "<br>Solar Dashboard &middot; modular@solardashboard.bid"),
            "text": f"{body}\n\n— {note}\n"}


def _resend_error(status: int, body: bytes) -> str:
    try:
        detail = str(json.loads(body).get("message", ""))
    except (ValueError, AttributeError):
        detail = ""
    detail = (detail or body.decode("utf-8", "replace"))[:300]
    if status in (401, 403):
        return tr("Resend je odbio API ključ ({error}).", {"error": detail})
    if status == 422:
        return tr("Resend nije prihvatio poruku: {error}", {"error": detail})
    if status == 429:
        return tr("Resend: previše poruka u kratkom vremenu, pokušajte ponovno za minutu.")
    return tr("Resend je javio grešku {status}: {error}", {"status": status, "error": detail})


def resend_send(s: dict[str, Any], key: str, recipients: list[str], m: dict[str, str]) -> None:
    if not valid_resend_key(key):
        raise MailError(tr("API ključ servisa Resend nije ispravan (počinje s re_)."))
    batch = [{"from": MAIL_FROM_ALERTS, "to": [r], "subject": m["subject"], "html": m["html"], "text": m["text"]}
             for r in recipients]
    try:
        status, body = http_request(RESEND_BATCH_URL, TIMEOUT_S, source_ip(s["internet_interface"]), "POST",
                                    json.dumps(batch).encode("utf-8"),
                                    {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                     "Idempotency-Key": uuid.uuid4().hex})
    except OSError as e:
        raise MailError(tr("Internet nije dostupan: {error}", {"error": e})) from e
    if status >= 300:
        raise MailError(_resend_error(status, body))


def smtp_send(s: dict[str, Any], password: str, sender: str, recipients: list[str], subj: str, body: str) -> None:
    if not valid_host_name(s["smtp_host"]):
        raise MailError(tr("Upišite naziv ili IP adresu poslužitelja e-pošte."))
    for v in (sender, s["smtp_user"], *recipients):
        if any(ord(c) < 0x20 or ord(c) == 0x7F for c in v):
            raise MailError(tr("Postavke e-pošte sadrže nedopušten znak (novi red ili kontrolni znak)."))
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "undisclosed-recipients:;"  # primatelji samo u omotnici (audit C-06)
    msg["Subject"] = subj
    msg["Date"] = formatdate()
    msg["Message-ID"] = f"<{int(time.time())}.{uuid.uuid4().hex[:12]}@solarni-monitor>"
    msg.set_content(body)
    src = source_ip(s["internet_interface"])
    addr = (src, 0) if src else None
    host, port = s["smtp_host"], s["smtp_port"]
    try:
        if s["smtp_security"] == "ssl":
            client: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=40, source_address=addr, context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(host, port, timeout=40, source_address=addr)
        with client:
            if s["smtp_security"] == "starttls":
                client.starttls(context=ssl.create_default_context())
            if s["smtp_user"]:
                client.login(s["smtp_user"], password)
            client.send_message(msg, from_addr=sender, to_addrs=recipients)
    except smtplib.SMTPAuthenticationError as e:
        raise MailError(tr("Poslužitelj e-pošte odbio je korisničko ime ili lozinku.")) from e
    except (TimeoutError, OSError) as e:
        if isinstance(e, smtplib.SMTPException):
            raise MailError(tr("Poslužitelj e-pošte javio je grešku: {error}", {"error": e})) from e
        raise MailError(tr("Nije moguće spojiti se na {host}:{port} ({error}).", {"host": host, "port": port, "error": e})) from e


def send_mail(s: dict[str, Any], subj: str, body: str, secret: str | None = None) -> list[str]:
    """Pošalji svim primateljima iz postavki; secret = ključ/lozinka iz obrasca (probna poruka). Vraća primatelje."""
    recipients, bad = parse_recipients(s["alert_emails"])
    if recipients is None:
        raise MailError(tr("Neispravna adresa e-pošte: {address}", {"address": bad}))
    recipients = recipients[:RESEND_BATCH_MAX]
    if s["mail_provider"] == "resend":
        if not recipients:
            raise MailError(tr("Upišite barem jednu adresu primatelja."))
        key = secret or s["resend_api_key_enc"]
        if not key:
            raise MailError(tr("Slanje e-pošte nije podešeno (Postavke → Obavijesti → API ključ servisa Resend)."))
        resend_send(s, key, recipients, alert_mail(subj, body, s["plant_name"]))
    else:
        if not recipients or not s["smtp_host"]:
            raise MailError(tr("Upišite SMTP poslužitelj i barem jednu adresu primatelja."))
        sender = s["smtp_from"] or s["smtp_user"] or recipients[0]
        smtp_send(s, (secret or s["smtp_password_enc"]) if s["smtp_user"] else "", sender, recipients, subj, body)
    log.info("E-pošta „%s“ poslana na %d adresa", subj, len(recipients))
    return recipients
