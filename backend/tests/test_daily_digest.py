from datetime import datetime
from zoneinfo import ZoneInfo

import daily_digest


def test_only_at_hour_skips_when_hour_differs(monkeypatch):
    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 7, 9, 5, tzinfo=tz)

    monkeypatch.setattr(daily_digest, "datetime", FakeDT)
    # provider validation would fail without keys, so a skip proves the guard ran first
    assert daily_digest.main(["--only-at-hour", "8", "--tz", "America/New_York"]) == 0


def test_no_provider_returns_2(monkeypatch):
    for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(daily_digest.config, "OLLAMA_BASE_URL", "")
    assert daily_digest.main(["--provider", "openrouter", "--no-email"]) == 2
