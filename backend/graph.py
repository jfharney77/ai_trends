"""LangGraph workflow: research the latest AI trends per category.

Topology
--------
    START ─▶ plan ─▶ (Send per category) research_category ─▶ compose_overview ─▶ END

* ``plan`` resolves the requested categories and records run metadata.
* ``research_category`` runs once per category in parallel (LangGraph ``Send``):
  it issues the category's search queries, then asks the LLM to turn the raw
  results into a structured list of trends with sources.
* ``compose_overview`` writes a short cross-category executive summary.

The graph is pure Python with injectable ``llm`` and ``search_fn`` so tests can
run it without network access.
"""

from __future__ import annotations

import json
import logging
import operator
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Callable, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

import config
from categories import Category, resolve_categories
from search import web_search

log = logging.getLogger(__name__)

SearchFn = Callable[[list[str]], list[dict]]


# --------------------------------------------------------------------------- state
class CategoryResult(TypedDict, total=False):
    category_id: str
    category_label: str
    headline: str
    trends: list[dict]
    sources: list[dict]
    search_result_count: int
    error: str | None
    model: str


class TrendsState(TypedDict, total=False):
    category_ids: list[str]
    provider: str | None
    model: str | None
    started_at: str
    results: Annotated[list[CategoryResult], operator.add]
    overview: str
    finished_at: str


class CategoryState(TypedDict):
    category_id: str
    provider: str | None
    model: str | None


# --------------------------------------------------------------------------- prompts
RESEARCH_SYSTEM = """You are an analyst who tracks the AI industry. You will receive raw web
search results (title, url, snippet, date) for one topic area. Identify the most
important recent trends, developments, releases, or shifts for that area.

Rules:
- Only use information present in the search results. Do not invent facts, products, or dates.
- Prefer items from the last couple of weeks. Today's date is {today}.
- Merge duplicate stories about the same event into a single trend.
- Each trend must cite one or more source URLs from the results, verbatim.
- Return 3 to 6 trends. If the results are too thin, return fewer and say so in the headline.

Respond with JSON only, matching this schema exactly:
{{
  "headline": "one sentence summarizing the state of this area right now",
  "trends": [
    {{
      "title": "short title",
      "summary": "2-3 sentences describing what happened and the evidence",
      "why_it_matters": "1-2 sentences on the implication",
      "sources": ["https://..."]
    }}
  ]
}}"""

OVERVIEW_SYSTEM = """You are writing the opening paragraph of a daily AI trends briefing for an
engineer who builds AI agents. You will receive per-category headlines and trend titles.
Write 3 to 5 sentences in plain prose: what stands out today across the areas,
and any connections between them. No bullet points, no headers, no preamble.
Today's date is {today}."""


# --------------------------------------------------------------------------- helpers
def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of an LLM reply, tolerating code fences."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in model response")
    return json.loads(text[start : end + 1])


