"""Command objects for the persist-turn pipeline (one per DB concern)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID


@dataclass(frozen=True)
class CreateAssistantMessageCommand:
    chat_id: UUID
    content: str
    grounded: bool | None
    langfuse_trace_id: str | None


@dataclass(frozen=True)
class InsertRAGRetrievalsCommand:
    message_id: UUID
    chunks: list[dict]
    used_point_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class WriteSemanticCacheCommand:
    query: str
    response: str
    sources: tuple[dict, ...]
    embedding: tuple[float, ...]  # empty tuple = skip


@dataclass(frozen=True)
class UpdateLongTermMemoryCommand:
    user_id: UUID
    query: str
    draft_answer: str
    recent_turns: list
    current_profile: object
    market_tickers: list[str]


@dataclass(frozen=True)
class TouchChatCommand:
    chat_id: UUID
