# AI Trends

A LangGraph agent that searches the web for the latest developments in five areas of AI and summarizes them with the model of your choice. Results arrive two ways: a React web page where you run the agent on demand, and a daily email at 8 AM Eastern driven by cron.

Categories:

1. Personalization and AI
2. Agent observability and monitoring
3. Agent memory
4. Agent orchestration
5. New AI models (LLMs, decision and reasoning models, anything else)

## How it works

```
START -> plan -> research_category (x5, in parallel via Send) -> compose_overview -> END
```

- `plan` resolves the requested categories.
- `research_category` runs once per category. It issues the category's search queries through DuckDuckGo (or Tavily when a key is present), then asks the LLM to turn the raw results into 3 to 6 trends, each with a summary, why it matters, and source URLs. Source URLs are checked against the actual search results; the UI marks any the model made up.
- `compose_overview` writes a short cross-category paragraph.

Each run is saved as JSON under `backend/data/runs/` and rendered to HTML under `backend/data/digests/`, so the web UI's history and the email use the same data.

## Layout

```
backend/
  main.py           FastAPI app (runs, history, model lists, email)
  graph.py          LangGraph workflow
  config.py         provider factory: openrouter | ollama | anthropic | openai
  search.py         web search (ddgs default, Tavily optional)
  categories.py     the five categories and their search queries
  emailer.py        HTML/plain-text email rendering and SMTP send
  storage.py        JSON persistence of runs
  daily_digest.py   cron entry point
  tests/            pytest suite (no network needed)
frontend/           Vite + React UI
scripts/            start/stop scripts and cron installer
```

## Setup

### 1. Backend configuration

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

| Setting | Purpose |
| --- | --- |
| `LLM_PROVIDER` | Default provider. `openrouter` (default), `ollama`, `anthropic`, or `openai`. The UI can override per run. |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | OpenRouter credentials and default model. |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Local Ollama. From WSL, use the Windows host IP, not localhost. The example file is pre-filled with your current gateway IP. |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | Optional direct accounts. |
| `TAVILY_API_KEY` | Optional. When set, search uses Tavily instead of DuckDuckGo. |
| `EMAIL_TO` | Comma-separated recipients. Defaults to jfharney@gmail.com. |
| `SMTP_USER`, `SMTP_PASSWORD` | Gmail address and an App Password (Google Account, Security, App passwords; requires 2-step verification). |
| `DIGEST_PROVIDER` | Provider for the morning email. Falls back to any configured provider if the preferred one has no key. |
| `DIGEST_TZ`, `DIGEST_HOUR` | When the email goes out. Default `America/New_York` at 8. |

### 2. Run the web app

```bash
scripts/start_all.sh        # backend on :8000 in the background, frontend on :5173
scripts/stop_all.sh
```

Or separately with `scripts/start_backend.sh` and `scripts/start_frontend.sh`. Open http://localhost:5173.

In the UI, pick categories, a provider, and a model. The model box offers the live model list from OpenRouter or your Ollama install. Progress shows per category while the graph runs. When done, you can preview the email HTML or send it to any address.

### 3. Daily email

```bash
scripts/install_cron.sh
```

This adds a crontab line that runs `scripts/run_daily_digest.sh`. Cron does not understand daylight saving, so the entry fires at each local hour that can correspond to 8 AM Eastern, and the wrapper exits immediately unless it is actually 8:00 in `DIGEST_TZ`. Output goes to `logs/daily_digest.log`. Remove it with `scripts/uninstall_cron.sh`.

Cron must be running in WSL. Check with `pgrep cron`; start it with `sudo service cron start`, or enable systemd in `/etc/wsl.conf` and run `sudo systemctl enable --now cron`. WSL itself must be up at 8 AM for the job to fire.

Test the digest without waiting:

```bash
cd backend && source .venv/bin/activate
python daily_digest.py --no-email            # run and save, no send
python daily_digest.py --to you@example.com  # run and send to one address
python daily_digest.py --provider ollama     # force a provider
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/config` | Providers, default models, categories, email status |
| GET | `/api/models?provider=` | Model list for a provider |
| POST | `/api/runs` | Start a run. Body: `category_ids`, `provider`, `model`, `email` |
| GET | `/api/runs` | Recent runs |
| GET | `/api/runs/{id}` | Full run with progress and results |
| POST | `/api/digest` | Same as the cron job: all categories, digest provider, email `EMAIL_TO` |
| POST | `/api/runs/{id}/email` | Email a finished run. Body: `to` (optional list) |
| GET | `/api/runs/{id}/digest.html` | Rendered email preview |

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q
```

The suite runs the graph with a fake LLM and fake search, exercises the API with FastAPI's test client, and checks the email renderer and the cron hour guard.
