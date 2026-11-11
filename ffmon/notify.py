"""Delivery: phone push via ntfy.sh, and/or email via SMTP (Gmail app password)."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

import requests


def push_ntfy(title: str, body: str, urgent: bool, click: str | None = None) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
    requests.post(f"{server}/{topic}", data=body.encode("utf-8"), timeout=30, headers={
        "Title": title.encode("utf-8"),
        "Priority": "high" if urgent else "default",
        "Tags": "rotating_light" if urgent else "football",
        **({"Click": click} if click else {}),
    }).raise_for_status()


def send_email(subject: str, body: str) -> None:
    to, user, pw = (os.environ.get(k) for k in ("EMAIL_TO", "SMTP_USER", "SMTP_PASS"))
    if not (to and user and pw):
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(body)
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    with smtplib.SMTP_SSL(host, int(os.environ.get("SMTP_PORT", 465)), timeout=30) as s:
        s.login(user, pw)
        s.send_message(msg)


def deliver(title: str, body: str, urgent: bool, click: str | None = None) -> list[str]:
    errors = []
    for name, fn in (("ntfy", lambda: push_ntfy(title, body, urgent, click)),
                     ("email", lambda: send_email(title, body))):
        try:
            fn()
        except Exception as e:  # keep going if one channel fails
            errors.append(f"{name}: {e}")
    return errors
