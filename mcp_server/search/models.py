from __future__ import annotations

from typing import TypedDict


class WebOrganicResult(TypedDict):
    title: str
    url: str
    snippet: str
    date: str | None
    favicon: str | None


class WebNewsResult(TypedDict):
    title: str
    url: str
    snippet: str
    source: str
    date: str
    thumbnail: str | None


class WebKnowledgeGraph(TypedDict):
    title: str
    description: str
    website: str | None
    facts: dict[str, str]
    profiles: list[dict]
    related_topics: list[dict]