def _format_results(results: list[dict], limit: int = 24) -> str:
    lines = []
    for i, r in enumerate(results[:limit], start=1):
        date = r.get("published") or "n/a"
        lines.append(
            f"[{i}] {r.get('title','').strip()}\n    url: {r.get('url','')}\n    date: {date}\n    {r.get('snippet','').strip()}"
        )
    return "\n\n".join(lines) if lines else "(no results)"


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return str(content)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- graph builder
def build_graph(llm_factory: Callable[[str | None, str | None], Any] | None = None, search_fn: SearchFn | None = None):
    """Compile the trends graph.

    ``llm_factory(provider, model)`` returns a LangChain chat model. Defaults to
    ``config.get_llm``. ``search_fn(queries)`` returns search result dicts.
    Defaults to ``search.web_search``.
    """
    llm_factory = llm_factory or (lambda p, m: config.get_llm(p, m))
    search_fn = search_fn or (lambda queries: web_search(queries))

    def plan(state: TrendsState) -> dict:
        cats = resolve_categories(state.get("category_ids"))
        return {
            "category_ids": [c.id for c in cats],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "results": [],
        }

    def fan_out(state: TrendsState) -> list[Send]:
        return [
            Send("research_category", {"category_id": cid, "provider": state.get("provider"), "model": state.get("model")})
            for cid in state["category_ids"]
        ]

    def research_category(cstate: CategoryState) -> dict:
        cat: Category = resolve_categories([cstate["category_id"]])[0]
        model_desc = config.describe_llm(cstate.get("provider"), cstate.get("model"))
        base: CategoryResult = {
            "category_id": cat.id,
            "category_label": cat.label,
            "headline": "",
            "trends": [],
            "sources": [],
            "search_result_count": 0,
            "error": None,
            "model": model_desc,
        }
        try:
            results = search_fn(list(cat.queries))
            base["search_result_count"] = len(results)
            base["sources"] = [{"title": r.get("title", ""), "url": r.get("url", ""), "published": r.get("published", "")} for r in results]
            if not results:
                base["headline"] = "No search results were returned for this category."
                return {"results": [base]}

            llm = llm_factory(cstate.get("provider"), cstate.get("model"))
            messages = [
                SystemMessage(content=RESEARCH_SYSTEM.format(today=_today())),
                HumanMessage(
                    content=(
                        f"Topic area: {cat.label}\nScope: {cat.description}\n\n"
                        f"Search results:\n\n{_format_results(results)}"
                    )
                ),
            ]
            reply = llm.invoke(messages)
            parsed = _extract_json(_content_to_text(reply.content))
            known_urls = {s["url"] for s in base["sources"]}
            trends = []
            for t in parsed.get("trends", []) or []:
                srcs = [u for u in (t.get("sources") or []) if isinstance(u, str)]
                trends.append(
                    {
                        "title": str(t.get("title", "")).strip(),
                        "summary": str(t.get("summary", "")).strip(),
                        "why_it_matters": str(t.get("why_it_matters", "")).strip(),
                        "sources": srcs,
                        "verified_sources": [u for u in srcs if u.rstrip("/") in known_urls],
                    }
                )
            base["headline"] = str(parsed.get("headline", "")).strip()
            base["trends"] = trends
        except Exception as exc:  # noqa: BLE001 - one category failing must not sink the run
            log.exception("research_category failed for %s", cat.id)
            base["error"] = f"{type(exc).__name__}: {exc}"
            if not base["headline"]:
                base["headline"] = "This category could not be summarized."
        return {"results": [base]}

    def compose_overview(state: TrendsState) -> dict:
        results = state.get("results", [])
        usable = [r for r in results if r.get("trends")]
        overview = ""
        if usable:
            try:
                llm = llm_factory(state.get("provider"), state.get("model"))
                digest = "\n".join(
                    f"- {r['category_label']}: {r['headline']}\n" + "\n".join(f"    * {t['title']}" for t in r["trends"])
                    for r in usable
                )
                reply = llm.invoke(
                    [SystemMessage(content=OVERVIEW_SYSTEM.format(today=_today())), HumanMessage(content=digest)]
                )
                overview = _content_to_text(reply.content).strip()
            except Exception as exc:  # noqa: BLE001
                log.exception("compose_overview failed")
                overview = f"(Overview unavailable: {type(exc).__name__}: {exc})"
        else:
            overview = "No trends could be gathered in this run."
        return {"overview": overview, "finished_at": datetime.now(timezone.utc).isoformat()}

    g = StateGraph(TrendsState)
    g.add_node("plan", plan)
    g.add_node("research_category", research_category)
    g.add_node("compose_overview", compose_overview)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", fan_out, ["research_category"])
    g.add_edge("research_category", "compose_overview")
    g.add_edge("compose_overview", END)
    return g.compile()


def run_trends(
    category_ids: list[str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    on_update: Callable[[str, dict], None] | None = None,
    graph=None,
) -> dict:
    """Execute the graph and return the final state as a plain dict.

    ``on_update(node_name, update)`` is called after every node finishes so a
    caller can report progress (the API uses it to mark categories done).
    """
    graph = graph or build_graph()
    initial: TrendsState = {"category_ids": category_ids or [], "provider": provider, "model": model}
    final: dict[str, Any] = {"category_ids": [], "results": [], "overview": ""}
    for update in graph.stream(initial, stream_mode="updates"):
        for node, payload in update.items():
            if not isinstance(payload, dict):
                continue
            if node == "research_category":
                final["results"].extend(payload.get("results", []))
            else:
                final.update(payload)
            if on_update:
                on_update(node, payload)
    final["provider"] = (provider or config.DEFAULT_PROVIDER).lower()
    final["model"] = model or config.DEFAULT_MODELS.get(final["provider"])
    # Keep category order stable regardless of which finished first.
    order = {cid: i for i, cid in enumerate(final.get("category_ids", []))}
    final["results"].sort(key=lambda r: order.get(r.get("category_id"), 99))
    return final
