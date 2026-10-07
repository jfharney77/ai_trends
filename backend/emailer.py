"""Render a run as an HTML/plain-text email and send it over SMTP."""

from __future__ import annotations

import html
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

import config

log = logging.getLogger(__name__)


def _esc(s: str | None) -> str:
    return html.escape(s or "")


def _domain(url: str) -> str:
    try:
        return url.split("//", 1)[1].split("/", 1)[0].removeprefix("www.")
    except IndexError:
        return url


def build_subject(run: dict) -> str:
    when = datetime.now(ZoneInfo(config.DIGEST_TZ)).strftime("%a %b %d, %Y")
    n = sum(len(r.get("trends", [])) for r in run.get("results", []))
    return f"AI Trends Briefing — {when} ({n} trends)"


def build_email_html(run: dict) -> str:
    when = datetime.now(ZoneInfo(config.DIGEST_TZ)).strftime("%A, %B %d, %Y")
    sections = []
    for r in run.get("results", []):
        trend_html = []
        for t in r.get("trends", []):
            links = " · ".join(
                f'<a href="{_esc(u)}" style="color:#0d6efd;text-decoration:none;">{_esc(_domain(u))}</a>'
                for u in t.get("sources", [])[:4]
            )
            trend_html.append(
                f"""
                <div style="margin:0 0 18px 0;">
                  <div style="font-weight:600;font-size:15px;color:#111;">{_esc(t.get('title'))}</div>
                  <div style="margin-top:4px;color:#333;line-height:1.5;">{_esc(t.get('summary'))}</div>
                  <div style="margin-top:4px;color:#555;line-height:1.5;"><span style="color:#777;">Why it matters:</span> {_esc(t.get('why_it_matters'))}</div>
                  <div style="margin-top:4px;font-size:13px;">{links}</div>
                </div>"""
            )
        err = r.get("error")
        err_html = (
            f'<div style="color:#9a3412;font-size:13px;margin-bottom:12px;">Problem: {_esc(err)}</div>' if err else ""
        )
        if not trend_html:
            trend_html.append('<div style="color:#777;">No trends found for this category.</div>')
        sections.append(
            f"""
            <div style="margin:28px 0 0 0;">
              <h2 style="font-size:18px;margin:0 0 6px 0;color:#111;">{_esc(r.get('category_label'))}</h2>
              <div style="color:#444;margin:0 0 14px 0;line-height:1.5;">{_esc(r.get('headline'))}</div>
              {err_html}
              {''.join(trend_html)}
            </div>"""
        )
    meta = f"Generated {_esc(run.get('finished_at') or run.get('created_at'))} using {_esc(run.get('provider'))}/{_esc(run.get('model'))}."
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f5f6f8;">
<div style="max-width:680px;margin:0 auto;padding:28px 20px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#fff;color:#111;">
  <h1 style="font-size:22px;margin:0;">AI Trends Briefing</h1>
  <div style="color:#666;font-size:14px;margin-top:4px;">{_esc(when)}</div>
  <p style="margin:20px 0 0 0;line-height:1.6;color:#222;">{_esc(run.get('overview'))}</p>
  {''.join(sections)}
  <div style="margin-top:32px;padding-top:14px;border-top:1px solid #e5e7eb;color:#888;font-size:12px;">{meta}</div>
</div>
</body></html>"""


def build_email_text(run: dict) -> str:
    lines = ["AI Trends Briefing", "", run.get("overview", ""), ""]
    for r in run.get("results", []):
        lines += [r.get("category_label", "").upper(), r.get("headline", ""), ""]
        for t in r.get("trends", []):
            lines.append(f"* {t.get('title')}")
            lines.append(f"  {t.get('summary')}")
            lines.append(f"  Why it matters: {t.get('why_it_matters')}")
            for u in t.get("sources", [])[:4]:
                lines.append(f"  {u}")
            lines.append("")
    lines.append(f"Generated with {run.get('provider')}/{run.get('model')}.")
    return "\n".join(lines)


def send_email(subject: str, html_body: str, text_body: str, to: list[str] | None = None) -> list[str]:
    """Send the message; returns the recipient list. Raises on misconfiguration."""
    recipients = to or config.EMAIL_TO
    if not recipients:
        raise RuntimeError("EMAIL_TO is empty; set it in backend/.env")
    if not config.SMTP_HOST or not config.SMTP_USER or not config.SMTP_PASSWORD:
        raise RuntimeError("SMTP_HOST, SMTP_USER and SMTP_PASSWORD must be set in backend/.env")
    sender = config.EMAIL_FROM or config.SMTP_USER

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=60) as server:
        if config.SMTP_USE_TLS:
            server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.sendmail(sender, recipients, msg.as_string())
    log.info("Sent digest to %s", recipients)
    return recipients


def email_run(run: dict, to: list[str] | None = None) -> list[str]:
    return send_email(build_subject(run), build_email_html(run), build_email_text(run), to)
