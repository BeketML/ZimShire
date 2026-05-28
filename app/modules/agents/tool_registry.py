"""ToolRegistry — global MCP tool store with tag-based filtering."""
from __future__ import annotations

import logging

from langchain_core.tools import BaseTool

from app.modules.agents.tool_allowlists import (
    AGENT_PRIMARY_TAG,
    AGENT_TOOL_ALLOWLIST,
    EXCLUDE_TAGS,
    AgentName,
)

logger = logging.getLogger(__name__)

_all_tools: dict[str, BaseTool] = {}


def set_all_tools(tools: dict[str, BaseTool]) -> None:
    global _all_tools
    _all_tools = dict(tools)
    tag_index = {name: sorted(tool_tags(t)) for name, t in tools.items()}
    logger.info("MCP registry loaded %d tools: %s", len(tools), tag_index)


def get_all_tools() -> dict[str, BaseTool]:
    if not _all_tools:
        raise RuntimeError("MCP tools not initialised — call init_mcp_client() first")
    return _all_tools


def tool_tags(tool: BaseTool) -> set[str]:
    tags: set[str] = set()
    meta = getattr(tool, "metadata", None) or {}
    if isinstance(meta, dict):
        for key in ("tags", "tag"):
            val = meta.get(key)
            if isinstance(val, (list, tuple, set, frozenset)):
                tags.update(str(t) for t in val)
            elif isinstance(val, str):
                tags.add(val)
        nested = meta.get("_meta")
        if isinstance(nested, dict):
            for key in ("tags", "tag", "fastmcp_tags"):
                val = nested.get(key)
                if isinstance(val, (list, tuple, set, frozenset)):
                    tags.update(str(t) for t in val)
                elif isinstance(val, str):
                    tags.add(val)
    return tags


def _is_ui_tool(name: str, tool: BaseTool) -> bool:
    if name.endswith("_ui"):
        return True
    return "ui" in tool_tags(tool)


def matches_agent(name: str, tool: BaseTool, agent: AgentName) -> bool:
    if _is_ui_tool(name, tool):
        return False
    tags = tool_tags(tool)
    primary = AGENT_PRIMARY_TAG[agent]
    if tags:
        return primary in tags and not (tags & EXCLUDE_TAGS)
    return name in AGENT_TOOL_ALLOWLIST[agent]
