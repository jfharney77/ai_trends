#!/usr/bin/env python3
"""Cron entry point: research all five categories and email the briefing.

Usage:
    python daily_digest.py                 # run now and send
    python daily_digest.py --no-email      # run and save, do not send
    python daily_digest.py --only-at-hour 8 --tz America/New_York
                                           # exit quietly unless local hour == 8
                                           # (lets a UTC crontab hit 8 AM Eastern across DST)
    python daily_digest.py --to a@b.com    # override EMAIL_TO

Recipients default to EMAIL_TO in backend/.env (jfharney@gmail.com unless changed).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config
import emailer
import storage
from graph import run_trends

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("daily_digest")


def pick_digest_provider(preferred: str) -> str | None:
    """Return the preferred provider if configured, else the first configured
    fallback (so a missing API key does not silently kill the morning email)."""
    try:
        config.validate_provider(preferred)
        return preferred
    except config.ConfigError as exc:
        log.warning("Provider %s unavailable: %s", preferred, exc)
    for alt in config.PROVIDERS:
        if alt == preferred:
            continue
        try:
            config.validate_provider(alt)
            log.warning("Falling back to provider %s", alt)
            return alt
        except config.ConfigError:
            continue
    log.error("No LLM provider is configured. Set OPENROUTER_API_KEY (or another provider) in backend/.env")
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-email", action="store_true", help="run and save but do not send email")
    ap.add_argument("--to", action="append", help="recipient (repeatable); overrides EMAIL_TO")
    ap.add_argument("--provider", default=config.DIGEST_PROVIDER, help="LLM provider for the digest")
    ap.add_argument("--model", default=None, help="model override")
    ap.add_argument("--categories", default="", help="comma-separated category ids (default: all)")
    ap.add_argument("--only-at-hour", type=int, default=None, help="exit 0 unless the local hour in --tz equals this")
    ap.add_argument("--tz", default=config.DIGEST_TZ, help="IANA timezone for --only-at-hour")
    args = ap.parse_args(argv)

    if args.only_at_hour is not None:
        now_local = datetime.now(ZoneInfo(args.tz))
        if now_local.hour != args.only_at_hour:
            log.info("Local time is %s; not %02d:00 in %s. Skipping.", now_local.strftime("%H:%M"), args.only_at_hour, args.tz)
            return 0

    provider = pick_digest_provider(args.provider)
    if provider is None:
        return 2
    args.provider = provider

    run_id = storage.new_run_id()
    cats = [c for c in args.categories.split(",") if c.strip()]
    run = {
        "id": run_id,
        "status": "running",
        "source": "cron",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": args.provider,
        "model": args.model or config.DEFAULT_MODELS[args.provider],
        "category_ids": cats,
        "results": [],
        "overview": "",
    }
    storage.save_run(run)
    log.info("Run %s starting with %s", run_id, config.describe_llm(args.provider, args.model))

    try:
        final = run_trends(cats or None, args.provider, args.model)
    except Exception as exc:  # noqa: BLE001
        run.update(status="failed", error=f"{type(exc).__name__}: {exc}", finished_at=datetime.now(timezone.utc).isoformat())
        storage.save_run(run)
        log.exception("run failed")
        return 1

    run.update(
        status="done",
        finished_at=datetime.now(timezone.utc).isoformat(),
        category_ids=final.get("category_ids", cats),
        results=final.get("results", []),
        overview=final.get("overview", ""),
        progress={r["category_id"]: ("error" if r.get("error") else "done") for r in final.get("results", [])},
    )
    storage.save_run(run)
    path = storage.save_digest_html(run_id, emailer.build_email_html(run))
    log.info("Saved digest HTML to %s", path)

    if args.no_email:
        log.info("--no-email given; not sending.")
        return 0
    try:
        sent = emailer.email_run(run, args.to)
    except Exception as exc:  # noqa: BLE001
        run.update(email_error=f"{type(exc).__name__}: {exc}")
        storage.save_run(run)
        log.exception("email failed")
        return 1
    run.update(emailed_to=sent, emailed_at=datetime.now(timezone.utc).isoformat())
    storage.save_run(run)
    log.info("Emailed digest to %s", ", ".join(sent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
