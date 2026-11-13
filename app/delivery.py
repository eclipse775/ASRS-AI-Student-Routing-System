"""Optional SMTP delivery. Credentials are server-side and never returned by the API."""
from email.message import EmailMessage
import os
import re
import smtplib
import ssl
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def gateway_status():
    host, sender = os.environ.get("SMTP_HOST", "").strip(), os.environ.get("SMTP_FROM", "").strip()
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        port = 0
    user, password = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", "")
    email_ready = bool(host and 1 <= port <= 65535 and EMAIL_RE.fullmatch(sender) and bool(user) == bool(password))
    return {"email_configured": email_ready}


def send_email(target, subject, body):
    config = gateway_status()
    if not config["email_configured"] or not EMAIL_RE.fullmatch(target or ""):
        return False, "email_unavailable"
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
        message = EmailMessage()
        message["From"] = os.environ["SMTP_FROM"].strip()
        message["To"] = target
        message["Subject"] = subject[:160]
        message.set_content(body[:2000])
        timeout = 8
        if port == 465:
            with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, timeout=timeout,
                                  context=ssl.create_default_context()) as client:
                if os.environ.get("SMTP_USER"):
                    client.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                client.send_message(message)
        else:
            with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=timeout) as client:
                if os.environ.get("SMTP_STARTTLS", "1").lower() not in ("0", "false", "no"):
                    client.starttls(context=ssl.create_default_context())
                if os.environ.get("SMTP_USER"):
                    client.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                client.send_message(message)
        return True, ""
    except (OSError, smtplib.SMTPException, ssl.SSLError, TimeoutError):
        return False, "email_delivery_failed"


def deliver(channel, target, subject, body):
    if channel != "email":
        return False, "unsupported_channel"
    return send_email(target, subject, body)


def safe_alert_reason(kind, raw_reason):
    if kind == "escalation":
        return "A missed emergency was reported."
    match = re.fullmatch(r"Emergency signals detected: ([A-Za-z0-9_, -]{1,240})", raw_reason or "")
    return "Emergency signals detected: " + match.group(1) if match else "An urgent safety alert requires attention."
