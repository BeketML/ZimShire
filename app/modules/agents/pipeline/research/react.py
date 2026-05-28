"""Shared ReAct subagent runner — MCP tools + artifact extraction from ToolMessage."""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from app.services.llm import get_subagent_model

logger = logging.getLogger(__name__)

AgentName = Literal["rag", "market", "web"]


def _parse_tool_content(content: Any) -> Any:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
    if isinstance(content, list):
        parts: list[Any] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            else:
                parts.append(block)
        if len(parts) == 1:
            return _parse_tool_content(parts[0])
        return parts
    return content


def extract_artifacts(agent: AgentName, messages: list) -> dict[str, Any]:
    artifacts: dict[str, Any] = {
        "rag_chunks": [],
        "web_sources": [],
        "market_data": {},
    }

    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        payload = _parse_tool_content(msg.content)
        if agent == "rag":
            if isinstance(payload, dict):
                artifacts["rag_chunks"].append(payload)
            elif isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        artifacts["rag_chunks"].append(item)
        elif agent == "web":
            if isinstance(payload, dict):
                artifacts["web_sources"].append(payload)
            elif isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        artifacts["web_sources"].append(item)
        elif agent == "market":
            if isinstance(payload, dict) and "error" not in payload:
                ticker = (
                    payload.get("ticker")
                    or payload.get("symbol")
                    or (payload.get("info") or {}).get("symbol")
                )
                if isinstance(ticker, str) and ticker:
                    existing = artifacts["market_data"].get(ticker)
                    if isinstance(existing, dict):
                        existing.update(payload)
                    else:
                        artifacts["market_data"][ticker] = payload

    if agent == "rag":
        return {"rag_chunks": artifacts["rag_chunks"]}
    if agent == "web":
        return {"web_sources": artifacts["web_sources"]}
    return {
        "market_data": artifacts["market_data"],
        "market_json": json.dumps(artifacts["market_data"], default=str) if artifacts["market_data"] else "",
    }


async def run_react_subagent(
    *,
    agent: AgentName,
    system_prompt: str,
    human_message: str,
    config: RunnableConfig,
    tools: list[BaseTool],
    error_label: str,
) -> tuple[str, dict[str, Any]]:
    if not tools:
        return f"{error_label}: no MCP tools available.", extract_artifacts(agent, [])

    llm = get_subagent_model()
    react = create_react_agent(llm, tools)

    try:
        result = await react.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_message),
                ]
            },
            config=config,
        )
        messages = result.get("messages", [])
        artifacts = extract_artifacts(agent, messages)
        last = messages[-1] if messages else None
        if isinstance(last, AIMessage):
            formatted = last.content if isinstance(last.content, str) else str(last.content)
        else:
            formatted = str(last) if last else ""
        return formatted, artifacts
    except Exception as exc:
        logger.exception("%s failed: %s", error_label, exc)
        return f"{error_label} encountered an error.", extract_artifacts(agent, [])
