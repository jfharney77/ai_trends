"""Run the LangGraph workflow end to end with a fake LLM and fake search."""

import json

from langchain_core.messages import AIMessage

from graph import build_graph, run_trends, _extract_json


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        human = messages[-1].content
        if human.startswith("Topic area:"):
            return AIMessage(
                content=json.dumps(
                    {
                        "headline": "Things happened.",
                        "trends": [
                            {
                                "title": "Trend A",
                                "summary": "Summary A",
                                "why_it_matters": "Because.",
                                "sources": ["https://example.com/a", "https://not-in-results.example"],
                            }
                        ],
                    }
                )
            )
        return AIMessage(content="Overview paragraph.")


def fake_search(queries):
    return [{"title": "A", "url": "https://example.com/a", "snippet": "s", "published": "2026-10-07"}]


def test_run_all_categories_in_parallel_and_compose_overview():
    llm = FakeLLM()
    g = build_graph(llm_factory=lambda p, m: llm, search_fn=fake_search)
    seen = []
    final = run_trends(None, "openrouter", "x", on_update=lambda n, p: seen.append(n), graph=g)

    assert [r["category_id"] for r in final["results"]] == [
        "personalization", "observability", "memory", "orchestration", "models",
    ]
    assert final["overview"] == "Overview paragraph."
    assert llm.calls == 6  # five categories + overview
    assert seen.count("research_category") == 5
    t = final["results"][0]["trends"][0]
    assert t["verified_sources"] == ["https://example.com/a"]
    assert final["provider"] == "openrouter" and final["model"] == "x"


def test_subset_of_categories_and_empty_search():
    llm = FakeLLM()
    g = build_graph(llm_factory=lambda p, m: llm, search_fn=lambda q: [])
    final = run_trends(["memory"], None, None, graph=g)
    assert len(final["results"]) == 1
    assert final["results"][0]["trends"] == []
    assert "No search results" in final["results"][0]["headline"]
    assert final["overview"].startswith("No trends")
    assert llm.calls == 0


def test_llm_failure_is_captured_per_category():
    class Boom:
        def invoke(self, messages):
            raise RuntimeError("provider down")

    g = build_graph(llm_factory=lambda p, m: Boom(), search_fn=fake_search)
    final = run_trends(["models"], None, None, graph=g)
    r = final["results"][0]
    assert r["error"].startswith("RuntimeError")
    assert r["search_result_count"] == 1


def test_extract_json_tolerates_fences_and_prose():
    assert _extract_json('Sure!\n```json\n{"a": 1}\n```')["a"] == 1
    assert _extract_json('here {"a": {"b": 2}} done')["a"]["b"] == 2
