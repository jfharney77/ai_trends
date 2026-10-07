"""FastAPI backend for the AI Trends agent.

Endpoints
---------
GET  /api/health
GET  /api/config                 providers, default models, categories, email status
GET  /api/models?provider=...    model list for the provider (OpenRouter / Ollama)
POST /api/runs                   start a run in the background -> {id}
GET  /api/runs                   recent runs (summary)
GET  /api/runs/{id}              full run incl. progress and results
POST /api/runs/{id}/email        email a finished run
GET  /api/runs/{id}/digest.html  rendered HTML digest preview
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import config
import emailer
import storage
from categories import ALL_CATEGORY_IDS, CATEGORIES, resolve_categories
from daily_digest import pick_digest_provider
from graph import run_trends

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ai_trends")

app = FastAPI(title="AI Trends Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_lock = threading.Lock()


class RunRequest(BaseModel):
    category_ids: list[str] = Field(default_factory=list, description="Empty means all five")
    provider: str | None = None
    model: str | None = None
    email: bool = False
    email_to: list[str] | None = None


class EmailRequest(BaseModel):
    to: list[str] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update_run(run_id: str, **fields) -> dict:
    with _lock:
        run = storage.load_run(run_id) or {}
        run.update(fields)
        storage.save_run(run)
        return run


def execute_run(run_id: str) -> None:
    """Run the graph for a stored run record, writing progress as it goes."""
    run = storage.load_run(run_id)
    if not run:
        return
    _update_run(run_id, status="running", started_at=_now())

    def on_update(node: str, payload: dict) -> None:
        if node == "research_category":
            for r in payload.get("results", []):
                with _lock:
                    cur = storage.load_run(run_id) or {}
                    progress = cur.get("progress", {})
                    progress[r["category_id"]] = "error" if r.get("error") else "done"
                    results = [x for x in cur.get("results", []) if x["category_id"] != r["category_id"]] + [r]
                    cur.update(progress=progress, results=results)
                    storage.save_run(cur)
        elif node == "compose_overview":
            _update_run(run_id, overview=payload.get("overview", ""), progress_stage="overview")

    try:
        final = run_trends(run.get("category_ids") or None, run.get("provider"), run.get("model"), on_update=on_update)
        run = _update_run(
            run_id,
            status="done",
            finished_at=_now(),
            overview=final.get("overview", ""),
            results=final.get("results", []),
            progress={r["category_id"]: ("error" if r.get("error") else "done") for r in final.get("results", [])},
            provider=final.get("provider"),
            model=final.get("model"),
        )
        storage.save_digest_html(run_id, emailer.build_email_html(run))
        if run.get("email_requested"):
            try:
                sent = emailer.email_run(run, run.get("email_to") or None)
                _update_run(run_id, emailed_to=sent, emailed_at=_now())
            except Exception as exc:  # noqa: BLE001
                log.exception("email failed")
                _update_run(run_id, email_error=f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        log.exception("run %s failed", run_id)
        _update_run(run_id, status="failed", finished_at=_now(), error=f"{type(exc).__name__}: {exc}")


@app.get("/api/health")
def health():
    return {"ok": True, "time": _now()}


@app.get("/api/config")
def get_config():
    return {
        "default_provider": config.DEFAULT_PROVIDER,
        "providers": config.provider_status(),
        "categories": [{"id": c.id, "label": c.label, "description": c.description} for c in CATEGORIES],
        "search_backend": __import__("search").pick_backend()[0],
        "email": {
            "configured": bool(config.SMTP_USER and config.SMTP_PASSWORD),
            "to": config.EMAIL_TO,
            "digest_tz": config.DIGEST_TZ,
            "digest_hour": config.DIGEST_HOUR,
        },
    }


@app.get("/api/models")
def list_models(provider: str):
    provider = provider.lower()
    try:
        if provider == "ollama":
            r = httpx.get(f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=5)
            r.raise_for_status()
            return {"provider": provider, "models": sorted(m["name"] for m in r.json().get("models", []))}
        if provider == "openrouter":
            r = httpx.get(f"{config.OPENROUTER_BASE_URL.rstrip('/')}/models", timeout=15)
            r.raise_for_status()
            ids = sorted(m["id"] for m in r.json().get("data", []))
            return {"provider": provider, "models": ids}
        if provider == "anthropic":
            return {"provider": provider, "models": ["claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5-20251001"]}
        if provider == "openai":
            return {"provider": provider, "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini", "o4-mini"]}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not list models for {provider}: {exc}") from exc
    raise HTTPException(status_code=400, detail=f"Unknown provider {provider!r}")


@app.post("/api/runs", status_code=202)
def create_run(req: RunRequest, background: BackgroundTasks):
    try:
        cats = resolve_categories(req.category_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    provider = (req.provider or config.DEFAULT_PROVIDER).lower()
    try:
        config.validate_provider(provider)
    except config.ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run_id = storage.new_run_id()
    run = {
        "id": run_id,
        "status": "queued",
        "source": "web",
        "created_at": _now(),
        "provider": provider,
        "model": req.model or config.DEFAULT_MODELS[provider],
        "category_ids": [c.id for c in cats],
        "progress": {c.id: "pending" for c in cats},
        "results": [],
        "overview": "",
        "email_requested": req.email,
        "email_to": req.email_to,
    }
    storage.save_run(run)
    background.add_task(execute_run, run_id)
    return {"id": run_id, "status": "queued"}


@app.post("/api/digest", status_code=202)
def run_digest(background: BackgroundTasks):
    """Do exactly what the 8 AM cron job does: all five categories, the digest
    provider (falling back to any configured one), then email EMAIL_TO."""
    if not (config.SMTP_USER and config.SMTP_PASSWORD):
        raise HTTPException(status_code=400, detail="SMTP_USER and SMTP_PASSWORD must be set in backend/.env before sending email")
    provider = pick_digest_provider(config.DIGEST_PROVIDER)
    if provider is None:
        raise HTTPException(status_code=400, detail="No LLM provider is configured (set OPENROUTER_API_KEY or another provider in backend/.env)")
    run_id = storage.new_run_id()
    run = {
        "id": run_id,
        "status": "queued",
        "source": "digest",
        "created_at": _now(),
        "provider": provider,
        "model": config.DEFAULT_MODELS[provider],
        "category_ids": ALL_CATEGORY_IDS,
        "progress": {c: "pending" for c in ALL_CATEGORY_IDS},
        "results": [],
        "overview": "",
        "email_requested": True,
        "email_to": config.EMAIL_TO,
    }
    storage.save_run(run)
    background.add_task(execute_run, run_id)
    return {"id": run_id, "status": "queued", "provider": provider, "email_to": config.EMAIL_TO}


@app.get("/api/runs")
def get_runs(limit: int = 30):
    return {"runs": storage.list_runs(limit)}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    try:
        run = storage.load_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.post("/api/runs/{run_id}/email")
def email_run(run_id: str, req: EmailRequest):
    run = storage.load_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    if run.get("status") != "done":
        raise HTTPException(status_code=409, detail="run is not finished")
    try:
        sent = emailer.email_run(run, req.to or None)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    _update_run(run_id, emailed_to=sent, emailed_at=_now(), email_error=None)
    return {"sent_to": sent}


@app.get("/api/runs/{run_id}/digest.html", response_class=HTMLResponse)
def digest_html(run_id: str):
    run = storage.load_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return emailer.build_email_html(run)


@app.get("/api/categories")
def categories():
    return {"categories": ALL_CATEGORY_IDS}
