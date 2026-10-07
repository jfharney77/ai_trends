import json

import pytest
from fastapi.testclient import TestClient

import config
import emailer
import main
import storage


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(config, "DIGESTS_DIR", tmp_path / "digests")
    yield


SAMPLE_RUN = {
    "id": "r1",
    "status": "done",
    "provider": "openrouter",
    "model": "m",
    "created_at": "2026-10-07T12:00:00+00:00",
    "finished_at": "2026-10-07T12:01:00+00:00",
    "overview": "Big <picture>.",
    "results": [
        {
            "category_id": "models",
            "category_label": "New AI models",
            "headline": "H",
            "trends": [
                {"title": "T & co", "summary": "S", "why_it_matters": "W", "sources": ["https://www.example.com/x"]}
            ],
        }
    ],
}


def test_email_html_escapes_and_links():
    html = emailer.build_email_html(SAMPLE_RUN)
    assert "Big &lt;picture&gt;." in html
    assert "T &amp; co" in html
    assert 'href="https://www.example.com/x"' in html and ">example.com<" in html
    text = emailer.build_email_text(SAMPLE_RUN)
    assert "* T & co" in text
    assert "(1 trends)" in emailer.build_subject(SAMPLE_RUN)


def test_create_run_validates_and_executes(monkeypatch):
    monkeypatch.setattr(config, "validate_provider", lambda p: None)
    monkeypatch.setattr(
        main,
        "run_trends",
        lambda cats, p, m, on_update=None: {
            "category_ids": cats,
            "results": [{"category_id": "memory", "category_label": "Agent memory", "headline": "h", "trends": []}],
            "overview": "o",
            "provider": p,
            "model": m,
        },
    )
    client = TestClient(main.app)
    bad = client.post("/api/runs", json={"category_ids": ["nope"]})
    assert bad.status_code == 400

    r = client.post("/api/runs", json={"category_ids": ["memory"], "provider": "openrouter", "model": "m"})
    assert r.status_code == 202
    run_id = r.json()["id"]
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "done"
    assert run["overview"] == "o"
    assert run["progress"] == {"memory": "done"}
    assert (config.DIGESTS_DIR / f"{run_id}.html").exists()
    assert client.get("/api/runs").json()["runs"][0]["id"] == run_id
    assert client.get(f"/api/runs/{run_id}/digest.html").status_code == 200


def test_email_endpoint_requires_finished_run(monkeypatch):
    storage.save_run({**SAMPLE_RUN, "status": "running"})
    client = TestClient(main.app)
    assert client.post("/api/runs/r1/email", json={}).status_code == 409
    storage.save_run(SAMPLE_RUN)
    monkeypatch.setattr(emailer, "email_run", lambda run, to=None: to or ["x@y.z"])
    r = client.post("/api/runs/r1/email", json={"to": ["a@b.c"]})
    assert r.json() == {"sent_to": ["a@b.c"]}
    assert storage.load_run("r1")["emailed_to"] == ["a@b.c"]


def test_config_endpoint_lists_categories():
    client = TestClient(main.app)
    data = client.get("/api/config").json()
    assert [c["id"] for c in data["categories"]] == ["personalization", "observability", "memory", "orchestration", "models"]
    assert set(data["providers"]) == {"openrouter", "ollama", "anthropic", "openai"}


def test_digest_endpoint_mirrors_cron(monkeypatch):
    monkeypatch.setattr(config, "SMTP_USER", "u")
    monkeypatch.setattr(config, "SMTP_PASSWORD", "p")
    monkeypatch.setattr(config, "EMAIL_TO", ["me@example.com"])
    monkeypatch.setattr(main, "pick_digest_provider", lambda pref: "ollama")
    monkeypatch.setattr(
        main, "run_trends",
        lambda cats, p, m, on_update=None: {"category_ids": cats, "results": [], "overview": "o", "provider": p, "model": m},
    )
    sent = {}
    monkeypatch.setattr(emailer, "email_run", lambda run, to=None: sent.setdefault("to", to))
    client = TestClient(main.app)
    r = client.post("/api/digest")
    assert r.status_code == 202
    run = client.get(f"/api/runs/{r.json()['id']}").json()
    assert run["source"] == "digest" and run["provider"] == "ollama"
    assert run["category_ids"] == ["personalization", "observability", "memory", "orchestration", "models"]
    assert run["emailed_to"] == ["me@example.com"] and sent["to"] == ["me@example.com"]


def test_digest_endpoint_requires_smtp(monkeypatch):
    monkeypatch.setattr(config, "SMTP_PASSWORD", "")
    assert TestClient(main.app).post("/api/digest").status_code == 400
