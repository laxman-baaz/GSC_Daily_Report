"""Minimal HTML email sender over SMTP (Gmail/Workspace app-password, or any SMTP)."""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()


def send_email(subject, html, to=None):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASS")
    to = to or os.getenv("REPORT_TO") or user
    if not (host and user and pw and to):
        raise RuntimeError("Set SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / REPORT_TO in .env.")

    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, pw)
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
    return to
