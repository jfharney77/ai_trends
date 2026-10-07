"""Web search used by the research agent.

Backends:
    ddgs    — DuckDuckGo via the `ddgs` package. No API key required. Default.
    tavily  — Tavily search API, used when TAVILY_API_KEY is set and
              SEARCH_PROVIDER is `tavily` or `auto`.

Both return the same lightweight dict shape so the graph does not care which
one answered.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

import config

log = logging.getLogger(__name__)

SearchResult = dict  # {"title", "url", "snippet", "published", "source"}


def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    out: list[SearchResult] = []
    for r in results:
        url = (r.get("url") or "").split("#")[0].rstrip("/")
        if not url or url in seen:
            continue
        seen.add(url)
        r["url"] = url
        out.append(r)
    return out


def search_ddgs(query: str, max_results: int, timelimit: str | None) -> list[SearchResult]:
    from ddgs import DDGS

    results: list[SearchResult] = []
    with DDGS() as ddgs:
        # News first (has dates), then general web to fill in.
        try:
            for r in ddgs.news(query, max_results=max_results, timelimit=timelimit):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("body", ""),
                        "published": r.get("date", ""),
                        "source": r.get("source", ""),
                    }
                )
        except Exception as exc:  # noqa: BLE001 - search backends are flaky
            log.warning("ddgs news failed for %r: %s", query, exc)
        if len(results) < max_results:
            try:
                for r in ddgs.text(query, max_results=max_results, timelimit=timelimit):
                    results.append(
                        {
                            "title": r.get("title", ""),
                            "url": r.get("href", ""),
                            "snippet": r.get("body", ""),
                            "published": "",
                            "source": "",
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("ddgs text failed for %r: %s", query, exc)
    return results[: max_results * 2]


def search_tavily(query: str, max_results: int, timelimit: str | None) -> list[SearchResult]:
    from tavily import TavilyClient

    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    days = {"d": 1, "w": 7, "m": 30}.get(timelimit or "", None)
    kwargs = {"max_results": max_results, "topic": "news", "search_depth": "basic"}
    if days:
        kwargs["days"] = days
    resp = client.search(query, **kwargs)
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", ""),
            "published": r.get("published_date", ""),
            "source": "",
        }
        for r in resp.get("results", [])
    ]


def pick_backend() -> tuple[str, Callable[[str, int, str | None], list[SearchResult]]]:
    pref = config.SEARCH_PROVIDER
    if pref == "tavily" or (pref == "auto" and os.getenv("TAVILY_API_KEY")):
        return "tavily", search_tavily
    return "ddgs", search_ddgs


def web_search(queries: list[str], max_results: int | None = None, timelimit: str | None = None) -> list[SearchResult]:
    """Run every query through the active backend and return deduplicated results."""
    name, fn = pick_backend()
    per_query = max_results or config.SEARCH_RESULTS_PER_QUERY
    tl = timelimit if timelimit is not None else config.SEARCH_TIMELIMIT
    all_results: list[SearchResult] = []
    for q in queries:
        try:
            all_results.extend(fn(q, per_query, tl or None))
        except Exception as exc:  # noqa: BLE001
            log.warning("%s search failed for %r: %s", name, q, exc)
    return _dedupe(all_results)
