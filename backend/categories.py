"""The five trend categories the agent researches.

Each category carries a short id used in API calls and file names, a display
label, and a handful of search queries that are issued to the web-search tool.
Queries are kept broad on purpose; the LLM does the filtering.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    description: str
    queries: tuple[str, ...] = field(default_factory=tuple)


CATEGORIES: list[Category] = [
    Category(
        id="personalization",
        label="Personalization and AI",
        description="How AI systems adapt to individual users: user modeling, recommendation, adaptive interfaces, personal assistants.",
        queries=(
            "AI personalization latest news",
            "personalized AI assistant user modeling",
            "LLM personalization recommendation systems",
        ),
    ),
    Category(
        id="observability",
        label="Agent observability and monitoring",
        description="Tracing, evaluation, monitoring, and debugging of LLM agents in production.",
        queries=(
            "AI agent observability tracing",
            "LLM agent monitoring evaluation tools",
            "agentops langsmith langfuse observability news",
        ),
    ),
    Category(
        id="memory",
        label="Agent memory",
        description="Short- and long-term memory for agents: episodic memory, memory stores, retrieval, forgetting, context management.",
        queries=(
            "AI agent memory long-term memory",
            "LLM agent memory architecture",
            "agent memory systems research",
        ),
    ),
    Category(
        id="orchestration",
        label="Agent orchestration",
        description="Multi-agent systems, workflow engines, planning, hand-offs, and frameworks for coordinating agents.",
        queries=(
            "multi-agent orchestration framework",
            "AI agent orchestration news",
            "LangGraph CrewAI AutoGen multi-agent updates",
        ),
    ),
    Category(
        id="models",
        label="New AI models",
        description="Newly released or announced models: LLMs, decision and reasoning models, multimodal, world models, and anything else.",
        queries=(
            "new AI model release",
            "new LLM announced this week",
            "new reasoning model decision model AI release",
        ),
    ),
]

CATEGORY_BY_ID: dict[str, Category] = {c.id: c for c in CATEGORIES}
ALL_CATEGORY_IDS: list[str] = [c.id for c in CATEGORIES]


def resolve_categories(ids: list[str] | None) -> list[Category]:
    """Return Category objects for the given ids, or all five when ids is empty."""
    if not ids:
        return list(CATEGORIES)
    unknown = [i for i in ids if i not in CATEGORY_BY_ID]
    if unknown:
        raise ValueError(f"Unknown category id(s): {', '.join(unknown)}")
    return [CATEGORY_BY_ID[i] for i in ids]
