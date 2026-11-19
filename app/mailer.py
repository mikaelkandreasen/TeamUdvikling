"""Udgående e-mail (SMTP, kun standardbibliotek) og validering af e-mailadresser.

Opsætning sker udelukkende via miljøvariabler (se compose.yaml): SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
SMTP_FROM, SMTP_SECURITY (starttls | ssl | none) og PUBLIC_URL (bruges til links i mails – aldrig Host-headeren).
"""
import re
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app

_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                 r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")


def normalize_email(raw):
    """Returnerer (adresse|None, fejltekst|None). Tom streng = ingen adresse. Afviser linjeskift (header-injektion)."""
    s = (raw or "").strip()
    if not s:
        return None, None
    if len(s) > 254 or not _RE.match(s):
        return None, "Ugyldig e-mailadresse."
    return s.lower(), None


def public_url():
    u = (current_app.config.get("PUBLIC_URL") or "").strip().rstrip("/")
    return u if u.startswith(("https://", "http://")) else ""


def configured():
    c = current_app.config
    return c.get("MAIL_BACKEND") == "memory" or bool(c.get("SMTP_HOST") and c.get("SMTP_FROM"))


def missing():
    """Kort forklaring på hvad der mangler, så administratoren ved hvad der skal sættes i Dockhand. Tom = klar."""
    todo = []
    if not configured():
        todo.append("SMTP_HOST og SMTP_FROM")
    if not public_url():
        todo.append("PUBLIC_URL (fx https://teamudvikling.saem.dk)")
    return " og ".join(todo)


def send(to, subject, body):
    c = current_app.config
    if c.get("MAIL_BACKEND") == "memory":                      # kun til tests
        current_app.extensions.setdefault("outbox", []).append({"to": to, "subject": subject, "body": body})
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = c["SMTP_FROM"], to, subject      # ValueError ved linjeskift i headere
    msg.set_content(body)
    sec = (c.get("SMTP_SECURITY") or "starttls").lower()
    ctx = ssl.create_default_context()
    port = int(c.get("SMTP_PORT") or (465 if sec == "ssl" else 587))
    srv = smtplib.SMTP_SSL(c["SMTP_HOST"], port, timeout=15, context=ctx) if sec == "ssl" else smtplib.SMTP(c["SMTP_HOST"], port, timeout=15)
    with srv:
        if sec == "starttls":
            srv.starttls(context=ctx)
        if c.get("SMTP_USER"):
            srv.login(c["SMTP_USER"], c.get("SMTP_PASSWORD") or "")
        srv.send_message(msg)
