"""Pydantic models for orchestrator planner + subagent contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SubagentPlanItem(BaseModel):
    name: Literal["rag", "market", "web"]
    enabled: bool
    query: str = ""
    years: list[int] | None = None
    tickers: list[str] | None = None
    data_type: Literal["info", "financials", "history", "price", "news", "earnings", "holders", "insider"] | None = None
    reason: str = ""


class OrchestratorPlan(BaseModel):
    subagents: list[SubagentPlanItem] = Field(default_factory=list)
    direct_answer_possible: bool = False


class SubagentResult(BaseModel):
    agent_name: Literal["rag", "market", "web"]
    sub_query: str
    formatted_context: str
    raw_artifacts: dict = Field(default_factory=dict)
