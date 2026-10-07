"""Persist runs as JSON files so the UI can show history and the digest can
reuse the latest result."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import config


def _ensure_dirs() -> None:
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    config.DIGESTS_DIR.mkdir(parents=True, exist_ok=True)


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]


def run_path(run_id: str) -> Path:
    if "/" in run_id or ".." in run_id:
        raise ValueError("bad run id")
    return config.RUNS_DIR / f"{run_id}.json"


def save_run(run: dict) -> Path:
    _ensure_dirs()
    path = run_path(run["id"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(run, indent=2, ensure_ascii=False))
    tmp.replace(path)
    return path


def load_run(run_id: str) -> dict | None:
    path = run_path(run_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_runs(limit: int = 50) -> list[dict]:
    _ensure_dirs()
    runs = []
    for path in sorted(config.RUNS_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        runs.append(
            {
                "id": data.get("id"),
                "status": data.get("status"),
                "created_at": data.get("created_at"),
                "finished_at": data.get("finished_at"),
                "provider": data.get("provider"),
                "model": data.get("model"),
                "category_ids": data.get("category_ids", []),
                "trend_count": sum(len(r.get("trends", [])) for r in data.get("results", [])),
                "source": data.get("source", "web"),
                "emailed_to": data.get("emailed_to"),
            }
        )
    return runs


def save_digest_html(run_id: str, html: str) -> Path:
    _ensure_dirs()
    path = config.DIGESTS_DIR / f"{run_id}.html"
    path.write_text(html)
    return path
