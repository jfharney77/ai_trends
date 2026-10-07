"""Environment-driven configuration and LLM provider factory.

Providers:
    openrouter (default)  — OpenAI-compatible API at https://openrouter.ai/api/v1
    ollama                — local models, reachable from WSL via the Windows host IP
    anthropic             — Anthropic API
    openai                — OpenAI API

Every provider is selected by LLM_PROVIDER in .env and can be overridden per
request from the web UI. Model names can likewise be overridden per request.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", BACKEND_DIR / "data"))
RUNS_DIR = DATA_DIR / "runs"
DIGESTS_DIR = DATA_DIR / "digests"

PROVIDERS = ("openrouter", "ollama", "anthropic", "openai")

DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter").strip().lower()

DEFAULT_MODELS = {
    "openrouter": os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
    "ollama": os.getenv("OLLAMA_MODEL", "hermes3:8b"),
    "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
    "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
}

OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()

LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))

SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "auto").strip().lower()  # auto | ddgs | tavily
SEARCH_RESULTS_PER_QUERY = int(os.getenv("SEARCH_RESULTS_PER_QUERY", "6"))
SEARCH_TIMELIMIT = os.getenv("SEARCH_TIMELIMIT", "w")  # d=day, w=week, m=month (ddgs)

# Email / digest
EMAIL_TO = [e.strip() for e in os.getenv("EMAIL_TO", "jfharney@gmail.com").split(",") if e.strip()]
EMAIL_FROM = os.getenv("EMAIL_FROM", "") or os.getenv("SMTP_USER", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "1").lower() not in ("0", "false", "no")
DIGEST_PROVIDER = os.getenv("DIGEST_PROVIDER", "").strip().lower() or DEFAULT_PROVIDER
DIGEST_TZ = os.getenv("DIGEST_TZ", "America/New_York")
DIGEST_HOUR = int(os.getenv("DIGEST_HOUR", "8"))


class ConfigError(RuntimeError):
    """Raised when a provider is selected but its configuration is incomplete."""


def validate_provider(provider: str) -> None:
    provider = provider.lower()
    if provider not in PROVIDERS:
        raise ConfigError(f"Unknown LLM_PROVIDER {provider!r}. Choose one of: {', '.join(PROVIDERS)}")
    if provider == "openrouter" and not os.getenv("OPENROUTER_API_KEY"):
        raise ConfigError("OPENROUTER_API_KEY is not set (see backend/.env)")
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        raise ConfigError("ANTHROPIC_API_KEY is not set (see backend/.env)")
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise ConfigError("OPENAI_API_KEY is not set (see backend/.env)")
    if provider == "ollama":
        if not OLLAMA_BASE_URL or "<" in OLLAMA_BASE_URL:
            raise ConfigError(
                "OLLAMA_BASE_URL is not set. From WSL use the Windows host IP: "
                "http://$(ip route show default | awk '{print $3; exit}'):11434"
            )


def provider_status() -> dict[str, dict]:
    """Report which providers are usable, for the UI's provider picker."""
    out: dict[str, dict] = {}
    for p in PROVIDERS:
        try:
            validate_provider(p)
            out[p] = {"configured": True, "default_model": DEFAULT_MODELS[p], "error": None}
        except ConfigError as exc:
            out[p] = {"configured": False, "default_model": DEFAULT_MODELS[p], "error": str(exc)}
    return out


def get_llm(provider: str | None = None, model: str | None = None, temperature: float | None = None):
    """Build a LangChain chat model for the requested provider."""
    provider = (provider or DEFAULT_PROVIDER).lower()
    validate_provider(provider)
    model = model or DEFAULT_MODELS[provider]
    temp = LLM_TEMPERATURE if temperature is None else temperature

    if provider == "openrouter":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url=OPENROUTER_BASE_URL,
            temperature=temp,
            timeout=LLM_TIMEOUT,
            default_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:5173"),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "AI Trends Agent"),
            },
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, temperature=temp, timeout=LLM_TIMEOUT)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=temp, timeout=LLM_TIMEOUT, max_tokens=4096)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, base_url=OLLAMA_BASE_URL, temperature=temp)
    raise ConfigError(f"Unsupported provider {provider!r}")


def describe_llm(provider: str | None, model: str | None) -> str:
    provider = (provider or DEFAULT_PROVIDER).lower()
    model = model or DEFAULT_MODELS.get(provider, "?")
    return f"{provider}/{model}"
