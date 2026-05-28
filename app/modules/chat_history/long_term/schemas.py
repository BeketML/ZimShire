from __future__ import annotations

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    name: str | None = None
    surname: str | None = None
    tracked_companies: list[str] = Field(default_factory=list)
    research_interests: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)
    explicit_memories: list[str] = Field(default_factory=list)


class MemoryExtraction(BaseModel):
    should_update: bool = False
    tickers: list[str] = Field(default_factory=list)
    research_topics: list[str] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)
    explicit_memories: list[str] = Field(default_factory=list)
    deprecate_keys: list[str] = Field(default_factory=list)
