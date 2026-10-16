"""Upload alerts - email (SMTP) and chat webhooks (Microsoft Teams Workflows, Google Chat, Slack).

settings["alerts"] = {
    "notify_on": "failure" | "always" | "never",
    "email_to": "a@x.org, b@x.org", "email_from": "", "smtp_host": "", "smtp_port": 587,
    "smtp_security": "starttls" | "ssl" | "none", "smtp_user": "", "smtp_password": "<protected>",
    "webhook_url": "",
}
"""
from __future__ import annotations

import json
import smtplib
import socket
import ssl
import urllib.request
from email.message import EmailMessage

from .app_config import APP_NAME

DEFAULTS = {"notify_on": "failure", "email_to": "", "email_from": "", "smtp_host": "", "smtp_port": 587,
            "smtp_security": "starttls", "smtp_user": "", "smtp_password": "", "webhook_url": ""}

STATUS_WORDS = {"ok": "finished OK", "held": "was HELD by the safety net", "failed": "FAILED"}


def get(settings: dict) -> dict:
    a = dict(DEFAULTS)
    a.update(settings.get("alerts") or {})
    return a


def should_notify(alerts: dict, status: str) -> bool:
    mode = alerts.get("notify_on", "failure")
    if mode == "never":
        return False
    return mode == "always" or status != "ok"


def subject_for(profile_name: str, status: str) -> str:
    return f"[{APP_NAME}] Upload '{profile_name}' {STATUS_WORDS.get(status, status)} on {socket.gethostname()}"


def send_email(alerts: dict, subject: str, body: str, to: str | None = None, attachments=(), html: str = ""):
    """Send with the alert SMTP settings. `to` overrides the alert recipients (used by report emails)."""
    from .uploader import unprotect
    to = [x.strip() for x in (to if to is not None else alerts.get("email_to", "")).replace(";", ",").split(",")
          if x.strip()]
    if not to or not alerts.get("smtp_host"):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = alerts.get("email_from") or alerts.get("smtp_user") or to[0]
    msg["To"] = ", ".join(to)
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    for name, data, mime in attachments:
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=name)
    host, port = alerts["smtp_host"], int(alerts.get("smtp_port") or 587)
    sec = alerts.get("smtp_security", "starttls")
    ctx = ssl.create_default_context()
    if sec == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=30, context=ctx)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        if sec == "starttls":
            server.starttls(context=ctx)
    try:
        if alerts.get("smtp_user"):
            server.login(alerts["smtp_user"], unprotect(alerts.get("smtp_password", "")))
        server.send_message(msg)
    finally:
        server.quit()
    return True


def webhook_payload(url: str, subject: str, body: str) -> dict:
    short = body if len(body) < 3500 else body[-3500:]
    if any(k in url.lower() for k in ("logic.azure.com", "powerautomate", "powerplatform", "environment.api")):
        # Microsoft Teams "Workflows" (Power Automate) webhook - expects an Adaptive Card
        return {"type": "message", "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard",
                        "version": "1.4", "body": [
                            {"type": "TextBlock", "text": subject, "weight": "Bolder", "wrap": True},
                            {"type": "TextBlock", "text": short, "wrap": True, "fontType": "Monospace",
                             "size": "Small"}]}}]}
    return {"text": f"*{subject}*\n```\n{short}\n```"}  # Slack, Google Chat and most others


def send_webhook(alerts: dict, subject: str, body: str):
    url = (alerts.get("webhook_url") or "").strip()
    if not url:
        return False
    data = json.dumps(webhook_payload(url, subject, body)).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()
    return True


def notify(settings: dict, subject: str, body: str) -> list[str]:
    """Send to every configured channel. Returns what was sent; raises if every configured channel failed."""
    alerts = get(settings)
    sent, errors = [], []
    for name, fn in (("email", send_email), ("webhook", send_webhook)):
        try:
            if fn(alerts, subject, body):
                sent.append(name)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
    if errors and not sent:
        raise RuntimeError("; ".join(errors))
    return sent


def notify_run(profile: dict, status: str, log_text: str):
    from .paths import load_settings
    settings = load_settings()
    if should_notify(get(settings), status):
        notify(settings, subject_for(profile["name"], status), log_text)


def send_test(settings: dict) -> str:
    sent = notify(settings, f"[{APP_NAME}] Test alert from {socket.gethostname()}",
                  "This is a test. Upload alerts are working.")
    return "Sent by " + " and ".join(sent) if sent else "Nothing is set up yet (add an email or a webhook)."
