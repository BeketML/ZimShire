"""ToolRegistry — MCP tool store with tag-based filtering."""
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


class ToolRegistry:
    """Holds all MCP tools and provides tag-based filtering. Stored on app.state."""

    def __init__(self, tools: dict[str, BaseTool] | None = None) -> None:
        self._tools: dict[str, BaseTool] = dict(tools) if tools else {}

    def set_tools(self, tools: dict[str, BaseTool]) -> None:
        self._tools = dict(tools)
        tag_index = {name: sorted(tool_tags(t)) for name, t in self._tools.items()}
        logger.info("ToolRegistry loaded %d tools: %s", len(self._tools), tag_index)

    def get_tools(self) -> dict[str, BaseTool]:
        if not self._tools:
            raise RuntimeError("ToolRegistry is empty — MCP client not initialised")
        return self._tools

    def matches_agent(self, name: str, tool: BaseTool, agent: AgentName) -> bool:
        return matches_agent(name, tool, agent)


# Module-level registry instance (used by graph nodes that can't receive app.state)
_registry = ToolRegistry()


def set_all_tools(tools: dict[str, BaseTool]) -> None:
    _registry.set_tools(tools)


def get_all_tools() -> dict[str, BaseTool]:
    return _registry.get_tools()


def get_registry() -> ToolRegistry:
    return _registry


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
